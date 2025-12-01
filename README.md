# Law RAG System

以 Notebook 為主入口的中文法律 RAG 系統，負責解析、切分、向量化 PDF/RTF/DOCX，並寫入 PostgreSQL（pgvector）。

---

## 🚀 Quick Start

1. **環境需求**：Python 3.9+、Docker + Docker Compose。
2. **安裝依賴**：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **設定環境變數**：新增 `.env`（已加入 `.gitignore`），至少填 `PGVECTOR_URL`、`EMBED_API_BASE`、`EMBED_API_KEY`。Docker compose 預設 DB 位於 `postgresql://postgres:postgres@localhost:15432/Judge`，Jupyter 埠預設 `25678`。
4. **啟動 Notebook + DB**：
   ```bash
   docker compose up -d
   ```
   - Jupyter（無 token/password）：http://localhost:25678
   - PostgreSQL：localhost:15432（與 `PGVECTOR_URL` 預設一致）

---

## 📁 Repository Layout

```
project_root/
├── .env                    # 環境變數佔位檔
├── docker-compose.yaml     # 本地資料庫服務
├── requirements.txt        # 依賴列表
├── README.md               # 入口說明（本文件）
│
├── notebooks/              # 主要進入點
│   ├── 1_build_index.ipynb # 初始化資料庫、讀檔、建立向量索引
│   └── 2_query_verify.ipynb# 載入 Agent、檢索並驗證回答
│
└── rag_system/             # 核心程式庫
    ├── config.py           # RAGConfig 統一配置
    ├── common.py           # 共用工具 (Log, LocalApiEmbeddings)
    ├── domain/             # 領域模型
    ├── infrastructure/     # 資料庫實作
    ├── application/        # 用例層 (索引、檢索、切塊)
    ├── tool/               # LangGraph 工具
    └── workflow.py         # Notebook/服務的流程入口
```

---

## 📖 Usage

- **Notebook 入口**：
  - `notebooks/1_build_index.ipynb`：直接呼叫 `rag_system` 模組初始化階層式 Schema、收集文件並建立索引（預設批次目錄 `data/input`，可在 Notebook 調整）。Notebook 首段會將 repo root 與 `venv` 的 site-packages 加入 `sys.path`。
  - `notebooks/2_query_verify.ipynb`：載入 `rag_system.workflow`，執行檢索與回答驗證（同樣在開頭將 repo root 與 `venv` site-packages 加入 `sys.path`）。
- **CLI / Service 入口（非 Notebook）**：
  - 單次查詢：`python -m rag_system.cli query "你的問題"`（可加 `--hierarchical`）。
  - 簡易 HTTP 服務：`python -m rag_system.cli serve --port 8080`，POST `/query`，payload `{ "question": "..." }`。
  - Shell 包裝：`./query.sh "你的問題"` 會自動呼叫上述 CLI。

---

## 🔀 Hierarchical Migration (簡版)

透過 `notebooks/1_build_index.ipynb` 直接初始化階層式 Schema 並索引文件；如需重新索引，設定 `force_reindex=True` 即可。舊版 CLI/scripts 已移除。

---

## 📐 Architecture (概要)

```mermaid
graph TB
    Start([User Query]) --> Agent[ReAct Agent]
    subgraph "Legal Document Query Flow"
        Agent --> Think[LLM Reasoning]
        Think --> Action{Select Action}
        Action -->|Route| RouterTool[select_collection]
        Action -->|Retrieve| RetrieveTool[retrieve_documents]
        Action -->|Search| MetadataTool[metadata_search]
        Action -->|Calculate| CalcTool[calculator_tool]
        RouterTool --> Observe[Observe Results]
        RetrieveTool --> Observe
        MetadataTool --> Observe
        CalcTool --> Observe
        Observe --> Think
        Action -->|Finish| Generate[Answer w/ Citations]
    end
    Generate --> End([Return Result])
    style Agent fill:#95e1d3
    style End fill:#f38181
```

如需更深入的模組與流程說明，請參考 `docs/DEVELOPER_GUIDE.md`。

---

**Last Updated**: 2025-10-08
