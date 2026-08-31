# 課程大綱與每週講義大綱

- **課程**：資料庫管理（統計系三年級，54 人）
- **時間**：每週四，50 ＋ 50 ＋ 35 分鐘（三段式：兩節講授＋一節課堂實作）
- **教室**：電腦教室（軟體無法自行安裝 → 全課程使用 **Google Colab**，只需瀏覽器與 Google 帳號）
- **講義**：本 repo `notebooks/unit01.ipynb`–`unit09.ipynb`——**可執行的投影片**，每份就是該週 135 分鐘的完整腳本（講授 ＋ 隨堂練習 ＋ 附錄 cheatsheet）；另有自學補充 `notebooks/extra_modern.ipynb`
- **先修**：Python（U01 課堂自我檢測；不足者依檢測結果補 Beazley [Practical Python Programming](https://github.com/dabeaz-course/practical-python)）
- **教科書（參考用，課堂以講義為準）**：
  - Silberschatz, Korth, Sudarshan, *Database System Concepts*, 7th ed.（章末 Practice Exercises 官方解答：https://www.db-book.com/）
  - Garcia-Molina, Ullman, Widom, *Database Systems: The Complete Book*, 2nd ed.
- **AI 政策**：鼓勵 AI 協作（vibe coding），但**你要能解釋交出的每一行**；專題末尾附「AI 使用說明」。
- **繳交方式（專題）**：Colab「檔案 → 下載 → 下載 .ipynb」，上傳課程平台（iLearn，或依課堂公布）。**不要求使用 GitHub。**

## 課程設計：一條「用」的主線 ＋ 一條「懂」的支線

- **主線（U01–U06）**：SQL → 資料建模 → Python×SQLite → Gradio 應用開發。終點是每人獨立完成一個**指派題目的資料庫應用程式**（詳 [projects.md](projects.md)），期末 15 分鐘簡報含 live demo。
- **支線（U06–U09，教師講授與現場實作示範）**：資料庫內部原理——儲存引擎、索引結構、查詢處理與最佳化、交易與復原、現代資料庫（列式／LSM／向量／文件）。這部分**不要求學生實作**，但會讓你把應用寫得更好，也是專題 Q&A 的觀念基礎。

## 評分

| 項目 | 佔比 | 內容 |
|---|---|---|
| **專題** | **70%** | 詳 [projects.md](projects.md) |
| **平時** | **30%** | 課堂出席與作業等 |

- **專題是唯一的繳交物。** 

## 每週講義大綱（135 分鐘 ＝ 50 ＋ 50 ＋ 35）

> 每份 notebook 都包含：兩節完整講授（含大量可跑範例與**隨堂練習**）＋ 第三節課堂實作 ＋ 附錄 cheatsheet。

### U01（09/10）Python 起手式與資料庫初見面
`notebooks/unit01.ipynb`
- **開場**：課程玩法（70/30、AI 協作政策、Colab 工作流）。
- **第 1 節**：用 Excel/CSV/pandas 管資料的五大慘案（並行遺失、當機半寫、查詢地獄、髒資料、慢）現場重演；DBMS ＝ 資料＋規則＋查詢引擎＋交易引擎；資料庫家族巡禮（SQLite／PostgreSQL／DuckDB／Redis／MongoDB／向量庫）與「怎麼選」；SQL 能做、Excel 很痛的十件事（秀場）。
- **第 2 節**：**Python 速成**（型別、容器、控制流、函數、例外、f-string、comprehension、dict 慣用、class、模組——每段皆「示範＋隨堂練習＋自動檢查器」）；**標準四件套上手**：sqlite3 第一支程式、numpy（default_rng）、pandas（read_sql/to_sql/groupby）、matplotlib（含中文字型 bootstrap）；宣告式 vs 程序式對照；期末完成品搶先看（迷你 Gradio 介面）。
- **課堂實作**：環境自檢；Python 自我檢測 8 題（附補課地圖）；「我的收藏表」隨堂練習。
- 附錄：Python cheatsheet（另薦 [gto76/python-cheatsheet](https://github.com/gto76/python-cheatsheet)）、sqlite3 API 速查。
- 讀物：Silberschatz ch1；Ullman ch1；Beazley Practical Python（依自測結果補）。

### U02（09/17）SQL（一）：關聯模型、建表約束與單表查詢
`notebooks/unit02.ipynb`（本單元起使用課程範例資料庫 univ.db）
- **第 0 節**：關聯模型（relation 是笛卡兒積子集、schema vs instance、superkey/candidate/primary/foreign key、NULL 初見面）。
- **第 1 節**：SQLite 型別與 affinity；`CREATE TABLE` 與六種約束逐一踩雷示範（含 `PRAGMA foreign_keys` 陷阱）；主鍵三型與代理鍵；`INSERT` 三姿勢與 UPSERT；`UPDATE/DELETE` 與「忘記 WHERE」災難＋交易逃生；`ALTER/DROP`；generated column；系統目錄 `sqlite_master`。
- **第 2 節**：`SELECT` 邏輯執行順序；WHERE 全套（BETWEEN/IN/LIKE/GLOB）；**NULL 三值邏輯專場**（統計人的 missing data 對照）；排序、去重、切頁/分頁；字串／**日期時間**／條件／型別函數；`CASE WHEN` 重編碼；無分組聚合與 `COUNT` 家族陷阱；`AVG(CASE…)` 比例技巧與分母陷阱；抽樣。
- **課堂實作**：單表查詢 12 題＋加碼 2 題（UPSERT、printf）。
- 讀物：Silberschatz ch2–3；Ullman ch2。

### U03（09/24）SQL（二）：join、聚合、子查詢與 window functions
`notebooks/unit03.ipynb`（新增 10 萬列合成電商 sales.db）
- **第 1 節**：join 全家（cross→inner→left/right/full→self）；ON vs WHERE 的 LEFT JOIN 陷阱；多表 join；anti-join；集合運算（UNION/INTERSECT/EXCEPT）。
- **第 2 節**：`GROUP BY/HAVING` 心智模型與條件式聚合（樞紐/pivot）；子查詢四型與 CTE、遞迴 CTE；**window functions 專場**（排名家族、LAG/LEAD 差分、移動平均 frame、NTILE、累積、佔比、PERCENT_RANK/CUME_DIST/FIRST_VALUE）；view；pandas↔SQL 對照與互轉；DuckDB（直接查 CSV／DataFrame）。
- **課堂實作**：電商資料分析 8 題。
- **課末 10 分**：★公布專題指派表＋題目導覽（回家精讀自己的題目）。
- 讀物：Silberschatz ch4–5；Ullman ch6。

### U04（10/01）資料庫設計：ER 模型與正規化 ＋ 專題 schema 工作坊
`notebooks/unit04.ipynb`
- **第 1 節**：設計流程；ER 三要素與基數；名詞動詞分析；**完整案例：把「社團活動報名」從情境訪談推到 DDL**；ER→關聯綱要三規則；應用系統七大建模模式（M:N＋屬性、時段區間、狀態機、事件流、快照 vs 即算、時序價格、階層自參照），每個附可跑示範。
- **第 2 節**：爛大表的三種異常現場重演；FD 與屬性閉包（附演算法找 candidate key）；1NF→2NF→3NF→BCNF 判斷流程與**逐步分解演算法**；無損分解 SQL 驗證；反正規化時機與星型 schema；多值相依/4NF 一頁速覽。
- **課堂實作（工作坊）**：為**自己被指派的題目**做名詞動詞分析 → 畫 ER → 寫 DDL 草稿 → 互檢＋schema 自檢器。
- 讀物：Silberschatz ch6–7；Ullman ch3–4。

### U05（10/08）應用開發（一）：sqlite3 深入 ＋ Gradio 入門 ＋ ★專題說明會
`notebooks/unit05.ipynb`
- **第 1 節**：sqlite3 API 全套（connection/cursor/`Row`/executemany/executescript/date adapter）；用 `?` 傳值的正確寫法與 `IN`/動態欄位處理；交易（commit/rollback/`with con:`/savepoint）；匯入效能（逐筆 vs executemany 差幾十倍）；合成擬真資料的統計手法（長尾、時間節律、右偏、相關欄位、假姓名地名）。
- **第 2 節**：**Gradio 入門**：Interface → Blocks；元件全覽（Textbox/Number/Slider/Dropdown/Radio/Dataframe/Plot/State）；事件綁定與 `gr.update`；多輸出、錯誤回饋；表單→資料庫→表格/圖表即時更新；分頁；Colab 內嵌與 `share=True`；完整三分頁 app 骨架。
- **★專題說明會（35）**：`projects.md` 逐條導讀（共同要求）；**播放兩支教師示範影片**（圖書館借閱管理、個人記帳分析——皆非指派題目）；AI 協作工作流。
- **課堂實作**：把資料層函數接上第一個 Gradio 分頁。
- 讀物：sqlite3 官方文件；Gradio Quickstart https://www.gradio.app/guides/quickstart 。

### U06（10/15）應用開發（二）：完整應用模式 ＋ 內幕（一）儲存引擎
`notebooks/unit06.ipynb`
- **第 1 節（應用）**：Gradio×SQLite **完整 CRUD 應用模板**（多分頁、表單驗證、下拉吃資料庫、報表嵌圖、State 管理、編輯/刪除的列選取）；**併發競態**：兩條 connection 重現超賣 → 條件式 UPDATE／`BEGIN IMMEDIATE` 防護（專題共同要求核心）。
- **第 2 節（內幕）**：記憶體階層數量級與 random/sequential I/O；page／record／slotted page；**hexdump 解剖 SQLite 檔案**（magic header、`PRAGMA page_size`、`dbstat`）；buffer pool 與 LRU（`PRAGMA cache_size` 實驗）；**教師現場實作 mini pager**（4KB page、I/O 計數器）。
- **課堂實作**：把 HW 進度的查詢函數接上完整 CRUD 分頁；競態防護練習。
- 讀物：Silberschatz ch12–13；Ullman ch13；https://sqlite.org/fileformat2.html 。

### U07（10/22）內幕（二）索引與效能 ＋ ★示範：索引效能實驗
`notebooks/unit07.ipynb`
- **第 1 節**：百萬列點查的痛；索引分類（dense/sparse、clustered/secondary、SQLite rowid B-tree）；**B+ tree 圖解與逐步分裂**；樹高 ⌈log_f N⌉；hash index 的能與不能；30 行 bisect 自製排序索引。
- **第 2 節**：`CREATE INDEX`＋`EXPLAIN QUERY PLAN` 讀法（SCAN vs SEARCH）；毫秒→微秒實測；複合索引與最左前綴；覆蓋索引；運算式殺死索引；**selectivity 與統計資訊**（NDV、直方圖）；索引寫入代價；何時建索引 checklist；**★教師完整示範「SQLite 索引效能實驗研究」**——因子設計、重複量測、log-log 圖、交叉點分析。
- **課堂實作**：索引偵探（先預測計畫再驗證）；對自己專題資料做索引前後計時。
- 讀物：Silberschatz ch14；Ullman ch14；Winand《SQL Performance Explained》。

### —（10/29）期中考週：本課停課

### U08（11/05）內幕（三）查詢處理與最佳化：現場造一個迷你 SQL 引擎
`notebooks/unit08.ipynb`
- **第 1 節**：SQL 的一生（parse→關聯代數→實體計畫→執行）；夠用的關聯代數（σ π ⋈ γ）；**教師現場實作 mini SQL 引擎**（tokenizer→遞迴下降 parser→AST→執行器）；iterator（volcano）模型。
- **第 2 節**：join 演算法（nested loop／block NL／hash／sort-merge）與 I/O 成本；Python 實測 NL vs hash 差百倍；等價變換與謂詞下推；join 順序與 n! 爆炸；成本估計靠統計（`ANALYZE`、`sqlite_stat1`、計畫翻轉實錄）；估計會錯：偏斜與相關性；**DuckDB 列式引擎對決**。
- **課堂實作**：計畫閱讀＋join 量測＋把 EXPLAIN 用回自己的專題。
- 讀物：Silberschatz ch15–16；Ullman ch15–16。

### U09（11/12）內幕（四）交易與復原 ＋ 現代資料庫速覽 ＋ ★報告規範
`notebooks/unit09.ipynb`
- **第 1 節**：ACID 逐字；轉帳中途 crash→rollback；**兩條 connection 重現並行異常**（lost update／nonrepeatable read／phantom）；隔離級別總表；鎖、2PL、死結；MVCC 與 WAL 模式。
- **第 2 節**：durability 與部分寫入；WAL 原理；**子行程 `os._exit()` 當機模擬**（journal 保資料完好）；`synchronous` 速度/安全取捨實測；30 行玩具 WAL replay；**現代資料庫速覽**：LSM-tree、列式、向量庫（AI 檢索 demo）、文件庫（SQLite JSON）——細節在 `extra_modern.ipynb`。
- **★報告規範（35）**：15 分鐘結構模板；demo 腳本化與備援；rubric 重申；常見翻車；檢查清單；兩題共同要求的 Q&A 演練。
- 讀物：Silberschatz ch17–19 選讀；Ullman ch17–18 選讀。

### U10–U15（11/19、11/26、12/03、12/10、12/17、12/24）專題報告 I–VI
- 每場 9 人 × 15 分鐘（12 簡報含 demo ＋ 2 Q&A ＋ 1 換場），時間到即切；順序課堂公布。
- 當天上課前上傳最終版 `.ipynb` 至課程平台；現場用自己的 Colab 展示（請先在無痕視窗測過重跑全部）。

### 自學補充：`notebooks/extra_modern.ipynb`
OLTP vs OLAP、列式儲存與 DuckDB、LSM-tree 玩具實作、Redis/Mongo/圖資料庫速覽、SQLite JSON、向量資料庫與 embedding 檢索、Text-to-SQL 與 AI×DB。

## 專題進度建議

| 到哪一週 | 建議完成的專題進度 | 對應課堂實作 |
|---|---|---|
| U04 | 讀懂自己的題目；ER 圖與 schema 草稿 | U04 工作坊 |
| U05 | schema 定稿、建表、合成萬列資料、資料層函數 | U05 課堂實作 |
| U06 | 第一個 Gradio CRUD 分頁能動；競態防護就位 | U06 課堂實作 |
| U07 | 對自己資料做索引效能對照；補齊報表查詢 | U07 課堂實作 |
| U08–U09 | 三分頁組裝、5 張報表、8 個測試、demo 排練與備援 | 自行推進 |
