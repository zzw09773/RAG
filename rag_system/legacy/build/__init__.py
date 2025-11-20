"""
RAG System Build Module

Document processing, chunking, indexing, and export tools.

Core components:
- preprocess: Convert documents to clean markdown
- chunking: Split documents into chunks
- indexer: Build vector database indexes
- db_utils: Database utilities
- export: Export chunks in various formats
"""

# Lazy imports to avoid RuntimeWarning with -m execution
def __getattr__(name):
    if name == "preprocess_main":
        from .preprocess import main as preprocess_main
        return preprocess_main
    elif name == "chunk_document_general":
        from .chunking import chunk_document_general
        return chunk_document_general
    elif name == "chunk_document_law":
        from .chunking import chunk_document_law
        return chunk_document_law
    elif name == "indexer_main":
        from .indexer import main as indexer_main
        return indexer_main
    elif name == "export_main":
        from .export import main as export_main
        return export_main
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "preprocess_main",
    "chunk_document_general",
    "chunk_document_law",
    "indexer_main",
    "export_main"
]