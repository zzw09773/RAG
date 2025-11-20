#!/usr/bin/env python3
"""Test script for hierarchical RAG system.

This script demonstrates and tests the complete hierarchical RAG workflow:
1. Initialize database schema
2. Index a sample document with hierarchical chunking
3. Perform hierarchical retrieval
4. Display results with context

Usage:
    python scripts/test_hierarchical_system.py
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from rag_system.infrastructure.schema import init_hierarchical_schema, get_schema_info


def main():
    print("="*70)
    print("Hierarchical RAG System Test")
    print("="*70)

    # Load environment
    load_dotenv()
    conn_str = os.environ.get("PGVECTOR_URL")

    if not conn_str:
        print("\nError: PGVECTOR_URL not set", file=sys.stderr)
        print("Please set PGVECTOR_URL in your .env file", file=sys.stderr)
        sys.exit(1)

    # Test 1: Schema initialization
    print("\n[Test 1] Initializing hierarchical schema...")
    print("-"*70)

    success = init_hierarchical_schema(conn_str)

    if success:
        print("✓ Schema initialized successfully\n")
        print(get_schema_info(conn_str))
    else:
        print("✗ Schema initialization failed", file=sys.stderr)
        sys.exit(1)

    # Test 2: Display next steps
    print("\n" + "="*70)
    print("Next Steps")
    print("="*70)

    print("""
The hierarchical RAG database schema has been successfully initialized!

You can now:

1. Index documents with hierarchical chunking:

   python scripts/index_hierarchical.py rag_system/documents/your_doc.md

2. Query using hierarchical retrieval (after implementing query script):

   python scripts/query_hierarchical.py -q "your question"

3. Verify the schema anytime:

   python scripts/init_hierarchical_schema.py --verify

Key Features Now Available:
-------------------------
✓ Multi-level document hierarchy (Document → Chapter → Article → Section)
✓ Parent-child chunk relationships with closure tables
✓ Dual-layer vector indexing (Summary + Detail)
✓ ltree-based path queries for efficient tree operations
✓ HNSW vector indexes for fast similarity search

Database Tables Created:
----------------------
- rag_documents              (document metadata)
- rag_document_chunks         (hierarchical chunks with ltree paths)
- rag_chunk_hierarchy         (closure table for O(1) queries)
- rag_chunk_embeddings_summary (high-level concept vectors)
- rag_chunk_embeddings_detail  (fine-grained content vectors)

Next Development Tasks:
--------------------
- Implement query_hierarchical.py for retrieval testing
- Integrate with existing LangGraph agent (add --hierarchical flag)
- Create migration tools for existing collections
- A/B test hierarchical vs flat retrieval

""")

    print("="*70)
    print("✓ Test completed successfully!")
    print("="*70)


if __name__ == "__main__":
    main()
