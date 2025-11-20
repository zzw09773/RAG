"""Collection routing tool for the legal RAG assistant."""
from typing import Callable
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from ..common import log
from ..build.db_utils import get_collection_stats

ROUTER_PROMPT_TEMPLATE = """You are an expert router for legal document collections. Based on the user's question and the available collections, choose the single best collection to search.

使用者問題: "{query}"

可用的法律文件集合與文件數:
{collections_info}

規則:
1. 優先選擇資料量 > 0 的集合
2. 多個集合都有資料時，挑選最相關者
3. 若皆為空集合，回傳文件數最多的集合名稱
4. 僅回傳集合名稱（繁體中文），勿加其他文字
"""

def create_router_tool(llm: ChatOpenAI, conn_str: str) -> Callable:
    """Create a legal collection routing tool.

    Args:
        llm: Language model used to score relevance across collections.
        conn_str: Database connection string.

    Returns:
        LangChain tool callable that selects an appropriate collection.
    """
    @tool
    def collection_router(query: str) -> str:
        """Select the most relevant legal document collection for a query.

        Use this tool first to decide which collection the retrieval tools
        should target.

        Args:
            query: Original user question.

        Returns:
            Name of the best-matching collection or an error message.
        """
        log(f"Routing legal query: '{query}'")

        try:
            stats = get_collection_stats(conn_str)
            if not stats:
                log("No collections found in the database.")
                return "錯誤: 尚未建立任何法律文件集合，請先執行索引。"

            log(f"Found collections with stats: {stats}")
            non_empty = [s for s in stats if s['doc_count'] > 0]

            if not non_empty:
                log("All collections are empty. Returning error.")
                return "錯誤: 所有法律文件集合目前皆為空，請先匯入文件。"

            collections_info = "\n".join(
                f"- {s['name']} ({s['doc_count']} 筆向量)"
                for s in stats
            )

            prompt = ROUTER_PROMPT_TEMPLATE.format(
                query=query,
                collections_info=collections_info
            )

            response = llm.invoke(prompt)
            selected_collection = response.content.strip()

            collection_names = [s['name'] for s in stats]
            if selected_collection in collection_names:
                log(f"Router selected collection: '{selected_collection}'")
                return selected_collection

            log(
                f"Router returned invalid collection '{selected_collection}'. Falling back to most populated collection."
            )
            return non_empty[0]['name']

        except Exception as e:
            error_msg = f"集合路由時發生錯誤: {str(e)}"
            log(f"ERROR: {error_msg}")
            return error_msg

    return collection_router
