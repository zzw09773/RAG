# Gemini Context: Law RAG System

## Project Overview
This project is a **Chinese Law RAG (Retrieval-Augmented Generation) System** designed to process legal documents (PDF/RTF/DOCX), index them into a vector database (PostgreSQL + pgvector), and provide an agentic query interface. It utilizes **LangGraph** for orchestration, enabling a ReAct agent workflow with hierarchical retrieval capabilities.

## Tech Stack
- **Language:** Python 3.9+
- **Frameworks:** LangChain, LangGraph, FastAPI
- **Database:** PostgreSQL with `pgvector` extension
- **Document Processing:** PyMuPDF, striprtf, python-docx
- **Embeddings/LLM:** Compatible with OpenAI-style APIs (e.g., NVIDIA NIM, vLLM)

## Key Workflows

### 1. Indexing (Data Ingestion)
- **Entry Point:** `notebooks/1_build_index.ipynb`
- **Process:**
  1.  Reads documents from `data/input`.
  2.  Parses hierarchical structure (Articles, Paragraphs).
  3.  Generates embeddings.
  4.  Stores in PostgreSQL (hierarchical schema).

### 2. Querying (Retrieval & Generation)
- **Entry Points:**
  - **Notebook:** `notebooks/2_query_verify.ipynb` (Interactive debugging/verification).
  - **CLI:** `python -m rag_system.cli query "question"`
  - **API:** `python api.py` (OpenAI-compatible endpoint at `/v1/chat/completions`).
- **Mechanism:** ReAct Agent with tools for:
  - `article_lookup`: Direct article retrieval.
  - `metadata_search`: Filter-based search.
  - `retrieve_hierarchical`: Two-stage retrieval (Summary → Details).

## Project Structure
```
/
├── api.py                  # FastAPI application (OpenAI-compatible)
├── docker-compose.yaml     # DB and Service orchestration
├── notebooks/              # Primary interactive workflows
│   ├── 1_build_index.ipynb # Indexing workflow
│   └── 2_query_verify.ipynb# Query verification
├── rag_system/             # Core Package
│   ├── config.py           # Configuration (RAGConfig)
│   ├── workflow.py         # LangGraph graph definition
│   ├── node.py             # Agent node logic
│   ├── application/        # Use cases (indexing, retrieval)
│   ├── domain/             # Data models (Entities, Value Objects)
│   ├── infrastructure/     # Database adapters (pgvector)
│   └── tool/               # Agent tools (Retrieval, Search)
├── data/                   # Data directory
│   ├── input/              # Raw documents
│   └── processed/          # Intermediate artifacts
└── docs/                   # Documentation
    └── DEVELOPER_GUIDE.md  # Detailed architecture docs
```

## Configuration
Configuration is managed via `rag_system/config.py` and `.env` file.

**Key Environment Variables:**
- `PGVECTOR_URL`: Database connection string (default: `postgresql://postgres:postgres@localhost:15432/Judge`).
- `EMBED_API_BASE`: Base URL for the embedding model API.
- `LLM_API_BASE`: Base URL for the Chat LLM API (defaults to `EMBED_API_BASE` if not set).
- `EMBED_API_KEY`: API Key for authentication.
- `EMBED_MODEL_NAME`: Model ID for embeddings (default: `nvidia/nv-embed-v2`).
- `CHAT_MODEL_NAME`: Model ID for chat (default: `openai/gpt-oss-20b`).

## Development & Usage

### Running the Stack
1.  **Start Database:**
    ```bash
    docker compose up -d
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run API:**
    ```bash
    python api.py
    ```

### Coding Conventions
- **Agentic Philosophy:** Follow `AGENT.md` for core principles.
- **Style:** Pythonic, type-hinted.
- **Architecture:** Domain-Driven Design (DDD) lite—separate `domain`, `infrastructure`, and `application` layers.
- **Testing:** `tests/` directory containing pytest suites.

## Specialized Files
- `AGENT.md`: "Linus Torvalds" persona and core engineering philosophy.
- `CLAUDE.md`: Interaction guidelines for AI assistants.
- `reindex_script.py`: Script version of the indexing notebook.
