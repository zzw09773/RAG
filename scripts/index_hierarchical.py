#!/usr/bin/env python3
"""Index documents using hierarchical chunking strategy.

This script uses the new Clean Architecture approach to index documents
with full hierarchical structure and multi-level vector indexing.

Usage:
    # Index a single document
    python scripts/index_hierarchical.py path/to/document.md

    # Index all documents in a directory
    python scripts/index_hierarchical.py path/to/documents/ --recursive

    # Force reindex existing documents
    python scripts/index_hierarchical.py path/to/document.md --force
"""
import argparse
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from rag_system.domain import DocumentId
from rag_system.infrastructure import (
    HierarchicalDocumentRepository,
    VectorStoreRepository,
    init_hierarchical_schema
)
from rag_system.application import (
    HierarchicalChunker,
    IndexDocumentUseCase,
    BulkIndexUseCase
)
from rag_system.application.indexing import EmbeddingService
from rag_system.common import LocalApiEmbeddings, log


def collect_files(path: Path, recursive: bool = False) -> list[Path]:
    """Collect document files from path.

    Args:
        path: File or directory path
        recursive: Whether to search recursively

    Returns:
        List of file paths
    """
    if path.is_file():
        return [path]

    if path.is_dir():
        pattern = "**/*" if recursive else "*"
        files = []
        for ext in [".md", ".txt"]:
            files.extend(path.glob(f"{pattern}{ext}"))
        return sorted(files)

    return []


def main():
    parser = argparse.ArgumentParser(
        description="Index documents with hierarchical chunking"
    )

    # Input arguments
    parser.add_argument(
        "path",
        type=Path,
        help="Path to document file or directory"
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively search directory for documents"
    )

    # Database arguments
    parser.add_argument(
        "--conn",
        default=None,
        help="PostgreSQL connection string (defaults to PGVECTOR_URL)"
    )

    # Embedding arguments
    parser.add_argument(
        "--embed-model",
        default=None,
        help="Embedding model name (defaults to EMBED_MODEL_NAME)"
    )
    parser.add_argument(
        "--embed-api-base",
        default=None,
        help="Embedding API base URL (defaults to EMBED_API_BASE)"
    )
    parser.add_argument(
        "--embed-api-key",
        default=None,
        help="API key (defaults to EMBED_API_KEY)"
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL verification"
    )
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=1024,
        help="Embedding vector dimension (default: 1024)"
    )

    # Chunking arguments
    parser.add_argument(
        "--max-chunk-size",
        type=int,
        default=800,
        help="Maximum chunk size in characters (default: 800)"
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=100,
        help="Chunk overlap in characters (default: 100)"
    )

    # Processing arguments
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force reindex even if document exists"
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue processing on errors"
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Initialize database schema before indexing"
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Get configuration
    conn_str = args.conn or os.environ.get("PGVECTOR_URL")
    embed_model = args.embed_model or os.environ.get("EMBED_MODEL_NAME", "nvidia/nv-embed-v2")
    embed_api_base = args.embed_api_base or os.environ.get("EMBED_API_BASE")
    embed_api_key = args.embed_api_key or os.environ.get("EMBED_API_KEY")

    # Validate configuration
    if not all([conn_str, embed_api_base, embed_api_key]):
        print("Error: Missing required configuration", file=sys.stderr)
        print("Set PGVECTOR_URL, EMBED_API_BASE, and EMBED_API_KEY environment variables", file=sys.stderr)
        print("Or provide them via command-line arguments", file=sys.stderr)
        sys.exit(1)

    # Initialize schema if requested
    if args.init_schema:
        print("Initializing hierarchical schema...")
        success = init_hierarchical_schema(conn_str)
        if not success:
            print("Failed to initialize schema", file=sys.stderr)
            sys.exit(1)
        print("✓ Schema initialized\n")

    # Collect files
    files = collect_files(args.path, args.recursive)

    if not files:
        print(f"No document files found in {args.path}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} document(s) to index\n")

    # Initialize components
    print("Initializing hierarchical RAG system...")

    # Repositories
    doc_repository = HierarchicalDocumentRepository(conn_str)
    vector_repository = VectorStoreRepository(conn_str, args.embedding_dim)

    # Embedding service
    embedding_model = LocalApiEmbeddings(
        api_base=embed_api_base,
        api_key=embed_api_key,
        model_name=embed_model,
        verify_ssl=not args.no_verify_ssl
    )
    embedding_service = EmbeddingService(embedding_model)

    # Chunker
    chunker = HierarchicalChunker(
        max_chunk_size=args.max_chunk_size,
        overlap=args.overlap
    )

    # Use cases
    index_use_case = IndexDocumentUseCase(
        doc_repository=doc_repository,
        vector_repository=vector_repository,
        embedding_service=embedding_service,
        chunker=chunker
    )

    print("✓ System initialized\n")

    # Index documents
    if len(files) == 1:
        # Single document
        file_path = files[0]
        try:
            document = index_use_case.execute(
                file_path=file_path,
                force_reindex=args.force
            )
            print(f"\n✓ Successfully indexed {file_path.name}")
            print(f"  - Document ID: {document.id}")
            print(f"  - Total chunks: {document.chunk_count}")
            print(f"  - Total chars: {document.total_chars}")

        except Exception as e:
            print(f"\n✗ Error indexing {file_path.name}: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        # Multiple documents
        bulk_use_case = BulkIndexUseCase(index_use_case)
        results = bulk_use_case.execute(
            file_paths=files,
            force_reindex=args.force,
            skip_errors=args.skip_errors
        )

        # Exit with error code if any failures
        if results["failed"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
