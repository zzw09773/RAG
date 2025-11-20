#!/usr/bin/env python3
import argparse
import os
import sys
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
import httpx

import orjson
from dotenv import load_dotenv

# Lazy-load langchain components to speed up CLI responsiveness
try:
    from langchain_postgres import PGVector
except ImportError:
    PGVector = None

from ..common import LocalApiEmbeddings, log
from .db_utils import ensure_pgvector, wipe_collection, delete_all_collections
from .chunking import chunk_document_law, chunk_document_general
from .structure_detector import detect_document_structure

# --- Utility Functions ---

def dumps(obj) -> bytes:
    """Serializes an object to a formatted JSON byte string."""
    return orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)

def sha1(s: str) -> str:
    """Computes the SHA1 hash of a string."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def write_text_outputs(chunks: List[Dict], out_dir: Path, collection_name: str):
    """Writes the chunked text to a simple .txt file for inspection."""
    chunks_sorted = sorted(chunks, key=lambda c: (c.get("source", ""), c.get("article_chunk_seq", 0)))
    
    output_lines = []
    for c in chunks_sorted:
        source_name = Path(c['source']).name
        line = f"【{source_name} | Article: {c.get('article', 'N/A')}】\n{c['content']}\n"
        output_lines.append(line)
        
    (out_dir / f"{collection_name}_chunks.txt").write_text("\n".join(output_lines), encoding="utf-8")

# --- Core Logic: Indexer Class ---

class Indexer:
    """Encapsulates the logic for indexing a single document source."""
    def __init__(self, config: argparse.Namespace):
        self.config = config
        self.out_dir = Path(config.output_dir).resolve()
        self.embedder = None
        self.llm_client = None

        if config.embed:
            if not config.embed_api_base or not config.embed_api_key:
                raise ValueError("Embedding requires API base and key.")
            self.embedder = LocalApiEmbeddings(
                api_base=config.embed_api_base,
                api_key=config.embed_api_key,
                model_name=config.model,
                verify_ssl=not config.no_verify_ssl
            )

        # Initialize LLM for structure detection if enabled
        if config.use_llm_detection:
            self._init_llm_client()

    def run(self, doc_path: Path):
        """Runs the full indexing pipeline for a single document path."""
        collection_name = self.config.collection or doc_path.stem
        log(f"Processing {doc_path.name} -> collection '{collection_name}'")

        if self.config.reset_collection:
            wipe_collection(self.config.conn, collection_name)

        strategy = self._determine_split_strategy(doc_path)
        chunks = self._chunk_document(doc_path, strategy)
        if not chunks:
            log(f"No chunks generated for {doc_path.name}. Skipping.")
            return

        self._export_artifacts(chunks, collection_name)

        if self.config.embed and self.embedder:
            self._embed_and_store(chunks, collection_name)
        else:
            log(f"Skipping embedding for {collection_name}. Re-run with --embed to save.")

    def _init_llm_client(self):
        """Initialize LLM client for structure detection."""
        try:
            from langchain_openai import ChatOpenAI

            llm_api_base = self.config.llm_api_base or os.environ.get("LLM_API_BASE")
            llm_api_key = self.config.llm_api_key or os.environ.get("LLM_API_KEY")
            chat_model = self.config.chat_model or os.environ.get("CHAT_MODEL_NAME", "openai/gpt-oss-20b")

            if not llm_api_base or not llm_api_key:
                log("⚠ LLM detection enabled but missing API credentials, falling back to regex")
                return

            self.llm_client = ChatOpenAI(
                base_url=llm_api_base,
                api_key=llm_api_key,
                model=chat_model,
                temperature=0,  # Deterministic classification
                timeout=30.0,
                http_client=httpx.Client(verify=False)
            )
            log(f"✓ LLM client initialized: {chat_model}")

        except ImportError:
            log("⚠ langchain_openai not installed, LLM detection disabled")
        except Exception as e:
            log(f"⚠ LLM initialization failed: {e}")

    def _determine_split_strategy(self, doc_path: Path) -> str:
        """
        Intelligent structure detection using multiple layers:
        1. LLM classification (if enabled)
        2. Regex pattern matching
        3. Filename heuristic
        """
        strategy = detect_document_structure(
            doc_path=doc_path,
            llm_client=self.llm_client,
            use_llm=self.config.use_llm_detection
        )

        log(f"→ Selected strategy: '{strategy}'")
        return strategy

    def _chunk_document(self, doc_path: Path, strategy: str) -> List[Dict]:
        """Chunks a document based on the selected strategy."""
        if strategy == "law":
            chunks = chunk_document_law(doc_path, self.config.max_chars, self.config.overlap)
        else:
            chunks = chunk_document_general(doc_path, self.config.max_chars, self.config.overlap)
        log(f"  - {doc_path.name} -> {len(chunks)} chunks.")
        return chunks

    def _export_artifacts(self, chunks: List[Dict], collection_name: str):
        """Exports chunks to JSON and TXT files."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / f"{collection_name}_chunks.json").write_bytes(dumps(chunks))
        write_text_outputs(chunks, self.out_dir, collection_name)
        log(f"Exported {len(chunks)} chunks to {self.out_dir}")

    def _embed_and_store(self, chunks: List[Dict], collection_name: str):
        """Embeds chunks and stores them in the vector database."""
        if PGVector is None:
            raise ImportError("langchain_postgres is not installed. Cannot proceed with embedding.")
        
        log(f"Embedding chunks for {collection_name}...")
        try:
            vs = PGVector(embeddings=self.embedder, collection_name=collection_name, connection=self.config.conn)
            
            texts = [c["content"] for c in chunks]
            metadatas = [{k: v for k, v in c.items() if k != "content"} for c in chunks]
            ids = [sha1(f"{m.get('source')}|{m.get('article')}|{c['content']}") for c, m in zip(chunks, metadatas)]
            
            vs.add_texts(texts=texts, metadatas=metadatas, ids=ids)

            meta = {"collection": collection_name, "count": len(texts), "model": self.config.model}
            (self.out_dir / f"{collection_name}_meta.json").write_bytes(dumps(meta))
            log(f"✓ Collection '{collection_name}' created with {len(texts)} vectors.")
        except Exception as e:
            log(f"ERROR: Embedding failed for {collection_name}: {e}")
            log("Please check your embedding API server and .env configuration.")

# --- Main Execution ---

def get_argument_parser() -> argparse.ArgumentParser:
    """Creates and returns the argument parser for the script."""
    parser = argparse.ArgumentParser(description="Build a vector index from preprocessed Markdown files.")
    # File I/O
    parser.add_argument("--input_dir", default="rag_system/processed_md", help="Input directory with .md files.")
    parser.add_argument("--input_file", default=None, help="Path to a single input .md file. Overrides --input_dir.")
    parser.add_argument("--output_dir", default="rag_system/output", help="Output directory for chunk exports.")
    # DB and Collection
    parser.add_argument("--conn", default=os.environ.get("PGVECTOR_URL"), help="PostgreSQL connection string.")
    parser.add_argument("--collection", default=None, help="PGVector collection name. Defaults to input file stem if not set.")
    parser.add_argument("--reset_collection", action="store_true", help="Delete collection before building.")
    parser.add_argument("--delete_all", action="store_true", help="Delete ALL collections from the database and exit.")
    # Chunking
    parser.add_argument("--max_chars", type=int, default=800)
    parser.add_argument("--overlap", type=int, default=120)
    # Embedding
    parser.add_argument("--embed", action="store_true", help="Run the embedding process and save to database.")
    parser.add_argument("--model", default=os.environ.get("EMBED_MODEL_NAME", "nvidia/nv-embed-v2"), help="Embedding model name.")
    parser.add_argument("--embed_api_base", default=os.environ.get("EMBED_API_BASE"), help="Embedding API base URL.")
    parser.add_argument("--embed_api_key", default=os.environ.get("EMBED_API_KEY"), help="Embedding API key.")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL certificate verification.")

    # Structure detection
    parser.add_argument("--use-llm-detection", action="store_true", help="Use LLM to detect document structure (more accurate).")
    parser.add_argument("--llm_api_base", default=os.environ.get("LLM_API_BASE"), help="LLM API base URL for structure detection.")
    parser.add_argument("--llm_api_key", default=os.environ.get("LLM_API_KEY"), help="LLM API key.")
    parser.add_argument("--chat_model", default=os.environ.get("CHAT_MODEL_NAME"), help="Chat model for LLM detection.")

    return parser

def run_pipeline(args: argparse.Namespace):
    """Orchestrates the main indexing pipeline."""
    if not args.conn:
        raise SystemExit("Connection string not found. Use --conn or PGVECTOR_URL.")

    ensure_pgvector(args.conn)

    if args.delete_all:
        delete_all_collections(args.conn)
        sys.exit(0)

    md_files = []
    if args.input_file:
        p = Path(args.input_file)
        if not p.is_file(): raise SystemExit(f"Error: Input file not found at {p}")
        md_files = [p]
    else:
        in_dir = Path(args.input_dir).resolve()
        if not in_dir.is_dir(): raise SystemExit(f"Error: Input directory not found at {in_dir}")
        md_files = sorted(list(in_dir.glob("*.md")))
    
    if not md_files:
        log(f"No .md files found to process. Did you run preprocess.py first?")
        sys.exit(0)

    try:
        indexer = Indexer(args)
        for doc_path in md_files:
            indexer.run(doc_path)
    except (ValueError, ImportError) as e:
        raise SystemExit(f"Error: {e}")

    log("All tasks complete.")

def main():
    """Main entry point of the script."""
    load_dotenv()
    parser = get_argument_parser()
    args = parser.parse_args()
    run_pipeline(args)

if __name__ == "__main__":
    main()