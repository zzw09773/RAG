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

### 2. Querying the Index

Use the `query_rag_pg.py` script to perform semantic searches on the indexed documents.

**Single Query:**

```bash
# Navigate to the rag_system directory
cd rag_system

# Use -q to specify your question and --collection to target a document collection
python query_rag_pg.py -q "What are the regulations for..." --collection <your_document_name>
```

**Interactive Mode:**

If you run the script without a query, it will enter an interactive mode, allowing you to ask multiple questions.

```bash
cd rag_system
python query_rag_pg.py --collection <your_document_name>
```

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