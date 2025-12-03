"""
RAG Service

A unified service for document indexing and retrieval using LangChain's ParentDocumentRetriever.
Replaces the previous over-engineered hierarchical chunking system.
"""
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import httpx

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_postgres.vectorstores import PGVector
from langchain.retrievers import ParentDocumentRetriever

# Standard imports for LangChain 0.3.0
from langchain.storage import LocalFileStore, EncoderBackedStore
# Note: In some 0.3.x versions, these might be in langchain.storage.file_system
# but langchain.storage usually re-exports them or provides backward compat.
# If this fails, we will need to be specific:
# from langchain.storage.file_system import LocalFileStore
# from langchain.storage.encoder_backed import EncoderBackedStore

from langchain_core.load import dumps, loads
import shutil

from .config import RAGConfig

logger = logging.getLogger(__name__)

class RAGService:
    """
    Unified RAG Service handling both Indexing and Retrieval.
    Wraps LangChain's ParentDocumentRetriever.
    """

    def __init__(self, config: RAGConfig):
        self.config = config
        self._init_components()

    def _init_components(self):
        """Initialize LangChain components."""
        
        # 0. Fix DB Connection String (psycopg2 compat)
        # LangChain PGVector uses psycopg3/sqlalchemy, but best to ensure standard postgresql:// format
        conn_str = self.config.conn_string
        if conn_str and "postgresql+psycopg2://" in conn_str:
            conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://")

        # 1. Embeddings with SSL Bypass
        # Use httpx client to control SSL verification if needed
        http_client = httpx.Client(verify=self.config.verify_ssl)
        
        self.embeddings = OpenAIEmbeddings(
            model=self.config.embed_model,
            openai_api_base=self.config.embed_api_base,
            openai_api_key=self.config.embed_api_key,
            check_embedding_ctx_length=False, # Disable check for custom models
            http_client=http_client,
            chunk_size=10 # Reduce batch size to avoid 504 Timeouts
        )

        # 2. Vector Store (for Child Chunks)
        # Using standard LangChain PGVector
        self.vectorstore = PGVector(
            embeddings=self.embeddings,
            collection_name=f"{self.config.default_collection}_vectors",
            connection=conn_str,
            use_jsonb=True,
        )

        # 3. Document Store (for Parent Chunks)
        # Using LocalFileStore BACKED by an Encoder (to handle Document objects)
        docstore_path = Path("./data/processed/docstore")
        docstore_path.mkdir(parents=True, exist_ok=True)
        
        # Define the raw byte store
        raw_store = LocalFileStore(str(docstore_path))
        
        # Wrap it with EncoderBackedStore using LangChain's serializer (dumps/loads)
        # This allows us to store Documents as JSON-like bytes
        def _dumps(x):
            return dumps(x).encode('utf-8')
            
        def _loads(x):
            return loads(x.decode('utf-8'))

        self.docstore = EncoderBackedStore(
            store=raw_store,
            key_encoder=lambda x: x, # Use ID as filename directly
            value_serializer=_dumps,
            value_deserializer=_loads
        )

        # 4. Text Splitters
        # Parent: Large chunks (preserve context)
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            separators=["\n第", "\n\n", "\n", "。", " ", ""]
        ) # Optimized for Chinese Law
        
        # Child: Small chunks (optimized for embedding search)
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, # Requested size
            chunk_overlap=100,
        )

        # 5. Retriever
        self.retriever = ParentDocumentRetriever(
            vectorstore=self.vectorstore,
            docstore=self.docstore,
            child_splitter=self.child_splitter,
            parent_splitter=self.parent_splitter,
            search_kwargs={"k": self.config.top_k}
        )

    def index_file(self, file_path: Path) -> int:
        """
        Index a single file.
        Returns number of parent chunks added.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Indexing file: {file_path.name}")
        
        try:
            # Read content
            content = file_path.read_text(encoding='utf-8')
            
            # Create generic Document
            doc = Document(
                page_content=content,
                metadata={
                    "source": file_path.name,
                    "file_path": str(file_path)
                }
            )

            # Add to retriever (handles splitting & storage)
            self.retriever.add_documents([doc], ids=None)
            
            logger.info(f"Successfully indexed {file_path.name}")
            return 1

        except Exception as e:
            logger.error(f"Failed to index {file_path.name}: {e}")
            raise

    def index_directory(self, dir_path: Path, pattern: str = "*.*") -> Dict[str, int]:
        """
        Index all files in a directory matching pattern.
        """
        results = {"success": 0, "failed": 0}
        
        files = list(dir_path.glob(pattern))
        logger.info(f"Found {len(files)} files in {dir_path}")

        for f in files:
            if f.is_file() and f.suffix.lower() in ['.txt', '.md', '.py', '.json']: # Basic filter
                try:
                    self.index_file(f)
                    results["success"] += 1
                except Exception as e:
                    logger.error(f"Error indexing {f.name}: {e}")
                    results["failed"] += 1
        
        return results

    def query(self, question: str) -> List[Document]:
        """
        Retrieve relevant documents for a question.
        Returns list of PARENT documents (full context).
        """
        logger.info(f"Querying: {question}")
        return self.retriever.invoke(question)

    def clear_index(self):
        """
        Clear all data from vectorstore and docstore.
        Warning: Destructive!
        """
        logger.warning("Clearing RAG index...")
        # Clear PGVector
        self.vectorstore.drop_tables() 
        self.vectorstore.create_tables_if_not_exists()
        
        # Clear FileStore
        docstore_path = Path("./data/processed/docstore")
        if docstore_path.exists():
            shutil.rmtree(docstore_path)
            docstore_path.mkdir()
            
        logger.info("Index cleared.")
