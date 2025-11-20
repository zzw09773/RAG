# Law RAG System

A Retrieval-Augmented Generation (RAG) system specialized for **Chinese legal documents**. It parses, chunks, vectorizes, and stores legal documents from various formats (PDF, RTF, DOCX) into a `PostgreSQL` database for efficient semantic search.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-0.2+-green.svg)](https://github.com/langchain-ai/langchain)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-blue.svg)](https://www.postgresql.org/)
[![PGVector](https://img.shields.io/badge/PGVector-0.7+-orange.svg)](https://github.com/pgvector/pgvector)

---

## 🚀 Quick Start

This guide provides the essential steps to set up and run the RAG system. For more detailed information on system architecture and development, please see the [Developer Guide](docs/DEVELOPER_GUIDE.md).

### 1. Prerequisites
- **Python**: 3.9 or newer.
- **Docker & Docker Compose**: For running the PostgreSQL database.

### 2. Environment & Dependencies

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

### 3. Application Configuration

```bash
# Create a .env file from the template
cp .env.example .env

# Edit the .env file and fill in your API keys and database settings
nano .env
```
A `PGVECTOR_URL` is required. For local development, it should be:
`postgresql+psycopg2://user:password@localhost:5433/rag_db`

### 4. Database Setup

This project uses Docker to run a PostgreSQL database with the `pgvector` extension.

```bash
# Start the PostgreSQL service in the background
docker compose up -d
```

---

## 📖 Usage

The system has two main functions: **building the index** from documents and **querying the index**.

### 1. Building the Index

The `build_all.sh` script automates the entire process of document preprocessing and indexing.

1.  Place your source documents (PDF, RTF, DOCX) into the `rag_system/documents` directory.
2.  Run the build script:

```bash
# Execute the automated build script
# The script will automatically skip collections that already exist.
./build_all.sh

# To force a rebuild of all documents, use the --force flag
./build_all.sh --force
```

The script will process each document, convert it to Markdown, chunk it, create vector embeddings, and store them in the database. Each document gets its own "collection" in the database, named after the document's filename.

### 2. Querying the Index (Notebook-first)

The recommended way to run the LangGraph agent is via the notebook workflow:

1.  Open `notebooks/legal_rag_workflow.ipynb` in JupyterLab / VS Code.
2.  Load your `.env`, instantiate `RAGConfig`, and call `run_query()` as shown in the notebook cells.
3.  Adjust `top_k`, `content_max_length`, or `use_hierarchical` flags directly in Python, without touching the CLI.

> **Note:** The old `query_rag_pg.py` CLI now exists only for backward compatibility and automation scripts. The notebook reflects the modular API (`rag_system.workflow`) and is the preferred integration surface.

**Legacy CLI (optional):**

```bash
cd rag_system
python query_rag_pg.py -q "行政程序法第102條規定了什麼？" --collection <your_collection>
```

### 3. **NEW** Hierarchical RAG System

The system now supports a hierarchical RAG architecture that provides improved retrieval quality and reduced token consumption.

#### Benefits
- **30-50% token savings** through hierarchical content organization
- **Improved retrieval quality** with multi-level semantic search
- **Automatic parent context** included with detailed results
- **Structured legal document hierarchy** (Document → Chapter → Article → Section)

#### Migration

Before using hierarchical RAG, you need to migrate your existing flat collections:

```bash
# 1. Initialize the hierarchical schema
python scripts/init_hierarchical_schema.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG"

# 2. Preview migration (dry-run)
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY" \
    --preview

# 3. Execute migration
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY"
```

#### Querying Hierarchical RAG

**Standalone Query:**
```bash
python scripts/query_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --embed-api-key "YOUR_API_KEY" \
    --query "行政程序法第102條規定了什麼？" \
    --k 5 \
    --show-context
```

**Retrieve-only with Hierarchical:**
```bash
cd rag_system
python query_rag_pg.py \
    -q "違反第3條規定會有什麼罰則？" \
    --hierarchical \
    --retrieve-only
```

**Compare Flat vs Hierarchical:**
```bash
python scripts/compare_flat_vs_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --embed-api-key "YOUR_API_KEY" \
    --query "我能否取得行政程序法第102條的上下文？" \
    --collection-name "law_collection"
```

For detailed migration instructions, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

---

## 📊 System Architecture

### Overall Architecture

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
        Action -->|Finish| Generate[Generate Answer with Citations]
    end

    Generate --> End([Return Result])

    style Agent fill:#95e1d3
    style End fill:#f38181
```

---

## 🔧 Development

For details on the system's architecture, including the `LangGraph` implementation, module responsibilities, and advanced configuration, please refer to the [**Developer Guide**](docs/DEVELOPER_GUIDE.md).

---
**Last Updated**: 2025-10-08