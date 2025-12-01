
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Setup paths to ensure rag_system is importable
# Script is at /home/jovyan/work/reindex_script.py
# repo_root should be /home/jovyan/work
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from rag_system.config import RAGConfig
from rag_system.infrastructure.schema import init_hierarchical_schema, get_schema_info
from rag_system.common import LocalApiEmbeddings
from rag_system.application.indexing import EmbeddingService, IndexDocumentUseCase, BulkIndexUseCase
from rag_system.application.chunking import HierarchicalChunker
from rag_system.infrastructure.database import HierarchicalDocumentRepository, VectorStoreRepository

# Load config
load_dotenv()
config = RAGConfig.from_env()
config.validate()

print(f"Re-indexing with fixed chunking strategy...")

# Initialize components
doc_repo = HierarchicalDocumentRepository(config.conn_string)
vector_repo = VectorStoreRepository(config.conn_string, embedding_dimension=4096)
embed_model = LocalApiEmbeddings(
    api_base=config.embed_api_base,
    api_key=config.embed_api_key,
    model_name=config.embed_model,
    verify_ssl=config.verify_ssl,
)
embedding_service = EmbeddingService(embed_model)
chunker = HierarchicalChunker()

index_use_case = IndexDocumentUseCase(
    doc_repository=doc_repo,
    vector_repository=vector_repo,
    embedding_service=embedding_service,
    chunker=chunker,
)
bulk_index = BulkIndexUseCase(index_use_case)

# Define files to index
files = [
    repo_root / "data/converted_md/陸海空軍懲罰法.md",
    # Add others if needed
]

valid_files = [f for f in files if f.exists()]

if valid_files:
    print(f"Indexing {len(valid_files)} files...")
    bulk_index.execute(valid_files, force_reindex=True, skip_errors=False)
else:
    print(f"No files found to index. Checked: {[str(f) for f in files]}")
