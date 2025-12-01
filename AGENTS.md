# Repository Guidelines

## Project Structure & Module Organization
- `rag_system/`: core library (workflow/agent wiring, tools, application/domain/infrastructure layers).
- `notebooks/`: primary entrypoints (`1_build_index.ipynb` for indexing, `2_query_verify.ipynb` for querying/verification).
- `tests/`: pytest suites (e.g., `tests/unit/test_sources.py`); add new tests under `tests/<area>/test_*.py`.
- `data/`, `examples/`, `docs/`: sample corpora, usage samples, and deeper architecture notes.

## Build, Test, and Development Commands
- Create env + install deps:
  ```bash
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  ```
- Start PostgreSQL + pgvector (required for notebooks):
  ```bash
  docker compose up -d
  docker compose ps           # verify healthy
  ```
- Run indexing/query flows via notebooks only:
  - `notebooks/1_build_index.ipynb`：初始化階層式 Schema，批次或單檔索引。
  - `notebooks/2_query_verify.ipynb`：載入 agent，執行查詢/驗證。
- Run tests (default):
  ```bash
  pytest                      # or pytest tests/unit/test_sources.py
  ```

## Coding Style & Naming Conventions
- Python, 4-space indent, type hints where practical; keep docstrings for public helpers.
- Follow existing patterns in `rag_system/`: functions `snake_case`, classes `PascalCase`, module-level constants `UPPER_SNAKE`.
- Keep outputs and prompts concise; avoid mixing English/Chinese in identifiers.
- Prefer small, pure functions; log via shared utilities in `rag_system/common.py` instead of ad-hoc prints.

## Testing Guidelines
- Use pytest; place fixtures alongside tests or in `tests/conftest.py` if added.
- Name tests after behavior (`test_<function>_<case>()`); assert user-visible strings and ordering where relevant (see `test_sources.py`).
- Target coverage on new logic paths, especially routing, retrieval fallbacks, and formatting branches.

## Commit & Pull Request Guidelines
- Match existing Conventional Commit style (`feat:`, `refactor:`, `chore:`). Scope optional but helpful.
- Commit messages: imperative, focused on intent (“Add hierarchical routing guard”).
- PRs: include summary of behavior changes, manual/automated test results (`pytest`, notebook steps, or script invocations), and links to issues if any. Attach screenshots only when UI/output formatting is affected.

## Environment & Security Tips
- Copy `.env` from template and fill `PGVECTOR_URL`; avoid committing secrets or notebook outputs with credentials.
- Keep Docker volumes intact unless intentionally resetting data (`docker compose down -v` wipes data).
- For large corpora, stage files under `data/` and avoid pushing proprietary documents; prefer `.gitignore` updates for temporary assets.

## Canonical Instructions
- 技術哲學、流程與 MCP 使用指南一律以 `AGENT.md` 為唯一來源；若有衝突或重複，以 `AGENT.md` 為準。
- `CLAUDE.md` 保留專案概述與環境設定，避免重複維護相同規則。
- 新增指引請整合進 `AGENT.md` 或本檔，避免再新增平行的重複文件。
