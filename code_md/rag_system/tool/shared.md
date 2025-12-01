# rag_system/tool/shared.py
```python
"""Shared utilities for RAG tools."""
from langchain_postgres import PGVector
from ..common import LocalApiEmbeddings


def get_vectorstore(
    connection_string: str,
    collection_name: str,
    api_base: str,
    api_key: str,
    embed_model: str,
    verify_ssl: bool = False
) -> PGVector:
    """Create and return a PGVector vectorstore instance.

    Args:
        connection_string: PostgreSQL connection string
        collection_name: Name of the PGVector collection
        api_base: API base URL for embeddings
        api_key: API key for embeddings
        embed_model: Name of the embedding model
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Configured PGVector vectorstore instance
    """
    embedder = LocalApiEmbeddings(
        api_base,
        api_key,
        embed_model,
        verify_ssl=verify_ssl
    )

    return PGVector(
        embeddings=embedder,
        collection_name=collection_name,
        connection=connection_string
    )
```
