#!/usr/bin/env python3
"""Comparison tool for flat vs hierarchical RAG retrieval.

This script helps validate migration quality by comparing retrieval results
and performance between the flat LangChain system and hierarchical RAG.

Usage:
    python scripts/compare_flat_vs_hierarchical.py \\
        --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \\
        --query "航空器設計需要什麼文件？" \\
        --collection-name "law_collection" \\
        --embed-api-key "YOUR_API_KEY" \\
        --k 5
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_system.common import log
from rag_system.domain import IndexingLevel, DocumentId
from rag_system.infrastructure.database import VectorStoreRepository
from rag_system.application.retrieval import (
    HierarchicalRetrievalUseCase,
    SummaryFirstRetrievalStrategy,
    RetrievalResult,
)

from langchain_postgres import PGVector
import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class ComparisonResult:
    """Results from comparing flat vs hierarchical retrieval."""

    query: str
    k: int

    # Flat retrieval results
    flat_results: List[Dict]
    flat_time_ms: float
    flat_total_tokens: int

    # Hierarchical retrieval results
    hierarchical_results: List[RetrievalResult]
    hierarchical_time_ms: float
    hierarchical_total_tokens: int

    # Comparison metrics
    token_savings_percent: float
    speedup_factor: float
    overlap_count: int


class FlatVsHierarchicalComparator:
    """Compares flat and hierarchical RAG retrieval."""

    def __init__(
        self,
        conn_str: str,
        embed_api_key: str,
        collection_name: str = "law_collection",
        embedding_dim: int = 4096,
        verify_ssl: bool = True,
    ):
        """Initialize comparator.

        Args:
            conn_str: PostgreSQL connection string
            embed_api_key: API key for embedding service
            collection_name: Name of flat LangChain collection
            embedding_dim: Dimension of embeddings
            verify_ssl: Whether to verify SSL
        """
        self.conn_str = conn_str
        self.embed_api_key = embed_api_key
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.verify_ssl = verify_ssl

        # Initialize hierarchical retrieval
        vector_repo = VectorStoreRepository(
            conn_str=conn_str,
            api_key=embed_api_key,
            embedding_dim=embedding_dim,
            verify_ssl=verify_ssl,
        )

        retrieval_strategy = SummaryFirstRetrievalStrategy(
            vector_repository=vector_repo,
            summary_k=3,
            detail_expansion_k=3,
        )

        self.hierarchical_retrieval = HierarchicalRetrievalUseCase(
            strategy=retrieval_strategy
        )

        # Initialize flat retrieval (LangChain)
        self._init_flat_retrieval()

    def _init_flat_retrieval(self) -> None:
        """Initialize flat LangChain retrieval."""
        try:
            from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

            embeddings = NVIDIAEmbeddings(
                model="nvidia/nv-embed-v2",
                api_key=self.embed_api_key,
                truncate="END",
            )

            # Note: PGVector expects standard postgresql:// URL
            clean_conn_str = self.conn_str.replace("postgresql+psycopg2://", "postgresql://")

            self.flat_vectorstore = PGVector(
                embeddings=embeddings,
                collection_name=self.collection_name,
                connection=clean_conn_str,
                use_jsonb=True,
            )

        except Exception as e:
            log(f"Warning: Could not initialize flat retrieval: {e}")
            self.flat_vectorstore = None

    def compare_retrieval(
        self,
        query: str,
        k: int = 5,
        document_id: str = None,
    ) -> ComparisonResult:
        """Compare flat vs hierarchical retrieval for a query.

        Args:
            query: Query string
            k: Number of results to retrieve
            document_id: Optional document ID filter for hierarchical search

        Returns:
            ComparisonResult with metrics
        """
        log(f"\n{'='*60}")
        log(f"Comparing Retrieval")
        log(f"{'='*60}")
        log(f"Query: {query}")
        log(f"k: {k}")
        if document_id:
            log(f"Document filter: {document_id}")
        log("")

        # Run flat retrieval
        log("Running flat retrieval...")
        flat_start = time.time()
        flat_results = self._run_flat_retrieval(query, k)
        flat_time = (time.time() - flat_start) * 1000
        flat_tokens = sum(len(r['content'].split()) for r in flat_results) if flat_results else 0

        log(f"  ✓ Flat retrieval: {len(flat_results) if flat_results else 0} results in {flat_time:.1f}ms")
        log(f"    Total tokens (approx): {flat_tokens}")

        # Run hierarchical retrieval
        log("\nRunning hierarchical retrieval...")
        hierarchical_start = time.time()
        doc_id = DocumentId(document_id) if document_id else None
        hierarchical_results = self.hierarchical_retrieval.execute(
            query=query,
            k=k,
            document_id=doc_id,
        )
        hierarchical_time = (time.time() - hierarchical_start) * 1000

        # Count hierarchical tokens (main content + context)
        hierarchical_tokens = 0
        for result in hierarchical_results:
            hierarchical_tokens += len(result.content.split())
            if result.parent_content:
                hierarchical_tokens += len(result.parent_content.split())
            for sibling in result.sibling_contents:
                hierarchical_tokens += len(sibling.split())

        log(f"  ✓ Hierarchical retrieval: {len(hierarchical_results)} results in {hierarchical_time:.1f}ms")
        log(f"    Total tokens (approx): {hierarchical_tokens}")

        # Calculate metrics
        if flat_tokens > 0:
            token_savings = ((flat_tokens - hierarchical_tokens) / flat_tokens) * 100
        else:
            token_savings = 0.0

        if hierarchical_time > 0:
            speedup = flat_time / hierarchical_time
        else:
            speedup = 1.0

        # Count content overlap
        overlap = self._calculate_overlap(flat_results, hierarchical_results)

        result = ComparisonResult(
            query=query,
            k=k,
            flat_results=flat_results or [],
            flat_time_ms=flat_time,
            flat_total_tokens=flat_tokens,
            hierarchical_results=hierarchical_results,
            hierarchical_time_ms=hierarchical_time,
            hierarchical_total_tokens=hierarchical_tokens,
            token_savings_percent=token_savings,
            speedup_factor=speedup,
            overlap_count=overlap,
        )

        self._print_comparison_summary(result)
        return result

    def _run_flat_retrieval(self, query: str, k: int) -> List[Dict]:
        """Run flat LangChain retrieval.

        Args:
            query: Query string
            k: Number of results

        Returns:
            List of result dicts
        """
        if not self.flat_vectorstore:
            log("  ⚠ Flat retrieval not available")
            return []

        try:
            results = self.flat_vectorstore.similarity_search_with_score(query, k=k)

            return [
                {
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'score': float(score),
                }
                for doc, score in results
            ]

        except Exception as e:
            log(f"  ✗ Flat retrieval failed: {e}")
            return []

    def _calculate_overlap(
        self,
        flat_results: List[Dict],
        hierarchical_results: List[RetrievalResult],
    ) -> int:
        """Calculate content overlap between flat and hierarchical results.

        Args:
            flat_results: Flat retrieval results
            hierarchical_results: Hierarchical retrieval results

        Returns:
            Number of overlapping results
        """
        if not flat_results:
            return 0

        flat_contents = set(r['content'][:100] for r in flat_results)
        hierarchical_contents = set(r.content[:100] for r in hierarchical_results)

        return len(flat_contents & hierarchical_contents)

    def _print_comparison_summary(self, result: ComparisonResult) -> None:
        """Print comparison summary.

        Args:
            result: ComparisonResult to print
        """
        log(f"\n{'='*60}")
        log(f"Comparison Summary")
        log(f"{'='*60}")

        log(f"\nPerformance:")
        log(f"  Flat time:         {result.flat_time_ms:6.1f} ms")
        log(f"  Hierarchical time: {result.hierarchical_time_ms:6.1f} ms")
        log(f"  Speedup:           {result.speedup_factor:.2f}x")

        log(f"\nToken Usage:")
        log(f"  Flat tokens:         {result.flat_total_tokens:5d}")
        log(f"  Hierarchical tokens: {result.hierarchical_total_tokens:5d}")
        log(f"  Savings:             {result.token_savings_percent:5.1f}%")

        log(f"\nResults:")
        log(f"  Flat results:        {len(result.flat_results)}")
        log(f"  Hierarchical results: {len(result.hierarchical_results)}")
        log(f"  Content overlap:     {result.overlap_count}/{min(len(result.flat_results), len(result.hierarchical_results))}")

        # Show sample results
        if result.hierarchical_results:
            log(f"\n{'='*60}")
            log(f"Sample Hierarchical Results")
            log(f"{'='*60}")

            for i, res in enumerate(result.hierarchical_results[:3], 1):
                log(f"\n[{i}] Score: {res.score:.4f}")
                log(f"    Chunk: {res.chunk_id}")
                log(f"    Type: {res.chunk_type}")
                log(f"    Path: {res.section_path}")
                log(f"    Content: {res.content[:200]}...")

                if res.parent_content:
                    log(f"    Parent: {res.parent_content[:100]}...")

                if res.sibling_contents:
                    log(f"    Siblings: {len(res.sibling_contents)} chunks")

    def run_test_suite(self, test_queries: List[str], k: int = 5) -> List[ComparisonResult]:
        """Run comparison on multiple test queries.

        Args:
            test_queries: List of test queries
            k: Number of results per query

        Returns:
            List of ComparisonResults
        """
        results = []

        log(f"\n{'='*60}")
        log(f"Running Test Suite: {len(test_queries)} queries")
        log(f"{'='*60}\n")

        for i, query in enumerate(test_queries, 1):
            log(f"\n[Test {i}/{len(test_queries)}]")
            result = self.compare_retrieval(query, k)
            results.append(result)

        # Print aggregate summary
        self._print_aggregate_summary(results)

        return results

    def _print_aggregate_summary(self, results: List[ComparisonResult]) -> None:
        """Print aggregate summary of test suite.

        Args:
            results: List of ComparisonResults
        """
        if not results:
            return

        avg_flat_time = sum(r.flat_time_ms for r in results) / len(results)
        avg_hierarchical_time = sum(r.hierarchical_time_ms for r in results) / len(results)
        avg_speedup = sum(r.speedup_factor for r in results) / len(results)

        avg_flat_tokens = sum(r.flat_total_tokens for r in results) / len(results)
        avg_hierarchical_tokens = sum(r.hierarchical_total_tokens for r in results) / len(results)
        avg_savings = sum(r.token_savings_percent for r in results) / len(results)

        log(f"\n{'='*60}")
        log(f"Aggregate Summary ({len(results)} queries)")
        log(f"{'='*60}")

        log(f"\nAverage Performance:")
        log(f"  Flat time:         {avg_flat_time:6.1f} ms")
        log(f"  Hierarchical time: {avg_hierarchical_time:6.1f} ms")
        log(f"  Average speedup:   {avg_speedup:.2f}x")

        log(f"\nAverage Token Usage:")
        log(f"  Flat tokens:         {avg_flat_tokens:6.1f}")
        log(f"  Hierarchical tokens: {avg_hierarchical_tokens:6.1f}")
        log(f"  Average savings:     {avg_savings:5.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="Compare flat vs hierarchical RAG retrieval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

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
        help="Single query to test",
    )

    parser.add_argument(
        "--queries-file",
        type=Path,
        help="File with test queries (one per line)",
    )

    parser.add_argument(
        "--collection-name",
        type=str,
        default="law_collection",
        help="Name of flat LangChain collection (default: law_collection)",
    )

    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Number of results to retrieve (default: 5)",
    )

    parser.add_argument(
        "--document-id",
        type=str,
        help="Filter hierarchical search to specific document",
    )

    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=4096,
        help="Embedding dimension (default: 4096)",
    )

    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL verification",
    )

    args = parser.parse_args()

    # Initialize comparator
    comparator = FlatVsHierarchicalComparator(
        conn_str=args.conn,
        embed_api_key=args.embed_api_key,
        collection_name=args.collection_name,
        embedding_dim=args.embedding_dim,
        verify_ssl=not args.no_verify_ssl,
    )

    # Get test queries
    if args.query:
        test_queries = [args.query]
    elif args.queries_file:
        if not args.queries_file.exists():
            log(f"Error: Queries file not found: {args.queries_file}")
            sys.exit(1)
        test_queries = [
            line.strip()
            for line in args.queries_file.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('#')
        ]
    else:
        # Default test queries
        test_queries = [
            "航空器設計需要什麼文件？",
            "違反第3條規定會有什麼罰則？",
            "航空器設計人應具備什麼資格？",
        ]

    # Run comparison
    if len(test_queries) == 1:
        comparator.compare_retrieval(
            query=test_queries[0],
            k=args.k,
            document_id=args.document_id,
        )
    else:
        comparator.run_test_suite(test_queries, k=args.k)


if __name__ == "__main__":
    main()
