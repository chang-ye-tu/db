# 💰 個人記帳分析 MoneyBook（教師示範專題）

<a href="https://colab.research.google.com/github/chang-ye-tu/db/blob/master/demo/moneybook/moneybook.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

第二個「**做完了的專題**」——流水帳＋統計分析型系統的完成度標竿，共同要求 10 條（[projects.md](../../projects.md) §2）全數達標，兼作教師錄影腳本。
**本題不在指派清單內**：請模仿它的結構與完成度，不要抄它的程式。

## 內容一覽

| 節 | 內容 | 對應共同要求 |
|---|---|---|
| §1–§2 | 訪談稿 → 設計決策（金額恆正＋分類的 `sign`、期初餘額不是收入、只有信用卡可負的跨欄 CHECK、刪除策略）→ schema 圖 → 4 表 DDL＋約束踩點 | 1 |
| §3 | 固定 seed 合成三年流水約 12,000 筆（長尾、星期與時段、季節、餐費通膨、每週與每月帳戶結清）＋逐筆累加的餘額稽核＋兩張圖 | 2 |
| §4 | CRUD：記一筆／更正／刪除（餘額同步回沖，先讀後寫用 `BEGIN IMMEDIATE`）／轉帳（rollback 示範）／設預算（UPSERT）／分類管理（外鍵擋下＋預算連鎖刪除） | 3、4 |
| §5 | **兩支手機同時記帳**：lost update 重現 → `BEGIN IMMEDIATE` 防護 | 4 |
| §6 | 報表 ×6（累積結餘、移動平均、本月預算、預算達成紀錄、星期 × 時段、`PERCENT_RANK`）＋圖 ×2 | 5 |
| §7 | 先量出最慢的查詢 → `EXPLAIN QUERY PLAN` → 複合索引 (cat_id, at) → 前後計時 | 6 |
| §8 | Gradio 三分頁（日常記帳／後台管理／統計報表），每次操作各開一條連線 | 7 |
| §9 | 測試總驗收 14 個 assert（其中 7 個應該失敗，並確認失敗後資料沒被改到），可重跑 | 8 |
| §10 | 十二分鐘簡報腳本（照 projects.md 的五段）與三層備援 | 10 |
| §11 | AI 使用說明（示範寫法，放在 notebook 最後） | 9 |

## 怎麼跑

Colab 開啟 → `執行階段 → 全部執行`（約 1–2 分鐘；seed=7 可重現）。
資料與預算共用 `DEMO_TODAY = "2026-11-15"`，且預算涵蓋 `2026-11`；介面日期須輸入 `YYYY-MM-DD`，記一筆後會立即刷新本月預算表。
§8 的 `app.launch()` 內嵌可操作介面；報告情境可改 `share=True`。
全本只用 sqlite3、numpy（合成資料）、matplotlib（兩張圖）與 Gradio；查詢與彙整都在 SQL 裡完成，沒有用 pandas。

對應題型：「交易流水＋快照＋分析」類系統；與 library 示範互補（超賣 vs lost update 兩種競態、條件式 UPDATE vs `BEGIN IMMEDIATE` 兩種防護）。
