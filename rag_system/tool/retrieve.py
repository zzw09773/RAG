"""Legal collection retrieval tool for the RAG assistant."""
from typing import Callable
from langchain.tools import tool
from .shared import get_vectorstore
from ..common import log
from ..config import DEFAULT_TOP_K, DEFAULT_CONTENT_MAX_LENGTH


def create_retrieve_tool(
    conn_str: str,
    embed_api_base: str,
    embed_api_key: str,
    embed_model: str,
    verify_ssl: bool,
    top_k: int = DEFAULT_TOP_K,
    content_max_length: int = DEFAULT_CONTENT_MAX_LENGTH
) -> Callable:
    """Create a flat legal document retrieval tool.

    Args:
        conn_str: Database connection string.
        embed_api_base: Embedding API base URL.
        embed_api_key: Embedding API key.
        embed_model: Embedding model name.
        verify_ssl: Whether to verify SSL certificates.
        top_k: Number of documents to retrieve.
        content_max_length: Maximum size of content per chunk.

    Returns:
        LangChain tool callable for ReAct agents.
    """
    @tool
    def retrieve_legal_documents(query: str, collection_name: str) -> str:
        """Search for relevant legal document chunks in a specific collection.

        This tool requires the caller to supply the collection name, typically
        obtained from the collection_router tool.

        Args:
            query: Natural language question.
            collection_name: Target collection to search.

        Returns:
            Formatted legal excerpts or an error message.
        """
        log(
            f"Retrieving legal documents for query: '{query}' in collection: '{collection_name}'"
        )

        try:
            vectorstore = get_vectorstore(
                connection_string=conn_str,
                collection_name=collection_name,
                api_base=embed_api_base,
                api_key=embed_api_key,
                embed_model=embed_model,
                verify_ssl=verify_ssl
            )

            documents = vectorstore.similarity_search(query, k=top_k)

            if not documents:
                log(f"No documents retrieved from collection '{collection_name}'")
                return (
                    f"在『{collection_name}』集合中找不到相關的法律文件內容。"
                    "請檢查問題或選擇其他集合。"
                )

            log(f"Retrieved {len(documents)} documents from '{collection_name}'")

            result_parts = []
            for i, doc in enumerate(documents, 1):
                source = doc.metadata.get('source', 'unknown')
                page = doc.metadata.get('page', '?')
                article = doc.metadata.get('article', '')
                section = doc.metadata.get('section', '')
                content = doc.page_content

                if len(content) > content_max_length:
                    content = content[:content_max_length] + "..."

                location = f"頁碼: {page}"
                if article:
                    location += f", 條文: {article}"
                if section:
                    location += f", 章節: {section}"

                formatted_doc = (
                    f"=== 文件 {i} (集合: {collection_name}) ===\n"
                    f"來源: {source}, {location}\n"
                    f"內容:\n{content}\n"
                )
                result_parts.append(formatted_doc)

            return "\n---\n".join(result_parts)

        except Exception as e:
            error_msg = f"從『{collection_name}』集合檢索文件時發生錯誤: {str(e)}"
            log(f"ERROR: {error_msg}")
            return error_msg

    return retrieve_legal_documents
