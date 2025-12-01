# RAG 系統快速入門

## 目前環境狀態 ✓

- ✅ Python 環境已就緒 (Python 3.11.7 + Anaconda)
- ✅ 所有依賴套件已安裝
- ✅ PostgreSQL + pgvector 資料庫已啟動
- ✅ vector (v0.8.1) 與 ltree (v1.3) 擴展已安裝
- ✅ 環境變數已配置 (`.env` 已修正)

## 下一步:初始化資料庫 Schema

在開始索引文件之前,需要先建立 RAG 系統所需的表格結構。直接開啟 `notebooks/1_build_index.ipynb`, 執行初始化 cell (`init_hierarchical_schema`) 即可。舊的 CLI scripts 已移除。

## 使用 Notebook 建立索引

### 1. 啟動 Jupyter（請在 repo 根目錄執行，Notebook 會自動加入 repo root 到 sys.path）

```bash
# 確保在虛擬環境中
cd /home/c1147259/桌面/RAG/RAG
jupyter notebook
```

### 2. 開啟 `notebooks/1_build_index.ipynb`

這個 notebook 會引導你完成:
1. 初始化階層式 Schema
2. 收集並批次索引 `data/input` 下的文件 (md/txt/pdf/docx/rtf，可在 Notebook 調整 `data_root`)
3. 執行階層式文件解析與向量化
4. 寫入 PostgreSQL

### 3. 開啟 `notebooks/2_query_verify.ipynb`

索引建立後,使用這個 notebook:
1. 載入 RAG workflow
2. 執行法律文件查詢
3. 驗證回答品質與引用來源
> Notebook 開頭會將 repo 根目錄與 `venv` 的 site-packages 加入 `sys.path`，若未選到 venv kernel 仍可匯入模組。

## 程式化使用範例

```python
from dotenv import load_dotenv
load_dotenv('.env')

from rag_system.workflow import create_llm, create_rag_workflow, run_query
from rag_system.config import RAGConfig

# 載入配置
config = RAGConfig.from_env()
config.validate()

# 建立 workflow (使用階層式檢索)
workflow = create_rag_workflow(config, use_hierarchical=True)

# 執行查詢
result = run_query(
    question="勞基法第 30 條規定為何?",
    config=config,
    use_hierarchical=True
)

# 顯示結果
print("回答:", result["generation"])
print("\n引用文件:")
for doc in result["retrieved_docs"]:
    print(f"  - {doc.metadata.get('source', 'Unknown')}")
```

## 常見問題

### Q: 環境變數沒有載入?

**A**: 在 Python 中使用 `python-dotenv`:

```python
from dotenv import load_dotenv
load_dotenv('/home/c1147259/桌面/RAG/RAG/.env')
```

### Q: 資料庫連線失敗?

**A**: 檢查資料庫是否在運行:

```bash
docker compose ps
# 應該看到 rag_db 處於 "Up (healthy)" 狀態

# 如果未啟動,執行:
docker compose up pgvector -d
```

### Q: 如何停止資料庫?

```bash
# 停止但保留資料
docker compose stop

# 停止並移除容器 (保留 volume)
docker compose down

# 完全清除 (包含所有資料)
docker compose down -v
```

## 相關文件

- [CLAUDE.md](CLAUDE.md):完整架構說明與開發指南
- [README.md](README.md):專案概述
- [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md):詳細開發指南

---

**提示**:建議從 `notebooks/1_build_index.ipynb` 開始,這是最直覺的使用方式!
