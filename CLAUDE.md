# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 專案概述

中文法律文件 RAG (Retrieval-Augmented Generation) 系統,使用 LangGraph ReAct Agent 架構,支援階層式文件索引與智慧檢索。主要透過 Jupyter Notebook 作為開發與操作入口。

**技術棧**:
- **Framework**: LangChain, LangGraph (ReAct pattern)
- **Database**: PostgreSQL + pgvector + ltree (階層式索引)
- **Document Processing**: PyMuPDF, python-docx, striprtf
- **Embedding**: 支援自訂 API (預設 nvidia/nv-embed-v2)
- **LLM**: 支援 OpenAI-compatible API (預設 openai/gpt-oss-20b)

---

## 環境設定

### 1. 必要環境變數

建立 `.env` 檔案,填入以下必要欄位:

```bash
# Database (必填)
PGVECTOR_URL=postgresql://postgres:postgres@localhost:5433/postgres

# Embedding API (必填)
EMBED_API_BASE=http://your-api-endpoint/v1
EMBED_API_KEY=your-api-key
EMBED_MODEL_NAME=nvidia/nv-embed-v2

# LLM API (選填,預設使用 EMBED_API_BASE)
LLM_API_BASE=http://your-llm-endpoint/v1
CHAT_MODEL_NAME=openai/gpt-oss-20b

# PostgreSQL (選填,有預設值)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
PG_PORT=5433
```

### 2. 啟動開發環境

```bash
# 1. 建立虛擬環境並安裝依賴
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 啟動 PostgreSQL + pgvector
docker compose up -d

# 3. 驗證資料庫狀態
docker compose ps
docker exec -it rag_db psql -U postgres -d postgres -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### 3. 資料庫管理

```bash
# 停止但保留資料
docker compose stop

# 停止並移除容器 (保留 volume)
docker compose down

# 完全清除 (包含所有資料)
docker compose down -v
```

---

## 開發工作流程

### 主要入口:Notebooks

系統設計為 **Notebook 優先**,所有核心流程都可透過 Notebook 互動式執行（請在 repo 根目錄啟動 Jupyter，Notebook 會自動把 repo root 加入 sys.path）:

1. **`notebooks/1_build_index.ipynb`**:初始化階層式 Schema、收集文件、建立向量索引
2. **`notebooks/2_query_verify.ipynb`**:載入 Agent workflow、執行檢索與回答驗證

### 建立索引 (Index Documents)

```bash
# Notebook 執行 (建議)
# 開啟 notebooks/1_build_index.ipynb 並依序執行 cells
```

### 查詢與測試

```bash
# Notebook 執行 (建議)
# 開啟 notebooks/2_query_verify.ipynb 並執行查詢
```

### 測試

```bash
# 執行單元測試
pytest tests/unit/test_sources.py -v
```

---

## 架構設計

### 核心架構:LangGraph ReAct Agent

系統使用 **單一 ReAct Agent** 處理所有法律文件查詢,透過工具選擇與反覆推理來解決複雜問題:

```
User Query → ReAct Agent → [Think → Select Tool → Observe → Think] → Answer + Citations
```

**可用工具**:
1. **`collection_router`**:根據查詢內容選擇最相關的法律集合
2. **`retrieve_legal_documents`**:向量檢索相關文件 (支援階層式或平面檢索)
3. **`metadata_search`**:基於元資料的精確搜尋
4. **`lookup_article_by_number`**:依條號查詢特定法條
5. **`python_calculator`**:執行數值計算

### 模組結構

```
rag_system/
├── workflow.py              # 工作流程工廠函式 (Notebook/Service 入口)
├── agent.py                 # LangGraph workflow builder
├── node.py                  # ReAct agent node 實作
├── state.py                 # GraphState 定義
├── config.py                # RAGConfig 集中式配置
├── common.py                # 共用工具 (Log, LocalApiEmbeddings)
│
├── domain/                  # 領域模型 (Entities, Value Objects)
├── infrastructure/          # 資料庫實作 (Schema, Repositories)
├── application/             # 用例層 (Chunking, Indexing, Retrieval)
├── tool/                    # LangChain 工具定義
│   ├── router.py                # Collection router
│   ├── retrieve.py              # 平面檢索
│   ├── retrieve_hierarchical.py # 階層式檢索
│   ├── metadata_search.py       # 元資料搜尋
│   ├── article_lookup.py        # 條號查詢
│   └── calculator.py            # 計算工具
│
```

### 階層式索引設計

使用 **PostgreSQL ltree extension** 管理文件樹狀結構:

```
rag_documents (文件根節點)
  └─ rag_document_chunks (階層式 chunks)
      ├── section_path: ltree (e.g., 'ch1.art2.sec3')
      ├── depth: 階層深度
      ├── chunk_type: 'document' | 'chapter' | 'article' | 'section' | 'detail'
      └── indexing_level: 'summary' | 'detail' | 'both'
```

**優勢**:
- 保留法律文件的結構資訊 (章→條→項→款)
- 支援上下文感知檢索 (檢索時可參考父節點 summary)
- 高效的樹狀查詢 (ltree 的 GiST 索引)

### 程式化介面

```python
from rag_system.workflow import create_llm, create_rag_workflow, run_query
from rag_system.config import RAGConfig

# 1. 從環境變數載入配置
config = RAGConfig.from_env()

# 2. 建立 LLM 與 workflow
llm = create_llm(config)
workflow = create_rag_workflow(config, llm=llm, use_hierarchical=True)

# 3. 執行查詢
result = run_query(
    question="勞基法第 30 條規定為何?",
    config=config,
    use_hierarchical=True
)

print(result["generation"])  # AI 生成的回答
print(result["retrieved_docs"])  # 檢索到的文件片段
```

### Subgraph 整合 (多 Agent 系統)

RAG 系統可作為 **獨立 subgraph** 整合到更大的 multi-agent 系統:

```python
from rag_system.subgraph import create_rag_subgraph
from rag_system.config import RAGConfig

# 建立 RAG subgraph node
rag_config = RAGConfig.from_env()
rag_node = create_rag_subgraph(llm, rag_config, name="rag_expert")

# 加入 supervisor graph
supervisor_graph.add_node("rag_expert", rag_node)
supervisor_graph.add_conditional_edges(
    "router",
    route_to_expert,
    {"rag_expert": "rag_expert", "other": "other_expert"}
)
supervisor_graph.add_edge("rag_expert", "supervisor")
```

**資料流**:
- **Input**: `state["messages"]` 最後一則訊息為使用者問題
- **Output**: `state["generation"]` 為 RAG subgraph 的回答

---

## 重要配置

### RAGConfig 可調參數

```python
from rag_system.config import RAGConfig

config = RAGConfig(
    # 檢索設定
    top_k=10,                      # 預設檢索文件數 (1-20)
    content_max_length=800,        # 每個文件片段最大長度 (100-2000)

    # 資料庫設定
    conn_string="postgresql://...",
    default_collection="laws",

    # 模型設定
    embed_model="nvidia/nv-embed-v2",
    chat_model="openai/gpt-oss-20b",
    temperature=0,                 # 0=確定性輸出

    # API 設定
    embed_api_base="http://...",
    llm_api_base="http://...",     # 可與 embed_api_base 不同
    embed_api_key="...",

    # SSL
    verify_ssl=False,
)
```

### 階層式 vs. 平面檢索

```python
# 階層式檢索 (建議用於法律文件)
workflow = create_rag_workflow(config, use_hierarchical=True)

# 平面檢索 (與舊版 LangChain vectorstore 相容)
workflow = create_rag_workflow(config, use_hierarchical=False)
```

---

## 常見開發情境

### 修改 Agent 推理邏輯

核心檔案:[rag_system/node.py](rag_system/node.py)

ReAct agent 的思考、工具選擇、觀察、回答生成邏輯都在此實作。

### 新增或修改工具

1. 在 `rag_system/tool/` 新增工具定義檔
2. 在 [rag_system/workflow.py:_build_tools](rag_system/workflow.py) 中註冊工具
3. Agent 會自動將工具加入可選項

### 調整階層式索引策略

核心檔案:[rag_system/infrastructure/schema.py](rag_system/infrastructure/schema.py)

修改 `chunk_type` 或 `indexing_level` 的定義,或調整 ltree path 的建立邏輯。

### 客製化文件解析與切塊

核心檔案:
- [rag_system/application/chunking.py](rag_system/application/chunking.py):切塊策略

---

## 指引單一來源

- 若有流程／哲學／MCP 使用準則需求，請直接參閱 `AGENT.md`，本檔不再重複維護相同內容。
- 如果 `CLAUDE.md` 與其他文件有衝突，一律以 `AGENT.md` 為準；本檔專注於專案概述、環境設定與常見操作路徑。

---

**最後更新**: 2025-11-20
