# Law RAG System - GEMINI Context

This document provides a comprehensive overview of the Law RAG System project for AI agents. Use this context to understand the project structure, architecture, and operational procedures.

## 1. Project Overview

**Type:** Python Software Project (Retrieval-Augmented Generation)
**Domain:** Legal Document Analysis and Question Answering (Traditional Chinese)
**Goal:** To parse, chunk, index, and retrieve legal documents (PDF, RTF, DOCX) using a hierarchical strategy, enabling an AI agent to answer user legal queries with precise citations.

## 2. Technology Stack

*   **Language:** Python 3.9+
*   **Orchestration:** LangChain, LangGraph
*   **Database:** PostgreSQL 17+
*   **Extensions:**
    *   `pgvector`: For vector similarity search.
    *   `ltree`: For hierarchical path storage (e.g., `root.chapter_1.article_7`).
*   **Infrastructure:** Docker, Docker Compose
*   **Key Libraries:** `psycopg2-binary`, `httpx`, `langchain-openai`, `langchain-postgres`.

## 3. Architecture & Core Components

The system is organized into a modular structure within `rag_system/`.

### 3.1. Indexing Pipeline (`rag_system/application/indexing.py`)
*   **Chunking (`chunking.py`):** Uses `HierarchicalChunker` to split documents into a tree structure:
    *   **Levels:** Document → Chapter → Article → Section → Detail.
    *   **Strategy:** Regex-based parsing for Chinese legal formats (`第X章`, `第X條`).
*   **Storage (`infrastructure/database.py`):**
    *   **Documents:** Stored in `rag_documents`.
    *   **Chunks:** Stored in `rag_document_chunks` with `ltree` paths.
    *   **Embeddings:** Stored in `rag_chunk_embeddings_detail` (and summary).

### 3.2. Retrieval System (`rag_system/application/retrieval.py`)
*   **Strategy:** Uses `DirectRetrievalStrategy` by default (configured in `tool/retrieve_hierarchical.py`).
    *   **Step 1:** Searches the **Detail** index directly using vector similarity.
    *   **Step 2:** Retrieves **Parent** context (ancestors like Chapter/Document titles) for the top matches.
    *   **Step 3:** Formats the output to show the Chunk content + Parent Context, excluding irrelevant sibling chunks.

### 3.3. Agent Workflow (`rag_system/workflow.py`, `node.py`)
*   **Type:** ReAct Agent (Reason + Act).
*   **Router:** `collection_router` tool determines which legal document collection to search.
*   **Retriever:** `retrieve_hierarchical` tool fetches content.
*   **Flow:**
    1.  User asks a question.
    2.  Agent calls `collection_router` to identify the relevant law (e.g., "陸海空軍懲罰法").
    3.  Agent calls `retrieve_hierarchical` with the specific query (e.g., "第7條").
    4.  Agent synthesizes the answer based *only* on retrieved data.

## 4. Operational Guide

### 4.1. Setup & Environment
1.  **Start Services:**
    ```bash
    docker compose up -d
    ```
    *   Database: `localhost:15432` (User/Pass: `postgres`/`postgres`, DB: `Judge`)
    *   Jupyter: `http://localhost:25678`

2.  **Environment Variables (`.env`):**
    *   `PGVECTOR_URL`: Database connection string.
    *   `EMBED_API_BASE`: Embedding model API endpoint.
    *   `EMBED_API_KEY`: API Key.

### 4.2. Common Commands

*   **Query (CLI):**
    The primary way to test the RAG pipeline from the terminal.
    ```bash
    ./query.sh "陸海空軍懲罰法第7條"
    ```
    *   *Note:* This script automatically uses the hierarchical retrieval system.

*   **Indexing (Notebook):**
    *   Open `notebooks/1_build_index.ipynb`.
    *   Place raw files in `data/input/`.
    *   Run the notebook to convert, chunk, and index files into PostgreSQL.

*   **Start HTTP Server:**
    ```bash
    python3 -m rag_system.cli serve --port 8080
    ```

### 4.3. Development Conventions

*   **Code Style:** Follow standard Python PEP 8.
*   **Logging:** Use `rag_system.common.log` for consistent logging.
*   **Modularity:**
    *   **Domain:** Value objects and Entities (pure Python).
    *   **Infrastructure:** Database code (SQL, specific libs).
    *   **Application:** Business logic (Use Cases).
    *   **Tool:** LangChain tool definitions.

## 5. Key Files Reference

*   `rag_system/config.py`: Central configuration logic.
*   `rag_system/infrastructure/schema.py`: Database schema definitions (`rag_documents`, etc.).
*   `rag_system/application/chunking.py`: Regex logic for parsing legal text.
*   `rag_system/node.py`: Agent prompt engineering and fallback logic.
*   `query.sh`: Wrapper script for CLI queries.

## 6. Recent Changes (Hierarchical Migration)

*   **Schema:** Migrated from flat `langchain_pg_collection` to hierarchical `rag_documents` tables.
*   **Router:** Updated to query `rag_documents` for stats.
*   **Retrieval:** Switched to `DirectRetrievalStrategy` to ensure small chunks (like "Article 7") are found by vector search on the detail level.
*   **Output Format:** Tuned to display "Parent Path + Main Content" only, reducing noise.
