# Developer Guide

This guide provides a detailed overview of the RAG system's architecture, components, and development practices.

---

## 📊 System Architecture

The system is now a single, modular LangGraph ReAct agent that runs primarily from notebooks. `rag_system.workflow` exposes factory functions so Jupyter notebooks, services, or the legacy CLI can all create the exact same workflow without duplicated wiring.

### Overall Architecture

```mermaid
graph TB
    Start([Notebook / CLI]) --> Init[Configure RAGConfig]
    Init --> Build[create_rag_workflow]
    Build --> Agent[ReAct Agent]
    Agent --> Think[LLM Reasoning]
    Think --> Action{Select Tool}
    Action -->|Route| RouterTool[collection_router]
    Action -->|Retrieve| RetrieveTool[retrieve_legal_documents]
    Action -->|Metadata| MetadataTool[metadata_search]
    Action -->|Lookup| ArticleTool[lookup_article_by_number]
    Action -->|Calculate| CalcTool[python_calculator]
    RouterTool --> Observe[Tool Output]
    RetrieveTool --> Observe
    MetadataTool --> Observe
    ArticleTool --> Observe
    CalcTool --> Observe
    Observe --> Think
    Action -->|Finish| Answer[Answer + Citations]
    Answer --> End([Notebook Output])

    style Agent fill:#95e1d3
    style End fill:#f38181
```

### Collection Router Logic

```mermaid
graph LR
    Query[User Query] --> Analyze[Router Prompt]
    Analyze --> Stats[Collection Stats]
    Stats --> Choose[LLM selects collection]
    Choose --> Result[collection_router tool output]
```

The router now only decides **which legal collection** to search. There is no longer a DATCOM branch; all queries stay inside the legal ReAct agent. The router prompt lists collection names plus document counts and asks the LLM to pick the most relevant one (or fall back to the largest non-empty collection).

---

## 📂 Project Structure

```
rag_system/
├── workflow.py              # Notebook/API helper for building workflows
├── query_rag_pg.py          # Legacy CLI wrapper
├── agent.py                 # LangGraph workflow builder
├── node.py                  # ReAct agent node
├── state.py                 # GraphState definition
├── tool/                    # Router, retrieval, metadata, calculator tools
├── application/             # Chunking & hierarchical retrieval use cases
├── domain/                  # Entities/value objects
├── infrastructure/          # Postgres repositories & schema helpers
├── legacy/
│   ├── build/                   # Legacy indexing and preprocessing pipeline
│   └── query_rag_pg.py          # Legacy CLI
└── notebooks/
    ├── 1_build_index.ipynb       # Indexing entry point
    └── 2_query_verify.ipynb      # Query + verification entry point
```

### Module Responsibilities

| Module | Responsibility |
|:---|:---|
| `workflow.py` | Exposes `create_llm`, `create_rag_workflow`, `run_query` for notebooks/services. |
| `agent.py` | Builds the LangGraph state graph and wires agent nodes. | 
| `node.py` | Implements the ReAct reasoning loop, formatting logic, and error handling. | 
| `tool/` | LangChain-compatible tools (router, flat/hierarchical retrieval, metadata search, calculator). | 
| `application/` | Clean Architecture use cases (indexing, retrieval, chunking). |
| `legacy/build/` | Offline preprocessing + indexing pipeline preserved for backward compatibility. |
| `notebooks/` | Default developer UX for interactive experimentation. |
| `legacy/query_rag_pg.py` | Legacy CLI maintained for automation compatibility. |

---

## 🔧 Building the Index (Notebook-first)

Preferred path：`notebooks/1_build_index.ipynb`。流程透過 `scripts/init_hierarchical_schema.py` 與 `scripts/index_hierarchical.py` 呼叫 Clean Architecture 用例，建立階層式索引。

### CLI equivalents

- 初始化 Schema
  ```bash
  python scripts/init_hierarchical_schema.py --conn $PGVECTOR_URL
  ```

- 遞迴索引資料夾
  ```bash
  python scripts/index_hierarchical.py data/ --recursive --conn $PGVECTOR_URL --force
  ```

### Legacy path

`rag_system/legacy/build_all.sh` 與 `rag_system/legacy/build/` 仍保留以免破壞舊流程，但不再建議使用。

---

## 📦 Database Setup (PostgreSQL + PGVector)

The recommended setup uses Docker Compose.

### 1. Start the Database

```bash
# This command starts a PostgreSQL container named 'rag_db'
# listening on localhost:5433.
docker compose up -d
```

### 2. Verify

```bash
# Check that the container is running and healthy
docker compose ps

# Connect and verify the 'vector' extension is enabled
docker exec -it rag_db psql -U user -d rag_db -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### 3. Stop and Clean Up

```bash
# Stop the container but preserve data
docker compose stop

# Stop and remove the container (data volume is preserved)
docker compose down

# Stop, remove the container, AND delete all data
docker compose down -v
```

For manual installation instructions, refer to the official documentation for PostgreSQL and PGVector.

---

## 🔌 Subgraph Integration

The RAG system is designed to be a self-contained subgraph that can be integrated into a larger multi-agent system.

### Core Concept

The `create_rag_subgraph` function in `rag_system/subgraph.py` returns a compiled LangGraph object. The parent graph delegates tasks to this subgraph, which handles all internal logic and returns the final answer.

### Integration Steps

1.  **Import**: Import `create_rag_subgraph` and `RAGConfig`.
    ```python
    from rag_system.subgraph import create_rag_subgraph
    from rag_system.config import RAGConfig
    ```

2.  **Initialize**: Create the RAG configuration and the subgraph node.
    ```python
    llm = ChatOpenAI(model="your-model")
    rag_config = RAGConfig.from_env()
    rag_node = create_rag_subgraph(llm, rag_config, name="rag_expert")
    ```

3.  **Add to Graph**: Add the `rag_node` to your supervisor graph.
    ```python
    supervisor_graph.add_node("rag_expert", rag_node)
    ```

4.  **Route**: Create conditional edges in your supervisor to route tasks to the `rag_expert` node.
    ```python
    supervisor_graph.add_conditional_edges(
        "router_node",
        lambda state: "rag_expert" if should_delegate(state) else "other_tool",
        {"rag_expert": "rag_expert", "other_tool": "other_tool_node"}
    )
    supervisor_graph.add_edge("rag_expert", "supervisor_evaluator_node")
    ```

### Data Flow

-   **Input**: The user's question should be the last message in the `messages` list of the graph state.
-   **Output**: The subgraph's answer is placed in the `generation` field of the state.

---
**Last Updated**: 2025-10-08
