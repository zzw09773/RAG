# rag_system/tool/metadata_search.py
```python
"""Generic metadata-based search tool for precise document retrieval."""
import re
from typing import Callable, Dict, Any, Optional
from langchain.tools import tool
import psycopg2
from sqlalchemy import create_engine, text
from ..common import log


def create_metadata_search_tool(conn_str: str) -> Callable:
    """Create a generic metadata-based search tool.

    This tool performs exact matching on document metadata fields,
    avoiding the limitations of vector similarity search for structured data.

    Supports searching by:
    - Article number (第24條, article 24)
    - Page number (page 5, 第5頁)
    - Source filename
    - Custom metadata fields

    Args:
        conn_str: The database connection string.

    Returns:
        A tool function that can be used by the ReAct agent.
    """
    @tool
    def search_by_metadata(
        collection_name: str,
        query: str,
        article: str = "",
        page: str = "",
        source: str = ""
    ) -> str:
        """Search documents using exact metadata matching.

        This tool is ideal for queries that reference specific structural elements
        like article numbers, page numbers, or source files.

        Use cases:
        - "第24條的內容" → article="第24條"
        - "第5頁有什麼" → page=5
        - "陸海空軍懲罰法的第24條" → source="陸海空軍懲罰法.md", article="第24條"
        - "違反第10條會怎樣" → extract article number from query

        Args:
            collection_name: The collection to search in (required).
            query: Original query string for automatic metadata extraction (required).
            article: Exact article number to match (e.g., "第24條"). Leave empty for auto-extraction.
            page: Exact page number to match (e.g., "5"). Leave empty for no page filter.
            source: Exact or partial source filename to match (e.g., "懲罰法"). Leave empty for auto-extraction.

        Returns:
            Matching documents with metadata, or an error message.
        """
        log(f"Metadata search in '{collection_name}': article={article}, page={page}, source={source}, query={query}")

        # Auto-extract metadata from query if no explicit values provided
        extracted_metadata = {}
        if query and not any([article, page, source]):
            extracted_metadata = _extract_metadata_from_query(query)
            article = extracted_metadata.get('article', article or "")
            page_num = extracted_metadata.get('page', 0)
            page = str(page_num) if page_num else page or ""
            source = extracted_metadata.get('source', source or "")
            log(f"Auto-extracted metadata: {extracted_metadata}")

        # Build SQL filter conditions
        conditions = []
        params = {"collection_name": collection_name}

        if article and article != "":
            # Normalize article format
            article_normalized = _normalize_article_number(article)
            conditions.append("lpe.cmetadata->>'article' = :article")
            params["article"] = article_normalized

        if page and page != "":
            try:
                page_int = int(page)
                conditions.append("CAST(lpe.cmetadata->>'page' AS INTEGER) = :page")
                params["page"] = page_int
            except ValueError:
                pass  # Invalid page number, skip filter

        if source and source != "":
            # Support partial matching for source
            conditions.append("lpe.cmetadata->>'source' ILIKE :source")
            params["source"] = f"%{source}%"

        if not conditions:
            return "錯誤：必須至少提供一個搜尋條件 (article, page, 或 source)。"

        try:
            # Prefer hierarchical storage if exists
            clean_conn = conn_str.replace("postgresql+psycopg2://", "postgresql://")
            with psycopg2.connect(clean_conn) as conn:
                with conn.cursor() as cur:
                    sql = """
                        SELECT
                            dc.content,
                            dc.source_file,
                            dc.page_number,
                            dc.article_number,
                            dc.section_path
                        FROM rag_document_chunks dc
                        JOIN rag_documents d ON dc.document_id = d.id
                        WHERE d.title = %(collection_name)s
                    """
                    dyn_filters = []
                    if article:
                        dyn_filters.append("dc.article_number = %(article)s")
                    if page:
                        dyn_filters.append("dc.page_number = %(page)s")
                    if source:
                        dyn_filters.append("dc.source_file ILIKE %(source)s")

                    if dyn_filters:
                        sql += " AND " + " AND ".join(dyn_filters)
                    sql += " ORDER BY dc.depth, dc.section_path LIMIT 20"

                    cur.execute(sql, params)
                    rows = cur.fetchall()

            if not rows:
                criteria = ", ".join([
                    f"article={article}" if article else "",
                    f"page={page}" if page else "",
                    f"source={source}" if source else ""
                ]).strip(", ")
                log(f"No documents found with criteria: {criteria}")
                return f"在 '{collection_name}' 中找不到符合條件的文件 ({criteria})。"

            log(f"Found {len(rows)} document(s) matching criteria")

            # Format results
            result_parts = []
            for row in rows:
                content = row[0]
                doc_source = row[1]
                doc_page = row[2]
                doc_article = row[3]
                section_path = row[4]

                metadata_info = []
                if doc_article:
                    metadata_info.append(f"條文: {doc_article}")
                if doc_page:
                    metadata_info.append(f"頁碼: {doc_page}")
                if section_path:
                    metadata_info.append(f"節點: {section_path}")
                metadata_str = ", ".join(metadata_info) if metadata_info else "N/A"

                formatted = (
                    f"=== 文件 (來自 {collection_name}) ===\n"
                    f"來源: {doc_source}\n"
                    f"Metadata: {metadata_str}\n"
                    f"內容:\n{content}\n"
                )
                result_parts.append(formatted)

            return "\n---\n".join(result_parts)

        except Exception as e:
            error_msg = f"Metadata 搜尋時發生錯誤: {str(e)}"
            log(f"ERROR: {error_msg}")
            return error_msg

    return search_by_metadata


def _extract_metadata_from_query(query: str) -> Dict[str, Any]:
    """Extract metadata fields from natural language query.

    Args:
        query: Natural language query string.

    Returns:
        Dictionary with extracted metadata fields.
    """
    metadata = {}

    # Extract article number
    article_patterns = [
        r'第\s*(\d+)\s*條',  # 第24條, 第 24 條
        r'article\s*(\d+)',  # article 24
        r'art\.\s*(\d+)',    # art. 24
    ]
    for pattern in article_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            article_num = match.group(1)
            metadata['article'] = f"第 {article_num} 條"
            break

    # Extract page number
    page_patterns = [
        r'第\s*(\d+)\s*頁',  # 第5頁, 第 5 頁
        r'page\s*(\d+)',     # page 5
        r'p\.\s*(\d+)',      # p. 5
    ]
    for pattern in page_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            metadata['page'] = int(match.group(1))
            break

    # Extract source hints (common keywords)
    source_keywords = {
        '懲罰法': '陸海空軍懲罰法',
        '權益': '軍人權益',
        '無人機': '無人機',
        '飛行': '飛行',
    }
    for keyword, source_hint in source_keywords.items():
        if keyword in query:
            metadata['source'] = source_hint
            break

    return metadata


def _normalize_article_number(article: str) -> str:
    """Normalize article number to standard format.

    Args:
        article: Article number in various formats.

    Returns:
        Normalized article number (e.g., "第 24 條").
    """
    # Extract number from various formats
    patterns = [
        r'第?\s*(\d+)\s*條?',  # 第24條, 24條, 第24, 24
        r'article\s*(\d+)',    # article 24
        r'art\.\s*(\d+)',      # art. 24
        r'(\d+)',              # plain number
    ]

    for pattern in patterns:
        match = re.search(pattern, article, re.IGNORECASE)
        if match:
            num = match.group(1)
            return f"第 {num} 條"

    # If no match, return as-is (might be already normalized)
    return article
```
