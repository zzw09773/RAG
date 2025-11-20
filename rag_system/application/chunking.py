"""Hierarchical chunking strategies for legal documents.

This module implements multi-level chunking that preserves document structure
and creates parent-child relationships between chunks.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter

from ..domain import (
    Document, Chunk, ChunkId, DocumentId, HierarchyPath,
    ChunkType, IndexingLevel
)
from ..common import log


# Regex patterns for Chinese legal documents
_RE_ARTICLE = re.compile(r"^(第\s*[一二三四五六七八九十百千零兩两0-9]+\s*條)", re.MULTILINE)
_RE_CHAPTER = re.compile(r"^(第\s*[一二三四五六七八九十百千零〇○兩两0-9]+\s*章)", re.MULTILINE)
_RE_SECTION = re.compile(r"^(第\s*[一二三四五六七八九十百千零〇○兩两0-9]+\s*款)", re.MULTILINE)
_RE_NUMBERED_ITEM = re.compile(r"^([一二三四五六七八九十百千]+、)", re.MULTILINE)
_RE_SUBITEM = re.compile(r"^(（[一二三四五六七八九十百千]+）)", re.MULTILINE)


@dataclass
class ChunkNode:
    """Temporary node for building chunk hierarchy."""
    content: str
    section_path: HierarchyPath
    chunk_type: ChunkType
    indexing_level: IndexingLevel
    parent: Optional['ChunkNode'] = None
    children: List['ChunkNode'] = None
    metadata: dict = None

    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.metadata is None:
            self.metadata = {}


class ChunkingStrategy(ABC):
    """Abstract base class for chunking strategies."""

    def __init__(self, max_chunk_size: int = 800, overlap: int = 100):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", " ", ""],
        )

    @abstractmethod
    def chunk(self, content: str, source_file: str) -> List[ChunkNode]:
        """Chunk content into hierarchical nodes.

        Args:
            content: Document content
            source_file: Source filename

        Returns:
            List of ChunkNodes forming a tree structure
        """
        pass

    def _create_summary(self, content: str, max_length: int = 300) -> str:
        """Extract summary from content (first paragraph or N chars)."""
        # Try to get first paragraph
        paragraphs = content.split('\n\n')
        if paragraphs and len(paragraphs[0]) <= max_length:
            return paragraphs[0]

        # Otherwise, take first N chars
        summary = content[:max_length].strip()
        if len(content) > max_length:
            summary += "..."
        return summary

    def _should_split_content(self, content: str) -> bool:
        """Determine if content needs to be split into smaller chunks."""
        return len(content) > self.max_chunk_size


class LegalDocumentChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for Chinese legal documents.

    Creates hierarchy: Document → Chapter → Article → Section → Detail
    """

    def chunk(self, content: str, source_file: str) -> List[ChunkNode]:
        """Chunk legal document into hierarchical structure."""
        log(f"Chunking legal document: {source_file}")

        # Create document root
        doc_summary = self._create_summary(content, max_length=500)
        doc_root = ChunkNode(
            content=doc_summary,
            section_path=HierarchyPath(segments=()),
            chunk_type=ChunkType.DOCUMENT,
            indexing_level=IndexingLevel.SUMMARY,
            metadata={"is_summary": True}
        )

        nodes = [doc_root]

        # Try to detect structure
        chapter_spans = list(_RE_CHAPTER.finditer(content))
        if chapter_spans:
            nodes.extend(self._chunk_by_chapters(content, source_file, doc_root))
        else:
            article_spans = list(_RE_ARTICLE.finditer(content))
            if article_spans:
                nodes.extend(self._chunk_by_articles(content, source_file, doc_root))
            else:
                # No clear structure, treat as single-level
                nodes.extend(self._chunk_flat(content, source_file, doc_root))

        log(f"  Generated {len(nodes)} hierarchical chunks")
        return nodes

    def _chunk_by_chapters(
        self,
        content: str,
        source_file: str,
        parent: ChunkNode
    ) -> List[ChunkNode]:
        """Chunk by chapters (第X章), then articles within each chapter."""
        chapter_spans = list(_RE_CHAPTER.finditer(content))
        nodes = []

        for i, chapter_match in enumerate(chapter_spans):
            chapter_title = chapter_match.group(1).strip()
            chapter_start = chapter_match.start()
            chapter_end = chapter_spans[i + 1].start() if i + 1 < len(chapter_spans) else len(content)
            chapter_content = content[chapter_start:chapter_end].strip()

            # Create chapter node
            chapter_path = parent.section_path.append(chapter_title)
            chapter_summary = self._create_summary(chapter_content)

            chapter_node = ChunkNode(
                content=f"{chapter_title}\n\n{chapter_summary}",
                section_path=chapter_path,
                chunk_type=ChunkType.CHAPTER,
                indexing_level=IndexingLevel.SUMMARY,
                parent=parent,
                metadata={"chapter_number": chapter_title}
            )
            parent.children.append(chapter_node)
            nodes.append(chapter_node)

            # Find articles within this chapter
            article_content = content[chapter_start:chapter_end]
            article_spans = list(_RE_ARTICLE.finditer(article_content))

            if article_spans:
                nodes.extend(self._chunk_by_articles(
                    article_content,
                    source_file,
                    chapter_node,
                    offset=0
                ))
            else:
                # No articles, split chapter content if too large
                if self._should_split_content(chapter_content):
                    nodes.extend(self._split_large_content(
                        chapter_content,
                        chapter_node,
                        ChunkType.DETAIL
                    ))

        return nodes

    def _chunk_by_articles(
        self,
        content: str,
        source_file: str,
        parent: ChunkNode,
        offset: int = 0
    ) -> List[ChunkNode]:
        """Chunk by articles (第X條), then sections within each article."""
        article_spans = list(_RE_ARTICLE.finditer(content))
        nodes = []

        for i, article_match in enumerate(article_spans):
            article_title = article_match.group(1).strip()
            article_start = article_match.start()
            article_end = article_spans[i + 1].start() if i + 1 < len(article_spans) else len(content)
            article_content = content[article_start:article_end].strip()

            # Create article path
            article_path = parent.section_path.append(article_title)

            # Determine indexing level based on content length
            # Important articles (moderate length) get indexed in BOTH layers
            indexing_level = IndexingLevel.BOTH if 200 <= len(article_content) <= 1000 else IndexingLevel.DETAIL

            # If content is small enough, create single article chunk
            if not self._should_split_content(article_content):
                article_node = ChunkNode(
                    content=article_content,
                    section_path=article_path,
                    chunk_type=ChunkType.ARTICLE,
                    indexing_level=indexing_level,
                    parent=parent,
                    metadata={"article_number": article_title}
                )
                parent.children.append(article_node)
                nodes.append(article_node)
            else:
                # Large article: create summary + detail chunks
                article_summary = self._create_summary(article_content)

                # Parent article chunk (summary)
                article_node = ChunkNode(
                    content=f"{article_title}\n\n{article_summary}",
                    section_path=article_path,
                    chunk_type=ChunkType.ARTICLE,
                    indexing_level=IndexingLevel.SUMMARY,
                    parent=parent,
                    metadata={"article_number": article_title, "is_summary": True}
                )
                parent.children.append(article_node)
                nodes.append(article_node)

                # Check for numbered items (一、二、三、)
                item_spans = list(_RE_NUMBERED_ITEM.finditer(article_content))
                if item_spans:
                    nodes.extend(self._chunk_by_items(
                        article_content,
                        article_node
                    ))
                else:
                    # No items, split into detail chunks
                    nodes.extend(self._split_large_content(
                        article_content,
                        article_node,
                        ChunkType.DETAIL
                    ))

        return nodes

    def _chunk_by_items(
        self,
        content: str,
        parent: ChunkNode
    ) -> List[ChunkNode]:
        """Chunk by numbered items (一、二、三、)."""
        item_spans = list(_RE_NUMBERED_ITEM.finditer(content))
        nodes = []

        for i, item_match in enumerate(item_spans):
            item_marker = item_match.group(1).strip()
            item_start = item_match.start()
            item_end = item_spans[i + 1].start() if i + 1 < len(item_spans) else len(content)
            item_content = content[item_start:item_end].strip()

            item_path = parent.section_path.append(item_marker)

            item_node = ChunkNode(
                content=item_content,
                section_path=item_path,
                chunk_type=ChunkType.SECTION,
                indexing_level=IndexingLevel.DETAIL,
                parent=parent,
                metadata={"item_marker": item_marker}
            )
            parent.children.append(item_node)
            nodes.append(item_node)

            # If item content is still too large, split further
            if self._should_split_content(item_content):
                nodes.extend(self._split_large_content(
                    item_content,
                    item_node,
                    ChunkType.DETAIL
                ))

        return nodes

    def _split_large_content(
        self,
        content: str,
        parent: ChunkNode,
        chunk_type: ChunkType
    ) -> List[ChunkNode]:
        """Split large content into smaller detail chunks."""
        # Get parent title for context
        parent_marker = parent.metadata.get("article_number") or parent.metadata.get("chapter_number") or ""

        splits = self.text_splitter.split_text(content)
        nodes = []

        for i, split_text in enumerate(splits, 1):
            # Include parent context in each split
            chunk_content = f"{parent_marker}\n\n{split_text}" if parent_marker else split_text

            split_path = parent.section_path.append(f"part-{i}")

            split_node = ChunkNode(
                content=chunk_content,
                section_path=split_path,
                chunk_type=chunk_type,
                indexing_level=IndexingLevel.DETAIL,
                parent=parent,
                metadata={"split_index": i, "parent_context": parent_marker}
            )
            parent.children.append(split_node)
            nodes.append(split_node)

        return nodes

    def _chunk_flat(
        self,
        content: str,
        source_file: str,
        parent: ChunkNode
    ) -> List[ChunkNode]:
        """Fallback: chunk without hierarchical structure."""
        if not self._should_split_content(content):
            node = ChunkNode(
                content=content,
                section_path=parent.section_path.append("content"),
                chunk_type=ChunkType.DETAIL,
                indexing_level=IndexingLevel.DETAIL,
                parent=parent
            )
            parent.children.append(node)
            return [node]

        splits = self.text_splitter.split_text(content)
        nodes = []

        for i, split_text in enumerate(splits, 1):
            node = ChunkNode(
                content=split_text,
                section_path=parent.section_path.append(f"chunk-{i}"),
                chunk_type=ChunkType.DETAIL,
                indexing_level=IndexingLevel.DETAIL,
                parent=parent,
                metadata={"chunk_index": i}
            )
            parent.children.append(node)
            nodes.append(node)

        return nodes


class MarkdownChunkingStrategy(ChunkingStrategy):
    """Chunking strategy for Markdown documents based on headers."""

    def chunk(self, content: str, source_file: str) -> List[ChunkNode]:
        """Chunk markdown by header hierarchy (#, ##, ###)."""
        log(f"Chunking markdown document: {source_file}")

        # Create document root
        doc_summary = self._create_summary(content, max_length=500)
        doc_root = ChunkNode(
            content=doc_summary,
            section_path=HierarchyPath(segments=()),
            chunk_type=ChunkType.DOCUMENT,
            indexing_level=IndexingLevel.SUMMARY,
            metadata={"is_summary": True}
        )

        # Parse markdown headers
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        headers = list(header_pattern.finditer(content))

        if not headers:
            # No headers, treat as flat
            return [doc_root] + self._chunk_flat(content, source_file, doc_root)

        nodes = [doc_root]
        current_parents = {0: doc_root}  # level -> parent node

        for i, header_match in enumerate(headers):
            level = len(header_match.group(1))  # Number of #
            title = header_match.group(2).strip()
            start = header_match.start()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
            section_content = content[start:end].strip()

            # Find parent (closest lower level)
            parent = current_parents.get(level - 1) or doc_root

            # Determine chunk type and indexing level
            if level == 1:
                chunk_type = ChunkType.CHAPTER
                indexing_level = IndexingLevel.SUMMARY
            elif level == 2:
                chunk_type = ChunkType.ARTICLE
                indexing_level = IndexingLevel.BOTH
            else:
                chunk_type = ChunkType.SECTION
                indexing_level = IndexingLevel.DETAIL

            section_path = parent.section_path.append(title)

            # Create node
            section_node = ChunkNode(
                content=section_content,
                section_path=section_path,
                chunk_type=chunk_type,
                indexing_level=indexing_level,
                parent=parent,
                metadata={"header_level": level, "title": title}
            )
            parent.children.append(section_node)
            nodes.append(section_node)

            # Update current parents for this level
            current_parents[level] = section_node

            # If content is too large, split it
            if self._should_split_content(section_content):
                nodes.extend(self._split_large_content(
                    section_content,
                    section_node,
                    ChunkType.DETAIL
                ))

        return nodes


class HierarchicalChunker:
    """Main chunker that selects appropriate strategy based on content."""

    def __init__(self, max_chunk_size: int = 800, overlap: int = 100):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

        # Initialize strategies
        self.legal_strategy = LegalDocumentChunkingStrategy(max_chunk_size, overlap)
        self.markdown_strategy = MarkdownChunkingStrategy(max_chunk_size, overlap)

    def chunk_file(self, file_path: Path, document_id: DocumentId) -> Document:
        """Chunk a file into a hierarchical Document.

        Args:
            file_path: Path to document file
            document_id: Document ID

        Returns:
            Document entity with hierarchical chunks
        """
        log(f"Chunking file: {file_path}")

        # Read content
        content = file_path.read_text(encoding='utf-8')

        # Select strategy
        strategy = self._select_strategy(content, file_path)

        # Chunk into nodes
        chunk_nodes = strategy.chunk(content, file_path.name)

        # Convert nodes to domain entities
        document = Document(
            id=document_id,
            title=file_path.stem,
            source_file=file_path.name
        )

        chunks = self._nodes_to_chunks(chunk_nodes, document_id, file_path.name)
        for chunk in chunks:
            document.add_chunk(chunk)

        return document

    def _select_strategy(self, content: str, file_path: Path) -> ChunkingStrategy:
        """Select chunking strategy based on content."""
        # Check for legal markers
        has_articles = bool(_RE_ARTICLE.search(content))
        has_chapters = bool(_RE_CHAPTER.search(content))

        if has_articles or has_chapters:
            log("  Using legal document chunking strategy")
            return self.legal_strategy

        # Check for markdown headers
        has_headers = bool(re.search(r'^#{1,6}\s+', content, re.MULTILINE))
        if has_headers or file_path.suffix.lower() == '.md':
            log("  Using markdown chunking strategy")
            return self.markdown_strategy

        # Default to legal (handles flat case)
        log("  Using legal document chunking strategy (default)")
        return self.legal_strategy

    def _nodes_to_chunks(
        self,
        nodes: List[ChunkNode],
        document_id: DocumentId,
        source_file: str
    ) -> List[Chunk]:
        """Convert ChunkNodes to Chunk entities."""
        chunks = []
        node_to_chunk_id = {}

        # First pass: create chunks and IDs
        for node in nodes:
            chunk_id = ChunkId.generate(
                source=source_file,
                section_path=str(node.section_path),
                content=node.content
            )
            node_to_chunk_id[id(node)] = chunk_id

            # Determine parent_id
            parent_id = None
            if node.parent:
                parent_id = node_to_chunk_id.get(id(node.parent))

            chunk = Chunk(
                id=chunk_id,
                document_id=document_id,
                content=node.content,
                section_path=node.section_path,
                chunk_type=node.chunk_type,
                indexing_level=node.indexing_level,
                parent_id=parent_id,
                source_file=source_file,
                article_number=node.metadata.get("article_number"),
                chapter_number=node.metadata.get("chapter_number"),
            )
            chunks.append(chunk)

        # Second pass: populate children_ids
        for node, chunk in zip(nodes, chunks):
            for child_node in node.children:
                child_chunk_id = node_to_chunk_id.get(id(child_node))
                if child_chunk_id:
                    chunk.add_child(child_chunk_id)

        return chunks
