"""系統目錄（catalog）：記下有哪些表與索引、它們的欄，以及資料從哪一頁開始。

仿照 SQLite 的 sqlite_schema，目錄本身也是一張表 minidb_schema，存在從第 0 頁開始的 heap file，
可以用 SELECT * FROM minidb_schema 查看。每一列是一張表或一個索引：

    type      'table' 或 'index'
    name      名稱
    tbl_name  索引所屬的表；表的這一欄是它自己
    rootpage  表：heap file 的第一頁；索引：B+ tree 的根（建立之後不變）
    sql       建立它的 CREATE 敘述（給人看）
    info      欄與約束（JSON，給引擎用）
"""

import json
from dataclasses import dataclass, field

from .btree import BPlusTree
from .errors import BindError
from .heap import HeapFile
from .record import Column, Schema

SCHEMA_TABLE = "minidb_schema"
SCHEMA_SCHEMA = Schema([Column("type", "TEXT", True), Column("name", "TEXT", True),
                        Column("tbl_name", "TEXT", True), Column("rootpage", "INTEGER", True),
                        Column("sql", "TEXT"), Column("info", "TEXT")])


@dataclass(eq=False)
class TableInfo:
    name: str
    schema: Schema
    first_page: int
    primary_key: list = field(default_factory=list)
    sql: str = ""
    heap: HeapFile | None = field(default=None, repr=False)
    rid: tuple | None = field(default=None, repr=False)     # 在 minidb_schema 裡的 RID


@dataclass(eq=False)
class IndexInfo:
    name: str
    table: str
    columns: list
    unique: bool
    root: int
    sql: str = ""
    positions: list = field(default_factory=list)          # 索引欄在表裡是第幾欄
    tree: BPlusTree | None = field(default=None, repr=False)
    rid: tuple | None = field(default=None, repr=False)

    def key_of(self, row: tuple) -> tuple:
        """一列的索引鍵。"""
        return tuple(row[p] for p in self.positions)


def key_schema(schema: Schema, positions: list) -> Schema:
    """索引鍵的 Schema：表的第 positions 欄（鍵不收 NULL，所以不必記 NOT NULL）。"""
    return Schema([Column(schema.columns[p].name, schema.columns[p].type) for p in positions])


class Catalog:
    def __init__(self, pool, wal=None):
        self.pool, self.wal = pool, wal
        if pool.pager.n_pages == 0:                  # 新的資料庫：第 0 頁是目錄的第一頁
            assert HeapFile.create(pool) == 0
        self.heap = HeapFile(pool, 0, SCHEMA_SCHEMA, SCHEMA_TABLE)
        self.tables: dict[str, TableInfo] = {}
        self.indexes: dict[str, IndexInfo] = {}
        self.load()

    def load(self) -> None:
        """讀 minidb_schema，重建記憶體裡的目錄。"""
        self.tables.clear()
        self.indexes.clear()
        self.tables[SCHEMA_TABLE] = TableInfo(SCHEMA_TABLE, SCHEMA_SCHEMA, 0, heap=self.heap)
        rows = list(self.heap.scan())
        for rid, (kind, name, tbl, root, sql, info) in rows:
            if kind == "table":
                d = json.loads(info)
                t = TableInfo(name, Schema.from_list(d["columns"]), root, d["primary_key"], sql, rid=rid)
                t.heap = HeapFile(self.pool, root, t.schema, name, self.wal)
                self.tables[name.lower()] = t
        for rid, (kind, name, tbl, root, sql, info) in rows:
            if kind == "index":
                d = json.loads(info)
                self._attach(IndexInfo(name, tbl, d["columns"], d["unique"], root, sql, rid=rid))

    def _attach(self, ix: IndexInfo) -> None:
        t = self.table(ix.table)
        ix.positions = [t.schema.index_of(c) for c in ix.columns]
        ix.tree = BPlusTree(self.pool, ix.root, key_schema(t.schema, ix.positions))
        self.indexes[ix.name.lower()] = ix

    # ------------------------------------------------------------- 查詢
    def table(self, name: str) -> TableInfo:
        t = self.tables.get(name.lower())
        if t is None:
            raise BindError(f"沒有表 {name}")
        return t

    def index(self, name: str) -> IndexInfo:
        ix = self.indexes.get(name.lower())
        if ix is None:
            raise BindError(f"沒有索引 {name}")
        return ix

    def indexes_on(self, table: str) -> list[IndexInfo]:
        return [ix for ix in self.indexes.values() if ix.table.lower() == table.lower()]

    def exists(self, name: str) -> bool:
        return name.lower() in self.tables or name.lower() in self.indexes

    # ------------------------------------------------------------- 修改（DDL）
    def add_table(self, name: str, schema: Schema, primary_key: list, sql: str) -> TableInfo:
        if self.exists(name):
            raise BindError(f"名稱 {name} 已經用過了")
        first = HeapFile.create(self.pool)
        info = json.dumps({"columns": schema.to_list(), "primary_key": primary_key}, ensure_ascii=False)
        rid = self.heap.insert(("table", name, name, first, sql, info))
        t = TableInfo(name, schema, first, primary_key, sql, rid=rid)
        t.heap = HeapFile(self.pool, first, schema, name, self.wal)
        self.tables[name.lower()] = t
        return t

    def add_index(self, name: str, table: str, columns: list, unique: bool, sql: str, root: int) -> IndexInfo:
        if self.exists(name):
            raise BindError(f"名稱 {name} 已經用過了")
        t = self.table(table)
        info = json.dumps({"columns": columns, "unique": unique}, ensure_ascii=False)
        rid = self.heap.insert(("index", name, t.name, root, sql, info))
        ix = IndexInfo(name, t.name, columns, unique, root, sql, rid=rid)
        self._attach(ix)
        return ix

    def drop_table(self, name: str) -> None:
        t = self.table(name)
        if t.name == SCHEMA_TABLE:
            raise BindError("不能刪除系統目錄")
        for ix in self.indexes_on(t.name):
            self.drop_index(ix.name)
        self.heap.delete(t.rid)                      # 資料頁不回收：檔案不會變小（第 6 章的命題 6.3.7）
        del self.tables[t.name.lower()]

    def drop_index(self, name: str) -> None:
        ix = self.index(name)
        self.heap.delete(ix.rid)
        del self.indexes[ix.name.lower()]
