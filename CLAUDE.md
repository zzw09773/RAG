# CLAUDE.md — 工作指引（精簡版）

此檔僅說明如何與專案互動；技術哲學與規範以 `AGENT.md` 為唯一來源，使用/架構詳見 `README.md` 與 `docs/DEVELOPER_GUIDE.md`。

## 角色
- 中文法律文件 RAG（LangGraph ReAct Agent，預設階層式檢索）。
- Notebook 優先；CLI/HTTP 為輔。

## 你要做的事（優先順序）
1) 先讀 `AGENT.md`（核心規範）  
2) 操作入口：`notebooks/1_build_index.ipynb`、`notebooks/2_query_verify.ipynb`  
3) 需要程式化：呼叫 `rag_system.workflow`；或 CLI/HTTP：
   - `python -m rag_system.cli query "問題"`（`--hierarchical` 可切換）
   - `python -m rag_system.cli serve --port 8080`，POST `/query` body `{ "question": "..." }`
   - `./query.sh "問題"` 包裝 CLI
4) 環境：依 `README.md` 的快速開始（venv + `pip install -r requirements.txt` + `docker compose up -d`，`.env` 設定 `PGVECTOR_URL` / `EMBED_API_BASE` / `EMBED_API_KEY`）。

## 檔案導覽
- `README.md`：唯一入口與操作指南（已合併 QUICKSTART）。
- `docs/DEVELOPER_GUIDE.md`：架構與模組詳解。
- `docs/governance/`：治理/ISO 文件（若需）。

## 作業原則
- 不新增平行規範文件；更新規範一律寫回 `AGENT.md`。
- 變更架構/流程時同步更新 `AGENT.md` 或 README（依內容而定）。
- 測試用 pytest；新增測試放 `tests/<area>/test_*.py`。
- 避免提交含憑證/密鑰或 Notebook 輸出。

## 常用指令
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose up -d
pytest
```
