"""Database 與 Connection：把各層接起來，執行 SQL。

    db = Database("demo.db")             # 開檔；上次沒有正常關閉時先做當機復原
    db.execute("CREATE TABLE ...")
    rows = db.execute("SELECT ... WHERE id = ?", (3,)).fetchall()
    con = db.connect()                    # 另一個連線（U09：兩個執行緒各用一個）

每一句的流程：剖析（同一段文字只剖析一次）→ binder → planner → 執行。
沒有 BEGIN 時，每一句自成一個交易（autocommit）。

競爭控制分兩層（完整內容第 9 章）：
  * 鎖（lock）：交易層級，嚴謹 2PL，鎖整張表（定義 9.2.2、9.2.3）；在 latch 之外等，所以等鎖時別的交易還能動（命題 9.2.8）。
  * latch：Database.latch 是一個 RLock，同一時間只有一句在讀寫頁；保護的是資料結構本身，不是交易的隔離（定義 9.2.1）。
復原：預寫日誌（定義 9.4.1、9.4.2）與當機之後的復原（演算法 9.4.10）。
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path

from .btree import BPlusTree
from .buffer import BufferPool
from .catalog import SCHEMA_TABLE, Catalog, key_schema
from .errors import BindError, DeadlockError, Error, IntegrityError, NotSupported, TransactionError
from .page import PAGE_SIZE, SlottedPage
from .pager import Pager
from .record import Column, Schema
from .sort import ExternalSort
from .sql import ast
from .sql.binder import Rel, Scope, bind_expr, bind_select, conjuncts
from .sql.expr import compile_expr, truth
from .sql.parser import parse
from .sql.planner import Planner, resolver
from .txn.lock import S, X, LockManager, NoLocks
from .txn.recovery import compensate, redo, undo
from .txn.wal import WAL


@dataclass
class Txn:
    id: int
    records: list = field(default_factory=list)     # 這個交易寫下的 insert、delete、newpage 紀錄


@dataclass
class Result:
    columns: list
    rows: list
    rowcount: int = -1
    plan: object = None

    def fetchall(self) -> list:
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Database:
    def __init__(self, path, page_size: int = PAGE_SIZE, pool_pages: int = 64, sort_memory_pages: int = 64,
                 locking: bool = True, lock_timeout: float = 10.0, fsync: bool = True):
        self.path = Path(path)
        self.sort_memory_pages = sort_memory_pages
        self.pager = Pager(self.path, page_size, fsync)
        new_file = self.pager.n_pages == 0               # 新的資料檔：目錄的第 0 頁還沒建立
        self.wal = WAL(str(self.path) + "-wal", fsync)
        self.wal.continue_after(self._max_page_lsn())   # 日誌檔遺失或換新時，LSN 仍往上接（定理 9.4.16 的 (g)）
        self.pool = BufferPool(self.pager, pool_pages, self.wal)
        self.catalog = Catalog(self.pool, self.wal)
        self.locks = LockManager(lock_timeout) if locking else NoLocks()
        self.latch = threading.RLock()
        self.active: dict[int, Txn] = {}
        self._parsed: dict[str, list] = {}
        self.statements = 0
        self.closed = False
        log = self.wal.records()
        self._next_txn = max((r["txn"] for r in log), default=0) + 1
        self.recovery = None                         # 復原的結果；沒有復原時是 None
        if not new_file:
            if log and log[-1].get("shutdown"):      # 上次正常關閉
                self.checkpoint()                    # 新的 checkpoint 不帶這個記號
            else:                                    # 上次沒有正常關閉，或日誌遺失了
                self.recovery = self._recover(log)   # 演算法 9.4.10
        self.default = Connection(self)

    # ------------------------------------------------------------- 方便用的入口
    def connect(self) -> "Connection":
        return Connection(self)

    def execute(self, sql: str, params=()) -> Result:
        return self.default.execute(sql, params)

    def executemany(self, sql: str, seq_of_params) -> Result:
        return self.default.executemany(sql, seq_of_params)

    def executescript(self, sql: str) -> None:
        self.default.executescript(sql)

    def explain(self, sql: str, params=(), analyze: bool = False) -> str:
        return self.default.explain(sql, params, analyze)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def load(self, table: str, rows) -> int:
        """把大量的列匯入一張空表（像 PostgreSQL 的 COPY）：不寫日誌、不逐筆維護索引；
        匯入後一次建好索引（外部排序 + bulk loading），再 checkpoint。傳回匯入的列數。
        匯入途中出錯（例如一列的型別、NOT NULL、唯一或長度不合格）時整批都不匯入：表與索引回到匯入之前，
        再拋出那個例外。途中當機（db.crash()）時不再寫任何東西：load 不寫日誌，當機之後表的內容沒有保證（第 9 章的實驗）。"""
        with self.latch:
            if self.active:
                raise TransactionError("load 要在沒有任何進行中的交易時執行")
            t = self.catalog.table(table)
            if t.name == SCHEMA_TABLE or next(t.heap.scan(), None) is not None:
                raise BindError("load 只能匯入一張空的表")
            indexes = self.catalog.indexes_on(t.name)
            tail = t.heap._last_page()               # 匯入只改鏈尾的這一頁，與之後接上的新頁
            with self.pool.page(tail) as p:
                before = bytes(p.data)
            seen = {ix.name: set() for ix in indexes if ix.unique}
            n = 0
            try:
                for row in rows:
                    row = t.schema.check(tuple(row))
                    for ix in indexes:
                        key = ix.key_of(row)
                        if ix.unique and None not in key:
                            if key in seen[ix.name]:
                                raise IntegrityError(f"UNIQUE 約束：{t.name} 有重複的 ({', '.join(ix.columns)}) = {key}")
                            seen[ix.name].add(key)
                    t.heap.insert(row)
                    n += 1
                self._rebuild_indexes(t, indexes)
            except BaseException:
                if not self.closed:                  # 匯入途中當機（db.crash()）時，什麼都不能再寫
                    with self.pool.page(tail, dirty=True) as p:
                        p.data[:] = before           # 鏈尾還原：之後接上的頁不在鏈上了（頁不回收）
                    t.heap._last = None
                    self._rebuild_indexes(t, indexes)    # 也蓋掉可能建了一半的索引
                    self.checkpoint()
                raise
            self.checkpoint()
            return n

    def _rebuild_indexes(self, t, indexes) -> None:
        """由表現在的內容重建這些索引；根的頁號不變，把新建的根複製過去。"""
        for ix in indexes:
            root = self.build_index(t, ix.positions, ix.unique)
            with self.pool.page(root) as src, self.pool.page(ix.root, dirty=True) as dst:
                dst.data[:] = src.data

    # ------------------------------------------------------------- 剖析
    def parse(self, sql: str) -> list:
        """剖析一段 SQL；同樣的文字只剖析一次（ANTLR 的 Python runtime 不快）。"""
        stmts = self._parsed.get(sql)
        if stmts is None:
            stmts = parse(sql)
            if len(self._parsed) > 1000:
                self._parsed.clear()
            self._parsed[sql] = stmts
        return stmts

    # ------------------------------------------------------------- 交易
    def begin_txn(self) -> Txn:
        """開始一個交易：給它下一個編號，寫一筆 begin（定義 9.4.1）。"""
        with self.latch:
            txn = Txn(self._next_txn)
            self._next_txn += 1
            self.active[txn.id] = txn
            self.wal.append(txn.id, "begin")
            return txn

    def commit_txn(self, txn: Txn) -> None:
        """提交：寫 commit 並寫出日誌（WAL 的規則 2，定義 9.4.2），再放掉全部的鎖（嚴謹 2PL，定義 9.2.3）。"""
        with self.latch:
            self.wal.append(txn.id, "commit")
            self.wal.flush()                         # WAL 規則 2：commit 之前日誌先寫到磁碟
            del self.active[txn.id]
        self.locks.release_all(txn.id)

    def undo_records(self, txn: Txn, start: int = 0) -> None:
        """由後往前撤銷 txn.records[start:]：每一筆寫一筆 CLR，索引也跟著改回來。
        start > 0 是交易中一句失敗時只撤銷這一句（第 8 章的定義 8.3.21；逾時的情形是定義 9.2.9）；鎖都還在，交易繼續。"""
        with self.latch:
            for rec in reversed(txn.records[start:]):
                if rec["type"] == "newpage":
                    continue                         # 新配置的頁留著，裡面沒有記錄
                t = self.catalog.table(rec["table"])
                clr = compensate(self.wal, t.heap, rec, txn.id)
                for ix in self.catalog.indexes_on(t.name):
                    if clr["type"] == "delete":
                        ix.tree.delete(ix.key_of(tuple(clr["before"])), tuple(clr["rid"]))
                    else:
                        ix.tree.insert(ix.key_of(tuple(clr["after"])), tuple(clr["rid"]))
            del txn.records[start:]

    def rollback_txn(self, txn: Txn) -> None:
        """回滾：撤銷全部的修改（寫 CLR）、寫 abort，再放掉全部的鎖。"""
        self.undo_records(txn)
        with self.latch:
            self.wal.append(txn.id, "abort")
            self.active.pop(txn.id, None)
        self.locks.release_all(txn.id)

    def lock(self, txn: Txn, table: str, mode: str) -> None:
        """在 latch 之外向 lock manager 要表鎖（命題 9.2.8）；成為死結的犧牲者時回滾整個交易（定義 9.3.6）。"""
        try:
            self.locks.acquire(txn.id, ("table", table.lower()), mode)
        except DeadlockError:
            self.rollback_txn(txn)
            raise

    # ------------------------------------------------------------- checkpoint、當機、關閉
    def checkpoint(self, shutdown: bool = False) -> None:
        """checkpoint（定義 9.4.5）：寫出日誌，把所有 dirty 的頁寫回並 fsync，再寫一筆 checkpoint；
        沒有進行中的交易時，日誌從這一筆重新開始。持有 latch，所以期間沒有敘述在修改頁。
        shutdown=True 是 close 的最後一次 checkpoint：紀錄另記 "shutdown": true，表示正常關閉。"""
        with self.latch:
            self.wal.flush()
            self.pool.flush_all()
            self.pager.sync()
            mark = {"shutdown": True} if shutdown else {}
            rec = self.wal.append(0, "checkpoint", active=sorted(self.active), **mark)
            self.wal.flush()
            if not self.active:
                self.wal.restart_from(rec)

    def crash(self) -> None:
        """模擬當機（附錄 C 的定義 C.3.3 (1)）：記憶體裡的頁與還沒寫到磁碟的日誌都消失。
        之後要用 Database(同一個檔名) 重新開啟，開啟時做復原（演算法 9.4.10）。"""
        with self.latch:
            self.wal.crash()
            self.pool.drop_all()
            self.pager.close(sync=False)
            self.closed = True

    def close(self) -> None:
        """正常關閉：最後一次 checkpoint 記下 shutdown，下次開啟時就不必復原。"""
        if self.closed:
            return
        if self.active:
            raise TransactionError("還有交易沒有結束")
        self.checkpoint(shutdown=True)
        self.wal.close()
        self.pager.close()
        self.closed = True

    def _recover(self, log: list) -> dict:
        """開檔時發現上次沒有正常關閉：先復原（演算法 9.4.10）。索引的頁不寫日誌，
        可能帶著沒有提交的修改寫回，所以日誌在 checkpoint 之後沒有紀錄時，也要重建索引。"""
        def heap_of(name):
            return self.catalog.table(name).heap
        losers = redo(log, heap_of)
        clrs = undo(log, losers, heap_of, self.wal)
        for t in self.catalog.tables.values():
            t.heap._last = None
        for ix in self.catalog.indexes.values():     # 索引沒有寫日誌：由 heap 重建
            root = self.build_index(self.catalog.table(ix.table), ix.positions, ix.unique)
            with self.pool.page(root) as src, self.pool.page(ix.root, dirty=True) as dst:
                dst.data[:] = src.data               # 根的頁號不變：把新建的根複製過去
        self.checkpoint()
        return {"records": len(log), "losers": sorted(losers), "undone": len(clrs)}

    def _max_page_lsn(self) -> int:
        """資料檔中最大的頁 LSN（重新開啟時讀每一頁的標頭，不計入讀取的頁數）。"""
        return max((SlottedPage(bytearray(self.pager.peek(q))).lsn for q in range(self.pager.n_pages)), default=0)

    # ------------------------------------------------------------- 索引
    def build_index(self, t, positions: list, unique: bool) -> int:
        """由表的內容建一棵 B+ tree，傳回根的頁號：(鍵, RID) 先外部排序（演算法 7.6.5），再由下而上建樹。"""
        n = len(positions)

        def entries():
            for rid, row in t.heap.scan():
                key = tuple(row[p] for p in positions)
                if None not in key:
                    yield key + rid
        ordered = ExternalSort(lambda e: e, self.sort_memory_pages, self.pager.page_size).sort(entries())
        pairs, last = [], None
        for e in ordered:
            key = e[:n]
            if unique and key == last:
                names = ", ".join(t.schema.names[p] for p in positions)
                raise IntegrityError(f"UNIQUE 約束：{t.name} 有重複的 ({names}) = {key}")
            pairs.append((key, e[n:]))
            last = key
        return BPlusTree.build(self.pool, key_schema(t.schema, positions), pairs)

    # ------------------------------------------------------------- 統計
    def stats(self) -> dict:
        return {"page_reads": self.pager.reads, "page_writes": self.pager.writes,
                "buffer_hits": self.pool.hits, "buffer_misses": self.pool.misses,
                "wal_flushes": self.wal.flushes, "statements": self.statements}

    def reset_stats(self) -> None:
        self.pager.reads = self.pager.writes = self.pool.hits = self.pool.misses = 0
        self.wal.flushes = self.statements = 0


class Connection:
    def __init__(self, db: Database):
        self.db, self.txn = db, None

    # ------------------------------------------------------------- 入口
    def execute(self, sql: str, params=()) -> Result:
        stmts = self.db.parse(sql)
        if len(stmts) != 1:
            raise NotSupported("execute 一次執行一句；多句請用 executescript")
        return self.run(stmts[0], tuple(params))

    def executemany(self, sql: str, seq_of_params) -> Result:
        """同一句、多組參數：只剖析一次；沒有 BEGIN 時，全部在同一個交易裡。"""
        stmts = self.db.parse(sql)
        if len(stmts) != 1 or not isinstance(stmts[0], (ast.Insert, ast.Update, ast.Delete)):
            raise NotSupported("executemany 只用在一句 INSERT、UPDATE 或 DELETE")
        auto = self.txn is None
        if auto:
            self.begin()
        total = 0
        try:
            for params in seq_of_params:
                total += self.run(stmts[0], tuple(params)).rowcount
        except BaseException:                        # 包括被中斷：自己開始的交易一定結束
            if auto and self.txn is not None:
                self.rollback()
            raise
        if auto:
            self.commit()
        return Result([], [], total)

    def executescript(self, sql: str) -> None:
        for stmt in self.db.parse(sql):
            self.run(stmt, ())

    def explain(self, sql: str, params=(), analyze: bool = False) -> str:
        """查詢計畫。analyze=True 時真的執行一次，並列出每個運算子交出的列數。"""
        stmt = self.db.parse(sql)[0]
        if not isinstance(stmt, ast.Select):
            raise NotSupported("explain 只用在 SELECT")
        res = self.run(stmt, tuple(params), execute=analyze)
        return res.plan.explain(analyze)

    def begin(self) -> None:
        if self.txn is not None:
            raise TransactionError("交易已經開始了")
        self.txn = self.db.begin_txn()

    def commit(self) -> None:
        if self.txn is None:
            raise TransactionError("沒有進行中的交易")
        txn, self.txn = self.txn, None
        self.db.commit_txn(txn)

    def rollback(self) -> None:
        if self.txn is None:
            raise TransactionError("沒有進行中的交易")
        txn, self.txn = self.txn, None
        self.db.rollback_txn(txn)

    # ------------------------------------------------------------- 分派
    def run(self, stmt, params: tuple, execute: bool = True) -> Result:
        db = self.db
        if db.closed:
            raise Error("資料庫已經關閉")
        db.statements += 1
        if isinstance(stmt, ast.Begin):
            self.begin()
            return Result([], [])
        if isinstance(stmt, ast.Commit):
            self.commit()
            return Result([], [])
        if isinstance(stmt, ast.Rollback):
            self.rollback()
            return Result([], [])
        if isinstance(stmt, ast.Explain):
            if not isinstance(stmt.stmt, ast.Select):
                raise NotSupported("EXPLAIN 只用在 SELECT")
            plan = self.run(stmt.stmt, params, execute=False).plan
            return Result(["plan"], [(line,) for line in plan.explain().splitlines()], plan=plan)
        if isinstance(stmt, (ast.CreateTable, ast.CreateIndex, ast.Drop)):
            return self.ddl(stmt)

        auto = self.txn is None
        if auto:
            self.txn = db.begin_txn()
        txn, mark = self.txn, len(self.txn.records)
        try:
            for name, mode in self.tables_used(stmt):
                db.lock(txn, name, mode)             # 在 latch 之外等鎖
            with db.latch:
                if isinstance(stmt, ast.Select):
                    result = self.select(stmt, params, execute)
                elif isinstance(stmt, ast.Insert):
                    result = self.insert(stmt, params)
                elif isinstance(stmt, ast.Update):
                    result = self.update(stmt, params)
                else:
                    result = self.delete(stmt, params)
        except DeadlockError:
            self.txn = None                          # db.lock 已經把整個交易 rollback
            raise
        except BaseException:                        # 一句失敗，或被中斷（例如 KeyboardInterrupt）
            if auto:
                self.txn = None
                db.rollback_txn(txn)
            else:                                    # 交易裡有一句失敗：只撤銷這一句，交易繼續（和 SQLite 一樣）
                db.undo_records(txn, mark)
            raise
        if auto:
            self.txn = None
            db.commit_txn(txn)
        return result

    def tables_used(self, stmt) -> list:
        """這一句要鎖哪些表（定義 9.2.2）：依 FROM 的次序，讀的表 S 鎖，寫的表 X 鎖。"""
        def sources(sel):
            out, s = [], sel.source
            while isinstance(s, ast.Join):
                out.append(s.right.name)
                s = s.left
            return ([s.name] if s is not None else []) + out[::-1]
        if isinstance(stmt, ast.Select):
            return [(n, S) for n in sources(stmt)]
        if isinstance(stmt, ast.Insert):
            reads = sources(stmt.query) if stmt.query else []
            return [(n, S) for n in reads if n.lower() != stmt.table.lower()] + [(stmt.table, X)]
        return [(stmt.table.name, X)]

    # ------------------------------------------------------------- DDL
    def ddl(self, stmt) -> Result:
        db = self.db
        if self.txn is not None or db.active:
            raise TransactionError("CREATE、DROP 要在沒有任何進行中的交易時執行")
        with db.latch:
            cat = db.catalog
            if isinstance(stmt, ast.CreateTable):
                if cat.exists(stmt.name):
                    if stmt.if_not_exists:
                        return Result([], [], 0)
                    raise BindError(f"名稱 {stmt.name} 已經用過了")
                names = [c.name.lower() for c in stmt.columns]
                if len(set(names)) != len(names):
                    raise BindError("欄名重複")
                for cols in [stmt.primary_key] + stmt.uniques:
                    for c in cols:
                        if c.lower() not in names:
                            raise BindError(f"約束裡的欄 {c} 不在表裡")
                pk = {c.lower() for c in stmt.primary_key}
                schema = Schema([Column(c.name, c.type, c.not_null or c.name.lower() in pk) for c in stmt.columns])
                t = cat.add_table(stmt.name, schema, list(stmt.primary_key), self.create_sql(stmt))
                if stmt.primary_key:
                    self.make_index(f"pk_{t.name}", t.name, stmt.primary_key, True)
                for i, cols in enumerate(stmt.uniques, start=1):
                    self.make_index(f"uq_{t.name}_{i}", t.name, cols, True)
            elif isinstance(stmt, ast.CreateIndex):
                if cat.exists(stmt.name):
                    if stmt.if_not_exists:
                        return Result([], [], 0)
                    raise BindError(f"名稱 {stmt.name} 已經用過了")
                if cat.table(stmt.table).name == SCHEMA_TABLE:
                    raise BindError("不能在系統目錄上建索引")
                self.make_index(stmt.name, stmt.table, stmt.columns, stmt.unique)
            else:
                exists = (stmt.name.lower() in cat.tables if stmt.kind == "TABLE"
                          else stmt.name.lower() in cat.indexes)
                if not exists:
                    if stmt.if_exists:
                        return Result([], [], 0)
                    raise BindError(f"沒有{'表' if stmt.kind == 'TABLE' else '索引'} {stmt.name}")
                (cat.drop_table if stmt.kind == "TABLE" else cat.drop_index)(stmt.name)
            db.checkpoint()                          # DDL 不寫日誌：做完立刻 checkpoint
        return Result([], [], 0)

    def make_index(self, name: str, table: str, columns: list, unique: bool) -> None:
        db, t = self.db, self.db.catalog.table(table)
        for c in columns:
            t.schema.index_of(c)
        sql = (f"CREATE {'UNIQUE ' if unique else ''}INDEX {ast.ident(name)} ON {ast.ident(t.name)} "
               f"({', '.join(ast.ident(c) for c in columns)})")
        root = db.build_index(t, [t.schema.index_of(c) for c in columns], unique)
        db.catalog.add_index(name, t.name, list(columns), unique, sql, root)

    @staticmethod
    def create_sql(stmt) -> str:
        cols = []
        for c in stmt.columns:
            cols.append(f"{ast.ident(c.name)} {c.type}" + (" NOT NULL" if c.not_null else "")
                        + (" UNIQUE" if c.unique else ""))
        if stmt.primary_key:
            cols.append(f"PRIMARY KEY ({', '.join(ast.ident(c) for c in stmt.primary_key)})")
        for u in stmt.uniques[len([c for c in stmt.columns if c.unique]):]:
            cols.append(f"UNIQUE ({', '.join(ast.ident(c) for c in u)})")
        return f"CREATE TABLE {ast.ident(stmt.name)} ({', '.join(cols)})"

    # ------------------------------------------------------------- SELECT
    def planner(self, params) -> Planner:
        return Planner(self.db.catalog, params, self.db.sort_memory_pages, self.db.pager.page_size)

    def select(self, stmt, params, execute: bool = True) -> Result:
        q = bind_select(stmt, self.db.catalog)
        plan = self.planner(params).plan(q)
        rows = list(plan.root) if execute else []
        return Result(plan.columns, rows, len(rows), plan)

    # ------------------------------------------------------------- INSERT、UPDATE、DELETE
    def writable(self, name: str):
        t = self.db.catalog.table(name)
        if t.name == SCHEMA_TABLE:
            raise BindError("系統目錄不能直接修改")
        return t

    def insert(self, stmt, params) -> Result:
        t = self.writable(stmt.table)
        names = stmt.columns or t.schema.names
        positions = [t.schema.index_of(n) for n in names]
        if len(set(positions)) != len(positions):
            raise BindError("INSERT 列出的欄重複了")
        if stmt.rows is not None:
            empty = Scope([])

            def value(e):
                if isinstance(e, ast.Param) and e.index < len(params):
                    return params[e.index]           # 最常見的情形：參數，直接取值
                if isinstance(e, ast.Lit):
                    return e.value
                return compile_expr(bind_expr(e, empty), lambda x: None, params)(())
            rows = [[value(e) for e in row] for row in stmt.rows]
        else:
            rows = self.select(stmt.query, params).rows
        for values in rows:
            if len(values) != len(positions):
                raise BindError(f"INSERT 有 {len(positions)} 欄，但這一列有 {len(values)} 個值")
            full = [None] * len(t.schema)
            for p, v in zip(positions, values):
                full[p] = v
            self.insert_row(t, t.schema.check(tuple(full)))
        return Result([], [], len(rows))

    def insert_row(self, t, row: tuple):
        indexes = self.db.catalog.indexes_on(t.name)
        for ix in indexes:
            self.check_unique(t, ix, row)
        rid = t.heap.insert(row, self.txn)
        for ix in indexes:
            ix.tree.insert(ix.key_of(row), rid)
        return rid

    @staticmethod
    def check_unique(t, ix, row: tuple, rid=None) -> None:
        if not ix.unique:
            return
        key = ix.key_of(row)
        if None not in key and any(r != rid for r in ix.tree.search(key)):
            what = "PRIMARY KEY" if ix.name == f"pk_{t.name}" else "UNIQUE"
            raise IntegrityError(f"{what} 約束：{t.name} 已經有 {', '.join(ix.columns)} = "
                                 f"{key[0] if len(key) == 1 else key} 的列")

    def targets(self, ref: ast.TableRef, where, params):
        """UPDATE、DELETE 要改的列：[(rid, 列)]。先全部找出來再改，避免改過的列又被找到
        （Halloween problem，第 8 章的定義 8.3.22）。"""
        t = self.writable(ref.name)
        rel = Rel(t.name, t, ref.indexed_by, ref.not_indexed)
        if ref.indexed_by:
            ix = self.db.catalog.index(ref.indexed_by)
            if ix.table.lower() != t.name.lower():
                raise BindError(f"索引 {ix.name} 不是表 {t.name} 的索引")
        scope = Scope([rel])
        conds = [bind_expr(c, scope) for c in conjuncts(where)]
        planner = self.planner(params)
        everything = {(0, j) for j in range(len(t.schema))}
        op, rest, _ = planner.scan(0, rel, conds, everything)
        check = planner.compile_all(rest, op.columns) if rest else None
        return t, scope, [(rid, row) for rid, row in op.with_rids() if check is None or truth(check(row)) == 1]

    def update(self, stmt, params) -> Result:
        t, scope, found = self.targets(stmt.table, stmt.where, params)
        sets = []
        for name, e in stmt.assignments:
            sets.append((t.schema.index_of(name), compile_expr(bind_expr(e, scope), resolver(
                [(0, j) for j in range(len(t.schema))]), params)))
        indexes = self.db.catalog.indexes_on(t.name)
        for rid, old in found:
            new = list(old)
            for p, f in sets:
                new[p] = f(old)
            new = t.schema.check(tuple(new))
            for ix in indexes:
                if ix.key_of(new) != ix.key_of(old):
                    self.check_unique(t, ix, new, rid)
            new_rid = t.heap.update(rid, new, self.txn)
            for ix in indexes:
                ix.tree.delete(ix.key_of(old), rid)
                ix.tree.insert(ix.key_of(new), new_rid)
        return Result([], [], len(found))

    def delete(self, stmt, params) -> Result:
        t, _, found = self.targets(stmt.table, stmt.where, params)
        indexes = self.db.catalog.indexes_on(t.name)
        for rid, old in found:
            t.heap.delete(rid, self.txn)
            for ix in indexes:
                ix.tree.delete(ix.key_of(old), rid)
        return Result([], [], len(found))
