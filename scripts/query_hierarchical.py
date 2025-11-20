#!/usr/bin/env python3
"""Hierarchical RAG query CLI tool.

This script provides a command-line interface for querying the hierarchical
RAG system using the Summary-First retrieval strategy.

Usage:
    # Basic query
    python scripts/query_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --embed-api-key "YOUR_API_KEY" \\
        --query "航空器設計需要什麼文件？"

    # Advanced options
    python scripts/query_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --embed-api-key "YOUR_API_KEY" \\
        --query "違反第3條規定會有什麼罰則？" \\
        --k 5 \\
        --summary-k 3 \\
        --detail-k 3 \\
        --document-id "doc_abc123" \\
        --show-context
"""

import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_system.common import log
from rag_system.domain import DocumentId
from rag_system.infrastructure.database import VectorStoreRepository
from rag_system.application.retrieval import (
    HierarchicalRetrievalUseCase,
    SummaryFirstRetrievalStrategy,
    RetrievalResult,
)


def format_result(result: RetrievalResult, index: int, show_context: bool = False) -> str:
    """Format a retrieval result for display.

    Args:
        result: RetrievalResult to format
        index: Result index (1-based)
        show_context: Whether to show hierarchical context

    Returns:
        Formatted string
    """
    lines = []

    # Header
    lines.append(f"\n{'='*70}")
    lines.append(f"[{index}] Score: {result.score:.4f}")
    lines.append(f"{'='*70}")

    # Metadata
    lines.append(f"Chunk ID: {result.chunk_id}")
    lines.append(f"Type: {result.chunk_type}")
    lines.append(f"Level: {result.indexing_level}")
    lines.append(f"Path: {result.section_path}")
    lines.append(f"Source: {result.source_file}")

    if result.article_number:
        lines.append(f"Article: {result.article_number}")
    if result.chapter_number:
        lines.append(f"Chapter: {result.chapter_number}")

    # Main content
    lines.append(f"\n--- Content ---")
    lines.append(result.content)

    # Hierarchical context (if requested)
    if show_context:
        if result.parent_content:
            lines.append(f"\n--- Parent Context ---")
            lines.append(result.parent_content)

        if result.children_contents:
            lines.append(f"\n--- Child Contexts ({len(result.children_contents)}) ---")
            for i, child in enumerate(result.children_contents, 1):
                lines.append(f"\n  [{i}] {child[:200]}...")

        if result.sibling_contents:
            lines.append(f"\n--- Sibling Contexts ({len(result.sibling_contents)}) ---")
            for i, sibling in enumerate(result.sibling_contents[:3], 1):
                lines.append(f"\n  [{i}] {sibling[:200]}...")

    return "\n".join(lines)


def print_summary(results: List[RetrievalResult], query: str) -> None:
    """Print query summary.

    Args:
        results: List of retrieval results
        query: Original query string
    """
    total_chars = sum(len(r.content) for r in results)
    total_tokens_approx = sum(len(r.content.split()) for r in results)

    # Add context tokens
    for r in results:
        if r.parent_content:
            total_tokens_approx += len(r.parent_content.split())
        for child in r.children_contents:
            total_tokens_approx += len(child.split())
        for sibling in r.sibling_contents:
            total_tokens_approx += len(sibling.split())

    log(f"\n{'='*70}")
    log(f"Query Summary")
    log(f"{'='*70}")
    log(f"Query: {query}")
    log(f"Results: {len(results)}")
    log(f"Total chars: {total_chars:,}")
    log(f"Total tokens (approx): {total_tokens_approx:,}")
    log(f"{'='*70}")


def main():
    parser = argparse.ArgumentParser(
        description="Query hierarchical RAG system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required arguments
    parser.add_argument(
        "--conn",
        type=str,
        required=True,
        help="PostgreSQL connection string",
    )

    parser.add_argument(
        "--embed-api-key",
        type=str,
        required=True,
        help="API key for embedding service",
    )

    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Query string",
    )

    # Optional arguments
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Total number of results to return (default: 5)",
    )

    parser.add_argument(
        "--summary-k",
        type=int,
        default=3,
        help="Number of summary chunks to retrieve in phase 1 (default: 3)",
    )

    parser.add_argument(
        "--detail-k",
        type=int,
        default=3,
        help="Number of detail chunks to retrieve per summary in phase 2 (default: 3)",
    )

    parser.add_argument(
        "--document-id",
        type=str,
        help="Filter results to specific document ID",
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
        "--show-context",
        action="store_true",
        help="Show hierarchical context (parent, children, siblings)",
    )

    parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    # Initialize components
    log("Initializing hierarchical retrieval system...")

    vector_repository = VectorStoreRepository(
        conn_str=args.conn,
        api_key=args.embed_api_key,
        embedding_dim=args.embedding_dim,
        verify_ssl=not args.no_verify_ssl,
    )

    retrieval_strategy = SummaryFirstRetrievalStrategy(
        vector_repository=vector_repository,
        summary_k=args.summary_k,
        detail_expansion_k=args.detail_k,
    )

    retrieval_use_case = HierarchicalRetrievalUseCase(strategy=retrieval_strategy)

    # Execute query
    log(f"\nQuerying: {args.query}")
    log(f"Retrieving top {args.k} results...")

    document_id = DocumentId(args.document_id) if args.document_id else None

    results = retrieval_use_case.execute(
        query=args.query,
        k=args.k,
        document_id=document_id,
    )

    # Output results
    if args.format == "json":
        import json

        output = {
            "query": args.query,
            "k": args.k,
            "results": [
                {
                    "chunk_id": str(r.chunk_id),
                    "score": r.score,
                    "content": r.content,
                    "chunk_type": r.chunk_type,
                    "indexing_level": r.indexing_level,
                    "section_path": r.section_path,
                    "source_file": r.source_file,
                    "article_number": r.article_number,
                    "chapter_number": r.chapter_number,
                    "parent_content": r.parent_content if args.show_context else None,
                    "children_count": len(r.children_contents) if args.show_context else 0,
                    "siblings_count": len(r.sibling_contents) if args.show_context else 0,
                }
                for r in results
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    else:
        # Text format
        for i, result in enumerate(results, 1):
            print(format_result(result, i, show_context=args.show_context))

        print_summary(results, args.query)


if __name__ == "__main__":
    main()
