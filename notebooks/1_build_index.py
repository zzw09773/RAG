#!/usr/bin/env python
# coding: utf-8

# # 1. 建立索引 (Build Index)
# 單一 Notebook 完成資料庫初始化與階層式索引，不再依賴 `scripts/` 目錄。
# 
# 流程：
# 1. 載入環境設定
# 2. 初始化階層式 Schema
# 3. 建立索引（單檔或整個資料夾）
# 
# 需設定環境變數：`PGVECTOR_URL`, `EMBED_API_BASE`, `EMBED_API_KEY`（模型名稱可選 `EMBED_MODEL_NAME`）。

# In[1]:


# Step 1: 載入環境變數與設定
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 確保專案根目錄在 sys.path（Notebook 跑在 notebooks/ 內，需要手動加入）
repo_root = Path.cwd().resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 將 venv 的 site-packages 加入 sys.path（kernel 若未選 venv 仍可找到套件）
venv_base = repo_root / "venv"
for sp in venv_base.glob("lib/python*/site-packages"):
    if str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

from rag_system.config import RAGConfig

load_dotenv()
config = RAGConfig.from_env()
config.validate()

print(f"Repo root set: {repo_root}")
print(f"Venv site-packages entries: {[str(p) for p in venv_base.glob('lib/python*/site-packages')]}")
print(f"PGVECTOR_URL set: {bool(config.conn_string)}")
print(f"Embed base: {config.embed_api_base}")
print(f"Embed model: {config.embed_model}")
print(f"Verify SSL: {config.verify_ssl}")


# ## Step 2: 初始化階層式 Schema
# 直接呼叫 `rag_system.infrastructure.schema`，可重複執行、具備 idempotent。

# In[2]:


from rag_system.infrastructure.schema import init_hierarchical_schema, get_schema_info

schema_ok = init_hierarchical_schema(config.conn_string)
print("Schema initialized:", schema_ok)
print(get_schema_info(config.conn_string))


# ## Step 3: 準備索引用的 Use Cases
# 使用 `IndexDocumentUseCase` 與 `BulkIndexUseCase` 直接在 Notebook 執行，不需 scripts/。

# In[3]:


from rag_system.common import LocalApiEmbeddings
from rag_system.application.indexing import EmbeddingService, IndexDocumentUseCase, BulkIndexUseCase
from rag_system.application.chunking import HierarchicalChunker
from rag_system.infrastructure.database import HierarchicalDocumentRepository, VectorStoreRepository

# 初始化核心元件
doc_repo = HierarchicalDocumentRepository(config.conn_string)
vector_repo = VectorStoreRepository(config.conn_string, embedding_dimension=4096)
embed_model = LocalApiEmbeddings(
    api_base=config.embed_api_base,
    api_key=config.embed_api_key,
    model_name=config.embed_model,
    verify_ssl=config.verify_ssl,
)
embedding_service = EmbeddingService(embed_model)
chunker = HierarchicalChunker()

index_use_case = IndexDocumentUseCase(
    doc_repository=doc_repo,
    vector_repository=vector_repo,
    embedding_service=embedding_service,
    chunker=chunker,
)
bulk_index = BulkIndexUseCase(index_use_case)

print("Use cases ready. Change embed_api_base/key/model via config if needed.")


# ## Step 3a: 將 RTF / DOCX / PDF 轉為 Markdown
# 把 `data/input` 下的檔案轉成 `.md` 存至 `data/converted_md`，再由後續索引步驟使用。

# In[4]:


from striprtf.striprtf import rtf_to_text
import fitz  # PyMuPDF
import docx

input_dir = repo_root / "data/input"
converted_dir = repo_root / "data/converted_md"
converted_dir.mkdir(parents=True, exist_ok=True)

supported = {".rtf", ".docx", ".pdf"}
converted = []
failed = []

for p in input_dir.rglob("*"):
    if not p.is_file():
        continue
    suffix = p.suffix.lower()
    if suffix not in supported:
        continue

    out_path = converted_dir / f"{p.stem}.md"
    try:
        if suffix == ".rtf":
            text = rtf_to_text(p.read_text(encoding="utf-8", errors="ignore"))
        elif suffix == ".docx":
            d = docx.Document(str(p))
            text = "\n".join([para.text for para in d.paragraphs])
        elif suffix == ".pdf":
            with fitz.open(p) as doc:
                text = "\n".join([page.get_text("text") for page in doc])
        else:
            continue

        out_path.write_text(text, encoding="utf-8")
        converted.append(out_path)
    except Exception as e:
        failed.append((p.name, str(e)))

print(f"Converted {len(converted)} files -> {converted_dir}")
if failed:
    print("Failed conversions:")
    for name, err in failed:
        print(f"  - {name}: {err}")


# ## Step 4: （可選）索引單一檔案
# 若只想先試單檔，可指定檔案路徑；預設批次索引目錄為 `data/input`，可在 Step 5 調整 `data_root`。

# In[5]:


# 單檔索引（可跳過）
sample_file = Path("data/example.md")
if sample_file.exists():
    index_use_case.execute(sample_file, force_reindex=True)
else:
    print("Sample file not found; skip single-file demo.")


# ## Step 5: 批次索引整個資料夾（預設步驟）
# 會自動搜尋常見文字與文件格式，並以 `BulkIndexUseCase` 執行。

# In[6]:


# 預設批次索引：使用 data/converted_md 的 .md 檔；若無則回退 data/input 的 .md。
from rag_system.application.indexing import IndexingLevel

converted_dir = repo_root / "data/converted_md"
raw_md_dir = repo_root / "data/input"

files = []
for base in [converted_dir, raw_md_dir]:
    if base.exists():
        files.extend([p for p in base.rglob("*") if p.is_file() and p.suffix.lower() == ".md"])

print(f"Found {len(files)} markdown files (converted + raw)")
if files:
    bulk_index.execute(files, force_reindex=True, skip_errors=False)
else:
    print("No markdown files found. Add files under data/input (rtf/docx/pdf will be converted) then rerun.")


# In[7]:


# Step 6: 顯示指定條文的階層式切分（預設第 10 條，陸海空軍懲罰法）
from rag_system.domain import DocumentId
from rag_system.infrastructure.database import HierarchicalDocumentRepository

# 可調整的示例參數
sample_source = "陸海空軍懲罰法.md"  # 轉檔後的檔名
article_keys = {"第12條", "第 12 條"}
preview_len = 2000  # 內容預覽長度

repo = HierarchicalDocumentRepository(config.conn_string)

# 取得文件 id
with repo._get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM rag_documents WHERE source_file = %s",
            (sample_source,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"找不到來源檔案 {sample_source} 的文件記錄")
        doc_id = DocumentId(value=row[0])

# 取得 root 節點（parent_id IS NULL）
with repo._get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM rag_document_chunks WHERE document_id = %s AND parent_id IS NULL",
            (str(doc_id),),
        )
        root_ids = [r[0] for r in cur.fetchall()]

if not root_ids:
    print(f"{sample_source} 尚未切分出任何階層節點")
else:
    # 簡單的樹形輸出（含深度）
    def render_tree(chunk, prefix=""):
        children = repo.get_children(chunk.id)
        marker = "●"  # 根/節點標記
        depth_info = f"depth={chunk.depth}"
        title = chunk.section_path or "root"
        article = chunk.article_number or ""
        preview = chunk.content
        if preview_len and len(preview) > preview_len:
            preview = preview[:preview_len] + "..."
        print(f"{prefix}{marker} {title} {article} ({depth_info}, type={chunk.chunk_type.value}, level={chunk.indexing_level.value})")
        if preview:
            print(f"{prefix}   摘要: {preview}")
        for idx, child in enumerate(children):
            is_last = idx == len(children) - 1
            branch = "└─" if is_last else "├─"
            next_prefix = prefix + ("   " if is_last else "│  ")
            print(prefix + branch, end="")
            render_tree(child, next_prefix)

    def find_and_render(chunk):
        target_keys = {k.replace(" ", "") for k in article_keys}
        if chunk.article_number and chunk.article_number.replace(" ", "") in target_keys:
            render_tree(chunk)
            return True
        found = False
        for child in repo.get_children(chunk.id):
            found |= find_and_render(child)
        return found

    any_rendered = False
    for rid in root_ids:
        root_chunk = repo.get_chunk_by_id(rid)
        any_rendered |= find_and_render(root_chunk)

    if not any_rendered:
        print(f"在 {sample_source} 中找不到條文 {article_keys}")


# In[ ]:




