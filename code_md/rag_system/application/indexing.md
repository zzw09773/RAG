# rag_system/application/indexing.py
```python
"""Use cases for indexing documents into hierarchical RAG system."""
from pathlib import Path
from typing import Optional
import numpy as np

from ..domain import Document, DocumentId, IndexingLevel
from ..infrastructure import HierarchicalDocumentRepository, VectorStoreRepository
from ..common import logger, log_json # Changed import from log to logger, log_json
from .chunking import HierarchicalChunker


class EmbeddingService:
    """Service for generating embeddings (adapter for external embedding models)."""

    def __init__(self, embed_function):
        """Initialize with embedding function.

        Args:
            embed_function: Function that takes text and returns embedding vector
                           (e.g., from LangChain's embedding models)
        """
        self.embed_function = embed_function

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for text.

        Args:
            text: Input text

        Returns:
            Embedding vector as numpy array
        """
        try:
            # Handle different embedding function interfaces
            if hasattr(self.embed_function, 'embed_query'):
                # LangChain embedding interface
                embedding = self.embed_function.embed_query(text)
            elif callable(self.embed_function):
                # Direct function call
                embedding = self.embed_function(text)
            else:
                raise ValueError("embed_function must be callable or have embed_query method")

            # Convert to numpy array
            if not isinstance(embedding, np.ndarray):
                embedding = np.array(embedding, dtype=np.float32)

            return embedding

        except Exception as e:
            logger.error(f"Error generating embedding: {e}") # Updated logging
            raise

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        try:
            # Try batch embedding if available
            if hasattr(self.embed_function, 'embed_documents'):
                embeddings = self.embed_function.embed_documents(texts)
                return [np.array(emb, dtype=np.float32) for emb in embeddings]
            else:
                # Fall back to individual embedding
                return [self.embed_text(text) for text in texts]

        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}") # Updated logging
            # Fall back to individual embedding
            return [self.embed_text(text) for text in texts]


class IndexDocumentUseCase:
    """Use case for indexing a document into hierarchical RAG system.

    This orchestrates:
    1. Chunking document into hierarchy
    2. Generating embeddings for chunks
    3. Storing chunks and embeddings in database
    """

    def __init__(
        self,
        doc_repository: HierarchicalDocumentRepository,
        vector_repository: VectorStoreRepository,
        embedding_service: EmbeddingService,
        chunker: Optional[HierarchicalChunker] = None
    ):
        """Initialize use case.

        Args:
            doc_repository: Repository for documents and chunks
            vector_repository: Repository for vector embeddings
            embedding_service: Service for generating embeddings
            chunker: Hierarchical chunker (creates default if None)
        """
        self.doc_repository = doc_repository
        self.vector_repository = vector_repository
        self.embedding_service = embedding_service
        self.chunker = chunker or HierarchicalChunker()

    def execute(
        self,
        file_path: Path,
        document_id: Optional[DocumentId] = None,
        force_reindex: bool = False
    ) -> Document:
        """Index a document file.

        Args:
            file_path: Path to document file
            document_id: Optional document ID (generated from filename if None)
            force_reindex: Whether to force reindexing if document exists

        Returns:
            Indexed Document entity

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If document already exists and force_reindex=False
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        # Generate document ID if not provided
        if document_id is None:
            document_id = DocumentId.from_filename(file_path.name)

        logger.info(f"Indexing document: {document_id} from {file_path.name}")
        log_json("document_indexing_start", {
            "document_id": str(document_id),
            "file_name": file_path.name,
            "file_path": str(file_path),
            "force_reindex": force_reindex
        })

        # Check if document already exists
        existing_doc = self.doc_repository.get_document(document_id)
        if existing_doc and not force_reindex:
            logger.warning(
                f"Document {document_id} already exists. "
                f"Use force_reindex=True to reindex."
            )
            log_json("document_indexing_skipped", {
                "document_id": str(document_id),
                "file_name": file_path.name,
                "reason": "already_exists_no_reindex"
            }, level="warning")
            raise ValueError(
                f"Document {document_id} already exists. "
                f"Use force_reindex=True to reindex."
            )

        # Step 1: Chunk document into hierarchy
        logger.info("  Step 1: Chunking document...")
        document = self.chunker.chunk_file(file_path, document_id)
        logger.info(f"    Created {len(document.chunks)} chunks")

        # Step 2: Save document metadata
        logger.info("  Step 2: Saving document metadata...")
        success = self.doc_repository.save_document(document)
        if not success:
            logger.error(f"Failed to save document {document_id}")
            log_json("document_indexing_failed", {
                "document_id": str(document_id),
                "file_name": file_path.name,
                "reason": "failed_to_save_metadata"
            }, level="error")
            raise RuntimeError(f"Failed to save document {document_id}")

        # Step 3: Save chunks in batch
        logger.info("  Step 3: Saving chunks...")
        success = self.doc_repository.save_chunks_batch(document.chunks)
        if not success:
            logger.error(f"Failed to save chunks for {document_id}")
            log_json("document_indexing_failed", {
                "document_id": str(document_id),
                "file_name": file_path.name,
                "reason": "failed_to_save_chunks"
            }, level="error")
            raise RuntimeError(f"Failed to save chunks for {document_id}")

        # Step 4: Build closure table for hierarchy
        logger.info("  Step 4: Building hierarchy closure table...")
        success = self.doc_repository.build_closure_table(document_id)
        if not success:
            logger.warning("    Warning: Failed to build closure table")
            log_json("document_indexing_warning", {
                "document_id": str(document_id),
                "file_name": file_path.name,
                "reason": "failed_to_build_closure_table"
            }, level="warning")

        # Step 5: Generate and save embeddings
        logger.info("  Step 5: Generating embeddings...")
        self._embed_and_store_chunks(document)

        logger.info(f"✓ Successfully indexed document {document_id}")
        logger.info(f"  - Total chunks: {len(document.chunks)}")
        logger.info(f"  - Summary chunks: {len(document.get_chunks_by_level(IndexingLevel.SUMMARY))}")
        logger.info(f"  - Detail chunks: {len(document.get_chunks_by_level(IndexingLevel.DETAIL))}")
        log_json("document_indexing_complete", {
            "document_id": str(document_id),
            "file_name": file_path.name,
            "total_chunks": len(document.chunks),
            "summary_chunks": len(document.get_chunks_by_level(IndexingLevel.SUMMARY)),
            "detail_chunks": len(document.get_chunks_by_level(IndexingLevel.DETAIL))
        })


        return document

    def _embed_and_store_chunks(self, document: Document):
        """Generate and store embeddings for all chunks.

        Args:
            document: Document with chunks
        """
        # Separate chunks by indexing level
        summary_chunks = []
        detail_chunks = []

        for chunk in document.chunks:
            if chunk.indexing_level in [IndexingLevel.SUMMARY, IndexingLevel.BOTH]:
                summary_chunks.append(chunk)
            if chunk.indexing_level in [IndexingLevel.DETAIL, IndexingLevel.BOTH]:
                detail_chunks.append(chunk)

        # Generate and store summary embeddings
        if summary_chunks:
            logger.info(f"    Embedding {len(summary_chunks)} summary chunks...") # Updated logging
            self._embed_and_store_batch(summary_chunks, IndexingLevel.SUMMARY)

        # Generate and store detail embeddings
        if detail_chunks:
            logger.info(f"    Embedding {len(detail_chunks)} detail chunks...") # Updated logging
            self._embed_and_store_batch(detail_chunks, IndexingLevel.DETAIL)

    def _embed_and_store_batch(self, chunks: list, level: IndexingLevel):
        """Generate and store embeddings for a batch of chunks.

        Args:
            chunks: List of Chunk entities
            level: Indexing level (SUMMARY or DETAIL)
        """
        # Extract texts
        texts = [chunk.content for chunk in chunks]

        # Generate embeddings in batch
        try:
            embeddings = self.embedding_service.embed_batch(texts)
        except Exception as e:
            logger.error(f"    Batch embedding failed: {e}, falling back to individual") # Updated logging
            embeddings = [self.embedding_service.embed_text(text) for text in texts]

        # Store embeddings
        for chunk, embedding in zip(chunks, embeddings):
            success = self.vector_repository.save_embedding(
                chunk.id,
                embedding,
                level
            )
            if not success:
                logger.warning(f"    Warning: Failed to save embedding for chunk {chunk.id}") # Updated logging


class BulkIndexUseCase:
    """Use case for indexing multiple documents."""

    def __init__(self, index_document_use_case: IndexDocumentUseCase):
        """Initialize bulk index use case.

        Args:
            index_document_use_case: Single document indexing use case
        """
        self.index_document = index_document_use_case

    def execute(
        self,
        file_paths: list[Path],
        force_reindex: bool = False,
        skip_errors: bool = True
    ) -> dict:
        """Index multiple documents.

        Args:
            file_paths: List of document file paths
            force_reindex: Whether to force reindexing existing documents
            skip_errors: Whether to continue on errors

        Returns:
            Dict with success/failure counts and details
        """
        results = {
            "total": len(file_paths),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }

        log_json("bulk_indexing_start", {
            "total_files": len(file_paths),
            "force_reindex": force_reindex,
            "skip_errors": skip_errors
        })

        for i, file_path in enumerate(file_paths, 1):
            logger.info(f"\n[{i}/{len(file_paths)}] Processing {file_path.name}...") # Updated logging

            try:
                document = self.index_document.execute(
                    file_path,
                    force_reindex=force_reindex
                )
                results["success"] += 1

            except ValueError as e:
                # Document already exists
                if "already exists" in str(e):
                    logger.info(f"  Skipped: {e}") # Updated logging
                    results["skipped"] += 1
                else:
                    logger.error(f"  Error: {e}") # Updated logging
                    results["failed"] += 1
                    results["errors"].append({
                        "file": file_path.name,
                        "error": str(e)
                    })
                    if not skip_errors:
                        raise

            except Exception as e:
                logger.error(f"  Error: {e}") # Updated logging
                results["failed"] += 1
                results["errors"].append({
                    "file": file_path.name,
                    "error": str(e)
                })
                if not skip_errors:
                    raise

        logger.info("\n" + "="*60) # Updated logging
        logger.info(f"Bulk indexing complete:") # Updated logging
        logger.info(f"  Total: {results['total']}") # Updated logging
        logger.info(f"  Success: {results['success']}") # Updated logging
        logger.info(f"  Skipped: {results['skipped']}") # Updated logging
        logger.info(f"  Failed: {results['failed']}") # Updated logging

        if results["errors"]:
            logger.info(f"\nErrors:") # Updated logging
            for err in results["errors"]:
                logger.info(f"  - {err['file']}: {err['error']}") # Updated logging
            log_json("bulk_indexing_complete", results, level="error")
        else:
            log_json("bulk_indexing_complete", results)


        return results
```
