"""
Document Structure Detection Module

Uses LLM to classify Chinese documents into law/regulation vs. general content.
Falls back to regex patterns when LLM is unavailable.
"""

import re
from pathlib import Path
from typing import Optional, Literal
from ..common import log

# ============================================================================
# REGEX PATTERNS FOR CHINESE REGULATIONS
# ============================================================================

# Core law article pattern: 第X條 (with various number formats)
_RE_LAW_ARTICLE = re.compile(
    r"第\s*[一二三四五六七八九十百千零〇○兩两0-9]+\s*條",
    re.MULTILINE
)

# Chapter/section markers: 第X章
_RE_CHAPTER = re.compile(
    r"第\s*[一二三四五六七八九十百千零〇○兩两0-9]+\s*章",
    re.MULTILINE
)

# Notice/guideline numbered items: 一、二、三、...
_RE_NUMBERED_ITEM = re.compile(
    r"^[一二三四五六七八九十百千]+、",
    re.MULTILINE
)

# Sub-items in parentheses: （一）（二）...
_RE_SUBITEM = re.compile(
    r"（[一二三四五六七八九十百千]+）",
    re.MULTILINE
)

# Legal/administrative keywords in title
_RE_LEGAL_KEYWORDS = re.compile(
    r"(法|條例|規則|辦法|要點|準則|綱要|標準|注意事項|作業|施行細則|規程|通則|律)",
    re.IGNORECASE
)

# ============================================================================
# LLM-BASED CLASSIFICATION
# ============================================================================

CLASSIFICATION_PROMPT = """你是文件結構分析專家。請判斷以下中文文件是否為法規/公文類型。

法規/公文的特徵：
- 包含「第X條」「第X章」等條款結構
- 使用「一、二、三、」或「（一）（二）」等項目編號
- 標題包含：法、條例、規則、辦法、要點、注意事項等關鍵字
- 正式、條列式的行政語言

一般文件的特徵：
- 敘述性段落為主
- 無明顯條款編號
- 學術論文、新聞報導、散文等

文件內容（前1000字）：
---
{preview}
---

請只回答一個字：
- 若為法規/公文類型，回答：是
- 若為一般文件，回答：否
"""

def classify_with_llm(content_preview: str, llm_client) -> Optional[Literal["law", "general"]]:
    """
    Use LLM to classify document structure.

    Args:
        content_preview: First 1000 chars of document
        llm_client: LangChain LLM instance (e.g. ChatOpenAI)

    Returns:
        "law" if regulation/official doc, "general" otherwise, None if failed
    """
    try:
        prompt = CLASSIFICATION_PROMPT.format(preview=content_preview[:1000])
        response = llm_client.invoke(prompt)
        answer = response.content.strip()

        if "是" in answer or "法規" in answer or "law" in answer.lower():
            log("✓ LLM classified as: law/regulation")
            return "law"
        else:
            log("✓ LLM classified as: general document")
            return "general"

    except Exception as e:
        log(f"⚠ LLM classification failed: {e}")
        return None

# ============================================================================
# REGEX-BASED DETECTION (FALLBACK)
# ============================================================================

def detect_structure_by_regex(content: str) -> Literal["law", "general"]:
    """
    Fallback structure detection using regex patterns.

    Returns:
        "law" if regulatory structure detected, "general" otherwise
    """
    # Count structural markers
    article_count = len(_RE_LAW_ARTICLE.findall(content[:3000]))
    chapter_count = len(_RE_CHAPTER.findall(content[:3000]))
    numbered_count = len(_RE_NUMBERED_ITEM.findall(content[:3000]))
    subitem_count = len(_RE_SUBITEM.findall(content[:3000]))

    # Decision logic: if ANY strong signal exists
    if article_count >= 2:  # At least 2 articles
        log(f"✓ Regex: Found {article_count} articles → law")
        return "law"

    if chapter_count >= 1:  # At least 1 chapter
        log(f"✓ Regex: Found {chapter_count} chapters → law")
        return "law"

    # Combination of numbered items + subitems (common in notices)
    if numbered_count >= 3 and subitem_count >= 2:
        log(f"✓ Regex: Found {numbered_count} items + {subitem_count} subitems → law")
        return "law"

    log("✗ Regex: No structural markers found → general")
    return "general"

# ============================================================================
# FILENAME-BASED HEURISTIC (LAST RESORT)
# ============================================================================

def detect_structure_by_filename(filename: str) -> Literal["law", "general"]:
    """
    Last-resort detection based on filename keywords.

    Returns:
        "law" if filename suggests regulation, "general" otherwise
    """
    if _RE_LEGAL_KEYWORDS.search(filename):
        log(f"✓ Filename contains legal keywords → law")
        return "law"

    log("✗ Filename has no legal keywords → general")
    return "general"

# ============================================================================
# UNIFIED DETECTION ENTRY POINT
# ============================================================================

def detect_document_structure(
    doc_path: Path,
    llm_client=None,
    use_llm: bool = True
) -> Literal["law", "general"]:
    """
    Comprehensive document structure detection with multiple fallback layers.

    Strategy priority:
    1. LLM classification (if available and enabled)
    2. Regex pattern detection
    3. Filename heuristic

    Args:
        doc_path: Path to document file
        llm_client: Optional LangChain LLM for classification
        use_llm: Whether to attempt LLM classification

    Returns:
        "law" for regulatory/official docs, "general" for others
    """
    log(f"Detecting structure for: {doc_path.name}")

    try:
        content = doc_path.read_text(encoding='utf-8')
    except Exception as e:
        log(f"⚠ Cannot read file: {e}, using filename only")
        return detect_structure_by_filename(doc_path.name)

    # Layer 1: LLM classification
    if use_llm and llm_client is not None:
        result = classify_with_llm(content, llm_client)
        if result is not None:
            return result

    # Layer 2: Regex pattern detection
    result = detect_structure_by_regex(content)
    if result == "law":
        return result

    # Layer 3: Filename heuristic (only if regex found nothing)
    log("→ Regex inconclusive, checking filename...")
    return detect_structure_by_filename(doc_path.name)
