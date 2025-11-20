
import psycopg2
from typing import List
from ..common import log

def ensure_pgvector(conn_str: str):
    """Ensures the vector extension is created in the database."""
    try:
        # The psycopg2 driver doesn't need the 'postgresql+psycopg2' scheme.
        clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(clean_conn_str) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                log("Ensured 'vector' extension exists.")
    except psycopg2.Error as e:
        # It's better to log the specific error than to swallow it.
        # This might happen due to permissions, already existing, etc.
        log(f"Could not ensure vector extension: {e}")
    except Exception as e:
        log(f"An unexpected error occurred while ensuring vector extension: {e}")

def wipe_collection(conn_str: str, name: str):
    """Deletes all data associated with a specific collection name."""
    try:
        clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(clean_conn_str) as conn:
            with conn.cursor() as cur:
                # Find the collection UUID from its name.
                cur.execute("SELECT uuid FROM langchain_pg_collection WHERE name = %s;", (name,))
                collection_id = cur.fetchone()
                
                if collection_id:
                    # Delete embeddings associated with the collection.
                    cur.execute("DELETE FROM langchain_pg_embedding WHERE collection_id = %s;", (collection_id[0],))
                    # Delete the collection itself.
                    cur.execute("DELETE FROM langchain_pg_collection WHERE uuid = %s;", (collection_id[0],))
                    log(f"Successfully reset collection '{name}'.")
                else:
                    log(f"Collection '{name}' not found, no need to reset.")
    except psycopg2.Error as e:
        log(f"Database error while wiping collection '{name}': {e}")
    except Exception as e:
        log(f"An unexpected error occurred while wiping collection '{name}': {e}")

def get_collection_names(conn_str: str) -> List[str]:
    """Fetches the names of all existing collections from the database."""
    collections = []
    try:
        clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(clean_conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM langchain_pg_collection;")
                rows = cur.fetchall()
                collections = [row[0] for row in rows]
    except psycopg2.Error as e:
        log(f"Database error while fetching collection names: {e}")
    return collections

def get_collection_stats(conn_str: str) -> List[dict]:
    """Fetches statistics for all collections including document counts.

    Returns:
        List of dicts with 'name' and 'doc_count' keys
    """
    stats = []
    try:
        clean_conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(clean_conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.name, COUNT(e.id) as doc_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    GROUP BY c.name
                    ORDER BY doc_count DESC, c.name
                """)
                rows = cur.fetchall()
                stats = [{"name": name, "doc_count": count} for name, count in rows]
    except psycopg2.Error as e:
        log(f"Database error while fetching collection stats: {e}")
    return stats

def delete_all_collections(conn_str: str):
    """Deletes all langchain_pg collections from the database."""
    from langchain_postgres import PGVector
    from langchain_core.embeddings import FakeEmbeddings

    collection_names = get_collection_names(conn_str)
    if not collection_names:
        log("No collections found to delete.")
        return

    log(f"Found collections to delete: {collection_names}")
    
    # A dummy embedder is needed to instantiate PGVector for the drop method.
    dummy_embedder = FakeEmbeddings(size=1)

    for name in collection_names:
        try:
            store = PGVector(
                connection=conn_str,
                collection_name=name,
                embeddings=dummy_embedder,
            )
            store.delete_collection()
            log(f"Successfully deleted collection '{name}'.")
        except Exception as e:
            log(f"Error deleting collection '{name}': {e}")
    
    log("Finished deleting all collections.")
