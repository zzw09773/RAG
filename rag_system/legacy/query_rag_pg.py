#!/usr/bin/env python3
"""Legacy CLI entry point for the LangGraph-based legal RAG agent.

Notebooks (see notebooks/2_query_verify.ipynb) are now the primary
execution environment. This CLI remains for compatibility and automation.
"""
import argparse
import os
import sys
import logging

from dotenv import load_dotenv

from .common import log, set_quiet_mode
from .state import GraphState
from .config import RAGConfig, DEFAULT_TOP_K, DEFAULT_CONTENT_MAX_LENGTH
from .tool.shared import get_vectorstore
from .workflow import create_llm, create_rag_workflow

# Hierarchical RAG imports (optional, only needed if --hierarchical flag is used)
try:
    from .domain import DocumentId
    from .infrastructure.database import VectorStoreRepository
    from .application.retrieval import (
        HierarchicalRetrievalUseCase,
        SummaryFirstRetrievalStrategy,
    )
    HIERARCHICAL_AVAILABLE = True
except ImportError:
    HIERARCHICAL_AVAILABLE = False


def run_retrieve_only(args: argparse.Namespace):
    """Retrieve-only mode: return documents as JSON without LLM generation."""
    import orjson

    if not args.collection or not args.query:
        raise SystemExit("Retrieve-only mode requires --collection and --query.")

    log(f"Retrieve-only mode for query: '{args.query}' in collection '{args.collection}'")

    vectorstore = get_vectorstore(
        connection_string=args.conn,
        collection_name=args.collection,
        api_base=args.embed_api_base,
        api_key=args.embed_api_key,
        embed_model=args.embed_model,
        verify_ssl=not args.no_verify_ssl
    )
    top_k = getattr(args, 'top_k', DEFAULT_TOP_K)
    docs = vectorstore.similarity_search(args.query, k=top_k)

    docs_json = [doc.model_dump() for doc in docs]
    print(orjson.dumps(docs_json).decode('utf-8'))


def run_hierarchical_retrieve_only(args: argparse.Namespace):
    """Hierarchical retrieve-only mode: return hierarchical results as JSON."""
    import orjson

    if not HIERARCHICAL_AVAILABLE:
        raise SystemExit("Hierarchical RAG is not available. Make sure all required modules are installed.")

    if not args.query:
        raise SystemExit("Hierarchical retrieve-only mode requires --query.")

    log(f"Hierarchical retrieve-only mode for query: '{args.query}'")

    # Initialize hierarchical retrieval
    vector_repository = VectorStoreRepository(
        conn_str=args.conn,
        api_key=args.embed_api_key,
        embedding_dim=getattr(args, 'embedding_dim', 4096),
        verify_ssl=not args.no_verify_ssl,
    )

    summary_k = getattr(args, 'summary_k', 3)
    detail_k = getattr(args, 'detail_k', 3)

    retrieval_strategy = SummaryFirstRetrievalStrategy(
        vector_repository=vector_repository,
        summary_k=summary_k,
        detail_expansion_k=detail_k,
    )

    retrieval_use_case = HierarchicalRetrievalUseCase(strategy=retrieval_strategy)

    # Execute retrieval
    top_k = getattr(args, 'top_k', DEFAULT_TOP_K)
    document_id = DocumentId(args.document_id) if getattr(args, 'document_id', None) else None

    results = retrieval_use_case.execute(
        query=args.query,
        k=top_k,
        document_id=document_id,
    )

    # Convert to JSON-serializable format
    results_json = [
        {
            "chunk_id": str(r.chunk_id),
            "score": r.score,
            "content": r.content,
            "chunk_type": r.chunk_type,
            "indexing_level": r.indexing_level,
            "section_path": r.section_path,
            "source_file": r.source_file,
            "article_number": r.article_number,
            "chapter_number": r.chapter_number,
            "parent_content": r.parent_content,
            "children_count": len(r.children_contents),
            "siblings_count": len(r.sibling_contents),
        }
        for r in results
    ]

    print(orjson.dumps(results_json).decode('utf-8'))


class RagApplication:
    """Legacy CLI wrapper around the modular workflow helpers."""

    def __init__(self, args: argparse.Namespace):
        self.args = args

        if not getattr(args, 'debug', False):
            self._setup_quiet_mode()
        else:
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("langchain").setLevel(logging.DEBUG)
            logging.getLogger("langgraph").setLevel(logging.DEBUG)
            logging.getLogger("rag_system").setLevel(logging.INFO)
            log("Debug mode enabled. Verbose logging is active.")

        self.config = RAGConfig(
            top_k=getattr(args, 'top_k', DEFAULT_TOP_K),
            content_max_length=getattr(
                args,
                'content_max_length',
                DEFAULT_CONTENT_MAX_LENGTH,
            ),
            conn_string=args.conn,
            embed_api_base=args.embed_api_base,
            llm_api_base=getattr(args, 'llm_api_base', None) or args.embed_api_base,
            embed_api_key=args.embed_api_key,
            embed_model=args.embed_model,
            chat_model=args.chat_model,
            temperature=0,
            verify_ssl=not args.no_verify_ssl,
        )
        self.config.validate()

        self.llm = create_llm(self.config)
        self.workflow = create_rag_workflow(
            self.config,
            llm=self.llm,
            use_hierarchical=getattr(args, 'hierarchical', False),
        )

    def _setup_quiet_mode(self):
        """Disable verbose logging for clean user output."""
        set_quiet_mode(True)
        logging.getLogger().setLevel(logging.WARNING)

        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", message="SSL verification is disabled")

    def build_graph(self):
        """Return the pre-built workflow (for backward compatibility)."""
        return self.workflow

    def run(self):
        """Main entry point for the agent application."""
        graph = self.build_graph()

        def run_single_query(question: str):
            """Process a single query through the agent."""
            initial_state: GraphState = {
                "question": question,
                "generation": "",
                "messages": [("user", question)],
                "collection": self.args.collection or "",
                "retrieved_docs": [],
            }
            try:
                final_state = graph.invoke(
                    initial_state,
                    config={"recursion_limit": 80}
                )
                generation = final_state.get('generation', '')
                if generation:
                    print(f"\nFinal Answer:\n{generation}\n")
                else:
                    print("\nFinal Answer:\n找不到相關答案。\n")
            except Exception as e:
                log(f"ERROR during query processing: {e}")
                print(f"\nError: 處理查詢時發生錯誤: {str(e)}\n", file=sys.stderr)

        if self.args.query:
            run_single_query(self.args.query)
        else:
            print("進入互動模式 (按 Ctrl+C 離開)...")
            while True:
                try:
                    question = input("> ").strip()
                    if question:
                        run_single_query(question)
                except (EOFError, KeyboardInterrupt):
                    print("\n結束。")
                    break

def main():
    """CLI entry point."""
    load_dotenv()

    # --- Environment Variable Debugging ---
    print("--- ENV DEBUG ---")
    pg_url = os.environ.get("PGVECTOR_URL")
    embed_base = os.environ.get("EMBED_API_BASE")
    llm_base = os.environ.get("LLM_API_BASE")
    api_key = os.environ.get("EMBED_API_KEY")
    print(f"PGVECTOR_URL: {pg_url}")
    print(f"EMBED_API_BASE: {embed_base}")
    print(f"LLM_API_BASE: {llm_base or embed_base}") # Show fallback
    if api_key:
        print(f"EMBED_API_KEY: ...{api_key[-4:]}")
    else:
        print("EMBED_API_KEY: Not set")
    print("--- END ENV DEBUG ---")
    # --- End Debugging ---

    parser = argparse.ArgumentParser()

    # Connection and model args
    parser.add_argument("--conn", default=os.environ.get("PGVECTOR_URL"), help="PostgreSQL 連接字串")
    parser.add_argument("--collection", default=None, help="(可選) 強制指定法律文件集合名稱，繞過自動路由")
    parser.add_argument("--embed_model", default=os.environ.get("EMBED_MODEL_NAME", "nvidia/nv-embed-v2"), help="嵌入模型名稱")
    parser.add_argument("--chat_model", default=os.environ.get("CHAT_MODEL_NAME", "openai/gpt-oss-20b"), help="聊天模型名稱")
    parser.add_argument("--embed_api_base", default=os.environ.get("EMBED_API_BASE"), help="Embedding model API base URL")
    parser.add_argument("--llm_api_base", default=os.environ.get("LLM_API_BASE"), help="LLM/Chat model API base URL. Falls back to embed_api_base if not set.")
    parser.add_argument("--embed_api_key", default=os.environ.get("EMBED_API_KEY"), help="API key for both services")
    parser.add_argument("--no-verify-ssl", action="store_true", help="停用 SSL 憑證驗證")

    # Query options
    parser.add_argument("-q", "--query", default=None, help="工程師的技術問題（若未指定則進入互動模式）")
    parser.add_argument("--retrieve-only", action="store_true", help="只檢索文件並以 JSON 格式輸出，不生成答案")
    parser.add_argument("--debug", action="store_true", help="啟用除錯模式，顯示詳細日誌")

    # RAG configuration options
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help=f"檢索文件數量 (預設: {DEFAULT_TOP_K})")
    parser.add_argument("--content-max-length", type=int, default=800, help="文件內容最大長度 (預設: 800)")

    # Hierarchical RAG options
    parser.add_argument("--hierarchical", action="store_true", help="使用階層式 RAG 系統（需要先執行遷移）")
    parser.add_argument("--summary-k", type=int, default=3, help="階層式檢索：摘要層檢索數量 (預設: 3)")
    parser.add_argument("--detail-k", type=int, default=3, help="階層式檢索：每個摘要擴展的細節數量 (預設: 3)")
    parser.add_argument("--document-id", type=str, help="階層式檢索：限定特定文件 ID")
    parser.add_argument("--embedding-dim", type=int, default=4096, help="階層式檢索：向量維度 (預設: 4096)")

    args = parser.parse_args()

    print("⚠️ 這個 CLI 僅供相容與自動化腳本使用，建議改用 notebooks/2_query_verify.ipynb。")

    # Handle retrieve-only mode separately
    if args.retrieve_only:
        if args.hierarchical:
            # Hierarchical retrieve-only mode
            if not all([args.conn, args.embed_api_base, args.embed_api_key]):
                raise SystemExit("錯誤: hierarchical retrieve-only 模式必須提供資料庫連接和 API base/key")
            run_hierarchical_retrieve_only(args)
        else:
            # Flat retrieve-only mode
            if not all([args.conn, args.embed_api_base, args.embed_api_key, args.collection]):
                raise SystemExit("錯誤: retrieve-only 模式必須提供資料庫連接、API base/key 以及 collection")
            run_retrieve_only(args)
        return

    if getattr(args, 'hierarchical', False):
        log("⚠ Warning: Hierarchical mode with LangGraph agent is experimental. Use scripts/query_hierarchical.py for full control.")

    # Main application workflow
    try:
        app = RagApplication(args)
        app.run()
    except ValueError as e:
        raise SystemExit(e)

if __name__ == "__main__":
    main()