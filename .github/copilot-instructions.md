# GitHub Copilot 專案指令

## 專案概述

這是一個基於 PostgreSQL + pgvector 的法律文件 RAG (Retrieval-Augmented Generation) 系統，透過階層式索引與 LangGraph Agent 執行檢索與回答。

## 技術堆疊

- **語言**: Python 3.11+
- **AI 框架**: LangGraph, LangChain
- **LLM**: OpenAI (gpt-oss-20b)
- **向量資料庫**: PostgreSQL with pgvector extension
- **文件處理**: python-docx, markdown
- **嵌入模型**: nvidia/nv-embed-v2

## 專案架構

### 核心模組結構
```
rag_system/
├── agent.py          # LangGraph agent 主邏輯
├── state.py          # Agent 狀態管理
├── node.py           # Graph 節點定義
├── subgraph.py       # 子圖定義
├── config.py         # 配置管理
├── build/            # 文件處理與索引建立
│   ├── document_parser.py
│   ├── chunking.py
│   ├── indexer.py
│   └── db_utils.py
└── tool/             # Agent 工具集
    ├── retrieve.py
    ├── calculator.py
    ├── metadata_search.py
    └── router.py
```

## 編碼規範

### Python 風格
- 遵循 PEP 8 規範
- 使用 type hints 標註函數參數和返回值
- 文檔字串使用 Google 風格
- 變數命名: 使用 snake_case
- 類別命名: 使用 PascalCase

### 文檔註解
```python
def example_function(param1: str, param2: int) -> dict:
    """
    簡短描述函數功能。
    
    Args:
        param1: 參數1說明
        param2: 參數2說明
    
    Returns:
        返回值說明
    
    Raises:
        ExceptionType: 異常說明
    """
    pass
```

### LangGraph Agent 開發規範

**開發哲學 (遵循 Linus Torvalds 原則)**:
1. **"Is this a real problem or imagined?"** - 拒絕過度工程
2. **"Is there a simpler way?"** - 尋找最簡單可行的解決方案
3. **"Will it break anything?"** - 絕不破壞現有程式碼

#### 核心規範

1. **狀態定義** (`state.py`):
   - **優先使用 `MessagesState`** - 通常已經足夠
   - 不要發明複雜的數據結構
   - 使用 TypedDict 定義狀態結構
   - 包含 `messages`, `metadata`, `context` 等欄位
   - 使用 Annotated 進行狀態合併邏輯定義

2. **節點函數** (`node.py`):
   - 節點函數必須接收 `state` 參數
   - **返回部分狀態更新 (dict),不是完整狀態**
   - 使用清晰的命名: `retrieve_node`, `generate_node`, `route_node`
   - 函數應少於 20 行
   - 最多 3 層縮排
   - 一個節點一個職責
   
   ```python
   # CORRECT: 返回更新的字典
   def my_node(state: State) -> Dict[str, Any]:
       return {
           "field_name": extracted_string,
           "messages": updated_message_list
       }
   ```

3. **Agent 建立優先級**:
   - **優先使用 `create_react_agent`** - 適用於基本工具調用、Q&A、標準聊天
   - **只在以下情況建立自訂 `StateGraph`**:
     - 複雜分支邏輯
     - 多 agent 協調
     - 進階串流模式
     - 使用者明確要求客製化工作流程
   
   ```python
   # CORRECT: 簡單且可部署
   from langgraph.prebuilt import create_react_agent
   
   graph = create_react_agent(model=model, tools=tools, prompt="instructions")
   app = graph  # 必須的導出名稱
   ```

4. **工具開發** (`tool/`):
   - 每個工具都是獨立的 Langchain Tool
   - 使用 `@tool` 裝飾器定義
   - 提供清晰的 tool description 給 LLM
   - 工具名稱使用 snake_case: `retrieve_documents`, `calculate_formula`

5. **部署優先規則**:
   - **不要添加 checkpointer** 除非明確要求 - 大多數應用不需要持久化狀態
   - **模型優先級**: Anthropic > OpenAI > Google
   - 必須導出 `app = graph`

6. **常見錯誤避免**:
   - ❌ 將 message 物件當成字串 → ✅ 使用 `.content` 提取內容
   - ❌ 返回完整狀態 → ✅ 只返回更新的字典
   - ❌ 可以用 `create_react_agent` 時建立複雜 StateGraph → ✅ 使用預建組件
   - ❌ 將 `interrupt()` 當成同步函數 → ✅ 理解它是暫停按鈕

### 資料庫操作

1. **連接管理**:
   - 使用 psycopg2 進行 PostgreSQL 連接
   - 使用 context manager 管理連接生命週期
   - 配置從環境變數或 `config.py` 讀取

2. **向量搜尋**:
   ```python
   # 使用 pgvector 的 <=> 運算符進行相似度搜尋
   cursor.execute("""
       SELECT content, metadata, 1 - (embedding <=> %s) as similarity
       FROM documents
       ORDER BY embedding <=> %s
       LIMIT %s
   """, (query_embedding, query_embedding, k))
   ```

3. **Metadata 過濾**:
   - 支援 section_type, chapter, document_name 過濾
   - 使用 JSONB 查詢語法

### 文件處理規範

1. **支援格式**: 
   - DOCX (主要格式)
   - Markdown (處理後格式)

2. **Chunking 策略**:
   - 基於語義邊界切分 (章節、段落)
   - 保留文件結構元數據
   - Chunk size: 500-1500 字元 (可配置)
   - 重疊: 100-200 字元

3. **Metadata 保存**:
   ```python
   metadata = {
       "document_name": str,
       "section_type": str,  # formula, example, theory, etc.
       "chapter": str,
       "page_number": int,
       "chunk_id": str
   }
   ```

## 特定領域知識

- 法律條文與條號查詢需保持條號、法規名稱、版本的精確性。
- 檢索與回答需附帶來源（條號或文件標識），確保可追溯。

## 測試規範

- 測試檔案命名: `test_*.py`
- 使用 pytest 框架
- 覆蓋核心功能: 文件解析、向量搜尋、公式計算
- Mock 外部 API 調用 (LLM, Embedding)

## 環境變數

必要的環境變數:
```bash
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://your-api-base-url
DB_HOST=localhost
DB_PORT=5432
DB_NAME=rag_db
DB_USER=postgres
DB_PASSWORD=your_password
```

## Docker 部署

- 使用 `docker-compose.yaml` 進行容器編排
- PostgreSQL 容器包含 pgvector 擴展
- 初始化腳本: `docker/init/01_create_vector.sql`

## 常見任務

### 添加新工具
1. 在 `rag_system/tool/` 創建新檔案
2. 使用 `@tool` 裝飾器定義工具
3. 在 `agent.py` 中註冊工具
4. 更新文檔

### 修改 Agent 流程
1. 在 `node.py` 定義新節點
2. 在 `agent.py` 更新 graph 連接
3. 測試新流程
4. 更新狀態定義 (如需要)

### 處理新文件類型
1. 在 `build/document_parser.py` 添加解析器
2. 更新 chunking 策略
3. 定義 metadata schema
4. 測試索引建立流程

## 注意事項

- **中文支援**: 所有文字處理需正確處理中文字元
- **Token 管理**: 注意 LLM context window 限制
- **錯誤處理**: 提供清晰的錯誤訊息,特別是資料庫和 API 錯誤
- **日誌記錄**: 使用 logging 模組記錄關鍵操作
- **效能**: 批次處理大量文件時注意記憶體使用

## 參考文件

- LangGraph 文檔: https://langchain-ai.github.io/langgraph/
- LangGraph Streaming: https://langchain-ai.github.io/langgraph/how-tos/stream-updates/
- LangGraph Config: https://langchain-ai.github.io/langgraph/how-tos/pass-config-to-tools/
- LangGraph Concepts: https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/
- pgvector 文檔: https://github.com/pgvector/pgvector
- OpenAI API: https://platform.openai.com/docs
- NVIDIA NV-Embed: https://huggingface.co/nvidia/nv-embed-v2

## 程式碼品味標準

**【品味評級】**
- 🟢 Good Taste: 函數少於 20 行,最多 3 層縮排,單一職責,清晰數據流
- 🟡 Decent: 可接受但有改進空間
- 🔴 Garbage: 過度複雜,需要重構

**評審重點:**
- 函數應少於 20 行
- 最多 3 層縮排
- 每個節點一個職責
- 不要有不必要的狀態欄位
- 清晰的數據流

> "Bad programmers worry about the code. Good programmers worry about data structures."

## AI 輔助指南

當 Copilot 協助開發時:
- **簡單至上**: 尋找最簡單可行的解決方案
- **數據結構優先**: 優先考慮數據結構設計,而非程式碼
- **消除特殊情況**: 找出所有 if/else 分支,思考是否可透過重新設計數據結構來消除
- **避免過度工程**: 拒絕解決不存在的問題
- **可讀性和維護性**: 優先考慮程式碼可讀性和維護性
- **錯誤處理和日誌**: 添加適當的錯誤處理和日誌
- **中文處理**: 考慮中文文件處理的特殊性
- **遵循架構**: 遵循現有的架構模式
- **清晰註解**: 提供清晰的註解說明複雜邏輯
- **測試小組件**: 在建立複雜 graph 之前測試小組件

**決策輸出模式:**

**【核心判斷】**
✅ 值得做: [原因] / ❌ 不值得做: [原因]

**【解決方案】**
如果值得做: 1) 簡化數據結構 2) 消除特殊情況 3) 使用最簡單清晰的方法 4) 確保零破壞

如果不值得做: "這解決了不存在的問題。真正的問題是 [XXX]。"

## 相關指南文件

- `CLAUDE.md`: LangGraph 開發的 Linus Torvalds 風格完整指南
- 本檔案整合了 CLAUDE.md 的核心原則,供 GitHub Copilot 參考
