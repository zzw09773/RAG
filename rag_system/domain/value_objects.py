"""Value objects for hierarchical RAG domain.

Value objects are immutable objects that represent domain concepts
through their attributes rather than identity.
"""
from dataclasses import dataclass
from typing import List
import hashlib


@dataclass(frozen=True)
class ChunkId:
    """Unique identifier for a chunk.

    Generated from a SHA-1 hash of source|section_path|content
    to ensure deterministic IDs across rebuilds.
    """
    value: str

    @classmethod
    def generate(cls, source: str, section_path: str, content: str) -> "ChunkId":
        """Generate a deterministic chunk ID from content."""
        key = f"{source}|{section_path}|{content[:100]}"
        chunk_id = hashlib.sha1(key.encode('utf-8')).hexdigest()
        return cls(value=chunk_id)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DocumentId:
    """Unique identifier for a document."""
    value: str

    @classmethod
    def from_filename(cls, filename: str) -> "DocumentId":
        """Generate document ID from filename."""
        # Remove extension and use as-is
        doc_id = filename.rsplit('.', 1)[0]
        return cls(value=doc_id)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class HierarchyPath:
    """Represents a hierarchical path in a legal document.

    Examples:
        - "第一章" (Chapter 1)
        - "第一章/第24條" (Chapter 1 / Article 24)
        - "第一章/第24條/第1款" (Chapter 1 / Article 24 / Section 1)
    """
    segments: tuple[str, ...]

    @classmethod
    def from_string(cls, path: str) -> "HierarchyPath":
        """Parse a path string into segments."""
        if not path:
            return cls(segments=())
        segments = tuple(path.split('/'))
        return cls(segments=segments)

    @classmethod
    def from_list(cls, segments: List[str]) -> "HierarchyPath":
        """Create from a list of segments."""
        return cls(segments=tuple(segments))

    def __str__(self) -> str:
        return '/'.join(self.segments)

    def __len__(self) -> int:
        """Return the depth of the path."""
        return len(self.segments)

    def parent(self) -> "HierarchyPath":
        """Get the parent path."""
        if len(self.segments) <= 1:
            return HierarchyPath(segments=())
        return HierarchyPath(segments=self.segments[:-1])

    def append(self, segment: str) -> "HierarchyPath":
        """Append a segment to create a child path."""
        return HierarchyPath(segments=self.segments + (segment,))

    @property
    def depth(self) -> int:
        """Return the depth level (0 for root)."""
        return len(self.segments)

    @property
    def is_root(self) -> bool:
        """Check if this is a root path."""
        return len(self.segments) == 0
