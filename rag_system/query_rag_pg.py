#!/usr/bin/env python3
"""RAG query system using ReAct agent with LangGraph.

This is the CLI entry point for querying the RAG system.
The system uses a single ReAct agent node that handles:
- Collection routing (if no collection is specified)
- Document retrieval via tools
- Reasoning and evaluation
- Answer generation with citations
"""
import argparse
import os
import sys
import httpx
import logging

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from .common import log, set_quiet_mode
from .state import GraphState
from .config import RAGConfig, DEFAULT_TOP_K
from .tool import create_retrieve_tool, create_router_tool, create_metadata_search_tool
from .tool.calculator import create_calculator_tool
from .tool.shared import get_vectorstore
from .node import create_agent_node
from .agent import build_workflow


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


class RagApplication:
    """RAG application with ReAct agent."""

    def __init__(self, args: argparse.Namespace):
        """Initialize the RAG application."""
        self.args = args

        # Use the new llm_api_base, fallback to embed_api_base
        llm_base = getattr(args, 'llm_api_base', None) or args.embed_api_base

        if not all([self.args.conn, self.args.embed_api_base, llm_base, self.args.embed_api_key]):
            raise ValueError("Configuration error: Database connection, API keys, and base URLs for all models are required.")

        if not getattr(args, 'debug', False):
            self._setup_quiet_mode()
        else:
            # In debug mode, enable verbose logging for relevant libraries
            logging.basicConfig(level=logging.INFO)
            logging.getLogger("langchain").setLevel(logging.DEBUG)
            logging.getLogger("langgraph").setLevel(logging.DEBUG)
            logging.getLogger("rag_system").setLevel(logging.INFO)
            log("Debug mode enabled. Verbose logging is active.")

        self.llm = self._create_llm()

    def _setup_quiet_mode(self):
        """Disable verbose logging for clean user output."""
        set_quiet_mode(True)
        logging.getLogger().setLevel(logging.WARNING)

        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", message="SSL verification is disabled")

    def _create_llm(self) -> ChatOpenAI:
        """Create and configure the LLM client."""
        client = httpx.Client(
            verify=not self.args.no_verify_ssl,
            follow_redirects=True,
            timeout=httpx.Timeout(120.0, connect=10.0)
        )
        # Use the dedicated LLM API base if provided, otherwise fallback to the embedding base
        api_base = getattr(self.args, 'llm_api_base', None) or self.args.embed_api_base
        log(f"Initializing ChatOpenAI with API base: {api_base}")

        return ChatOpenAI(
            model=self.args.chat_model,
            openai_api_key=self.args.embed_api_key,
            openai_api_base=api_base,
            temperature=0,
            http_client=client
        )

    def build_graph(self):
        """Build the LangGraph workflow for legal document RAG.

        Creates a ReAct agent with tools for document retrieval,
        metadata search, and mathematical calculations.
        """
        # Get configurable parameters
        top_k = getattr(self.args, 'top_k', DEFAULT_TOP_K)
        content_max_length = getattr(self.args, 'content_max_length', 800)

        # Create tools for legal document retrieval and reasoning
        router_tool = create_router_tool(self.llm, self.args.conn)
        retrieve_tool = create_retrieve_tool(
            conn_str=self.args.conn,
            embed_api_base=self.args.embed_api_base,
            embed_api_key=self.args.embed_api_key,
            embed_model=self.args.embed_model,
            verify_ssl=not self.args.no_verify_ssl,
            top_k=top_k,
            content_max_length=content_max_length
        )
        metadata_search_tool = create_metadata_search_tool(
            conn_str=self.args.conn
        )
        calculator_tool = create_calculator_tool()

        # Combine all tools
        tools = [router_tool, retrieve_tool, metadata_search_tool, calculator_tool]

        # Create general agent node (direct entry point)
        general_agent_node = create_agent_node(self.llm, tools)

        # Build workflow
        return build_workflow(general_agent_node)

    def run(self):
        """Main entry point for the agent application."""
        graph = self.build_graph()

        def run_single_query(question: str):
            """Process a single query through the agent."""
            initial_state: GraphState = {"question": question, "generation": ""}
            try:
                # Invoke with increased recursion limit for complex ReAct reasoning
                # Complex DATCOM file generation may require extensive tool calls:
                # router → retrieve (multiple) → calculate → format → validate
                final_state = graph.invoke(
                    initial_state,
                    config={"recursion_limit": 100}
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
    parser.add_argument("--collection", default=None, help="(可選) 強制指定設計領域（如『空氣動力學』），繞過路由功能")
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

    args = parser.parse_args()

    # Handle retrieve-only mode separately
    if args.retrieve_only:
        if not all([args.conn, args.embed_api_base, args.embed_api_key, args.collection]):
             raise SystemExit("錯誤: retrieve-only 模式必須提供資料庫連接、API base/key 以及 collection")
        run_retrieve_only(args)
        return

    # For the main agent, if a design area is provided, we can inject it into the query
    # to save the agent a routing step.
    if args.collection and args.query:
        log(f"Design area '{args.collection}' is specified, injecting it into the query.")
        args.query = f"使用『{args.collection}』設計領域來回答這個問題: {args.query}"

    # Main application workflow
    try:
        app = RagApplication(args)
        app.run()
    except ValueError as e:
        raise SystemExit(e)

if __name__ == "__main__":
    main()