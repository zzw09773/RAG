# Law RAG System

以 Notebook 為主入口的中文法律 RAG 系統，負責解析、切分、向量化 PDF/RTF/DOCX，並寫入 PostgreSQL（pgvector）。下列內容已合併原 QUICKSTART，作為單一入口指南。

---

## 🚀 快速開始
- 環境需求：Python 3.9+，Docker + Docker Compose。
- 安裝依賴：
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- 環境變數：建立 `.env`（已在 `.gitignore`），至少設定 `PGVECTOR_URL`、`EMBED_API_BASE`、`EMBED_API_KEY`。預設 DB：`postgresql://postgres:postgres@localhost:15432/Judge`；Jupyter 連線埠 `25678`。
- 啟動 DB / Notebook：
  ```bash
  docker compose up -d
  docker compose ps   # 確認 healthy
  ```
  - Jupyter（無 token）：http://localhost:25678
  - PostgreSQL：localhost:15432（對應 `PGVECTOR_URL` 預設）

---

## 🧭 開發/操作路徑
- Notebook（推薦）
  - `notebooks/1_build_index.ipynb`：初始化階層式 Schema、收集/批次索引 `data/input`（可在 Notebook 調整路徑）。
  - `notebooks/2_query_verify.ipynb`：載入 workflow，執行查詢與引用驗證。Notebook 開頭會把 repo root 與 venv site-packages 加入 `sys.path`。
- CLI / HTTP
  - 單次查詢：`python -m rag_system.cli query "你的問題"`（可加 `--hierarchical`）。
  - HTTP：`python -m rag_system.cli serve --port 8080`，POST `/query`，body `{ "question": "..." }`。
  - Shell 包裝：`./query.sh "你的問題"` 直接呼叫 CLI。

---

## 📁 專案結構
```
project_root/
├── docker-compose.yaml
├── requirements.txt
├── notebooks/              # 互動入口
│   ├── 1_build_index.ipynb
│   └── 2_query_verify.ipynb
├── rag_system/             # 核心程式庫
│   ├── config.py           # RAGConfig
│   ├── workflow.py         # LangGraph workflow helper
│   ├── node.py             # ReAct node + fallback
│   ├── tool/               # router/retrieve/metadata/article tools
│   ├── application/        # indexing/retrieval use cases
│   ├── infrastructure/     # Postgres/pgvector 存取
│   └── domain/             # entities/value objects
├── data/                   # 預設輸入/樣例資料目錄
├── docs/                   # 開發與治理文件
└── tests/                  # pytest suites
```

---

## 📐 架構概要
- 單一 LangGraph ReAct Agent：router → retrieval → 回答 + 參考資料。
- 預設使用階層式檢索（兩階段摘要→細節）；可切換 legacy 平lat 檢索。
- 詳細流程與模組說明：`docs/DEVELOPER_GUIDE.md`。

---

## 相關文件
- `AGENT.md`：唯一技術指引與開發哲學。
- `docs/DEVELOPER_GUIDE.md`：深入架構與模組說明。
- `CLAUDE.md`：與本專案互動的注意事項（將保留為精簡版）。
- `docs/governance/`：治理與 ISO/IEC 42001 相關文件。

**Last Updated**: 2025-10-08
