# rag_system/tool/article_lookup.py
```python
"""Article-specific lookup tool using metadata filtering."""
import re
from typing import Callable
from langchain.tools import tool
from sqlalchemy import create_engine, text
from ..common import log


def create_article_lookup_tool(conn_str: str) -> Callable:
    """Create a tool for precise article number lookup using metadata filtering.

    This tool performs exact matching on article numbers in metadata,
    avoiding the limitations of vector similarity search for structured identifiers.

    Args:
        conn_str: The database connection string.

    Returns:
        A tool function that can be used by the ReAct agent.
    """
    @tool
    def lookup_article_by_number(query: str, collection_name: str) -> str:
        """Look up specific legal articles by their exact article number.

        Use this tool when the user asks about a SPECIFIC article number (e.g., "第24條", "Article 24").
        This tool performs exact matching on metadata, which is more reliable than vector search
        for structured identifiers like article numbers.

        Args:
            query: The query containing an article number (e.g., "第24條的內容", "違反第10條").
            collection_name: The collection to search in.

        Returns:
            The article content with metadata, or an error message.
        """
        log(f"Article lookup for query: '{query}' in collection: '{collection_name}'")

        # Extract article number using regex
        article_patterns = [
            r'第\s*(\d+)\s*條',  # Chinese format: 第24條, 第 24 條
            r'article\s*(\d+)',  # English format: article 24
            r'art\.\s*(\d+)',    # Abbreviated: art. 24
        ]

        article_num = None
        for pattern in article_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                article_num = match.group(1)
                break

        if not article_num:
            return "無法從查詢中識別出條文編號。請使用 retrieve_legal_documents 工具進行一般檢索。"

        # Format article number to match database format
        article_key = f"第 {article_num} 條"
        log(f"Looking up article: {article_key}")

        try:
            import psycopg2

            clean_conn = conn_str.replace("postgresql+psycopg2://", "postgresql://")
            with psycopg2.connect(clean_conn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            dc.content,
                            dc.source_file,
                            dc.page_number,
                            dc.article_number,
                            dc.section_path
                        FROM rag_document_chunks dc
                        JOIN rag_documents d ON dc.document_id = d.id
                        WHERE d.title = %s
                          AND dc.article_number = %s
                        ORDER BY dc.depth, dc.section_path
                        """,
                        (collection_name, article_key),
                    )
                    rows = cur.fetchall()

            if not rows:
                log(f"Article {article_key} not found in collection '{collection_name}'")
                return f"在 '{collection_name}' 中找不到 {article_key}。"

            log(f"Found {len(rows)} chunk(s) for article {article_key}")

            result_parts = []
            for row in rows:
                content, source, page, article, section_path = row
                formatted = (
                    f"=== {article} (來自 {collection_name}) ===\n"
                    f"來源: {source}, 頁碼: {page}, 節點: {section_path}\n"
                    f"內容:\n{content}\n"
                )
                result_parts.append(formatted)

            return "\n---\n".join(result_parts)

        except Exception as e:
            error_msg = f"查詢 {article_key} 時發生錯誤: {str(e)}"
            log(f"ERROR: {error_msg}")
            return error_msg

    return lookup_article_by_number
```
