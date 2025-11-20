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
3. **設定環境變數**：複製並填寫 `.env` 中的空白值（`PGVECTOR_URL` 為必填）。
4. **啟動資料庫**：
   ```bash
   docker compose up -d
   ```

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
├── scripts/                # 維運與管理腳本
│   ├── init_hierarchical_schema.py
│   ├── index_hierarchical.py
│   └── migrate_to_hierarchical.py
│
└── rag_system/             # 核心程式庫
    ├── config.py           # RAGConfig 統一配置
    ├── common.py           # 共用工具 (Log, LocalApiEmbeddings)
    ├── domain/             # 領域模型
    ├── infrastructure/     # 資料庫實作
    ├── application/        # 用例層 (索引、檢索、切塊)
    ├── tool/               # LangGraph 工具
    ├── workflow.py         # Notebook/服務的流程入口
    └── legacy/             # 舊版 CLI 與建置腳本
```

---

## 📖 Usage

- **Notebook 入口**：
  - `notebooks/1_build_index.ipynb`：初始化階層式 Schema、收集文件、建立索引。
  - `notebooks/2_query_verify.ipynb`：載入 `rag_system.workflow`，執行檢索與回答驗證。
- **腳本工具**：
  - `scripts/init_hierarchical_schema.py`：建立/驗證資料表。
  - `scripts/index_hierarchical.py`：呼叫 `IndexDocumentUseCase` 進行階層式索引。
  - `scripts/migrate_to_hierarchical.py`：從平面集合遷移到階層式架構。
- **Legacy**：舊版 CLI 與建置流程位於 `rag_system/legacy/`，僅為相容性保留。

---

## 🔀 Hierarchical Migration (簡版)

```bash
# 1) 建立階層式 Schema
python scripts/init_hierarchical_schema.py --conn "$PGVECTOR_URL"

# 2) 預覽遷移
python scripts/migrate_to_hierarchical.py --conn "$PGVECTOR_URL" \
    --collection-name "law_collection" --embed-api-key "YOUR_API_KEY" --preview

# 3) 執行遷移
python scripts/migrate_to_hierarchical.py --conn "$PGVECTOR_URL" \
    --collection-name "law_collection" --embed-api-key "YOUR_API_KEY"
```

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
