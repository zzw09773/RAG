"""Database schema for hierarchical RAG system.

Creates the new hierarchical tables alongside existing LangChain tables.
Uses PostgreSQL with pgvector extension and ltree for hierarchical paths.
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from ..common import log


# SQL for creating the hierarchical schema
HIERARCHICAL_SCHEMA_SQL = """
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS ltree;

-- Table 1: documents (aggregate root)
CREATE TABLE IF NOT EXISTS rag_documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_file TEXT NOT NULL UNIQUE,
    law_category TEXT,
    version TEXT,
    total_chars INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    effective_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Table 2: document_chunks (hierarchical chunks with ltree path)
CREATE TABLE IF NOT EXISTS rag_document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES rag_document_chunks(id) ON DELETE CASCADE,

    -- Content
    content TEXT NOT NULL,
    content_hash TEXT,
    char_count INTEGER NOT NULL,

    -- Hierarchy (using ltree for efficient tree operations)
    section_path LTREE NOT NULL,
    depth INTEGER NOT NULL,
    chunk_type TEXT NOT NULL CHECK (chunk_type IN ('document', 'chapter', 'article', 'section', 'detail')),
    indexing_level TEXT NOT NULL CHECK (indexing_level IN ('summary', 'detail', 'both')),

    -- Metadata
    source_file TEXT NOT NULL,
    page_number INTEGER DEFAULT 1,
    article_number TEXT,
    chapter_number TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Additional metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT depth_matches_path CHECK (depth = nlevel(section_path) - 1),
    CONSTRAINT root_no_parent CHECK ((depth = 0 AND parent_id IS NULL) OR depth > 0)
);

-- Table 3: chunk_hierarchy (closure table for fast ancestor/descendant queries)
-- This allows O(1) queries for "all descendants" or "all ancestors"
CREATE TABLE IF NOT EXISTS rag_chunk_hierarchy (
    ancestor_id TEXT NOT NULL REFERENCES rag_document_chunks(id) ON DELETE CASCADE,
    descendant_id TEXT NOT NULL REFERENCES rag_document_chunks(id) ON DELETE CASCADE,
    depth INTEGER NOT NULL CHECK (depth >= 0),
    PRIMARY KEY (ancestor_id, descendant_id)
);

-- Table 4: chunk_embeddings_summary (summary-level vectors)
CREATE TABLE IF NOT EXISTS rag_chunk_embeddings_summary (
    chunk_id TEXT PRIMARY KEY REFERENCES rag_document_chunks(id) ON DELETE CASCADE,
    embedding vector(4096),  -- nvidia/nv-embed-v2 produces 4096-dimensional vectors
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table 5: chunk_embeddings_detail (detail-level vectors)
CREATE TABLE IF NOT EXISTS rag_chunk_embeddings_detail (
    chunk_id TEXT PRIMARY KEY REFERENCES rag_document_chunks(id) ON DELETE CASCADE,
    embedding vector(4096),  -- nvidia/nv-embed-v2 produces 4096-dimensional vectors
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance

-- Document lookups
CREATE INDEX IF NOT EXISTS idx_documents_source_file ON rag_documents(source_file);
CREATE INDEX IF NOT EXISTS idx_documents_category ON rag_documents(law_category);

-- Chunk hierarchy and relationships
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON rag_document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent_id ON rag_document_chunks(parent_id);
CREATE INDEX IF NOT EXISTS idx_chunks_section_path ON rag_document_chunks USING GIST(section_path);
CREATE INDEX IF NOT EXISTS idx_chunks_depth ON rag_document_chunks(depth);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON rag_document_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_indexing_level ON rag_document_chunks(indexing_level);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_chunks_doc_depth ON rag_document_chunks(document_id, depth);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON rag_document_chunks(document_id, chunk_type);

-- Closure table indexes
CREATE INDEX IF NOT EXISTS idx_hierarchy_ancestor ON rag_chunk_hierarchy(ancestor_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_descendant ON rag_chunk_hierarchy(descendant_id);
CREATE INDEX IF NOT EXISTS idx_hierarchy_depth ON rag_chunk_hierarchy(depth);

-- Vector similarity search indexes
-- Note: Both HNSW and ivfflat have a 2000 dimension limit in pgvector
-- For 4096 dimensions, we skip creating vector indexes here
-- Similarity search will use sequential scan (slower but functional)
-- Future: Consider dimension reduction or upgrade to pgvector version with higher limits
-- CREATE INDEX IF NOT EXISTS idx_embeddings_summary_vector
--     ON rag_chunk_embeddings_summary
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
--
-- CREATE INDEX IF NOT EXISTS idx_embeddings_detail_vector
--     ON rag_chunk_embeddings_detail
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- JSONB indexes for metadata queries
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON rag_documents USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON rag_document_chunks USING GIN(metadata);

-- Trigger to update updated_at on documents
CREATE OR REPLACE FUNCTION update_document_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_document_timestamp ON rag_documents;

CREATE TRIGGER trigger_update_document_timestamp
    BEFORE UPDATE ON rag_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_document_updated_at();

-- View: chunk_with_ancestors (convenient for queries)
CREATE OR REPLACE VIEW chunk_with_ancestors AS
SELECT
    c.id,
    c.document_id,
    c.content,
    c.section_path,
    c.depth,
    c.chunk_type,
    ARRAY_AGG(h.ancestor_id ORDER BY h.depth DESC) FILTER (WHERE h.ancestor_id != c.id) as ancestor_ids
FROM rag_document_chunks c
LEFT JOIN rag_chunk_hierarchy h ON c.id = h.descendant_id
GROUP BY c.id, c.document_id, c.content, c.section_path, c.depth, c.chunk_type;
"""


def init_hierarchical_schema(conn_str: str) -> bool:
    """Initialize the hierarchical RAG database schema.

    Creates all tables, indexes, and views required for the hierarchical system.
    Safe to run multiple times (uses IF NOT EXISTS).

    Args:
        conn_str: PostgreSQL connection string

    Returns:
        True if successful, False otherwise
    """
    try:
        # Clean connection string for psycopg2
        clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")

        log("Initializing hierarchical RAG schema...")

        with psycopg2.connect(clean_conn_str) as conn:
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            with conn.cursor() as cur:
                # Execute schema creation
                cur.execute(HIERARCHICAL_SCHEMA_SQL)

        log("✓ Hierarchical schema initialized successfully")
        return True

    except Exception as e:
        log(f"✗ Error initializing schema: {e}")
        return False


def verify_schema(conn_str: str) -> dict:
    """Verify that the hierarchical schema is properly installed.

    Args:
        conn_str: PostgreSQL connection string

    Returns:
        Dict with verification results
    """
    clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")

    results = {
        "extensions": {},
        "tables": {},
        "indexes": {},
    }

    try:
        with psycopg2.connect(clean_conn_str) as conn:
            with conn.cursor() as cur:
                # Check extensions
                cur.execute("""
                    SELECT extname FROM pg_extension
                    WHERE extname IN ('vector', 'ltree')
                """)
                installed_extensions = {row[0] for row in cur.fetchall()}
                results["extensions"]["vector"] = "vector" in installed_extensions
                results["extensions"]["ltree"] = "ltree" in installed_extensions

                # Check tables
                expected_tables = [
                    "rag_documents",
                    "rag_document_chunks",
                    "rag_chunk_hierarchy",
                    "rag_chunk_embeddings_summary",
                    "rag_chunk_embeddings_detail",
                ]

                for table in expected_tables:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM pg_tables
                            WHERE tablename = %s
                        )
                    """, (table,))
                    results["tables"][table] = cur.fetchone()[0]

                # Check key indexes
                expected_indexes = [
                    "idx_chunks_section_path",
                    "idx_embeddings_summary_vector",
                    "idx_embeddings_detail_vector",
                ]

                for index in expected_indexes:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM pg_indexes
                            WHERE indexname = %s
                        )
                    """, (index,))
                    results["indexes"][index] = cur.fetchone()[0]

        return results

    except Exception as e:
        log(f"Error verifying schema: {e}")
        return results


def get_schema_info(conn_str: str) -> str:
    """Get human-readable schema information.

    Args:
        conn_str: PostgreSQL connection string

    Returns:
        Formatted string with schema info
    """
    results = verify_schema(conn_str)

    info = ["=== Hierarchical RAG Schema Status ===\n"]

    info.append("Extensions:")
    for ext, installed in results["extensions"].items():
        status = "✓" if installed else "✗"
        info.append(f"  {status} {ext}")

    info.append("\nTables:")
    for table, exists in results["tables"].items():
        status = "✓" if exists else "✗"
        info.append(f"  {status} {table}")

    info.append("\nKey Indexes:")
    for index, exists in results["indexes"].items():
        status = "✓" if exists else "✗"
        info.append(f"  {status} {index}")

    return "\n".join(info)
