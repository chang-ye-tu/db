# minidb

課程「資料庫管理」U06–U09 一層一層組出來的關聯資料庫引擎，純 Python。

| 回 | 層 | 模組 |
|---|---|---|
| U06 | 儲存：頁、記錄、檔案、buffer pool、heap file | `page.py`、`record.py`、`pager.py`、`buffer.py`、`heap.py` |
| U07 | 索引與排序：B+ tree、外部合併排序 | `btree.py`、`sort.py` |
| U08 | SQL 前端與執行：剖析、binder、planner、運算子 | `sql/`、`catalog.py` |
| U09 | 交易：鎖、WAL、當機復原 | `txn/`、`db.py` |

## 安裝

    pip install "antlr4-python3-runtime==4.13.2"

練習集的第一格會安裝當週的版本，不必自己裝。

## 用法

```python
from minidb import Database

db = Database("demo.db")
db.execute("CREATE TABLE room (room_id INTEGER PRIMARY KEY, name TEXT NOT NULL, floor INTEGER NOT NULL)")
db.executemany("INSERT INTO room VALUES (?, ?, ?)", [(1, "研討室 1", 1), (2, "研討室 2", 1)])
print(db.execute("SELECT name FROM room WHERE floor = ?", (1,)).fetchall())
print(db.explain("SELECT name FROM room WHERE room_id = 2"))
print(db.stats())          # 讀寫了幾頁、buffer 命中幾次
db.close()
```

## 支援的 SQL

- `CREATE TABLE`（INTEGER、REAL、TEXT；`PRIMARY KEY`、`NOT NULL`、`UNIQUE`）、`CREATE [UNIQUE] INDEX`、`DROP TABLE`、`DROP INDEX`；
- `INSERT`（`VALUES` 或 `SELECT`）、`UPDATE`、`DELETE`；
- `SELECT`：`WHERE`、`JOIN`（INNER、LEFT、CROSS、`USING`）、`GROUP BY`、`HAVING`、`ORDER BY`、`LIMIT`、`OFFSET`、`DISTINCT`、彙總函數與常用的純量函數；SQLite 的 `INDEXED BY`、`NOT INDEXED`；
- `BEGIN`、`COMMIT`、`ROLLBACK`、`EXPLAIN`；參數 `?`。

超出這個子集的語法會拋出 `NotSupported`，並說明是哪一種語法。

## 授權

引擎以 MIT 授權釋出，全文見 `LICENSE`。

`minidb/sql/sqlite_parser/` 由 ANTLR 4.13.2 依 [grammars-v4](https://github.com/antlr/grammars-v4/tree/5a0ddb4aa12c1502d7bd5ec8fb8673e607b3b191/sql/sqlite) 的 SQLite 文法產生，文法的授權（MIT）見該目錄的 `LICENSE-grammar.txt`。
