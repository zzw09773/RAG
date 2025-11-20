# 🗺️ 法規 RAG 系統 - 精簡路線圖

**專案版本**: v0.3.0 | **目標版本**: v1.0.0 (2026 Q2)  
**定位**: 專注於中文法律文件的階層式 RAG 服務，聚焦索引品質、Notebook 體驗與模組化整合。舊有 DATCOM/UAV 相關規劃已退場。

---

## 🎯 願景與成功指標
- 建立可追溯、節省 Token 的法律檢索助手，支援 Notebook、微服務或自動化流程。
- 量化目標 (v1.0.0):
  - 測試覆蓋率 ≥ 80%
  - Notebook 預設流程可在 5 分鐘內完成首次查詢
  - 查詢成功率 ≥ 95%
  - 引用區塊 100% 附帶檢索來源

---

## 📊 目前進度
- **階段**: Phase 1 (現代化基礎) 開發中。
- **已完成**:
  - `workflow.py` 模組化，Notebook (`notebooks/legal_rag_workflow.ipynb`) 成為主工作流。
  - Router / Retrieve 工具全面改為法律語境命名。
- **待完成**:
  - 補強測試、文件同步更新、Notebook + CLI 共用設定的自動驗證。

---

## 🛣️ 里程碑概覽

| Phase | 時間 | 核心目標 | 主要交付物 | 狀態 |
| --- | --- | --- | --- | --- |
| **v0.4.0**<br>現代化基礎 | 2025/10 – 2025/11 | 完成模組化、Notebook 化、測試骨架 | Notebook 範本、workflow API、pytest 基礎、引用檢查 | 進行中 |
| **v0.6.0**<br>檢索品質 | 2025/12 – 2026/01 | 加強階層式檢索、評估與調參工具 | summary-first 調校儀表板、檢索對比腳本、metrics 儲存 | 排程中 |
| **v0.8.0**<br>協作擴充 | 2026/02 – 2026/03 | 回饋循環、權限模型、監控 | 使用者評分 API、角色權限、Prometheus/Grafana | 排程中 |
| **v1.0.0**<br>產品化發布 | 2026/04 – 2026/05 | 高可用部署、治理要求 | K8s 部署腳本、壓力測試、操作手冊 | 排程中 |

---

## 🔍 里程碑重點

### Phase 1 – 現代化基礎 (v0.4.0)
**焦點**
- 模組化：`workflow.py` 提供 create_llm / create_rag_workflow / run_query。CLI 僅作相容層。
- Notebook：`notebooks/legal_rag_workflow.ipynb` 展示完整流程，含設定、查詢、除錯。
- 測試：針對 router / retrieve / citation 流程建立 pytest，覆蓋率達 50%+。
- 文件：README、Developer Guide、ROADMAP 皆更新為法律 RAG 語境。

**成功條件**
- Notebook 只需 `.env` 即可執行查詢。
- Router/ Retrieve 工具名稱、提示全面對齊法律語境。
- pytest pipeline 穩定，引用區塊測試通過。

### Phase 2 – 檢索品質強化 (v0.6.0)
**焦點**
- 階層式檢索：摘要層 vs 細節層 AB test、回傳結構化 metadata。
- 評估：建立查詢集合、標註工具、Precision/Recall 報表。
- Notebook 插件：可自定義檢索策略（flat/hierarchical/hybrid）。

**成功條件**
- 階層式檢索節省 Token ≥ 30%、回答品質評分 ≥ 4.3/5。
- Notebook 中可一鍵切換檢索策略並查看指標。

### Phase 3 – 協作與可觀察性 (v0.8.0)
**焦點**
- 回饋：Notebook 與 API 皆可提交答案評分。
- 權限：簡易角色/金鑰管理、查詢審計。
- 監控：Prometheus / Grafana 儀表板、OpenTelemetry trace。

### Phase 4 – 產品化 (v1.0.0)
**焦點**
- Kubernetes 部署（含自動擴展、備援）。
- 壓力測試、安全掃描、自動備份。
- 完整操作、維運、遷移文件。

---

## 📈 關鍵指標 (KPI)
- Notebook 啟動→首次回答 < 5 分鐘。
- 引用區塊缺失率 < 1%。
- Test coverage ≥ 80%。
- 重大事件回覆時間 < 30 分鐘。

---

## ✅ 下一步檢核表 (v0.4.0)
1. Notebook / workflow API 實際驗證三次完整 run。
2. Router / Retrieve / Metadata / Article Lookup 完整單元測試。
3. README、Developer Guide、MIGRATION GUIDE 全數去除 DATCOM/設計領域敘述。
4. 整合測試：Notebook ↔ CLI 使用相同設定並產出一致引用。
