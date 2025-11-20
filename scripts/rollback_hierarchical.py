#!/usr/bin/env python3
"""Rollback utility for hierarchical RAG migration.

This script safely removes hierarchical data while preserving the original
flat LangChain collections.

Usage:
    # Remove specific document
    python scripts/rollback_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --document-id "doc_abc123"

    # Remove all hierarchical data
    python scripts/rollback_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --drop-all

    # Drop entire hierarchical schema
    python scripts/rollback_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --drop-schema
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_system.common import log
from rag_system.domain import DocumentId
from rag_system.infrastructure.database import HierarchicalDocumentRepository

import psycopg2
from psycopg2.extras import RealDictCursor


class HierarchicalRollback:
    """Handles rollback of hierarchical RAG data."""

    def __init__(self, conn_str: str):
        """Initialize rollback utility.

        Args:
            conn_str: PostgreSQL connection string
        """
        self.conn_str = conn_str
        self.doc_repository = HierarchicalDocumentRepository(conn_str)

    def list_hierarchical_documents(self) -> List[Dict]:
        """List all documents in hierarchical system.

        Returns:
            List of document info dicts
        """
        clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

        try:
            with psycopg2.connect(clean_conn_str) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            d.id,
                            d.title,
                            d.source_file,
                            d.law_category,
                            d.chunk_count,
                            d.created_at,
                            COUNT(DISTINCT es.chunk_id) as summary_embeddings,
                            COUNT(DISTINCT ed.chunk_id) as detail_embeddings
                        FROM rag_documents d
                        LEFT JOIN rag_chunk_embeddings_summary es ON es.chunk_id IN (
                            SELECT id FROM rag_document_chunks WHERE document_id = d.id
                        )
                        LEFT JOIN rag_chunk_embeddings_detail ed ON ed.chunk_id IN (
                            SELECT id FROM rag_document_chunks WHERE document_id = d.id
                        )
                        GROUP BY d.id, d.title, d.source_file, d.law_category, d.chunk_count, d.created_at
                        ORDER BY d.created_at DESC
                    """)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log(f"Error listing documents: {e}")
            return []

    def get_document_stats(self, document_id: DocumentId) -> Optional[Dict]:
        """Get statistics for a specific document.

        Args:
            document_id: Document ID to query

        Returns:
            Dict with document statistics, or None if not found
        """
        clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

        try:
            with psycopg2.connect(clean_conn_str) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            COUNT(DISTINCT c.id) as total_chunks,
                            COUNT(DISTINCT h.ancestor_id) as hierarchy_entries,
                            COUNT(DISTINCT es.chunk_id) as summary_embeddings,
                            COUNT(DISTINCT ed.chunk_id) as detail_embeddings,
                            STRING_AGG(DISTINCT c.chunk_type::text, ', ') as chunk_types
                        FROM rag_document_chunks c
                        LEFT JOIN rag_chunk_hierarchy h ON c.id = h.descendant_id
                        LEFT JOIN rag_chunk_embeddings_summary es ON c.id = es.chunk_id
                        LEFT JOIN rag_chunk_embeddings_detail ed ON c.id = ed.chunk_id
                        WHERE c.document_id = %s
                    """, (str(document_id),))
                    return dict(cur.fetchone()) if cur.rowcount > 0 else None
        except Exception as e:
            log(f"Error getting document stats: {e}")
            return None

    def delete_document(self, document_id: DocumentId, dry_run: bool = False) -> bool:
        """Delete a single document from hierarchical system.

        Args:
            document_id: Document ID to delete
            dry_run: If True, only show what would be deleted

        Returns:
            True if successful, False otherwise
        """
        log(f"\n{'[DRY RUN] ' if dry_run else ''}Deleting document: {document_id}")

        # Get document info
        document = self.doc_repository.get_document(document_id)
        if not document:
            log(f"  ✗ Document not found: {document_id}")
            return False

        # Get statistics
        stats = self.get_document_stats(document_id)
        if stats:
            log(f"  Document: {document.title}")
            log(f"  Source: {document.source_file}")
            log(f"  Total chunks: {stats['total_chunks']}")
            log(f"  Hierarchy entries: {stats['hierarchy_entries']}")
            log(f"  Summary embeddings: {stats['summary_embeddings']}")
            log(f"  Detail embeddings: {stats['detail_embeddings']}")
            log(f"  Chunk types: {stats['chunk_types']}")

        if dry_run:
            log(f"  ✓ Would delete all associated data (cascading)")
            return True

        # Perform deletion
        try:
            self.doc_repository.delete_document(document_id)
            log(f"  ✓ Document deleted successfully")
            return True
        except Exception as e:
            log(f"  ✗ Deletion failed: {e}")
            return False

    def delete_all_documents(self, dry_run: bool = False) -> bool:
        """Delete all documents from hierarchical system.

        Args:
            dry_run: If True, only show what would be deleted

        Returns:
            True if successful, False otherwise
        """
        documents = self.list_hierarchical_documents()

        if not documents:
            log("No hierarchical documents found")
            return True

        log(f"\n{'='*60}")
        log(f"{'[DRY RUN] ' if dry_run else ''}Deleting ALL hierarchical data")
        log(f"{'='*60}")
        log(f"Total documents: {len(documents)}\n")

        success_count = 0
        fail_count = 0

        for i, doc_info in enumerate(documents, 1):
            doc_id = DocumentId(doc_info['id'])
            log(f"[{i}/{len(documents)}] {doc_info['title']}")

            if dry_run:
                log(f"  Would delete: {doc_info['chunk_count']} chunks, "
                    f"{doc_info['summary_embeddings']} summary + "
                    f"{doc_info['detail_embeddings']} detail embeddings")
                success_count += 1
            else:
                if self.delete_document(doc_id, dry_run=False):
                    success_count += 1
                else:
                    fail_count += 1

        log(f"\n{'='*60}")
        log(f"Deletion {'Preview' if dry_run else 'Complete'}")
        log(f"{'='*60}")
        log(f"  Success: {success_count}")
        log(f"  Failed:  {fail_count}")

        return fail_count == 0

    def drop_hierarchical_schema(self, confirm: bool = False) -> bool:
        """Drop the entire hierarchical schema.

        WARNING: This removes all tables, indexes, and views.
        The flat LangChain tables are preserved.

        Args:
            confirm: Must be True to actually drop schema

        Returns:
            True if successful, False otherwise
        """
        if not confirm:
            log("\n⚠ WARNING: This will DROP all hierarchical tables!")
            log("  The following tables will be removed:")
            log("    - rag_documents")
            log("    - rag_document_chunks")
            log("    - rag_chunk_hierarchy")
            log("    - rag_chunk_embeddings_summary")
            log("    - rag_chunk_embeddings_detail")
            log("  The flat LangChain tables will be PRESERVED.")
            log("\nTo confirm, use: --drop-schema --confirm")
            return False

        clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

        DROP_SCHEMA_SQL = """
        -- Drop views
        DROP VIEW IF EXISTS chunk_with_ancestors CASCADE;

        -- Drop tables (in reverse dependency order)
        DROP TABLE IF EXISTS rag_chunk_embeddings_detail CASCADE;
        DROP TABLE IF EXISTS rag_chunk_embeddings_summary CASCADE;
        DROP TABLE IF EXISTS rag_chunk_hierarchy CASCADE;
        DROP TABLE IF EXISTS rag_document_chunks CASCADE;
        DROP TABLE IF EXISTS rag_documents CASCADE;

        -- Drop functions
        DROP FUNCTION IF EXISTS update_document_updated_at() CASCADE;
        """

        try:
            log("\nDropping hierarchical schema...")

            with psycopg2.connect(clean_conn_str) as conn:
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

                with conn.cursor() as cur:
                    cur.execute(DROP_SCHEMA_SQL)

            log("  ✓ Hierarchical schema dropped successfully")
            log("  ✓ Flat LangChain tables preserved")
            return True

        except Exception as e:
            log(f"  ✗ Error dropping schema: {e}")
            return False

    def show_status(self) -> None:
        """Show current hierarchical system status."""
        documents = self.list_hierarchical_documents()

        log(f"\n{'='*60}")
        log(f"Hierarchical RAG System Status")
        log(f"{'='*60}")

        if not documents:
            log("\nNo hierarchical documents found")
            return

        log(f"\nTotal documents: {len(documents)}\n")

        total_chunks = sum(d['chunk_count'] for d in documents)
        total_summary = sum(d['summary_embeddings'] for d in documents)
        total_detail = sum(d['detail_embeddings'] for d in documents)

        for i, doc in enumerate(documents, 1):
            log(f"{i:2d}. {doc['title']}")
            log(f"    ID: {doc['id']}")
            log(f"    Source: {doc['source_file']}")
            log(f"    Category: {doc.get('law_category', 'N/A')}")
            log(f"    Chunks: {doc['chunk_count']}")
            log(f"    Embeddings: {doc['summary_embeddings']} summary + {doc['detail_embeddings']} detail")
            log(f"    Created: {doc['created_at']}")
            log("")

        log(f"{'='*60}")
        log(f"Totals:")
        log(f"  Documents: {len(documents)}")
        log(f"  Chunks: {total_chunks}")
        log(f"  Summary embeddings: {total_summary}")
        log(f"  Detail embeddings: {total_detail}")
        log(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Rollback hierarchical RAG migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--conn",
        type=str,
        required=True,
        help="PostgreSQL connection string",
    )

    parser.add_argument(
        "--document-id",
        type=str,
        help="Delete specific document by ID",
    )

    parser.add_argument(
        "--drop-all",
        action="store_true",
        help="Delete all hierarchical documents",
    )

    parser.add_argument(
        "--drop-schema",
        action="store_true",
        help="Drop entire hierarchical schema (WARNING: irreversible)",
    )

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive operations",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions without making changes",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show hierarchical system status",
    )

    args = parser.parse_args()

    # Initialize rollback utility
    rollback = HierarchicalRollback(conn_str=args.conn)

    # Show status
    if args.status or not any([args.document_id, args.drop_all, args.drop_schema]):
        rollback.show_status()
        return

    # Drop schema
    if args.drop_schema:
        success = rollback.drop_hierarchical_schema(confirm=args.confirm)
        sys.exit(0 if success else 1)

    # Drop all documents
    if args.drop_all:
        success = rollback.delete_all_documents(dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # Drop specific document
    if args.document_id:
        doc_id = DocumentId(args.document_id)
        success = rollback.delete_document(doc_id, dry_run=args.dry_run)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
