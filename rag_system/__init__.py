"""
RAG System Core Library

This package follows a Clean Architecture-inspired layout:
    - ``domain``: Entities and value objects that model documents and hierarchy.
    - ``infrastructure``: Database repositories and schema helpers.
    - ``application``: Use cases such as indexing, retrieval, and chunking.
    - ``tool``: LangGraph tool implementations for agent workflows.
    - ``workflow``: LangGraph orchestration entry points for notebooks.
"""

from .common import log, set_quiet_mode, LocalApiEmbeddings

__version__ = "2.0.0"
__author__ = "RAG System Team"
__all__ = ["log", "set_quiet_mode", "LocalApiEmbeddings"]
