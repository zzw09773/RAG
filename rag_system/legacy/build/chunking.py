
import re
import uuid
from pathlib import Path
from typing import List, Dict

from langchain.text_splitter import RecursiveCharacterTextSplitter, TextSplitter

from ..common import log

# Regex patterns for different Chinese legal document structures
# Exclude placeholder patterns like 第○○條, 第○條 (used in examples)
_RE_ARTICLE = re.compile(r"^(第\s*[一二三四五六七八九十百千零兩两0-9]+\s*條)", re.MULTILINE)  # 第X條 at line start, exclude ○
_RE_CHAPTER = re.compile(r"^(第\s*[一二三四五六七八九十百千零〇○兩两0-9]+\s*章)", re.MULTILINE)  # 第X章 at line start
_RE_NUMBERED_ITEM = re.compile(r"^([一二三四五六七八九十百千]+、)", re.MULTILINE)  # 一、二、
_RE_SUBITEM = re.compile(r"^(（[一二三四五六七八九十百千]+）)", re.MULTILINE)  # （一）（二）

# Basic text cleaning regex
_RE_MULTI_SPACE = re.compile(r"[ \t\u3000]+")
_RE_MULTI_NL = re.compile(r"\n{3,}")

# LaTeX math expression patterns (protect these from cleaning)
_RE_LATEX_DISPLAY = re.compile(r'\$\$[^$]+?\$\$', re.DOTALL)  # Display math: $$...$$
_RE_LATEX_INLINE = re.compile(r'\$[^$\n]+?\$')  # Inline math: $...$

def clean_text(s: str) -> str:
    """
    Basic cleaning: collapses whitespace and normalizes newlines.
    Preserves LaTeX math expressions ($...$ and $$...$$).
    """
    # Step 1: Extract and replace LaTeX expressions with placeholders
    latex_blocks = []
    def save_latex(match):
        latex_blocks.append(match.group(0))
        return f"__LATEX_{len(latex_blocks)-1}__"

    # Protect display math first (to avoid conflicts with inline math)
    s = _RE_LATEX_DISPLAY.sub(save_latex, s)
    s = _RE_LATEX_INLINE.sub(save_latex, s)

    # Step 2: Apply standard text cleaning
    s = s.replace("\r", "").strip()
    s = _RE_MULTI_SPACE.sub(" ", s)
    s = _RE_MULTI_NL.sub("\n\n", s)

    # Step 3: Restore LaTeX expressions
    for i, block in enumerate(latex_blocks):
        s = s.replace(f"__LATEX_{i}__", block)

    return s

def get_law_text_splitter(max_chars: int, overlap: int) -> TextSplitter:
    """Returns a text splitter suitable for splitting content within a law article."""
    return RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],  # Split by paragraph first
    )

def chunk_document_law(doc_path: Path, max_chars: int, overlap: int) -> List[Dict]:
    """
    Splits a preprocessed Markdown file based on Chinese legal document structures.

    Supports multiple marker types with priority:
    1. 第X條 (articles) - highest priority
    2. 第X章 (chapters) - medium priority
    3. 一、二、三、 (numbered items) - for notices/guidelines
    """
    log(f"  - Splitting {doc_path.name} with 'law' strategy...")
    try:
        full_text = doc_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        log(f"    - ERROR: File not found: {doc_path}")
        return []

    # Try different marker types in priority order
    article_spans = list(_RE_ARTICLE.finditer(full_text))
    if article_spans:
        log(f"    - Found {len(article_spans)} '第X條' markers")
        return _chunk_by_markers(full_text, article_spans, doc_path.name, max_chars, overlap, "article")

    chapter_spans = list(_RE_CHAPTER.finditer(full_text))
    if chapter_spans:
        log(f"    - Found {len(chapter_spans)} '第X章' markers, using as primary structure")
        # Also detect numbered items within chapters
        return _chunk_by_chapters_with_items(full_text, chapter_spans, doc_path.name, max_chars, overlap)

    numbered_spans = list(_RE_NUMBERED_ITEM.finditer(full_text))
    if numbered_spans:
        log(f"    - Found {len(numbered_spans)} '一、' style markers")
        return _chunk_by_markers(full_text, numbered_spans, doc_path.name, max_chars, overlap, "item")

    log(f"    - No structural markers found in {doc_path.name}. Falling back to general splitting.")
    return chunk_document_general(doc_path, max_chars, overlap)

def _chunk_by_markers(full_text: str, markers: List, source_name: str, max_chars: int, overlap: int, marker_type: str) -> List[Dict]:
    """
    Generic chunking function for any type of structural markers.

    Args:
        full_text: Full document text
        markers: List of regex match objects
        source_name: Document filename
        max_chars: Maximum characters per chunk
        overlap: Overlap between chunks
        marker_type: Type of marker ("article", "chapter", "item")
    """
    chunks = []
    text_splitter = get_law_text_splitter(max_chars, overlap)

    for i, match in enumerate(markers):
        marker_title = match.group(1).strip()
        content_start_pos = match.end(1)
        end_pos = markers[i + 1].start() if i + 1 < len(markers) else len(full_text)

        marker_body = full_text[content_start_pos:end_pos].strip()
        if not marker_body:
            continue

        # If the whole section fits, keep it as one chunk
        if len(marker_title) + len(marker_body) + 2 <= max_chars:
            content = f"{marker_title}\n\n{marker_body}"
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": content,
                "source": source_name,
                "page": 1,
                "article": marker_title,
                "article_chunk_seq": 1
            })
        else:
            # If too long, split the body and prepend the title to each chunk
            body_chunks = text_splitter.split_text(marker_body)
            for k, part in enumerate(body_chunks):
                content = f"{marker_title}\n\n{part}"
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": content,
                    "source": source_name,
                    "page": 1,
                    "article": marker_title,
                    "article_chunk_seq": k + 1
                })

    log(f"    - Chunked {len(markers)} {marker_type}s into {len(chunks)} chunks.")
    return chunks

def _chunk_by_chapters_with_items(full_text: str, chapter_spans: List, source_name: str, max_chars: int, overlap: int) -> List[Dict]:
    """
    Special handling for documents with chapters (第X章) and nested items (一、).

    Strategy: Use chapters as primary structure, then detect numbered items within each chapter.
    """
    chunks = []
    text_splitter = get_law_text_splitter(max_chars, overlap)

    # Handle preamble content (before first chapter)
    if chapter_spans:
        preamble = full_text[:chapter_spans[0].start()].strip()
        if preamble:
            log(f"    - Found preamble content ({len(preamble)} chars), preserving as metadata chunk")
            if len(preamble) <= max_chars:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": preamble,
                    "source": source_name,
                    "page": 1,
                    "article": "前言",
                    "article_chunk_seq": 1
                })
            else:
                # Split long preamble
                preamble_parts = text_splitter.split_text(preamble)
                for k, part in enumerate(preamble_parts):
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "content": part,
                        "source": source_name,
                        "page": 1,
                        "article": "前言",
                        "article_chunk_seq": k + 1
                    })

    for i, chapter_match in enumerate(chapter_spans):
        chapter_title = chapter_match.group(1).strip()
        chapter_start = chapter_match.end(1)
        chapter_end = chapter_spans[i + 1].start() if i + 1 < len(chapter_spans) else len(full_text)
        chapter_text = full_text[chapter_start:chapter_end].strip()

        if not chapter_text:
            continue

        # Look for numbered items (一、二、) within this chapter
        item_spans = list(_RE_NUMBERED_ITEM.finditer(chapter_text))

        if item_spans and len(item_spans) >= 2:
            # Chapter has structured items, split by them
            log(f"    - Chapter '{chapter_title}' has {len(item_spans)} numbered items")
            for j, item_match in enumerate(item_spans):
                item_title = item_match.group(1).strip()
                item_start = item_match.end(1)
                item_end = item_spans[j + 1].start() if j + 1 < len(item_spans) else len(chapter_text)
                item_body = chapter_text[item_start:item_end].strip()

                if not item_body:
                    continue

                full_item_title = f"{chapter_title} - {item_title}"
                combined_content = f"{full_item_title}\n\n{item_body}"

                if len(combined_content) <= max_chars:
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "content": combined_content,
                        "source": source_name,
                        "page": 1,
                        "article": full_item_title,
                        "article_chunk_seq": 1
                    })
                else:
                    # Split long item content
                    body_parts = text_splitter.split_text(item_body)
                    for k, part in enumerate(body_parts):
                        chunks.append({
                            "id": str(uuid.uuid4()),
                            "content": f"{full_item_title}\n\n{part}",
                            "source": source_name,
                            "page": 1,
                            "article": full_item_title,
                            "article_chunk_seq": k + 1
                        })
        else:
            # Chapter has no structured items, treat as single unit
            combined = f"{chapter_title}\n\n{chapter_text}"
            if len(combined) <= max_chars:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": combined,
                    "source": source_name,
                    "page": 1,
                    "article": chapter_title,
                    "article_chunk_seq": 1
                })
            else:
                parts = text_splitter.split_text(chapter_text)
                for k, part in enumerate(parts):
                    chunks.append({
                        "id": str(uuid.uuid4()),
                        "content": f"{chapter_title}\n\n{part}",
                        "source": source_name,
                        "page": 1,
                        "article": chapter_title,
                        "article_chunk_seq": k + 1
                    })

    log(f"    - Processed {len(chapter_spans)} chapters into {len(chunks)} chunks")
    return chunks

def chunk_document_general(doc_path: Path, max_chars: int, overlap: int) -> List[Dict]:
    """Splits a preprocessed Markdown file using a general-purpose recursive text splitter."""
    log(f"  - Splitting {doc_path.name} with 'general' strategy...")
    try:
        full_text = doc_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        log(f"    - ERROR: File not found: {doc_path}")
        return []

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""], # Common separators
    )

    parts = text_splitter.split_text(full_text)
    
    chunks = [{
        "id": str(uuid.uuid4()), 
        "content": part, 
        "source": str(doc_path.name), 
        "page": 1, # Page info is 1 for single MD file
        "chunk_seq": i + 1
    } for i, part in enumerate(parts)]
    log(f"    - Split into {len(chunks)} chunks.")
    return chunks
