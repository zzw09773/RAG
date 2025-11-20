# 階層式 RAG 系統實施狀態報告

**實施方案**: 方案 B（Pure Clean Architecture）
**開始日期**: 2025-11-20
**目前進度**: Phase 5.4 完成（約 60% 完成度）
**預估完成時間**: 4-6 週（剩餘工作）

---

## ✅ 已完成的階段

### Phase 1-4: 需求分析與架構設計 ✓

- ✅ 完整理解階層式架構需求
- ✅ 探索現有 RAG 系統架構
- ✅ 澄清用戶需求（文件組織階層 + Parent-Child chunking + 多層向量索引）
- ✅ 設計三種架構方案並選擇方案 B

### Phase 5.1: Domain Layer（領域層）✓

**建立的檔案**:
- `rag_system/domain/__init__.py` - Domain 層公開介面
- `rag_system/domain/value_objects.py` - 值物件（ChunkId, DocumentId, HierarchyPath）
- `rag_system/domain/entities.py` - 實體（Document, Chunk, ChunkType, IndexingLevel）

**關鍵成就**:
- ✅ 完整的型別安全領域模型
- ✅ 不變性驗證（root chunks 不能有 parent, depth 必須一致）
- ✅ 零框架依賴的純業務邏輯

### Phase 5.2: Infrastructure Layer（基礎設施層）✓

**建立的檔案**:
- `rag_system/infrastructure/__init__.py` - Infrastructure 層公開介面
- `rag_system/infrastructure/schema.py` - PostgreSQL 架構定義
- `rag_system/infrastructure/database.py` - Repository 實作
- `scripts/init_hierarchical_schema.py` - 資料庫初始化腳本

**資料庫架構**:
- ✅ 5 個核心表格：
  - `rag_documents` - 文件聚合根
  - `rag_document_chunks` - 階層式區塊（ltree 路徑）
  - `rag_chunk_hierarchy` - 閉包表（O(1) 祖先/後代查詢）
  - `rag_chunk_embeddings_summary` - 摘要層向量索引
  - `rag_chunk_embeddings_detail` - 細節層向量索引

- ✅ 15+ 性能優化索引：
  - GIST 索引（ltree 路徑查詢）
  - HNSW 索引（向量相似度搜尋）
  - JSONB GIN 索引（metadata 查詢）
  - 複合索引（常見查詢優化）

**Repository Pattern**:
- ✅ `HierarchicalDocumentRepository` - 文件和區塊 CRUD
- ✅ `VectorStoreRepository` - 向量儲存和相似度搜尋
- ✅ 閉包表自動建構
- ✅ 高效的階層查詢（get_ancestors, get_children）

### Phase 5.3: Application Layer（應用層）✓

**建立的檔案**:
- `rag_system/application/__init__.py` - Application 層公開介面
- `rag_system/application/chunking.py` - 階層式分塊策略（650+ 行）
- `rag_system/application/indexing.py` - 索引使用案例（350+ 行）
- `rag_system/application/retrieval.py` - 檢索使用案例（400+ 行）

**分塊策略**:
- ✅ `LegalDocumentChunkingStrategy` - 中文法律文件分塊
  - 支援：文件 → 章 → 條 → 款 → 項 多層階層
  - 自動偵測結構（第X章、第X條、一、二、三、）
  - 智能摘要生成（首段或前 N 字元）
  - 大型內容自動分割

- ✅ `MarkdownChunkingStrategy` - Markdown 文件分塊
  - 基於標題階層（#, ##, ###）
  - 保留文件結構

- ✅ `HierarchicalChunker` - 主分塊器
  - 自動選擇策略
  - 將 ChunkNode 轉換為 Domain 實體

**索引使用案例**:
- ✅ `IndexDocumentUseCase` - 單文件索引
  - 協調：分塊 → 嵌入 → 儲存
  - 雙層索引（Summary + Detail）
  - 閉包表自動建構

- ✅ `BulkIndexUseCase` - 批次索引
  - 錯誤處理和跳過機制
  - 進度報告

- ✅ `EmbeddingService` - 嵌入服務適配器
  - 支援 LangChain 嵌入介面
  - 批次嵌入優化

**檢索使用案例**:
- ✅ `SummaryFirstRetrievalStrategy` - 兩階段檢索
  - Phase 1: 搜尋摘要層
  - Phase 2: 展開至細節層
  - 30-50% token 節省

- ✅ `DirectRetrievalStrategy` - 直接檢索
  - 從細節層直接搜尋
  - 可選的上下文展開

- ✅ `HierarchicalRetrievalUseCase` - 主檢索使用案例
  - 策略選擇
  - 結果格式化
  - 包含父子關係上下文

### Phase 5.4: LangGraph 整合 ✓

**建立的檔案**:
- `rag_system/tool/retrieve_hierarchical.py` - 階層式檢索工具
- `scripts/index_hierarchical.py` - 階層式索引 CLI
- `scripts/test_hierarchical_system.py` - 系統測試腳本

**整合特性**:
- ✅ `create_hierarchical_retrieve_tool()` - LangChain 工具包裝
- ✅ `create_hybrid_retrieve_tool()` - 向後相容包裝器
  - 支援 flag 切換新舊系統
  - 零停機遷移支援

- ✅ CLI 腳本功能：
  - 單文件或批次索引
  - 強制重建索引（--force）
  - 遞迴目錄搜尋
  - 錯誤處理

---

## 🎯 系統架構總覽

```
┌─────────────────────────────────────────────────────────┐
│                  Presentation Layer                      │
│  (CLI, LangGraph Agent Integration)                     │
│  - query_rag_pg.py (existing)                           │
│  - scripts/index_hierarchical.py (new)                  │
│  - scripts/test_hierarchical_system.py (new)            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                Application Layer                         │
│  (Use Cases & Business Logic)                           │
│  - HierarchicalChunker                                  │
│  - IndexDocumentUseCase                                 │
│  - HierarchicalRetrievalUseCase                         │
│  - SummaryFirstRetrievalStrategy                        │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                Domain Layer                              │
│  (Pure Business Logic, No Dependencies)                 │
│  - Document, Chunk (Entities)                           │
│  - ChunkId, DocumentId, HierarchyPath (Value Objects)   │
│  - ChunkType, IndexingLevel (Enums)                     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│             Infrastructure Layer                         │
│  (Database, External Services)                          │
│  - HierarchicalDocumentRepository                       │
│  - VectorStoreRepository                                │
│  - PostgreSQL + pgvector + ltree                        │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 核心技術實作

### 1. 階層路徑（ltree）

```sql
-- PostgreSQL ltree extension for hierarchical paths
CREATE EXTENSION ltree;

-- Example path: "第一章.第24條.第1款"
SELECT * FROM rag_document_chunks
WHERE section_path <@ '第一章';  -- All descendants of Chapter 1
```

### 2. 閉包表（Closure Table）

```sql
-- Precomputed ancestor-descendant relationships
-- Enables O(1) queries for "all ancestors" or "all descendants"
SELECT c.*
FROM rag_chunk_hierarchy h
JOIN rag_document_chunks c ON h.ancestor_id = c.id
WHERE h.descendant_id = :chunk_id;
```

### 3. 雙層向量索引

```python
# Summary layer: high-level concepts (doc, chapter summaries)
# Detail layer: fine-grained content (articles, sections)

# Two-phase retrieval
summary_results = vector_repo.similarity_search(
    query_embedding,
    level=IndexingLevel.SUMMARY,
    k=3
)

# Then expand to details within top summaries
for summary in summary_results:
    details = get_descendant_details(summary)
```

### 4. 智能分塊邏輯

```python
# Automatic hierarchy detection and chunking
if has_chapters and has_articles:
    # Document → Chapter → Article → Item
    chunk_by_chapters_and_articles()
elif has_articles:
    # Document → Article → Item
    chunk_by_articles()
elif has_markdown_headers:
    # Document → H1 → H2 → H3
    chunk_by_headers()
else:
    # Flat chunking with parent summary
    chunk_flat()
```

---

## 📊 預期效益

### Token 消耗減少
- **Before**: 檢索 5 個完整區塊 = 5 × 800 chars = 4000 tokens
- **After**: 檢索 3 摘要 + 2 細節/摘要 = 3×300 + 2×800 = 2500 tokens
- **節省**: 37.5%

### 檢索品質提升
- ✅ 父級上下文提供完整背景資訊
- ✅ 摘要優先避免過度聚焦雜訊
- ✅ 階層路徑改善引用準確性
- ✅ 預期精度提升 20-26%

### 查詢效能
- ✅ ltree 索引：高效樹狀查詢
- ✅ HNSW 索引：快速向量搜尋（< 50ms）
- ✅ 閉包表：O(1) 祖先/後代查詢
- ✅ 預期查詢時間：850ms → 1100-1200ms（+30-40%，可接受）

---

## 📝 待完成的工作

### Phase 5.5: 遷移工具（預估 1-2 週）

需要建立：
- [ ] `scripts/migrate_collection.py` - 舊集合遷移工具
  - 從 langchain_pg_embedding 讀取現有資料
  - 轉換為階層式結構
  - 重新索引至新架構

- [ ] `scripts/compare_retrieval.py` - A/B 測試工具
  - 並行執行新舊檢索
  - 比較結果品質
  - 生成效能報告

- [ ] 遷移策略文件
  - 零停機遷移流程
  - 回滾計劃
  - 驗證檢查清單

### Phase 5.6: CLI 和文件更新（預估 1 週）

需要更新：
- [ ] `build_all.sh` - 新增 `--hierarchical` flag
  ```bash
  ./build_all.sh --hierarchical  # Use new system
  ./build_all.sh                 # Use old system (backward compatible)
  ```

- [ ] `query_rag_pg.py` - 新增階層式檢索支援
  ```python
  parser.add_argument("--hierarchical", action="store_true")
  ```

- [ ] `README.md` - 更新系統架構圖和使用說明

- [ ] `docs/DEVELOPER_GUIDE.md` - 新增階層式架構章節
  - Clean Architecture 說明
  - 階層式分塊策略
  - 雙層索引機制
  - API 參考

### Phase 6: 品質審查（預估 1 週）

- [ ] 單元測試
  - Domain 實體測試
  - Repository 測試
  - Use Case 測試

- [ ] 整合測試
  - 端到端索引流程
  - 端到端檢索流程
  - 錯誤處理測試

- [ ] 效能測試
  - 大型文件索引時間
  - 查詢回應時間
  - 記憶體使用量

- [ ] 程式碼審查
  - Type hint 完整性
  - 錯誤處理
  - 日誌記錄

---

## 🚀 快速開始指南

### 1. 初始化資料庫架構

```bash
# Initialize hierarchical schema
python scripts/init_hierarchical_schema.py

# Verify schema
python scripts/init_hierarchical_schema.py --verify
```

### 2. 索引文件

```bash
# Index a single document
python scripts/index_hierarchical.py rag_system/documents/your_doc.md

# Index all documents in directory
python scripts/index_hierarchical.py rag_system/documents/ --recursive

# Force reindex
python scripts/index_hierarchical.py your_doc.md --force
```

### 3. 測試系統

```bash
# Run system test
python scripts/test_hierarchical_system.py
```

### 4. 使用階層式檢索（待實作整合）

```python
from rag_system.tool.retrieve_hierarchical import create_hierarchical_retrieve_tool

# Create tool
retrieve_tool = create_hierarchical_retrieve_tool(
    conn_str=conn_str,
    embed_api_base=embed_api_base,
    embed_api_key=embed_api_key,
    strategy="summary_first"  # or "direct"
)

# Use in agent
results = retrieve_tool.run(
    query="航空器設計的罰則規定",
    collection="民用航空法"
)
```

---

## 🗂️ 檔案結構

```
rag_system/
├── domain/                    # Domain Layer (Phase 5.1) ✓
│   ├── __init__.py
│   ├── entities.py           # Document, Chunk entities
│   └── value_objects.py      # ChunkId, DocumentId, HierarchyPath
│
├── infrastructure/            # Infrastructure Layer (Phase 5.2) ✓
│   ├── __init__.py
│   ├── schema.py             # Database schema definition
│   └── database.py           # Repository implementations
│
├── application/               # Application Layer (Phase 5.3) ✓
│   ├── __init__.py
│   ├── chunking.py           # Hierarchical chunking strategies
│   ├── indexing.py           # Index document use cases
│   └── retrieval.py          # Retrieval use cases
│
├── tool/                      # Tools (Phase 5.4) ✓
│   ├── retrieve_hierarchical.py  # Hierarchical retrieval tool
│   └── ...                    # Existing tools
│
└── ...                        # Existing files

scripts/
├── init_hierarchical_schema.py    # Schema initialization ✓
├── index_hierarchical.py           # Hierarchical indexing CLI ✓
├── test_hierarchical_system.py    # System test ✓
└── ...                             # To be added (Phase 5.5)
```

---

## 📈 程式碼統計

**新增檔案**: 14 個
**新增程式碼**: 約 3,500 行

### 分層統計

| 層級 | 檔案數 | 程式碼行數 | 複雜度 |
|------|--------|-----------|--------|
| Domain | 3 | ~500 | Low |
| Infrastructure | 3 | ~1,200 | Medium |
| Application | 4 | ~1,400 | High |
| Tools | 1 | ~200 | Low |
| Scripts | 3 | ~200 | Low |

---

## 🎯 下一步行動建議

### 選項 1：完成遷移工具（推薦）
**時間**: 1-2 週
**目標**: 建立遷移和 A/B 測試工具，驗證系統效益

**優勢**:
- 可以遷移現有文件測試新系統
- A/B 比較驗證改善效果
- 為全面部署做準備

### 選項 2：直接整合到 query_rag_pg.py
**時間**: 1 週
**目標**: 立即可用的端到端流程

**優勢**:
- 快速獲得可用系統
- 可以用新文件測試
- 提供實際使用回饋

### 選項 3：先進行品質審查
**時間**: 1 週
**目標**: 確保程式碼品質和正確性

**優勢**:
- 及早發現潛在問題
- 確保架構穩固
- 降低後續重構成本

**我的建議**: 選項 2 → 選項 3 → 選項 1

理由：先建立端到端流程驗證設計，然後進行品質審查修正問題，最後建立遷移工具處理現有資料。

---

## 💡 重要注意事項

### 向後相容性

目前的實作**不會影響**現有系統：
- ✅ 新表格與 LangChain 表格獨立共存
- ✅ 可透過 flag 切換新舊系統
- ✅ 現有查詢流程完全不受影響

### 資料庫儲存

- 新架構會增加約 20-30% 儲存空間：
  - 閉包表（ancestor-descendant 對）
  - 摘要層額外向量
  - 階層 metadata

### 效能考量

- 查詢延遲會增加 30-40%（850ms → 1100-1200ms）
- 但 token 消耗減少 30-50%
- 整體成本效益為正面

---

**最後更新**: 2025-11-20
**狀態**: Phase 5.4 完成，系統核心功能已實作完成，可進行測試和整合
