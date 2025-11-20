#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import List, Dict
import orjson
from ..common import log

def load_json(path: Path):
    with open(path, "rb") as f:
        return orjson.loads(f.read())


def write_text_outputs(chunks: List[Dict], out_dir: Path):
    def sort_key(c: Dict):
        from pathlib import Path as P
        page = c.get("page", 0)
        seq = str(c.get("chunk_seq", "0"))
        if '-' in seq:
            main_seq, sub_seq = seq.split('-', 1)
            return (P(c["source"]).name, int(page), int(main_seq), int(sub_seq))
        return (P(c["source"]).name, int(page), int(seq), 0)

    chunks_sorted = sorted(chunks, key=sort_key)
    # log(f"--- DEBUG: Found {len(chunks_sorted)} chunks to process. ---")

    # Markdown
    md_lines: List[str] = []
    last_src = None
    for c in chunks_sorted:
        # log(f"--- DEBUG: Processing chunk with source: {c.get('source')} ---")
        src_name = Path(c["source"]).name
        if src_name != last_src:
            if last_src is not None:
                md_lines.append("\n---")
            md_lines.append(f"# {src_name}")
            last_src = src_name

        chunk_num = c.get('article_chunk_seq') or c.get('chunk_seq', '?')
        md_lines.append(f"\n## p{c.get('page', '?')} #{chunk_num}")
        md_lines.append("")

        content = c["content"].strip()

        if 'article' in c:
            parts = content.split('\n\n', 1)
            title = parts[0]
            body = parts[1] if len(parts) > 1 else ''
            md_lines.append(f"### {title}")
            if body:
                body_lines = body.strip().split('\n')
                for line in body_lines:
                    md_lines.append(f"- {line.strip()}")
        else:
            content_lines = content.strip().split('\n')
            for line in content_lines:
                md_lines.append(f"- {line.strip()}")

    (out_dir / "chunks.md").write_text("\n".join(md_lines), encoding="utf-8")

    # Plain text
    txt_lines: List[str] = []
    for c in chunks_sorted:
        src_name = Path(c["source"]).name
        txt_lines.append(f"【{src_name} p{c.get('page','?')} #{c.get('chunk_seq','?')}】")
        txt_lines.append(c["content"].strip())
        txt_lines.append("")
    (out_dir / "chunks.txt").write_text("\n".join(txt_lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="從 chunks.json 匯出 chunks.md 與 chunks.txt")
    ap.add_argument("--output_dir", default="rag_system/output", help="輸出資料夾，預期含 chunks.json")
    args = ap.parse_args()

    out_dir = Path(args.output_dir).resolve()
    chunks_path = out_dir / "chunks.json"
    if not chunks_path.exists():
        log(f"找不到 {chunks_path}，請先建立切塊或指定正確目錄")
        raise SystemExit(1)
    chunks = load_json(chunks_path)
    write_text_outputs(chunks, out_dir)
    print(f"已輸出：{out_dir/'chunks.md'}, {out_dir/'chunks.txt'}")


if __name__ == "__main__":
    main()
