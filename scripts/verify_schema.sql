-- Verification SQL script for hierarchical RAG schema
-- Run this to verify the schema is correctly initialized

-- Check extensions
SELECT 'Extensions:' as check_type;
SELECT extname, extversion
FROM pg_extension
WHERE extname IN ('vector', 'ltree');

-- Check tables
SELECT '' as separator;
SELECT 'Tables:' as check_type;
SELECT tablename, schemaname
FROM pg_tables
WHERE tablename LIKE 'rag_%'
ORDER BY tablename;

-- Check table row counts
SELECT '' as separator;
SELECT 'Table Statistics:' as check_type;
SELECT
    'rag_documents' as table_name,
    COUNT(*) as row_count
FROM rag_documents
UNION ALL
SELECT
    'rag_document_chunks',
    COUNT(*)
FROM rag_document_chunks
UNION ALL
SELECT
    'rag_chunk_hierarchy',
    COUNT(*)
FROM rag_chunk_hierarchy
UNION ALL
SELECT
    'rag_chunk_embeddings_summary',
    COUNT(*)
FROM rag_chunk_embeddings_summary
UNION ALL
SELECT
    'rag_chunk_embeddings_detail',
    COUNT(*)
FROM rag_chunk_embeddings_detail;

-- Check indexes
SELECT '' as separator;
SELECT 'Indexes:' as check_type;
SELECT
    indexname,
    tablename
FROM pg_indexes
WHERE tablename LIKE 'rag_%'
  AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;
