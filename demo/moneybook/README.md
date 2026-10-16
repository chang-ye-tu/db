# 💰 個人記帳分析 MoneyBook（教師示範專題）

<a href="https://colab.research.google.com/github/chang-ye-tu/db/blob/master/demo/moneybook/moneybook.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

第二個「**做完了的專題**」——流水帳＋統計分析型系統的完成度標竿，共同要求 10 條（[projects.md](../../projects.md) §2）全數達標，兼作教師錄影腳本。
**本題不在指派清單內**：請模仿它的結構與完成度，不要抄它的程式。

## 內容一覽

| 節 | 內容 | 對應共同要求 |
|---|---|---|
| §1–§2 | 訪談稿 → 設計決策（金額恆正、信用卡可負的跨欄 CHECK）→ 4 表 DDL＋踩點 | 1 |
| §3 | 固定 seed 合成三年流水 11,000+ 列（長尾、週節律、通膨趨勢、帳戶習慣）＋餘額對帳 | 2 |
| §4 | CRUD：記一筆／轉帳（兩帳戶四動作一交易）／設預算（UPSERT）／刪除回沖 | 3、4 |
| §5 | **兩支手機同時記帳**：lost update 重現 → DB 端算術防護 | 4 |
| §6 | 報表 ×6（累積結餘、佔比、移動平均、預算達成、時段熱點、PERCENT_RANK） | 5 |
| §7 | `EXPLAIN QUERY PLAN` ＋ 複合索引 (cat_id, at) 前後計時 | 6 |
| §8 | Gradio 三分頁（記帳／轉帳與預算／報表） | 7 |
| §9 | 測試總驗收 14 項（含日期與預算月份格式的失敗案例） | 8 |
| §10–§11 | AI 使用說明（示範寫法）＋12 分鐘六步 demo 腳本與三層備援 | 9、10 |

## 怎麼跑

Colab 開啟 → `執行階段 → 全部執行`（約 1 分鐘；seed=7 可重現）。
資料與預算共用 `DEMO_TODAY = "2026-11-15"`，且預算涵蓋 `2026-11`；介面日期須輸入 `YYYY-MM-DD`，新記一筆後會立即刷新同月預算表。
最後一格 `app.launch()` 內嵌可操作介面；報告情境可改 `share=True`。

對應題型：「交易流水＋快照＋分析」類系統；與 library 示範互補（超賣 vs lost update 兩種競態）。
