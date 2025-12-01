"""Repository implementations for hierarchical RAG system.

Implements data access layer using Repository pattern.
All database operations are encapsulated here.
"""
from typing import List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor, Json
import numpy as np

from ..domain import Document, Chunk, ChunkId, DocumentId, HierarchyPath
from ..domain import ChunkType, IndexingLevel
from ..common import log


class HierarchicalDocumentRepository:
    """Repository for managing hierarchical documents and chunks.

    Handles CRUD operations for documents and their chunk hierarchies.
    """

    def __init__(self, conn_str: str):
        """Initialize repository.

        Args:
            conn_str: PostgreSQL connection string
        """
        self.conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")

    def _get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self.conn_str)

    def save_document(self, document: Document) -> bool:
        """Save or update a document (without chunks).

        Args:
            document: Document entity to save

        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO rag_documents (
                            id, title, source_file, law_category, version,
                            total_chars, chunk_count, effective_date, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            law_category = EXCLUDED.law_category,
                            version = EXCLUDED.version,
                            total_chars = EXCLUDED.total_chars,
                            chunk_count = EXCLUDED.chunk_count,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        str(document.id),
                        document.title,
                        document.source_file,
                        document.law_category,
                        document.version,
                        document.total_chars,
                        document.chunk_count,
                        document.effective_date,
                        Json({})  # metadata JSONB
                    ))
                conn.commit()
            return True
        except Exception as e:
            log(f"Error saving document {document.id}: {e}")
            return False

    def _sanitize_ltree_path(self, path_str: str, depth: int) -> str:
        """Sanitize path for ltree compatibility.

        ltree labels must consist of alphanumeric characters and underscores only.
        The resulting path must have (depth + 1) levels to satisfy the constraint:
        depth = nlevel(section_path) - 1

        Args:
            path_str: Original path string
            depth: Expected depth

        Returns:
            ltree-compatible path with correct number of levels
        """
        import re
        import hashlib

        # For root (depth=0), return single-level path
        if not path_str or depth == 0:
            return 'root'

        # Split by / to get segments
        segments = path_str.split('/')
        sanitized_segments = ['root']  # Always start with root

        for seg in segments:
            if not seg:  # Skip empty segments
                continue

            # Remove or replace non-alphanumeric chars
            # Keep Chinese content but hash it to ASCII-safe format
            if any(ord(c) > 127 for c in seg):  # Has non-ASCII
                # Create a hash-based label
                seg_hash = hashlib.md5(seg.encode('utf-8')).hexdigest()[:8]
                sanitized_segments.append(f'seg_{seg_hash}')
            else:
                # Remove spaces and special chars, keep alphanumeric and underscore
                sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', seg)
                sanitized_segments.append(sanitized or 'empty')

        result = '.'.join(sanitized_segments)

        # Verify nlevel matches depth + 1
        expected_levels = depth + 1
        actual_levels = len(sanitized_segments)

        if actual_levels != expected_levels:
            log(f"Warning: ltree path level mismatch. Expected {expected_levels}, got {actual_levels}. Path: {result}")

        return result

    def save_chunk(self, chunk: Chunk) -> bool:
        """Save a single chunk.

        Args:
            chunk: Chunk entity to save

        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Convert HierarchyPath to ltree format
                    ltree_path = self._sanitize_ltree_path(str(chunk.section_path), chunk.depth)

                    cur.execute("""
                        INSERT INTO rag_document_chunks (
                            id, document_id, parent_id, content, char_count,
                            section_path, depth, chunk_type, indexing_level,
                            source_file, page_number, article_number, chapter_number,
                            metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s::ltree, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            section_path = EXCLUDED.section_path,
                            depth = EXCLUDED.depth
                    """, (
                        str(chunk.id),
                        str(chunk.document_id),
                        str(chunk.parent_id) if chunk.parent_id else None,
                        chunk.content,
                        chunk.char_count,
                        ltree_path,
                        chunk.depth,
                        chunk.chunk_type.value,
                        chunk.indexing_level.value,
                        chunk.source_file,
                        chunk.page_number,
                        chunk.article_number,
                        chunk.chapter_number,
                        Json({})  # metadata JSONB
                    ))
                conn.commit()
            return True
        except Exception as e:
            log(f"Error saving chunk {chunk.id}: {e}")
            return False

    def save_chunks_batch(self, chunks: List[Chunk]) -> bool:
        """Save multiple chunks efficiently.

        Args:
            chunks: List of chunks to save

        Returns:
            True if successful
        """
        if not chunks:
            return True

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Prepare data for batch insert
                    chunk_data = []
                    for chunk in chunks:
                        ltree_path = self._sanitize_ltree_path(str(chunk.section_path), chunk.depth)

                        chunk_data.append((
                            str(chunk.id),
                            str(chunk.document_id),
                            str(chunk.parent_id) if chunk.parent_id else None,
                            chunk.content,
                            chunk.char_count,
                            ltree_path,
                            chunk.depth,
                            chunk.chunk_type.value,
                            chunk.indexing_level.value,
                            chunk.source_file,
                            chunk.page_number,
                            chunk.article_number,
                            chunk.chapter_number,
                            Json({})  # metadata JSONB
                        ))

                    # Batch insert with ON CONFLICT
                    execute_values(
                        cur,
                        """
                        INSERT INTO rag_document_chunks (
                            id, document_id, parent_id, content, char_count,
                            section_path, depth, chunk_type, indexing_level,
                            source_file, page_number, article_number, chapter_number,
                            metadata
                        ) VALUES %s
                        ON CONFLICT (id) DO NOTHING
                        """,
                        chunk_data,
                        template="(%s, %s, %s, %s, %s, %s::ltree, %s, %s, %s, %s, %s, %s, %s, %s)"
                    )

                conn.commit()
            return True
        except Exception as e:
            log(f"Error saving chunks batch: {e}")
            return False

    def build_closure_table(self, document_id: DocumentId) -> bool:
        """Build the closure table for a document's chunk hierarchy.

        This populates rag_chunk_hierarchy with all ancestor-descendant pairs.
        Must be called after all chunks are inserted.

        Args:
            document_id: Document to build closure table for

        Returns:
            True if successful
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Delete existing entries for this document
                    cur.execute("""
                        DELETE FROM rag_chunk_hierarchy
                        WHERE ancestor_id IN (
                            SELECT id FROM rag_document_chunks WHERE document_id = %s
                        )
                    """, (str(document_id),))

                    # Build closure table using ltree path queries
                    # For each chunk, find all its ancestors using ltree operators
                    cur.execute("""
                        INSERT INTO rag_chunk_hierarchy (ancestor_id, descendant_id, depth)
                        SELECT
                            ancestor.id as ancestor_id,
                            descendant.id as descendant_id,
                            (nlevel(descendant.section_path) - nlevel(ancestor.section_path)) as depth
                        FROM rag_document_chunks descendant
                        CROSS JOIN rag_document_chunks ancestor
                        WHERE
                            descendant.document_id = %s
                            AND ancestor.document_id = %s
                            AND descendant.section_path <@ ancestor.section_path
                    """, (str(document_id), str(document_id)))

                conn.commit()
            return True
        except Exception as e:
            log(f"Error building closure table for {document_id}: {e}")
            return False

    def get_document(self, document_id: DocumentId) -> Optional[Document]:
        """Retrieve a document by ID (without chunks).

        Args:
            document_id: Document ID

        Returns:
            Document entity or None if not found
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM rag_documents WHERE id = %s
                    """, (str(document_id),))

                    row = cur.fetchone()
                    if not row:
                        return None

                    return Document(
                        id=DocumentId(value=row['id']),
                        title=row['title'],
                        source_file=row['source_file'],
                        law_category=row['law_category'],
                        version=row['version'],
                        total_chars=row['total_chars'],
                        chunk_count=row['chunk_count'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at'],
                        effective_date=row.get('effective_date'),
                    )
        except Exception as e:
            log(f"Error retrieving document {document_id}: {e}")
            return None

    def get_chunk_by_id(self, chunk_id: ChunkId) -> Optional[Chunk]:
        """Retrieve a chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk entity or None if not found
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM rag_document_chunks WHERE id = %s
                    """, (str(chunk_id),))

                    row = cur.fetchone()
                    if not row:
                        return None

                    return self._row_to_chunk(row)
        except Exception as e:
            log(f"Error retrieving chunk {chunk_id}: {e}")
            return None

    def get_ancestors(self, chunk_id: ChunkId, max_depth: Optional[int] = None) -> List[Chunk]:
        """Get all ancestor chunks of a given chunk.

        Args:
            chunk_id: Chunk to get ancestors for
            max_depth: Optional maximum depth to traverse (None = all)

        Returns:
            List of ancestor chunks, ordered from immediate parent to root
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    depth_filter = f"AND h.depth <= {max_depth}" if max_depth else ""

                    cur.execute(f"""
                        SELECT c.*
                        FROM rag_chunk_hierarchy h
                        JOIN rag_document_chunks c ON h.ancestor_id = c.id
                        WHERE h.descendant_id = %s
                          AND h.ancestor_id != %s
                          {depth_filter}
                        ORDER BY h.depth ASC
                    """, (str(chunk_id), str(chunk_id)))

                    return [self._row_to_chunk(row) for row in cur.fetchall()]
        except Exception as e:
            log(f"Error retrieving ancestors for {chunk_id}: {e}")
            return []

    def get_children(self, chunk_id: ChunkId) -> List[Chunk]:
        """Get immediate children of a chunk.

        Args:
            chunk_id: Parent chunk ID

        Returns:
            List of child chunks
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM rag_document_chunks
                        WHERE parent_id = %s
                        ORDER BY section_path
                    """, (str(chunk_id),))

                    return [self._row_to_chunk(row) for row in cur.fetchall()]
        except Exception as e:
            log(f"Error retrieving children for {chunk_id}: {e}")
            return []

    def _row_to_chunk(self, row: dict) -> Chunk:
        """Convert database row to Chunk entity."""
        # Convert ltree path back to HierarchyPath
        ltree_path = row['section_path']
        if ltree_path == 'root':
            section_path = HierarchyPath(segments=())
        else:
            section_path = HierarchyPath.from_string(ltree_path.replace('.', '/'))

        return Chunk(
            id=ChunkId(value=row['id']),
            document_id=DocumentId(value=row['document_id']),
            content=row['content'],
            section_path=section_path,
            chunk_type=ChunkType(row['chunk_type']),
            indexing_level=IndexingLevel(row['indexing_level']),
            parent_id=ChunkId(value=row['parent_id']) if row['parent_id'] else None,
            source_file=row['source_file'],
            page_number=row['page_number'],
            char_count=row['char_count'],
            article_number=row['article_number'],
            chapter_number=row['chapter_number'],
            created_at=row['created_at'],
        )


class VectorStoreRepository:
    """Repository for managing chunk embeddings.

    Handles vector storage and similarity search operations.
    """

    def __init__(self, conn_str: str, embedding_dimension: int = 1024):
        """Initialize repository.

        Args:
            conn_str: PostgreSQL connection string
            embedding_dimension: Dimension of embedding vectors
        """
        self.conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
        self.embedding_dimension = embedding_dimension

    def _get_connection(self):
        """Get a database connection."""
        return psycopg2.connect(self.conn_str)

    def save_embedding(
        self,
        chunk_id: ChunkId,
        embedding: np.ndarray,
        level: IndexingLevel
    ) -> bool:
        """Save an embedding vector for a chunk.

        Args:
            chunk_id: Chunk ID
            embedding: Embedding vector
            level: Indexing level (summary or detail)

        Returns:
            True if successful
        """
        if level not in [IndexingLevel.SUMMARY, IndexingLevel.DETAIL]:
            raise ValueError(f"Level must be SUMMARY or DETAIL, got {level}")

        table = "rag_chunk_embeddings_summary" if level == IndexingLevel.SUMMARY else "rag_chunk_embeddings_detail"

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        INSERT INTO {table} (chunk_id, embedding)
                        VALUES (%s, %s)
                        ON CONFLICT (chunk_id) DO UPDATE
                        SET embedding = EXCLUDED.embedding
                    """, (str(chunk_id), embedding.tolist()))
                conn.commit()
            return True
        except Exception as e:
            log(f"Error saving embedding for {chunk_id} at {level}: {e}")
            return False

    def similarity_search(
        self,
        query_embedding: np.ndarray,
        level: IndexingLevel,
        k: int = 5,
        document_id: Optional[DocumentId] = None
    ) -> List[Tuple[ChunkId, float]]:
        """Perform similarity search.

        Args:
            query_embedding: Query vector
            level: Which index to search (SUMMARY or DETAIL)
            k: Number of results
            document_id: Optional filter by document

        Returns:
            List of (chunk_id, similarity_score) tuples
        """
        if level not in [IndexingLevel.SUMMARY, IndexingLevel.DETAIL]:
            raise ValueError(f"Level must be SUMMARY or DETAIL, got {level}")

        table = "rag_chunk_embeddings_summary" if level == IndexingLevel.SUMMARY else "rag_chunk_embeddings_detail"

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    if document_id:
                        cur.execute(f"""
                            SELECT e.chunk_id, (1 - (e.embedding <=> %s::vector)) as similarity
                            FROM {table} e
                            JOIN rag_document_chunks c ON e.chunk_id = c.id
                            WHERE c.document_id = %s
                            ORDER BY e.embedding <=> %s::vector
                            LIMIT %s
                        """, (query_embedding.tolist(), str(document_id), query_embedding.tolist(), k))
                    else:
                        cur.execute(f"""
                            SELECT chunk_id, (1 - (embedding <=> %s::vector)) as similarity
                            FROM {table}
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s
                        """, (query_embedding.tolist(), query_embedding.tolist(), k))

                    results = [(ChunkId(value=row[0]), float(row[1])) for row in cur.fetchall()]
                    return results
        except Exception as e:
            log(f"Error in similarity search: {e}")
            return []
