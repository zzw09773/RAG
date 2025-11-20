# 階層式 RAG 系統遷移指南

本指南說明如何從現有的平面 LangChain 向量儲存遷移到新的階層式 RAG 架構。

## 目錄

1. [遷移前準備](#遷移前準備)
2. [遷移流程](#遷移流程)
3. [驗證與測試](#驗證與測試)
4. [回滾方案](#回滾方案)
5. [常見問題](#常見問題)

---

## 遷移前準備

### 1. 環境檢查

確認系統環境符合要求：

```bash
# 檢查 PostgreSQL 版本 (需要 >= 12)
psql --version

# 檢查擴展是否已安裝
python scripts/init_hierarchical_schema.py --conn "YOUR_CONN_STRING"
```

### 2. 備份現有資料

**重要：遷移前務必備份！**

```bash
# 備份整個資料庫
pg_dump -h localhost -p 65432 -U postgres ASRD_RAG > backup_$(date +%Y%m%d).sql

# 或只備份特定表
pg_dump -h localhost -p 65432 -U postgres ASRD_RAG \
    -t langchain_pg_collection \
    -t langchain_pg_embedding \
    > backup_langchain_$(date +%Y%m%d).sql
```

### 3. 確認源文件可用

遷移過程會重新分塊文件，因此需要保留原始文件：

```bash
# 列出現有集合
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --list

# 預覽特定集合的遷移狀況
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --preview
```

預覽會顯示每個文件的狀態：
- ✓ 表示源文件存在，可以遷移
- ✗ 表示源文件不存在，遷移會失敗

---

## 遷移流程

### 步驟 1: 初始化階層式架構

如果尚未初始化，先建立新的資料庫架構：

```bash
python scripts/init_hierarchical_schema.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG"
```

這會建立以下表格：
- `rag_documents` - 文件聚合根
- `rag_document_chunks` - 階層式區塊
- `rag_chunk_hierarchy` - 閉包表（快速查詢祖先/後代）
- `rag_chunk_embeddings_summary` - 摘要層向量
- `rag_chunk_embeddings_detail` - 細節層向量

### 步驟 2: 試運行遷移

先以 dry-run 模式測試：

```bash
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY" \
    --dry-run
```

Dry-run 模式會：
- ✓ 顯示將會處理的文件
- ✓ 檢查源文件是否存在
- ✓ 預估遷移時間
- ✗ **不會**實際寫入資料庫

### 步驟 3: 執行遷移

確認 dry-run 結果無誤後，執行實際遷移：

```bash
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY" \
    --embedding-dim 4096 \
    --no-verify-ssl
```

遷移過程會：
1. 讀取源文件
2. 使用階層式策略重新分塊
3. 儲存文件和區塊到新架構
4. 建立階層關係（閉包表）
5. 生成雙層向量（摘要 + 細節）

### 步驟 4: 處理失敗的文件

如果某些文件遷移失敗（源文件不存在），您有幾個選擇：

**選項 A: 取得源文件後重試**

```bash
# 只遷移特定文件（補遷移）
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY"
```

遷移工具會自動跳過已遷移的文件。

**選項 B: 強制重新遷移**

```bash
# 使用 --force 重新遷移已存在的文件
python scripts/migrate_to_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --collection-name "law_collection" \
    --embed-api-key "YOUR_API_KEY" \
    --force
```

---

## 驗證與測試

### 1. 檢查遷移完整性

使用驗證腳本檢查資料：

```bash
# 檢查資料庫架構
python scripts/test_hierarchical_system.py
```

或直接查詢：

```sql
-- 檢查文件數量
SELECT COUNT(*) FROM rag_documents;

-- 檢查區塊數量和層級分佈
SELECT
    chunk_type,
    indexing_level,
    COUNT(*) as count
FROM rag_document_chunks
GROUP BY chunk_type, indexing_level;

-- 檢查向量數量
SELECT
    'Summary' as layer,
    COUNT(*) as total_embeddings,
    pg_column_size(embedding) / 4 as dimensions
FROM rag_chunk_embeddings_summary
UNION ALL
SELECT
    'Detail',
    COUNT(*),
    pg_column_size(embedding) / 4
FROM rag_chunk_embeddings_detail;

-- 檢查階層關係
SELECT COUNT(*) as total_relationships
FROM rag_chunk_hierarchy;
```

### 2. 比較平面 vs 階層式檢索

使用比較工具測試檢索品質和性能：

```bash
# 單一查詢測試
python scripts/compare_flat_vs_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --embed-api-key "YOUR_API_KEY" \
    --query "航空器設計需要什麼文件？" \
    --collection-name "law_collection" \
    --k 5
```

比較指標：
- **Token 使用量**：階層式應節省 30-50%
- **檢索時間**：階層式可能稍慢（因兩階段檢索）
- **結果品質**：檢查內容重疊和相關性

### 3. 批次測試

使用測試查詢檔案：

```bash
# 建立測試查詢檔案
cat > test_queries.txt <<EOF
航空器設計需要什麼文件？
違反第3條規定會有什麼罰則？
航空器設計人應具備什麼資格？
設計變更時需要重新申請核准嗎？
EOF

# 執行批次測試
python scripts/compare_flat_vs_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --embed-api-key "YOUR_API_KEY" \
    --queries-file test_queries.txt \
    --collection-name "law_collection"
```

---

## 回滾方案

如果遷移後發現問題，可以使用回滾工具。

### 檢查當前狀態

```bash
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --status
```

### 刪除特定文件

```bash
# Dry-run 預覽
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --document-id "doc_abc123" \
    --dry-run

# 實際刪除
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --document-id "doc_abc123"
```

### 刪除所有階層式資料

```bash
# Dry-run 預覽
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --drop-all \
    --dry-run

# 實際刪除所有文件（保留表結構）
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --drop-all
```

### 完全移除階層式架構

⚠️ **警告：此操作不可逆！**

```bash
python scripts/rollback_hierarchical.py \
    --conn "postgresql+psycopg2://postgres:postgres@localhost:65432/ASRD_RAG" \
    --drop-schema \
    --confirm
```

這會刪除所有階層式表格，但**保留**原始的 LangChain 表格。

### 從備份恢復

如果需要完全恢復：

```bash
# 停止所有連線
psql -h localhost -p 65432 -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='ASRD_RAG';"

# 刪除並重建資料庫
dropdb -h localhost -p 65432 -U postgres ASRD_RAG
createdb -h localhost -p 65432 -U postgres ASRD_RAG

# 恢復備份
psql -h localhost -p 65432 -U postgres ASRD_RAG < backup_20250320.sql
```

---

## 常見問題

### Q1: 遷移需要多長時間？

**答**：取決於文件數量和大小：
- 小型文件（< 10 頁）：約 5-10 秒/文件
- 中型文件（10-50 頁）：約 15-30 秒/文件
- 大型文件（> 50 頁）：約 30-60 秒/文件

主要時間花在：
- 重新分塊：30%
- 向量生成（API 呼叫）：60%
- 資料庫寫入：10%

### Q2: 遷移會影響現有的平面系統嗎？

**答**：不會。階層式系統使用獨立的表格：
- 現有的 `langchain_pg_collection` 和 `langchain_pg_embedding` 保持不變
- 可以同時運行兩個系統
- 建議先測試階層式系統，確認無誤後再淘汰平面系統

### Q3: 如何處理 API 速率限制？

**答**：如果遇到 API 速率限制：

```python
# 方案 1: 分批遷移
# 先遷移部分文件
python scripts/migrate_to_hierarchical.py \
    --conn "..." \
    --collection-name "law_collection" \
    --embed-api-key "..." \
    # 遷移工具會跳過已遷移的文件

# 方案 2: 使用本地模型
# TODO: 未來版本支持本地 embedding 模型
```

### Q4: 向量索引為什麼被註解掉？

**答**：pgvector 的 HNSW 和 ivfflat 索引限制為 2000 維度，而 nv-embed-v2 產生 4096 維度向量。

當前解決方案：
- 使用循序掃描（sequential scan）進行相似度搜尋
- 對於小型資料集（< 1000 區塊）性能可接受

未來選項：
1. 使用 PCA 降維至 2000 維度
2. 升級 pgvector 版本（如果未來支援更高維度）
3. 使用其他向量資料庫（如 Milvus、Qdrant）

### Q5: 階層式分塊策略如何運作？

**答**：階層式策略針對法律文件建立 4 層結構：

1. **Document 層**（深度 0）
   - 整份文件的摘要
   - 索引層級：Summary

2. **Chapter 層**（深度 1）
   - 章節標題 + 章節摘要
   - 索引層級：Summary
   - 模式：`## 第X章 ...`

3. **Article 層**（深度 2）
   - 條文標題 + 條文內容摘要
   - 索引層級：Both（摘要 + 細節）
   - 模式：`### 第 X 條`

4. **Section/Detail 層**（深度 3+）
   - 條文內的段落和細節
   - 索引層級：Detail
   - 模式：段落、列表項目

### Q6: 如何自訂分塊策略？

**答**：可以繼承 `ChunkingStrategy` 基礎類別：

```python
from rag_system.application.chunking import ChunkingStrategy
from rag_system.domain import ChunkType, IndexingLevel

class CustomChunkingStrategy(ChunkingStrategy):
    """自訂分塊策略"""

    def chunk_file(self, file_path: Path, document_id: DocumentId) -> Document:
        # 實作您的分塊邏輯
        pass
```

參考現有的 `LegalDocumentChunkingStrategy` 和 `MarkdownChunkingStrategy`。

### Q7: ltree 路徑中的 seg_xxxxx 是什麼？

**答**：ltree 只支援 ASCII 字元（字母、數字、底線），不支援中文。

解決方案：
- 中文段落使用 MD5 雜湊轉換為 ASCII
- 格式：`seg_[8位MD5]`
- 範例：`"第一章"` → `"seg_5c7a713a"`

完整路徑範例：
```
root.seg_5c7a713a.seg_0de7dcd3
```

對應中文路徑：
```
root/第一章/第24條
```

### Q8: 遷移後如何更新應用程式？

**答**：有兩種整合方式：

**方式 A: 使用新的檢索 CLI**

```bash
# 使用階層式檢索
python scripts/query_hierarchical.py \
    --conn "..." \
    --query "您的問題" \
    --k 5
```

**方式 B: 在現有程式中添加參數**

```bash
# query_rag_pg.py 添加 --hierarchical 選項（待實作）
python query_rag_pg.py \
    --query "您的問題" \
    --hierarchical  # 使用新系統
```

### Q9: Token 節省如何計算？

**答**：Token 節省來自以下機制：

1. **摘要優先檢索**：先搜尋摘要層（較短內容）
2. **階層式內容組合**：
   - 只返回相關的父區塊內容（不是全部）
   - 只返回相關的子區塊內容（不是全部）
   - 過濾不相關的兄弟區塊

計算公式：
```
Token 節省 = (平面系統 tokens - 階層系統 tokens) / 平面系統 tokens × 100%
```

使用比較工具可以看到實際數據。

### Q10: 可以遷移部分文件嗎？

**答**：可以。遷移工具會：
- ✓ 自動跳過已遷移的文件
- ✓ 只處理新文件或使用 `--force` 的文件
- ✓ 支援增量遷移

範例工作流程：
```bash
# 第一批：遷移前 10 個文件
# （手動處理或修改遷移工具）

# 第二批：遷移剩餘文件
python scripts/migrate_to_hierarchical.py \
    --conn "..." \
    --collection-name "law_collection" \
    --embed-api-key "..."
# 會自動跳過已遷移的前 10 個文件
```

---

## 遷移檢查清單

使用此清單確保遷移順利：

### 遷移前
- [ ] 備份資料庫
- [ ] 確認源文件可用
- [ ] 測試環境驗證（先在測試環境遷移）
- [ ] 檢查 API key 有效
- [ ] 執行 dry-run 預覽

### 遷移中
- [ ] 監控遷移進度
- [ ] 記錄任何錯誤訊息
- [ ] 檢查資料庫連線穩定

### 遷移後
- [ ] 執行完整性檢查
- [ ] 驗證資料數量正確
- [ ] 執行測試查詢
- [ ] 比較平面 vs 階層式結果
- [ ] 測量 token 節省量
- [ ] 更新應用程式整合
- [ ] 更新文件

### 生產部署
- [ ] 在測試環境完整驗證
- [ ] 準備回滾計畫
- [ ] 排程維護時間窗口
- [ ] 通知相關人員
- [ ] 監控系統性能
- [ ] 收集使用者反饋

---

## 取得協助

如果遇到問題：

1. 檢查日誌輸出的錯誤訊息
2. 查閱本指南的常見問題
3. 檢查 `HIERARCHICAL_IMPLEMENTATION_STATUS.md` 的技術細節
4. 使用 `--status` 檢查系統狀態
5. 使用 `--dry-run` 模式測試操作

## 相關文件

- [HIERARCHICAL_IMPLEMENTATION_STATUS.md](HIERARCHICAL_IMPLEMENTATION_STATUS.md) - 實作狀態和技術細節
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - 開發者指南
- [README.md](README.md) - 專案概覽

---

最後更新：2025-01-20
