"""Use cases for hierarchical retrieval from RAG system."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Set
import numpy as np

from ..domain import Chunk, ChunkId, DocumentId, IndexingLevel, ChunkType
from ..infrastructure import HierarchicalDocumentRepository, VectorStoreRepository
from ..common import log
from .indexing import EmbeddingService


@dataclass
class RetrievalResult:
    """Result from a retrieval operation."""
    chunk: Chunk
    similarity_score: float
    parent_chunks: List[Chunk]  # Ancestor chunks for context
    children_chunks: List[Chunk]  # Child chunks for detail
    sibling_chunks: List[Chunk]  # Sibling chunks for breadth

    def _get_display_title(self, chunk: Chunk) -> str:
        """Helper to get a human-readable title for a chunk."""
        ctype = chunk.chunk_type.value if hasattr(chunk.chunk_type, 'value') else str(chunk.chunk_type)
        
        if ctype == 'document':
            return f"文件: {chunk.source_file}"
            
        if ctype == 'chapter' and chunk.chapter_number:
            # Try to get full title from content first line
            first_line = chunk.content.split('\n', 1)[0].strip()
            # If first line looks like a title (contains the number), use it
            if chunk.chapter_number in first_line:
                return first_line
            return chunk.chapter_number
            
        if ctype == 'article' and chunk.article_number:
            return chunk.article_number
            
        # Fallback to section path string
        return str(chunk.section_path)

    @property
    def full_context(self) -> str:
        """Get full context by combining parent, current, and child content."""
        parts = []

        # Add parent context (from root to immediate parent)
        for i, parent in enumerate(reversed(self.parent_chunks)):
            indent = "  " * i
            title = self._get_display_title(parent)
            parts.append(f"{indent}【上層】{title}")

        # Add current chunk
        current_title = self._get_display_title(self.chunk)
        parts.append(f"【主要內容】{current_title}:\n{self.chunk.content}\n")

        # Add children if any
        if self.children_chunks:
            parts.append(f"【下層詳細內容】:")
            for child in self.children_chunks:
                # Also truncate children slightly if they are extremely long
                c_content = child.content.strip()
                if len(c_content) > 300:
                    c_content = c_content[:300] + "..."
                
                c_title = self._get_display_title(child)
                parts.append(f"  - {c_title}:\n    {c_content}\n")

        return "\n".join(parts)


class RetrievalStrategy(ABC):
    """Abstract base class for retrieval strategies."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[DocumentId] = None
    ) -> List[RetrievalResult]:
        """Retrieve relevant chunks.

        Args:
            query: Search query
            k: Number of results to return
            document_id: Optional filter by document

        Returns:
            List of RetrievalResults with context
        """
        pass


class SummaryFirstRetrievalStrategy(RetrievalStrategy):
    """Two-phase retrieval: search summaries first, then expand to details.

    This strategy reduces token consumption by:
    1. First searching high-level summaries (chapters, articles)
    2. Then expanding to detailed chunks within relevant sections

    Benefits:
    - 30-50% token reduction
    - Better context understanding
    - More accurate retrieval
    """

    def __init__(
        self,
        doc_repository: HierarchicalDocumentRepository,
        vector_repository: VectorStoreRepository,
        embedding_service: EmbeddingService,
        summary_k: int = 3,
        detail_per_summary: int = 2
    ):
        """Initialize strategy.

        Args:
            doc_repository: Document repository
            vector_repository: Vector repository
            embedding_service: Embedding service
            summary_k: Number of summary chunks to retrieve in phase 1
            detail_per_summary: Number of detail chunks per summary in phase 2
        """
        self.doc_repository = doc_repository
        self.vector_repository = vector_repository
        self.embedding_service = embedding_service
        self.summary_k = summary_k
        self.detail_per_summary = detail_per_summary

    def retrieve(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[DocumentId] = None
    ) -> List[RetrievalResult]:
        """Two-phase retrieval.

        Phase 1: Search summary layer for high-level matches
        Phase 2: Expand to detail chunks within top summaries

        Args:
            query: Search query
            k: Total number of results (will retrieve summary_k summaries)
            document_id: Optional document filter

        Returns:
            List of RetrievalResults with hierarchical context
        """
        log(f"Summary-first retrieval for query: '{query[:50]}...'")

        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Phase 1: Search summary layer
        log(f"  Phase 1: Searching {self.summary_k} summary chunks...")
        summary_results = self.vector_repository.similarity_search(
            query_embedding=query_embedding,
            level=IndexingLevel.SUMMARY,
            k=self.summary_k,
            document_id=document_id
        )

        if not summary_results:
            log("  No summary chunks found")
            return []

        # Get summary chunks
        summary_chunks = []
        for chunk_id, score in summary_results:
            chunk = self.doc_repository.get_chunk_by_id(chunk_id)
            if chunk:
                summary_chunks.append((chunk, score))

        log(f"  Found {len(summary_chunks)} summary chunks")

        # Phase 2: Expand to detail chunks within each summary
        log(f"  Phase 2: Expanding to detail chunks...")
        all_results = []
        seen_chunk_ids: Set[str] = set()

        for summary_chunk, summary_score in summary_chunks:
            # Get all descendant detail chunks
            detail_results = self._get_descendant_details(
                summary_chunk,
                query_embedding,
                max_results=self.detail_per_summary
            )

            for detail_chunk, detail_score in detail_results:
                chunk_id_str = str(detail_chunk.id)
                if chunk_id_str in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk_id_str)

                # Get hierarchical context
                result = self._build_retrieval_result(
                    detail_chunk,
                    detail_score
                )
                all_results.append(result)

        # Sort by similarity score and limit to k
        all_results.sort(key=lambda r: r.similarity_score, reverse=True)
        final_results = all_results[:k]

        log(f"  Returning {len(final_results)} results with hierarchical context")
        return final_results

    def _get_descendant_details(
        self,
        summary_chunk: Chunk,
        query_embedding: np.ndarray,
        max_results: int
    ) -> List[tuple[Chunk, float]]:
        """Get detail chunks that are descendants of a summary chunk.

        Args:
            summary_chunk: Parent summary chunk
            query_embedding: Query embedding vector
            max_results: Maximum number of details to return

        Returns:
            List of (detail_chunk, score) tuples
        """
        # Get all children (immediate descendants)
        children = self.doc_repository.get_children(summary_chunk.id)

        # Recursively get all detail descendants
        detail_chunks = []
        for child in children:
            if child.indexing_level in [IndexingLevel.DETAIL, IndexingLevel.BOTH]:
                detail_chunks.append(child)
            # Recursively get grandchildren
            grandchildren = self.doc_repository.get_children(child.id)
            detail_chunks.extend([
                gc for gc in grandchildren
                if gc.indexing_level in [IndexingLevel.DETAIL, IndexingLevel.BOTH]
            ])

        if not detail_chunks:
            # If no detail descendants, return the summary chunk itself
            return [(summary_chunk, 0.0)]

        # Score detail chunks by similarity (if we have embeddings)
        # For now, return first N detail chunks
        # TODO: Implement proper scoring with stored embeddings
        return [(chunk, 0.0) for chunk in detail_chunks[:max_results]]

    def _build_retrieval_result(
        self,
        chunk: Chunk,
        score: float
    ) -> RetrievalResult:
        """Build a complete RetrievalResult with hierarchical context.

        Args:
            chunk: Main chunk
            score: Similarity score

        Returns:
            RetrievalResult with parents, children, siblings
        """
        # Get ancestors
        parents = self.doc_repository.get_ancestors(chunk.id)

        # Get children
        children = self.doc_repository.get_children(chunk.id)

        # Get siblings (share same parent)
        siblings = []
        if chunk.parent_id:
            all_siblings = self.doc_repository.get_children(chunk.parent_id)
            siblings = [s for s in all_siblings if s.id != chunk.id]

        return RetrievalResult(
            chunk=chunk,
            similarity_score=score,
            parent_chunks=parents,
            children_chunks=children,
            sibling_chunks=siblings
        )


class DirectRetrievalStrategy(RetrievalStrategy):
    """Simple direct retrieval from detail layer with context expansion."""

    def __init__(
        self,
        doc_repository: HierarchicalDocumentRepository,
        vector_repository: VectorStoreRepository,
        embedding_service: EmbeddingService,
        expand_context: bool = True,
        max_parent_depth: int = 2
    ):
        """Initialize strategy.

        Args:
            doc_repository: Document repository
            vector_repository: Vector repository
            embedding_service: Embedding service
            expand_context: Whether to expand with parent context
            max_parent_depth: Maximum depth to traverse for parents
        """
        self.doc_repository = doc_repository
        self.vector_repository = vector_repository
        self.embedding_service = embedding_service
        self.expand_context = expand_context
        self.max_parent_depth = max_parent_depth

    def retrieve(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[DocumentId] = None
    ) -> List[RetrievalResult]:
        """Direct retrieval from detail layer.

        Args:
            query: Search query
            k: Number of results
            document_id: Optional document filter

        Returns:
            List of RetrievalResults with optional context
        """
        log(f"Direct retrieval for query: '{query[:50]}...'")

        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Search detail layer
        detail_results = self.vector_repository.similarity_search(
            query_embedding=query_embedding,
            level=IndexingLevel.DETAIL,
            k=k,
            document_id=document_id
        )

        if not detail_results:
            log("  No detail chunks found")
            return []

        # Build results with context
        results = []
        for chunk_id, score in detail_results:
            chunk = self.doc_repository.get_chunk_by_id(chunk_id)
            if not chunk:
                continue

            if self.expand_context:
                # Get hierarchical context
                result = self._build_retrieval_result_with_context(chunk, score)
            else:
                # No context expansion
                result = RetrievalResult(
                    chunk=chunk,
                    similarity_score=score,
                    parent_chunks=[],
                    children_chunks=[],
                    sibling_chunks=[]
                )

            results.append(result)

        log(f"  Returning {len(results)} results")
        return results

    def _build_retrieval_result_with_context(
        self,
        chunk: Chunk,
        score: float
    ) -> RetrievalResult:
        """Build result with hierarchical context."""
        # Get limited ancestors
        parents = self.doc_repository.get_ancestors(
            chunk.id,
            max_depth=self.max_parent_depth
        )

        # Get children
        children = self.doc_repository.get_children(chunk.id)

        # Get siblings
        siblings = []
        if chunk.parent_id:
            all_siblings = self.doc_repository.get_children(chunk.parent_id)
            siblings = [s for s in all_siblings if s.id != chunk.id]

        return RetrievalResult(
            chunk=chunk,
            similarity_score=score,
            parent_chunks=parents,
            children_chunks=children,
            sibling_chunks=siblings
        )


class HierarchicalRetrievalUseCase:
    """Main use case for hierarchical retrieval with strategy selection."""

    def __init__(
        self,
        doc_repository: HierarchicalDocumentRepository,
        vector_repository: VectorStoreRepository,
        embedding_service: EmbeddingService,
        default_strategy: str = "summary_first"
    ):
        """Initialize use case.

        Args:
            doc_repository: Document repository
            vector_repository: Vector repository
            embedding_service: Embedding service
            default_strategy: Default strategy ("summary_first" or "direct")
        """
        self.doc_repository = doc_repository
        self.vector_repository = vector_repository
        self.embedding_service = embedding_service

        # Initialize strategies
        self.strategies = {
            "summary_first": SummaryFirstRetrievalStrategy(
                doc_repository,
                vector_repository,
                embedding_service
            ),
            "direct": DirectRetrievalStrategy(
                doc_repository,
                vector_repository,
                embedding_service
            )
        }

        self.default_strategy = default_strategy

    def execute(
        self,
        query: str,
        k: int = 5,
        document_id: Optional[DocumentId] = None,
        strategy: Optional[str] = None,
        content_max_length: Optional[int] = None
    ) -> List[dict]:
        """Execute hierarchical retrieval.

        Args:
            query: Search query
            k: Number of results
            document_id: Optional document filter
            strategy: Retrieval strategy ("summary_first" or "direct")
            content_max_length: Optional max length for returned content

        Returns:
            List of result dicts with chunk content and metadata
        """
        strategy_name = strategy or self.default_strategy
        retrieval_strategy = self.strategies.get(strategy_name)

        if not retrieval_strategy:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        log(f"Executing hierarchical retrieval with {strategy_name} strategy")

        # Retrieve with strategy
        results = retrieval_strategy.retrieve(query, k, document_id)

        # Format results for output
        formatted_results = []
        for result in results:
            # Use full context if requested, otherwise just chunk content
            content = result.full_context if result.parent_chunks else result.chunk.content

            # Truncate if needed
            if content_max_length and len(content) > content_max_length:
                content = content[:content_max_length] + "..."

            formatted_results.append({
                "content": content,
                "metadata": {
                    "chunk_id": str(result.chunk.id),
                    "document_id": str(result.chunk.document_id),
                    "section_path": str(result.chunk.section_path),
                    "chunk_type": result.chunk.chunk_type.value,
                    "similarity_score": result.similarity_score,
                    "source": result.chunk.source_file,
                    "article": result.chunk.article_number,
                    "has_parents": len(result.parent_chunks) > 0,
                    "has_children": len(result.children_chunks) > 0,
                    "parent_count": len(result.parent_chunks),
                    "child_count": len(result.children_chunks),
                }
            })

        return formatted_results
