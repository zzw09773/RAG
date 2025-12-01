# rag_system/domain/entities.py
```python
"""Domain entities for hierarchical RAG system.

Entities have identity and lifecycle. They represent core business concepts
with behavior and invariants.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

from .value_objects import ChunkId, DocumentId, HierarchyPath


class ChunkType(str, Enum):
    """Type of chunk based on its role in the hierarchy."""
    DOCUMENT = "document"       # Top-level document summary
    CHAPTER = "chapter"         # Chapter-level summary (第X章)
    ARTICLE = "article"         # Article-level summary (第X條)
    SECTION = "section"         # Section/item detail (第X款, 一、二、三、)
    DETAIL = "detail"           # Detailed content chunk


class IndexingLevel(str, Enum):
    """Determines which vector index(es) should contain this chunk."""
    SUMMARY = "summary"         # High-level concepts (doc, chapter summaries)
    DETAIL = "detail"           # Fine-grained content (articles, sections)
    BOTH = "both"              # Indexed in both layers (important articles)


@dataclass
class Chunk:
    """A hierarchical chunk of a legal document.

    Represents a portion of text with its position in the document hierarchy
    and relationships to other chunks.

    Invariants:
        - Root chunks (depth=0) must have parent_id=None
        - Non-root chunks must have parent_id set
        - section_path depth must match depth attribute
        - summary chunks are indexed in SUMMARY layer
        - detail chunks are indexed in DETAIL layer
    """
    id: ChunkId
    document_id: DocumentId
    content: str
    section_path: HierarchyPath
    chunk_type: ChunkType
    indexing_level: IndexingLevel

    # Hierarchy relationships
    parent_id: Optional[ChunkId] = None
    children_ids: List[ChunkId] = field(default_factory=list)

    # Metadata
    source_file: str = ""
    page_number: int = 1
    char_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Legal document specific
    article_number: Optional[str] = None  # e.g., "第24條"
    chapter_number: Optional[str] = None  # e.g., "第一章"

    def __post_init__(self):
        """Validate invariants after initialization."""
        self.char_count = len(self.content)
        self._validate_hierarchy_invariants()

    def _validate_hierarchy_invariants(self):
        """Ensure hierarchy relationships are consistent."""
        depth = self.section_path.depth

        # Root chunks must not have parent
        if depth == 0 and self.parent_id is not None:
            raise ValueError(f"Root chunk {self.id} cannot have a parent")

        # Non-root chunks must have parent
        if depth > 0 and self.parent_id is None:
            raise ValueError(f"Non-root chunk {self.id} at depth {depth} must have a parent")

    @property
    def depth(self) -> int:
        """Return the depth of this chunk in the hierarchy."""
        return self.section_path.depth

    @property
    def is_root(self) -> bool:
        """Check if this is a root-level chunk."""
        return self.depth == 0

    @property
    def has_children(self) -> bool:
        """Check if this chunk has children."""
        return len(self.children_ids) > 0

    def add_child(self, child_id: ChunkId):
        """Add a child chunk reference."""
        if child_id not in self.children_ids:
            self.children_ids.append(child_id)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "section_path": str(self.section_path),
            "chunk_type": self.chunk_type.value,
            "indexing_level": self.indexing_level.value,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "children_ids": [str(cid) for cid in self.children_ids],
            "source_file": self.source_file,
            "page_number": self.page_number,
            "char_count": self.char_count,
            "article_number": self.article_number,
            "chapter_number": self.chapter_number,
            "depth": self.depth,
        }


@dataclass
class Document:
    """Aggregate root for a legal document.

    Represents a complete legal document with its metadata and
    hierarchical chunk structure.

    Invariants:
        - Must have at least one chunk (the document root)
        - All chunks must belong to this document
        - Chunk hierarchy must form a valid tree
    """
    id: DocumentId
    title: str
    source_file: str
    chunks: List[Chunk] = field(default_factory=list)

    # Metadata
    total_chars: int = 0
    chunk_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Legal document specific
    law_category: Optional[str] = None  # e.g., "刑法", "民法"
    effective_date: Optional[datetime] = None
    version: Optional[str] = None

    def __post_init__(self):
        """Update computed fields."""
        self._update_statistics()

    def _update_statistics(self):
        """Recalculate document statistics."""
        self.chunk_count = len(self.chunks)
        self.total_chars = sum(chunk.char_count for chunk in self.chunks)

    def add_chunk(self, chunk: Chunk):
        """Add a chunk to this document.

        Args:
            chunk: Chunk to add

        Raises:
            ValueError: If chunk belongs to a different document
        """
        if chunk.document_id != self.id:
            raise ValueError(
                f"Chunk {chunk.id} belongs to document {chunk.document_id}, "
                f"not {self.id}"
            )

        self.chunks.append(chunk)
        self._update_statistics()
        self.updated_at = datetime.utcnow()

    def get_root_chunks(self) -> List[Chunk]:
        """Get all root-level chunks (depth=0)."""
        return [chunk for chunk in self.chunks if chunk.is_root]

    def get_chunks_by_type(self, chunk_type: ChunkType) -> List[Chunk]:
        """Get all chunks of a specific type."""
        return [chunk for chunk in self.chunks if chunk.chunk_type == chunk_type]

    def get_chunks_by_level(self, indexing_level: IndexingLevel) -> List[Chunk]:
        """Get all chunks for a specific indexing level."""
        return [
            chunk for chunk in self.chunks
            if chunk.indexing_level == indexing_level
            or chunk.indexing_level == IndexingLevel.BOTH
        ]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "title": self.title,
            "source_file": self.source_file,
            "total_chars": self.total_chars,
            "chunk_count": self.chunk_count,
            "law_category": self.law_category,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
```
