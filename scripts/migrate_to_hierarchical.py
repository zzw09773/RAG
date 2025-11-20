#!/usr/bin/env python3
"""Migration utility to convert flat LangChain collections to hierarchical RAG.

This script migrates existing documents from the flat langchain_pg_embedding
and langchain_pg_collection tables to the new hierarchical schema.

Usage:
    python scripts/migrate_to_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --collection-name "law_collection" \\
        --embed-api-key "YOUR_API_KEY" \\
        --dry-run  # Optional: preview without making changes
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from datetime import datetime
import hashlib

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_system.common import log
from rag_system.domain import Document, Chunk, ChunkType, IndexingLevel, DocumentId, ChunkId
from rag_system.infrastructure.database import (
    HierarchicalDocumentRepository,
    VectorStoreRepository,
)
from rag_system.application.chunking import LegalDocumentChunkingStrategy

import psycopg2
from psycopg2.extras import RealDictCursor


class FlatToHierarchicalMigrator:
    """Migrates flat LangChain collections to hierarchical RAG structure."""

    def __init__(
        self,
        conn_str: str,
        embed_api_key: str,
        embedding_dim: int = 4096,
        verify_ssl: bool = True,
    ):
        """Initialize migrator.

        Args:
            conn_str: PostgreSQL connection string
            embed_api_key: API key for embedding service
            embedding_dim: Dimension of embeddings (default: 4096 for nv-embed-v2)
            verify_ssl: Whether to verify SSL for embedding API
        """
        self.conn_str = conn_str
        self.embed_api_key = embed_api_key
        self.embedding_dim = embedding_dim
        self.verify_ssl = verify_ssl

        # Initialize repositories
        self.doc_repository = HierarchicalDocumentRepository(conn_str)
        self.vector_repository = VectorStoreRepository(
            conn_str=conn_str,
            api_key=embed_api_key,
            embedding_dim=embedding_dim,
            verify_ssl=verify_ssl,
        )

        # Initialize chunking strategy
        self.chunker = LegalDocumentChunkingStrategy()

    def get_collections(self) -> List[Dict]:
        """Get all available LangChain collections.

        Returns:
            List of collection info dicts with name, uuid, and document count
        """
        clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

        try:
            with psycopg2.connect(clean_conn_str) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            c.name,
                            c.uuid,
                            c.cmetadata,
                            COUNT(DISTINCT e.document) as doc_count,
                            COUNT(e.id) as chunk_count
                        FROM langchain_pg_collection c
                        LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                        GROUP BY c.name, c.uuid, c.cmetadata
                        ORDER BY c.name
                    """)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log(f"Error fetching collections: {e}")
            return []

    def get_collection_documents(self, collection_name: str) -> List[Dict]:
        """Get all unique documents in a collection.

        Args:
            collection_name: Name of the LangChain collection

        Returns:
            List of document info dicts with source file and chunk count
        """
        clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

        try:
            with psycopg2.connect(clean_conn_str) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            e.document as source_file,
                            COUNT(e.id) as chunk_count,
                            MIN(e.cmetadata) as sample_metadata
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = %s
                        GROUP BY e.document
                        ORDER BY e.document
                    """, (collection_name,))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log(f"Error fetching documents: {e}")
            return []

    def migrate_document(
        self,
        source_file: str,
        collection_name: str,
        force_reindex: bool = False,
        dry_run: bool = False,
    ) -> Optional[Document]:
        """Migrate a single document from flat to hierarchical structure.

        Args:
            source_file: Path to the source file
            collection_name: Name of source LangChain collection
            force_reindex: Whether to re-chunk and re-embed the document
            dry_run: If True, only simulate migration without writing to DB

        Returns:
            Migrated Document object, or None if migration failed
        """
        log(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating: {source_file}")

        # Check if document already exists in hierarchical system
        document_id = DocumentId(f"doc_{hashlib.md5(source_file.encode()).hexdigest()[:16]}")
        existing_doc = self.doc_repository.get_document(document_id)

        if existing_doc and not force_reindex:
            log(f"  ⚠ Document already exists in hierarchical system (use --force to re-migrate)")
            return existing_doc

        # Check if source file exists
        file_path = Path(source_file)
        if not file_path.exists():
            log(f"  ✗ Source file not found: {source_file}")
            log(f"    Cannot re-chunk. Use --preserve-chunks to migrate existing chunks as-is.")
            return None

        if dry_run:
            log(f"  ✓ Would re-chunk and index: {source_file}")
            log(f"    Document ID: {document_id}")
            return None

        # Re-chunk the document with hierarchical strategy
        log(f"  → Re-chunking with hierarchical strategy...")
        try:
            document = self.chunker.chunk_file(file_path, document_id)
            log(f"  ✓ Created {len(document.chunks)} hierarchical chunks")

            # Save to database
            log(f"  → Saving to hierarchical schema...")
            self.doc_repository.save_document(document)
            self.doc_repository.save_chunks_batch(document.chunks)
            self.doc_repository.build_closure_table(document.id)

            # Generate and store embeddings
            log(f"  → Generating embeddings...")
            self._embed_and_store_chunks(document)

            log(f"  ✓ Migration complete: {document.id}")
            return document

        except Exception as e:
            log(f"  ✗ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _embed_and_store_chunks(self, document: Document) -> None:
        """Generate and store embeddings for document chunks.

        Args:
            document: Document with chunks to embed
        """
        summary_chunks = [c for c in document.chunks if c.indexing_level in [IndexingLevel.SUMMARY, IndexingLevel.BOTH]]
        detail_chunks = [c for c in document.chunks if c.indexing_level in [IndexingLevel.DETAIL, IndexingLevel.BOTH]]

        if summary_chunks:
            log(f"    → Embedding {len(summary_chunks)} summary chunks...")
            self.vector_repository.add_chunks_batch(summary_chunks, IndexingLevel.SUMMARY)

        if detail_chunks:
            log(f"    → Embedding {len(detail_chunks)} detail chunks...")
            self.vector_repository.add_chunks_batch(detail_chunks, IndexingLevel.DETAIL)

    def migrate_collection(
        self,
        collection_name: str,
        force_reindex: bool = False,
        dry_run: bool = False,
    ) -> Tuple[int, int]:
        """Migrate all documents in a collection.

        Args:
            collection_name: Name of the LangChain collection to migrate
            force_reindex: Whether to re-chunk and re-embed documents
            dry_run: If True, only simulate migration

        Returns:
            Tuple of (successful_count, failed_count)
        """
        log(f"\n{'='*60}")
        log(f"{'[DRY RUN] ' if dry_run else ''}Migrating collection: {collection_name}")
        log(f"{'='*60}")

        # Get all documents in collection
        documents = self.get_collection_documents(collection_name)

        if not documents:
            log(f"No documents found in collection: {collection_name}")
            return 0, 0

        log(f"Found {len(documents)} documents to migrate")

        success_count = 0
        fail_count = 0

        for i, doc_info in enumerate(documents, 1):
            source_file = doc_info['source_file']
            log(f"\n[{i}/{len(documents)}] Processing: {source_file}")

            result = self.migrate_document(
                source_file=source_file,
                collection_name=collection_name,
                force_reindex=force_reindex,
                dry_run=dry_run,
            )

            if result or (dry_run and Path(source_file).exists()):
                success_count += 1
            else:
                fail_count += 1

        log(f"\n{'='*60}")
        log(f"Migration {'Preview' if dry_run else 'Complete'}")
        log(f"{'='*60}")
        log(f"  Success: {success_count}")
        log(f"  Failed:  {fail_count}")
        log(f"  Total:   {len(documents)}")

        return success_count, fail_count

    def show_migration_preview(self, collection_name: str) -> None:
        """Show preview of what would be migrated.

        Args:
            collection_name: Name of collection to preview
        """
        documents = self.get_collection_documents(collection_name)

        log(f"\n{'='*60}")
        log(f"Migration Preview: {collection_name}")
        log(f"{'='*60}")
        log(f"Total documents: {len(documents)}\n")

        for i, doc_info in enumerate(documents, 1):
            source_file = doc_info['source_file']
            chunk_count = doc_info['chunk_count']
            file_exists = Path(source_file).exists()
            exists_mark = "✓" if file_exists else "✗"

            log(f"{i:3d}. {exists_mark} {source_file}")
            log(f"     Flat chunks: {chunk_count}")

            if file_exists:
                log(f"     Status: Ready to re-chunk with hierarchical strategy")
            else:
                log(f"     Status: Source file not found (migration will fail)")

        log(f"\n{'='*60}")
        log(f"Files found: {sum(1 for d in documents if Path(d['source_file']).exists())}/{len(documents)}")
        log(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate flat LangChain collections to hierarchical RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--conn",
        type=str,
        required=True,
        help="PostgreSQL connection string",
    )

    parser.add_argument(
        "--collection-name",
        type=str,
        help="Name of LangChain collection to migrate (omit to list collections)",
    )

    parser.add_argument(
        "--embed-api-key",
        type=str,
        help="API key for embedding service (required for migration)",
    )

    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=4096,
        help="Embedding dimension (default: 4096 for nv-embed-v2)",
    )

    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL verification for embedding API",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-migration of existing documents",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available collections and exit",
    )

    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show detailed preview of migration",
    )

    args = parser.parse_args()

    # Initialize migrator
    migrator = FlatToHierarchicalMigrator(
        conn_str=args.conn,
        embed_api_key=args.embed_api_key or "",
        embedding_dim=args.embedding_dim,
        verify_ssl=not args.no_verify_ssl,
    )

    # List collections
    if args.list or not args.collection_name:
        collections = migrator.get_collections()
        if not collections:
            log("No collections found in database")
            return

        log("\n=== Available Collections ===\n")
        for coll in collections:
            log(f"Collection: {coll['name']}")
            log(f"  UUID: {coll['uuid']}")
            log(f"  Documents: {coll['doc_count']}")
            log(f"  Chunks: {coll['chunk_count']}")
            log(f"  Metadata: {coll.get('cmetadata', {})}")
            log("")

        if not args.collection_name:
            log("Use --collection-name to migrate a specific collection")
            return

    # Show preview
    if args.preview:
        migrator.show_migration_preview(args.collection_name)
        return

    # Validate API key for actual migration
    if not args.dry_run and not args.embed_api_key:
        log("Error: --embed-api-key is required for migration (omit for --dry-run)")
        sys.exit(1)

    # Perform migration
    success, failed = migrator.migrate_collection(
        collection_name=args.collection_name,
        force_reindex=args.force,
        dry_run=args.dry_run,
    )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
