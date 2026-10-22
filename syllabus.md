# 課程與每週講義大綱

- **課程**：資料庫管理
- **講義**：目前發布 `notebooks/unit01.ipynb` 至 `unit09.ipynb`，包含規則、執行範例、驗證及綜合練習。另有自學補充 `notebooks/extra_modern.ipynb`，歷史版本見 [archive](archive/README.md)。
- **先修**：Python（U01 課堂自我檢測；不足者依檢測結果補 Beazley [Practical Python Programming](https://github.com/dabeaz-course/practical-python)）
- **教科書（參考用，課堂以講義為準）**：
  - Silberschatz, Korth, Sudarshan, *Database System Concepts*, 7th ed.（章末 Practice Exercises 官方解答：https://www.db-book.com/）
  - Garcia-Molina, Ullman, Widom, *Database Systems: The Complete Book*, 2nd ed.
- **AI 政策**：鼓勵 AI 協作，但**要能解釋交出的每一行**；專題末尾附「AI 使用說明」。
- **專題繳交方式**：報告當天**現場以自己的 Colab 開啟報告**；報告結束後繳交最終版 `.ipynb`（方式另外公布）。

## 課程設計：一條「用」的主線 ＋ 一條「懂」的支線

- **主線（U01–U06）**：Python 資料處理與資料管理觀念 → SQL → 資料建模 → Python 資料層 → PostgreSQL 的服務與權限 → Gradio 應用開發。課程使用 SQLite 與 PostgreSQL；指派專題仍使用 SQLite 與 Gradio（詳 [projects.md](projects.md)），期末 15 分鐘簡報含 live demo。
- **實作環境**：U02–U04 使用 SQLite，區分標準 SQL 與 SQLite 語法，不安排其他資料庫的語法或行為對照。PostgreSQL 自 U06 引進（在 Colab 內安裝）；U01 僅保留系統選型介紹。
- **支線（U06–U09，教師講授與現場實作示範）**：資料庫內部原理——儲存引擎、索引結構、查詢處理與最佳化、交易與復原、現代資料庫（列式／LSM／向量／文件）。

## 評分

| 項目 | 佔比 | 內容 |
|---|---|---|
| **專題** | **70%** | 詳 [projects.md](projects.md) |
| **平時** | **30%** | 課堂出席與作業等 |

## 每週講義大綱

### U01（09/10）Python、資料處理與資料管理入門

`notebooks/unit01.ipynb`

- **開場**：課程、專題、AI 協作政策及 Colab 的執行與儲存。以 Python／pandas 重現助教修改被舊副本覆蓋、78 分只寫成 7 且遺漏資料仍可讀取，以及同一人的學號與姓名出現不同寫法。由執行結果介紹資料保存、備份、資料完整性、修改協調及資料庫／DBMS／應用程式的角色。不使用 SQL 或資料庫 API。
- **系統選型**：從使用者、讀寫方式、離線需求、資料新鮮度與維護責任辨認需求；比較日常交易與分析、嵌入式與伺服器式，以及 SQLite、PostgreSQL／MySQL、DuckDB、鍵值／文件／向量系統的適用情境。介紹帳號與權限；以離線收銀、教學評量報表、搶票庫存及判決書搜尋練習提出候選方案與待驗證條件。
- **1**：Python 值、容器、流程、推導式與函數；示範、待完成練習、檢查器及分開的參考解答。
- **2**：例外、檔案、CSV、class 與模組；建立資料驗證及接受／拒絕流程，讀寫 CSV、保存 JSON 報告。
- **3**：NumPy 陣列、遮罩、缺值與模擬；pandas 型別、篩選、排序、分組、拼接與 CSV 重讀；matplotlib 示意圖與實際報表。說明檔案、分析工具與 DBMS 的分工，判斷何時繼續使用 Excel／pandas，並區分正式資料與分析副本。AI 審查包含錯誤初稿、反例及修正工作區。
- **綜合練習**：八題 Python 自測、課程資料拼接、系所報表及自己的 CSV 資料處理流程；核對正常、非法、重複及空資料，並解釋單靠驗證為何不能避免副本覆寫。
- **延伸**：七題 Python 進階題，不計入核心投影片。
- 讀物：Silberschatz ch1；Ullman ch1；Beazley Practical Python（依自測結果補）。

### U02（09/17 起）SQL（一）：資料表、查詢與資料異動

`notebooks/unit02.ipynb`

- **資料全貌**：先展示大學範例五張基礎表的欄位、典型資料及對照圖，再依序建表與加入全部合成資料；不要求已有資料庫檔。大學資料、獨立語法實驗、借閱原型各用一個記憶體資料庫，由 con、lab_con、library_con 分別操作。各範例表在使用前展示欄位及典型資料。
- **1：SQL 操作的資料與規則**。表列欄、資料粒度、schema／instance、關聯模型、鍵與缺值；區分 SQL、引擎與 Python API，再建立連線。
- **2：建立資料表與新增資料**。關鍵字、識別字、常值與語法模板；CREATE TABLE 的欄位定義、基本約束，INSERT 的欄位與值對應；首次新增前交代提交與回滾，再教參數綁定及批次寫入。
- **3：撰寫單表查詢**。逐步建立 SELECT／FROM／WHERE／ORDER BY 骨架，教 AND／OR、範圍、名單、文字比對及 DISTINCT；以關聯運算說明篩列、取欄與多重集合。介紹運算式、兩種別名與作用範圍、邏輯處理順序及值參數的界線。
- **4：修改與刪除資料**。UPDATE／SET、DELETE／WHERE 的一般形式、影響範圍、原值計算與核對方法；學生自行撰寫條件更新及刪除，實驗後回滾。
- **5：約束與五表結構**。以拒絕測試驗證必填、唯一、複合鍵、CHECK、預設值及外鍵；建立課程、修課、教師與授課資料，說明外鍵也約束刪除。
- **6：缺值、計算與整體統計**。完整三值邏輯、CASE、純量函數、轉型、字串及比例；COUNT／SUM／AVG／MIN／MAX、COUNT DISTINCT、缺值分母與空輸入。單表統計與每列運算分開教；分組統計由 U03 接續。
- **7–8：結果介面、資料保存與操作形式**。cursor 取用、整組回滾、記憶體／檔案生命週期；日期、型別驗證、自動編號、多列寫入、INSERT SELECT、RETURNING、UPSERT、CASCADE、ALTER 與 view。引擎差異在對應用法旁標註，不置於基本 SQL 撰寫之前。
- **9–10：操作原型與綜合練習**。使用獨立記憶體資料庫組成借閱登記函數，驗證新增、查詢、改期、歸還、刪除及報表；保留原大學資料十二題及自己的資料操作原型。
- **練習安排**：一般形式與範例之後立即自行撰寫，不只在章末答題。generated column、GLOB、週末時數及隨機抽樣保留於對應操作章，但不進入預設投影主線。
- 讀物：Silberschatz ch2–3；Ullman ch2。

### U03（09/24 起）SQL（二）：語法、查詢推理與報表

`notebooks/unit03.ipynb`

使用 SQLite 教導查詢組合的語法、語意與推理，再以報表驗證。U02 的單表語言基礎先完成，U03 不重新講授同一章。兩份教材均可跨次授課；U02 的結果介面及操作原型、U03 的視窗與新情境報表，可銜接後續資料層課程，不壓縮必要定義與練習。

- **資料來源**：沿用 U02 的學生、教師、課程、修課及授課五表，先交代每列的意思、欄位及典型資料。講義自行建立記憶體資料庫，不依賴 U02 的執行狀態。
- **先備檢核**：用教師薪資條件檢查括號與 NULL；用高分修課／通知名單檢查輸出粒度與 DISTINCT。各題先獨立作答，再核對理由，接續辨認單表缺少的資訊。
- **1：連接與配對規則**。INNER／LEFT 的一般形式、配對數量、完整連接鍵、ON／WHERE 及 NULL；以笛卡兒積說明 CROSS，以同表兩角色說明 self join。學生先推導列數，再核對修課、授課及學伴名單。
- **2：分組、子查詢及查詢組合**。GROUP BY／HAVING 的語法與處理階段、分組鍵、成績分桶、空輸入與缺值；純量／單欄／表結果的形狀，EXISTS、相關引用與作用域；衍生表、多步 CTE、UNION／ALL、INTERSECT、EXCEPT。每種寫法都有一般規則、可執行例子與反例。
- **3：視窗函數的文法與語意**。逐步建立 OVER 骨架，區分分區、排序、窗框及最終顯示順序。教排名、LAG 引數、累積與移動平均；以同分資料檢查預設窗框與 ROWS 差異，說明哪些函數不受窗框控制。由邏輯階段推導為何需要外層篩選。
- **4：從新需求組成查詢**。以小型收款資料，先交代來源與欄位，再由輸出粒度推導各查詢步驟。示範轉用已學規則後，獨立完成每個帳戶最後一筆及完整歷史計算。
- **綜合練習**：保留六題教務查詢，整合名單、含零報表、門檻、集合、排名及學期比較；參考答案與題目分開。學生需解釋規則與選擇，不只核對數字。
- 讀物：Silberschatz ch4–5；Ullman ch6。

### U04（10/01）從需求到可驗證的資料庫設計

`notebooks/unit04.ipynb`

本單元以 SQLite 執行建表與驗證，不安排其他資料庫的語法或行為對照。依需求、一般規則、推導、反例及獨立撰寫展開；必要內容可跨次授課，不把三章當成三節課的硬性分界。

- **主案例**：同一個社團活動報名系統。從一張登記表到會員、社團、活動及報名四表，業務規則、代碼及典型資料前後一致。
- **1：由需求畫出可解釋的 ER 圖**。分辨實體／集合、屬性、關係及關係屬性；由業務規則而非目前資料決定鍵、雙向基數與完整／部分參與。教 1:N、M:N、1:1 的一般映射、代理鍵不能取代業務唯一性，以及弱實體與部分鍵；各項規則均安排判斷與反例。
- **2：由資料異常說明拆表理由**。保留更新、插入、刪除實驗；以 FD、F⁺、Armstrong 規則及屬性閉包推導超鍵、最小候選鍵與主屬性。教完全／部分相依及 1NF／2NF／3NF／BCNF 的一般判準；用共同欄位證明二分與逐步分解無損，區分無損與保相依。SQL 反例與手算交替進行，不以完整分解演算法作為主線。
- **3：將設計實作並驗證**。從一般 DDL 形式獨立撰寫活動、報名表，以正常與拒絕資料檢查約束；自行撰寫含零計數、名額決策及取消／遞補後報表。交代操作前後條件、不變量、狀態轉移、條件式更新與整組失敗回滾。分清資料庫約束、應用檢查與跨列規則，不把單連線示範當作多人安全證明。
- **綜合練習與專題銜接**：以圖書借閱檢查能否把已教方法用於新需求，辨認書目、副本及借閱的關係，再完成 ER、DDL、正常／違規資料與查詢。作答在前，參考答案與理由在後。
- 讀物：Silberschatz ch6–7；Ullman ch3–4。

### U05（10/08）從資料庫到可以展示的應用

`notebooks/unit05.ipynb`

以「系上獎學金申請與名額核定」為貫穿情境（學生、獎學金、申請、評分四表），把專題共同要求逐項示範一次。本單元使用 SQLite，不安排 PostgreSQL。

- **1 資料層**：全域連線在另一執行緒失敗的原因；短連線與連線工廠（每條連線開外鍵檢查）；每個寫入操作兩層 `with`（`closing` 關連線、`with db` 管交易）；資料層函數的規則；`ValueError` 中文訊息與 `friendly`／`safe_call`；條件式更新；測試資料庫、每個測試前重建、查回資料狀態。
- **2 合成資料**：先寫生成假設；固定 seed；以 Python 內建的 random、namedtuple、list、dict 產生事件（只有 Poisson 用 numpy）：依資格與熱門度抽樣、拖延型申請時間、撤回與審查評分；使用 numpy 時整數被存成 BLOB 的陷阱；單一交易批次匯入；匯入後以 `ROW_NUMBER()` 排名的 `UPDATE ... FROM` 依評分核定；以「找違規」查詢驗收規則，以圖驗收分布。
- **3 交易與競態**：內層函數不提交、外層組成交易；兩條連線手動交錯重現超額核定；條件式 `UPDATE` 與 `BEGIN IMMEDIATE` 兩種防護；以 Barrier 讓多個執行緒真正同時操作；回歸測試。
- **4 報表與效能**：問題 → 粒度 → SQL → 圖；LEFT JOIN 含零、條件計數、分母、RANK／累計和；圖表函數回傳 Figure；自動索引、複合索引最左欄、`EXPLAIN QUERY PLAN`、建索引前後的中位數計時與代價。
- **5 Gradio**：Interface → Blocks；`click(fn, inputs, outputs)` 的約定；回呼函數只接線且可直接測試；Dropdown 顯示名稱傳主鍵；選列與 State；報表分頁；三分頁應用。
- **6 專題**：共同要求逐條對照做法與證據；demo 腳本、可重置狀態與備援；AI 使用說明寫法。
- **練習**：不核定、成績與申請數、撤回遞補、委員寬嚴報表、只能撤回自己的申請；綜合練習為把五個步驟搬到自己的題目。
- 讀物：Python `sqlite3`、SQLite `EXPLAIN QUERY PLAN` 與 Gradio 官方文件。

### U06（10/15）資料異動、競爭控制與儲存頁

`notebooks/unit06.ipynb`

以「圖書館研討室預約」為貫穿情境（學生點數、研討室、預約、異動紀錄）。§1 使用 SQLite；§2 介紹 PostgreSQL（Colab 第一格自動安裝）；§3 在 PostgreSQL 上處理競爭控制，並與 SQLite 對照；§4 拆解 SQLite 檔案，再以 Python 實作小型儲存層。各節以「先猜」、可執行的對照與自動驗收推進。

- **1 資料異動**：規則分兩層（函數檢查與資料庫約束）；時段重疊判斷與條件式扣點；軟刪除與硬刪除，外鍵擋下與 `CASCADE`／`SET NULL` 的選擇；`BEFORE` 觸發器擋下不合法的狀態變化，`AFTER` 觸發器自動寫異動紀錄。練習 A：改期（重疊檢查排除自己、補扣與退點）。
- **2 認識 PostgreSQL**：連線字串與三種連線錯誤；一條連線一個行程（`pg_backend_pid`、`ps`、`idle in transaction`）、主行程與背景行程、`max_connections`；三張表的型別改寫（identity、`timestamp`）與 psycopg2 的 Python 型別；型別檢查對照（SQLite type affinity、`STRICT`）與七句 SQL 方言差異（`LIKE`、boolean、`NULL` 排序、雙引號、名稱大小寫、`GROUP BY`）；出錯後整個交易作廢（25P02）；來回次數與大量寫入（`executemany`、`execute_values`、`COPY`）；資料庫、schema、`search_path` 與資料目錄中的檔案；角色、`GRANT`／`REVOKE`、欄位權限、群組角色與 `PUBLIC`；`psql`。練習 B：收回報表角色的權限（自動驗收六項）。
- **3 競爭控制**：重新處理 U05 §3。先問「這個決定讀了哪些列」：同一列的遺失更新，以原子 `UPDATE`、`SELECT ... FOR UPDATE`、版本號（表單選列帶入後存檔）防護；跨列的寫入偏斜（一句「檢查＋寫入」在 PostgreSQL 不安全）以鎖母列防護；時段重疊的幻影以排除約束（`EXCLUDE USING gist`）防護。`lock_timeout`、`NOWAIT`、失敗交易須 rollback 後才能重用連線；死結的成環與偵測（40P01）、依固定順序上鎖、以 `with_retry` 只對暫時性錯誤重試整個交易。練習 C：點數轉讓（參數與點數檢查、依學號順序鎖住兩列，自動驗收五項）。SQLite 單一寫者對照；八個執行緒同時操作，分類計數並以查詢驗證沒有違規，觀察排除約束下的死結。
- **4 儲存頁**：SQLite 檔頭與 `dbstat`、葉頁的 cell pointer；UTF-8 記錄編碼；slotted page（刪除、整理、槽號不變）；pager 與 `fsync`；buffer pool 的 LRU、pin、dirty page，當機時未寫回的修改遺失，以及循序掃描的命中率。練習 D：`fetch` 之後一定 `unpin`。刪除與更新之後：SQLite 的空頁清單與 `VACUUM`；PostgreSQL 頁中的舊版本（`ctid`、`pageinspect`）、轉址與 `VACUUM`。
- **PostgreSQL 挑戰（課後）**：`book_pg` 同時守住點數、筆數與時段；同列競爭必須等待後依最新資料判斷或被拒絕，不同列互不等待；所有等待有上限，失敗交易可回滾並重新使用連線（自動驗收六項）。
- **課後練習**：完成挑戰並說明理由；在自己的專題重現並防護一條同列、一條跨列規則的競態；寫 SQLite 版的 `with_retry`；把專題資料庫搬進 PostgreSQL（型別、`COPY`、唯讀角色）並找出結果不同的查詢；以 `dbstat`、檔頭空頁數與 `VACUUM` 分析主要資料表的頁數與每頁列數。
- **自學延伸**：`FOR UPDATE SKIP LOCKED`。
- 讀物：Silberschatz ch12–13，ch18 鎖與死結的部分；PostgreSQL 文件〈Database Roles〉、〈Privileges〉、〈Explicit Locking〉、〈Exclusion Constraints〉、〈Routine Vacuuming〉；SQLite〈Database File Format〉。

### U07（10/22）索引結構與工作負載效能

`notebooks/unit07.ipynb`

延續 U06 的研討室預約，資料放大到一百萬筆（PostgreSQL 與 SQLite 以相同公式產生）。以「讀了幾頁」衡量成本：§0 補上二分搜尋與樹的預備知識；§1 以 Python 實作 B+ tree；§2 在 PostgreSQL 上讀計畫、比較各種索引；§3 計算寫入與空間的代價，並在 SQLite 上驗證，最後以工作負載的總頁數選索引。

- **0 預備知識**：二分搜尋的迴圈與比較次數（一百萬個鍵：從頭找與二分搜尋）；`bisect_left`／`bisect_right` 回傳切點，查值、數範圍、`insort`；節點與參考（鏈結串列，改參考就能插入）；二元搜尋樹的遞迴插入、沿路搜尋（`visit` 計數）、中序走訪與樹高、依序插入使樹長歪；一個節點放多個分隔鍵，以 `bisect_right` 選子節點。練習 0：以 `bisect` 數 `BETWEEN` 範圍內的鍵、在二元搜尋樹上做範圍查詢（自動驗收四項，含讀取次數）。
- **1 索引的結構**：以頁計的二分搜尋、排序檔插入的搬移成本；稠密／稀疏索引、多層索引；B+ tree 的節點、葉鏈與查詢（`visit` 計頁）；葉分裂（複製）與內部節點分裂（搬移）、根分裂；`check_tree` 驗證平衡；fanout 與樹高；隨機／依序插入的填滿率與 bulk loading；不合併的刪除；hash 索引。練習 A：以葉鏈做範圍查詢（自動驗收三項，含讀取頁數上限）。
- **2 PostgreSQL 的計畫與索引**：`EXPLAIN`、`EXPLAIN (ANALYZE, BUFFERS)`；Index Scan、Bitmap Heap Scan、Index Only Scan；`pageinspect` 看 B+ tree 的層數、項目數與（鍵, ctid）；選擇度與 `random_page_cost`；複合索引欄位順序（等值在前、範圍在後）、BitmapAnd、以索引省去排序；部分索引、運算式索引與可搜尋的寫法；哪些條件用不上索引；index-only scan 與 visibility map、`INCLUDE`；`pg_stats` 與過期統計；hash 索引。練習 B：替四個查詢選索引（頁數上限、結果不變、總大小，自動驗收六項）。
- **3 索引的代價與 SQLite**：索引數與寫入時間、WAL；HOT 更新；索引大小、膨脹與 `REINDEX`；建索引的鎖與 `CONCURRENTLY`；SQLite 的 `COVERING INDEX` 與 `TEMP B-TREE`；外鍵欄沒有索引時刪除父列的成本；rowid 與 `WITHOUT ROWID`；`CLUSTER`、correlation 與 BRIN；列數 × 索引的因子試驗（暖身、7 次中位數與 IQR、對數圖）；工作負載的總頁數帳。練習 C：兩個 SQLite 索引滿足四個操作（不得 SCAN、TEMP B-TREE，自動驗收五項）。
- **PostgreSQL 挑戰（課後）**：替含寫入的工作負載選至多四個索引：結果不變、每天總頁數、Q1 每次頁數與每次寫入頁數在上限內（自動驗收五項）。
- **課後練習**：以頁數帳說明挑戰的選擇；替專題的工作負載提出並量測索引；由下而上建 B+ tree；在因子試驗加入查詢範圍。
- **自學延伸**：`pg_trgm` 與 GIN 支援 `LIKE '%…%'`。
- 讀物：Silberschatz ch14；PostgreSQL 文件〈Indexes〉、〈Using EXPLAIN〉、〈Statistics Used by the Planner〉；SQLite〈Query Planning〉、〈The WITHOUT ROWID Optimization〉。

### U08（10/29）查詢處理與最佳化：打造迷你 SQL 引擎

`notebooks/unit08.ipynb`

延續研討室預約，問題從「查一筆」變成報表（各系的使用時數、社團幹部的預約）。§1 以 Python 寫一個能執行 SELECT、JOIN、GROUP BY 的迷你 SQL 引擎，逐句與 SQLite 對答案；§2 以列數與頁數比較 join 演算法、外部排序與計畫改寫；§3 在一百萬筆偏斜資料上讀 PostgreSQL 的計畫與統計。

- **1 迷你 SQL 引擎**：bag 語意（`DISTINCT`、`UNION` 與 `UNION ALL`）；關聯代數的 σ、π、⋈、γ；tokenizer、遞迴下降 parser 與運算子優先順序、AST、語法錯誤訊息；binder 的名稱解析與歧義；運算式求值與 NULL 的三值邏輯；iterator 運算子（Scan、Filter、NestedLoopJoin、Project、Limit、Count）與 pipelining；HashAggregate 與空輸入；planner 把 AST 組成運算子樹，12 句查詢以 bag 與 SQLite 比對。練習 A：Sort 運算子（多鍵、遞減、NULL 的順序，自動驗收五項）。
- **2 Join 與最佳化**：nested loop 與 block nested loop 的頁數公式；index nested loop；hash join 的 build／probe、Grace 分割與偏斜；sort-merge join；外部排序的 runs 與趟數；謂詞下推（中間結果與時間）；左深 join 順序與笛卡兒積；SQLite 的 automatic index、`ANALYZE`／`sqlite_stat1` 與 skip-scan。練習 B：HashJoin 運算子（含 NULL 鍵、兩邊各讀一次，自動驗收三項）。
- **3 PostgreSQL 的計畫與統計**：成本參數；Hash Join 的 build／probe；啟動成本與 `LIMIT`（Memoize）；rows × loops；等值 join 的估計公式與跨表偏斜造成的低估；以 `enable_*` 比較替代計畫（結果完全相同、碰頁次數）；Merge Join；三表 join 順序與 `join_collapse_limit`；MCV 與 statistics target；extended statistics（dependencies、ndistinct、運算式）；`work_mem` 與排序、hash join、hash 分組的溢寫（結果逐列或以 bag 比較）；Incremental Sort；半連接、反連接與 `NOT IN` 的 NULL 陷阱；先分組再 join；平行查詢。練習 C：找出計畫中估計誤差最大的一步（自動驗收五項）。
- **PostgreSQL 挑戰（課後）**：以 extended statistics 與 `work_mem` 讓兩個估計的誤差在兩倍內、排序不溢寫，三個查詢的結果完全相同（自動驗收五項）。
- **課後練習**：比較挑戰前後估計最差的一步；替迷你引擎加上 `HAVING` 與謂詞下推；改寫社團幹部的查詢，讓估計接近實際。
- 讀物：Silberschatz ch15–16；PostgreSQL 文件〈Using EXPLAIN〉、〈Statistics Used by the Planner〉、〈Controlling the Planner with Explicit JOIN Clauses〉、〈CREATE STATISTICS〉；SQLite〈The SQLite Query Optimizer Overview〉。

### U09（11/05）交易、隔離、復原與備份驗收

`notebooks/unit09.ipynb`

延續研討室預約，回答三個問題：規則 R3（每人最多 2 筆尚未開始的預約）不靠程式上鎖，資料庫擋得住嗎？當機之後，已提交的預約還在嗎？備份真的還原得回來嗎？§1 以紙筆模型（Python）建立排程理論；§2 在 PostgreSQL 上觀察三個隔離等級的實際異常與拒絕；§3 由 toy 日誌走到 PostgreSQL 的 WAL 與真正的當機實驗，並對照 SQLite 的 journal 與 WAL；§4 備份、還原與驗收。

- **1 排程與可序列化**：ACID；排程的執行與遺失更新、髒讀、不可重複讀；衝突與優先圖、盲寫（衝突可序列化只是充分條件）；視圖可序列化；可復原、不會連鎖中止與連鎖中止；2PL（strict 與 rigorous）的模擬（等待、可序列化與死結）。練習 A：由優先圖求等價的序列順序（拓樸排序，自動驗收六項）。
- **2 PostgreSQL 的隔離等級與多版本**：標準的四個等級與 PostgreSQL 的實作、設定隔離等級；READ COMMITTED 的不可重複讀與幻影（U06 防護一的依據）；REPEATABLE READ 的快照時點與寫入衝突（`40001`）；寫入偏斜；SERIALIZABLE（SSI）的讀寫依存、pivot 與優先圖、SIRead 鎖、鎖的粒度與索引（偽陽性）、`with_retry` 重試、`READ ONLY DEFERRABLE`；`xmin`／`xmax` 與快照；長交易擋住 VACUUM（`pgstattuple`）。練習 B：多版本的可見性規則（自動驗收十項）。
- **3 復原**：steal／no-force 與當機時的磁碟；WAL 的兩條規則；只重做已提交的為什麼不夠；steal／force 的四種組合；checkpoint。練習 C：toy 日誌的 redo／undo 復原（自動驗收八種當機情況）。PostgreSQL 的 `pg_waldump`、checkpoint 與 redo 點、整頁寫入、UNLOGGED 表、殺掉伺服器行程的當機實驗、`fsync` 的代價與 `synchronous_commit`；SQLite 的 rollback journal（子程序當機與 hot journal）、WAL 模式與 checkpoint；savepoint 與外層回滾。
- **4 備份與還原**：`pg_dump` 的內容與順序、備份裡的 SQL；寫入進行中的備份一致性（快照）；還原到新資料庫並驗收內容與約束；以 TOC 清單從備份救回一張表；備份與還原的時間、RPO／RTO；`pg_basebackup` 與 PITR；SQLite 的一致備份（`backup()`、`VACUUM INTO`）與專題的備份演練。
- **PostgreSQL 挑戰（課後）**：不上鎖，以 SERIALIZABLE 與重試完成 R3 的預約（同時預約要遇到 `40001` 並重來，不同學生不必重來）；寫出抓得到少了索引、約束、資料表或內容被改過的還原驗收（自動驗收九項）。
- **課後練習**：索引與 SSI 的偽陽性；復原途中再當機（compensation log record）；專題的備份演練與 RPO／RTO；專題中「要看別的列才能決定」的規則在 SQLite 與 PostgreSQL 的差別。
- 讀物：Silberschatz ch17–19；PostgreSQL 文件〈Transaction Isolation〉、〈Reliability and the Write-Ahead Log〉、〈Backup and Restore〉；SQLite〈Atomic Commit In SQLite〉、〈Write-Ahead Logging〉。

### U10–U15（11/12、11/19、11/26、12/03、12/10、12/17、12/24）專題報告 I–VII
- 每人 15 分鐘（12 簡報含 demo ＋ 2 Q&A ＋ 1 換場），時間到即切；場次與順序待公布。
- 現場用自己的 Colab 展示；報告結束後繳交最終版 `.ipynb`。

### 自學補充：`notebooks/extra_modern.ipynb`
OLTP vs OLAP、列式儲存與 DuckDB、LSM-tree 玩具實作、Redis/Mongo/圖資料庫速覽、SQLite JSON、向量資料庫與 embedding 檢索、Text-to-SQL 與 AI×DB。
