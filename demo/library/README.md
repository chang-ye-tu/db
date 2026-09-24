# 📚 圖書館借閱管理系統（教師示範專題）

<a href="https://colab.research.google.com/github/chang-ye-tu/db/blob/master/demo/library/library.ipynb" target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/></a>

一個「**做完了的專題**」長什麼樣——共同要求 10 條（[projects.md](../../projects.md) §2）全數達標的完整示範，兼作教師錄影腳本。
**本題不在指派清單內**：請模仿它的結構與完成度，不要抄它的程式（報告時任指一段要能解釋）。

## 內容一覽

| 節 | 內容 | 對應共同要求 |
|---|---|---|
| §1–§2 | 訪談稿 → 名詞動詞分析 → ER → 4 表 DDL（含部分唯一索引）＋約束踩點 | 1 |
| §3 | 固定 seed 合成 13,000+ 列（長尾、學期節律、右偏逾期）＋庫存對帳 | 2 |
| §4 | CRUD 資料層：借書／還書（喚醒預約）／續借／預約／辦證⋯⋯全部 `?` 傳值＋交易 | 3、4 |
| §5 | **兩條連線搶最後一本書**：先重現超賣，再用條件式 UPDATE 防護 | 4 |
| §6 | 報表 ×6（window ×2、join ×4、matplotlib 圖 ×2） | 5 |
| §7 | `EXPLAIN QUERY PLAN` ＋ 索引前後計時 | 6 |
| §8 | Gradio 三分頁（流通櫃台／後台管理／統計報表） | 7 |
| §9 | 測試總驗收 13 項（含日期格式與歷史借閱 FK 的失敗案例） | 8 |
| §10–§11 | AI 使用說明（示範寫法）＋12 分鐘六步 demo 腳本與三層備援 | 9、10 |

## 怎麼跑

Colab 開啟 → `執行階段 → 全部執行`（約 1 分鐘；資料固定 seed，人人相同）。
資料生成與借還／逾期判斷共用 `DEMO_TODAY = "2026-11-15"`；介面的業務日期可改，但須輸入 `YYYY-MM-DD`，因此不受真正執行日影響。
最後一格 `app.launch()` 會內嵌可操作介面；報告情境可改 `share=True` 取得臨時公開網址。

對應題型：「借還・流轉・狀態」類系統的完成度標竿。
