#!/usr/bin/env python3
"""Initialize the hierarchical RAG database schema.

This script creates the new hierarchical tables alongside existing LangChain tables.
It's safe to run multiple times (uses IF NOT EXISTS).

Usage:
    python scripts/init_hierarchical_schema.py [--verify]
"""
import argparse
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from rag_system.infrastructure.schema import (
    init_hierarchical_schema,
    verify_schema,
    get_schema_info
)


def main():
    parser = argparse.ArgumentParser(description="Initialize hierarchical RAG schema")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify schema instead of creating it"
    )
    parser.add_argument(
        "--conn",
        default=None,
        help="PostgreSQL connection string (defaults to PGVECTOR_URL env var)"
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Get connection string
    conn_str = args.conn or os.environ.get("PGVECTOR_URL")
    if not conn_str:
        print("Error: No connection string provided.", file=sys.stderr)
        print("Set PGVECTOR_URL environment variable or use --conn flag.", file=sys.stderr)
        sys.exit(1)

    if args.verify:
        # Verify schema
        print(get_schema_info(conn_str))
    else:
        # Initialize schema
        success = init_hierarchical_schema(conn_str)

        if success:
            print("\n" + get_schema_info(conn_str))
            print("\n✓ Hierarchical schema initialized successfully!")
            print("\nNext steps:")
            print("  1. Index documents using the new hierarchical chunker")
            print("  2. Use the hierarchical retrieval tools in your queries")
            sys.exit(0)
        else:
            print("\n✗ Failed to initialize schema", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
