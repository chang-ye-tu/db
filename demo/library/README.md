# 📚 圖書館借閱管理系統（教師示範專題）

<a href="https://colab.research.google.com/github/chang-ye-tu/db/blob/master/demo/library/library.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

一個「**做完了的專題**」長什麼樣——共同要求 10 條（[projects.md](../../projects.md) §2）全數達標的完整示範，兼作教師錄影腳本。
**本題不在指派清單內**：請模仿它的結構與完成度，不要抄它的程式（報告時任指一段要能解釋）。

## 內容一覽

| 節 | 內容 | 對應共同要求 |
|---|---|---|
| §1–§2 | 訪談稿 → 名詞動詞分析 → 設計決策 → schema 圖 → 4 表 DDL（含兩個部分唯一索引）＋約束踩點 | 1 |
| §3 | 固定 seed：兩萬次借書需求逐筆模擬（架上有書才借得到；越熱門的書館方買越多冊）→ 約一萬七千筆借閱（長尾、學期節律、右偏借期）＋三條 SQL 稽核＋兩張圖 | 2 |
| §4 | CRUD 資料層：借書（rollback 示範）／還書（喚醒預約）／續借／預約與取消預約（狀態標記，不刪列）／辦證、改 email、退證／入館、調整冊數、刪除書目（外鍵擋下）——全部 `?` 傳值＋交易，先讀後寫的操作用 `BEGIN IMMEDIATE` | 3、4 |
| §5 | **兩條連線搶最後一本書**：先重現超賣，再用條件式 UPDATE 防護 | 4 |
| §6 | 報表 ×5（window ×2、多表 join ×3）＋圖 ×2，每張附「它回答什麼問題」 | 5 |
| §7 | 先量出最慢的查詢 → `EXPLAIN QUERY PLAN` → 建索引 → 前後計時 | 6 |
| §8 | Gradio 三分頁（流通櫃台／後台管理／統計報表），每次操作各開一條連線 | 7 |
| §9 | 測試總驗收 13 個 assert（其中 8 個應該失敗），可重跑 | 8 |
| §10 | 十二分鐘簡報腳本（照 projects.md 的五段）與三層備援 | 10 |
| §11 | AI 使用說明（示範寫法，放在 notebook 最後） | 9 |

## 怎麼跑

Colab 開啟 → `執行階段 → 全部執行`（約 1–2 分鐘；第一個程式格安裝 Gradio 與中文字型；資料固定 seed，人人相同）。
資料生成與借還／逾期判斷共用 `DEMO_TODAY = "2026-11-15"`；介面的業務日期可改，但須輸入 `YYYY-MM-DD`，因此不受真正執行日影響。
§8 的 `app.launch()` 會內嵌可操作介面；報告情境可改 `share=True` 取得臨時公開網址。
全本只用 sqlite3、numpy（合成資料）、matplotlib（兩張圖）與 Gradio；查詢與彙整都在 SQL 裡完成，沒有用 pandas。

對應題型：「借還・流轉・狀態」類系統的完成度標竿。
