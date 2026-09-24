# 課程與每週講義大綱

- **課程**：資料庫管理
- **講義**：目前發布 `notebooks/unit01.ipynb` 至 `unit04.ipynb`，包含規則、執行範例、驗證及綜合練習；U05–U09 待重新編修。另有自學補充 `notebooks/extra_modern.ipynb`，歷史版本見 [archive](archive/README.md)。
- **先修**：Python（U01 課堂自我檢測；不足者依檢測結果補 Beazley [Practical Python Programming](https://github.com/dabeaz-course/practical-python)）
- **教科書（參考用，課堂以講義為準）**：
  - Silberschatz, Korth, Sudarshan, *Database System Concepts*, 7th ed.（章末 Practice Exercises 官方解答：https://www.db-book.com/）
  - Garcia-Molina, Ullman, Widom, *Database Systems: The Complete Book*, 2nd ed.
- **AI 政策**：鼓勵 AI 協作，但**要能解釋交出的每一行**；專題末尾附「AI 使用說明」。
- **專題繳交方式**：報告當天**現場以自己的 Colab 開啟報告**；報告結束後繳交最終版 `.ipynb`（方式另外公布）。

## 課程設計：一條「用」的主線 ＋ 一條「懂」的支線

- **主線（U01–U06）**：Python 資料處理與資料管理觀念 → SQL → 資料建模 → Python 資料層 → PostgreSQL 的服務與權限 → Gradio 應用開發。課程使用 SQLite 與 PostgreSQL；指派專題仍使用 SQLite 與 Gradio（詳 [projects.md](projects.md)），期末 15 分鐘簡報含 live demo。
- **實作環境**：U02–U04 使用 SQLite，區分標準 SQL 與 SQLite 語法，不安排其他資料庫的語法或行為對照。PostgreSQL 從 U05 正式引進；U01 僅保留系統選型介紹。
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

### U05（10/08）Python 資料層、PostgreSQL 與 Gradio
待重新編修。
- **1**：短連線資料層；cursor、Row、參數與動態識別字；轉帳、失敗回滾與 savepoint；日期適配、批次匯入及公平量測。
- **2**：獨立 PostgreSQL 服務、database/schema/role；Psycopg、identity、NUMERIC、日期與時點；失敗交易、最小權限、view 授權與 COPY。
- **3**：可驗證的合成資料；Interface → Blocks；查詢、新增、選列、State、報表、CSV 與三分頁應用。
- **PostgreSQL 挑戰**：普通報表角色能讀指定 view，但不能改表或讀敏感欄；COPY 失敗整批撤銷。延伸 RLS 驗證直接 SQL 也不能偽造擁有者。
- **綜合練習**：資料層修改函數、UI 連接、角色權限與資料生成驗收。
- **延伸**：缺值及離群生成、完整四表購買／退款、專題規格與示範程式導讀。
- 讀物：Python sqlite3、Psycopg、PostgreSQL 權限與 Gradio 官方文件。

### U06（10/15）資料異動、競爭控制與儲存頁
待重新編修。
- **1**：完整 CRUD、驗證、軟刪與硬刪、選列回填、狀態與 audit trigger。
- **2**：兩個 PostgreSQL session 的遺失更新、列鎖、條件式更新、FOR UPDATE、等待逾時與版本衝突；SQLite 的單一寫者、BEGIN IMMEDIATE、取消、候補與區間預約另作實驗。
- **3**：page/record/slotted page、SQLite header 與 dbstat；buffer pool、LRU、pin、dirty page；可重開的 mini pager 與 UTF-8 記錄層。
- **PostgreSQL 挑戰**：同列競爭必須被阻擋或拒絕，不同列可以分別修改；所有等待有上限，失敗交易可回滾並重新使用連線。
- **綜合練習**：完整資料異動、受控交錯與頁面讀寫驗收。
- 讀物：Silberschatz ch12–13；PostgreSQL 鎖文件；SQLite 檔案格式。

### U07（10/22）索引結構與工作負載效能
待重新編修。
- **1**：線性與排序查找、稠密／稀疏索引、完整 B+ tree 分裂與葉鏈、平衡驗證、fanout 與 hash。
- **2**：PostgreSQL EXPLAIN ANALYZE/BUFFERS、索引掃描、bitmap、複合／部分／運算式索引、index-only scan 與可見性、ANALYZE。
- **3**：索引的讀取、寫入及空間成本；SQLite 計畫、FK 索引、rowid/WITHOUT ROWID；最高百萬列的因子試驗、重複量測及對數圖。
- **PostgreSQL 挑戰**：以查詢結果、計畫、可見性與總工作負載證明索引選擇，不以單次時間或指定節點當答案。
- **綜合練習**：提出索引組合，保留逐列正確性與讀寫成本證據。
- 讀物：Silberschatz ch14；PostgreSQL、SQLite 索引與計畫文件。

### U08（10/29）查詢處理與最佳化：打造迷你 SQL 引擎
待重新編修。
- **1**：集合／bag 語意與關聯代數；tokenizer → parser → AST → 名稱檢查 → iterator；完整 mini SQL 與 GROUP BY。
- **2**：nested loop、hash、sort-merge 與 block 模型；外部排序、partition、謂詞下推與 join 順序；SQLite ANALYZE/stat1。
- **3**：PostgreSQL 實際 join 計畫、rows × loops、偏斜與相關性、extended statistics、work_mem 與暫存檔；DuckDB 對照。
- **PostgreSQL 挑戰**：比較估計與實際列數；以完整相同結果驗證替代計畫及排序／hash 溢寫，不能只比較耗時。
- **綜合練習**：引擎功能、演算法、計畫閱讀與統計改善的整合實驗。
- 讀物：Silberschatz ch15–16；PostgreSQL EXPLAIN 與統計文件；DuckDB 文件。

### U09（11/05）交易、隔離、復原與備份驗收
待重新編修。
- **1**：ACID、schedule、衝突可序列化、相依圖、2PL 與可復原性；PostgreSQL READ COMMITTED／REPEATABLE READ／SERIALIZABLE 的實際異常與拒絕。
- **2**：多版本可見性、死結、固定鎖序、整筆交易重試；WAL、undo/redo、checkpoint 與耐久設定。
- **3**：PostgreSQL 備份還原；SQLite journal/WAL 子程序崩潰、checkpoint、同步設定與一致備份；savepoint 與外層回滾；toy WAL 按日誌順序重播。
- **PostgreSQL 挑戰**：受控重現 write skew 與死結，辨認 SQLSTATE 並重試整筆交易；還原至新資料庫後驗證資料及限制。
- **綜合練習**：交易不變量、並行排程、故障及還原驗收。
- **延伸**：LSM／列式、JSON／詞頻向量實驗；專題報告、展示證據與備援演練。專題規格仍以 SQLite 為準。
- 讀物：Silberschatz ch17–19；PostgreSQL 隔離、鎖與備份文件；SQLite WAL 文件。

### U10–U15（11/12、11/19、11/26、12/03、12/10、12/17、12/24）專題報告 I–VII
- 每人 15 分鐘（12 簡報含 demo ＋ 2 Q&A ＋ 1 換場），時間到即切；場次與順序待公布。
- 現場用自己的 Colab 展示；報告結束後繳交最終版 `.ipynb`。

### 自學補充：`notebooks/extra_modern.ipynb`
OLTP vs OLAP、列式儲存與 DuckDB、LSM-tree 玩具實作、Redis/Mongo/圖資料庫速覽、SQLite JSON、向量資料庫與 embedding 檢索、Text-to-SQL 與 AI×DB。
