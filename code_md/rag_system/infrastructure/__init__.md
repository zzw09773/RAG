# rag_system/infrastructure/__init__.py
```python
"""Infrastructure layer for hierarchical RAG system.

This layer contains implementations of data access, external services,
and framework-specific code.
"""
from .database import HierarchicalDocumentRepository, VectorStoreRepository
from .schema import init_hierarchical_schema

__all__ = [
    "HierarchicalDocumentRepository",
    "VectorStoreRepository",
    "init_hierarchical_schema",
]
```
