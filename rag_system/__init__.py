"""
RAG System Core Library

This package follows a Clean Architecture-inspired layout:
    - ``domain``: Entities and value objects that model documents and hierarchy.
    - ``infrastructure``: Database repositories and schema helpers.
    - ``application``: Use cases such as indexing, retrieval, and chunking.
    - ``tool``: LangGraph tool implementations for agent workflows.
    - ``workflow``: LangGraph orchestration entry points for notebooks.

Legacy assets are preserved under ``rag_system.legacy`` for backward compatibility
(e.g., the old CLI and build scripts). New development should depend on the
application-level use cases and notebook workflows instead of the legacy entry points.
"""

from .common import log, set_quiet_mode, LocalApiEmbeddings

__version__ = "2.0.0"
__author__ = "RAG System Team"
__all__ = ["log", "set_quiet_mode", "LocalApiEmbeddings"]