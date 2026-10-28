"""運算子：查詢計畫的每個節點都是一個 iterator，一次交出一列（Volcano 模型）。

第 8 章的定義 8.3.1 說明 iterator 模型：上層向下層要一列，下層才去拿它需要的列；所以 Limit 拿夠了，
下層就不再讀。每個運算子都是 Op 的子類別：

    columns     輸出的每一欄是什麼：[(FROM 的第幾張表, 第幾欄)] 或彙總之後的運算式
    __iter__    依序交出輸出的列（tuple）
    describe()  一行說明，EXPLAIN 用
    children()  下層的運算子

rows_out 記錄這個運算子一共交出了幾列，loops 記錄它被從頭讀了幾次（EXPLAIN ANALYZE 用）。
"""

import heapq

from ..sort import ExternalSort
from .expr import Aggregate, Desc, sort_key, truth


class Op:
    rows_out = loops = 0

    def children(self) -> list:
        return []

    def __iter__(self):
        self.loops += 1
        for row in self.rows():
            self.rows_out += 1
            yield row

    def rows(self):
        raise NotImplementedError

    def explain(self, analyze: bool = False, depth: int = 0) -> list[str]:
        line = "  " * depth + self.describe()
        if analyze:
            line += f"  （交出 {self.rows_out} 列" + (f"，讀了 {self.loops} 次）" if self.loops > 1 else "）")
        lines = [line]
        for child in self.children():
            lines += child.explain(analyze, depth + 1)
        return lines


# ---------------------------------------------------------------- 掃描
class SeqScan(Op):
    """全表掃描：依序讀 heap file 的每一頁。"""

    def __init__(self, rel_no: int, rel):
        self.rel_no, self.rel = rel_no, rel
        self.columns = [(rel_no, j) for j in range(len(rel.table.schema))]

    def with_rids(self):
        yield from self.rel.table.heap.scan()

    def rows(self):
        for _, row in self.with_rids():
            yield row

    def describe(self):
        t = self.rel.table.name
        return f"SeqScan {t}" + (f" AS {self.rel.alias}" if self.rel.alias != t else "")


class IndexScan(Op):
    """索引掃描：在 B+ tree 找出鍵在範圍內的項目，再依 RID 到 heap 讀那一列。

    only=True 時是 index-only scan：要用的欄都在索引鍵裡，不必讀 heap（其餘的欄是 None）。"""

    def __init__(self, rel_no: int, rel, index, lo=None, hi=None, lo_inc=True, hi_inc=True,
                 text: str = "", only: bool = False):
        self.rel_no, self.rel, self.index = rel_no, rel, index
        self.lo, self.hi, self.lo_inc, self.hi_inc = lo, hi, lo_inc, hi_inc
        self.text, self.only = text, only
        self.columns = [(rel_no, j) for j in range(len(rel.table.schema))]
        self.heap_fetches = 0

    def with_rids(self):
        heap, width = self.rel.table.heap, len(self.rel.table.schema)
        for key, rid in self.index.tree.range(self.lo, self.hi, self.lo_inc, self.hi_inc):
            if self.only:
                row = [None] * width
                for p, v in zip(self.index.positions, key):
                    row[p] = v
                yield rid, tuple(row)
            else:
                self.heap_fetches += 1
                yield rid, heap.get(rid)

    def rows(self):
        for _, row in self.with_rids():
            yield row

    def describe(self):
        t = self.rel.table.name
        kind = "IndexOnlyScan" if self.only else "IndexScan"
        alias = f" AS {self.rel.alias}" if self.rel.alias != t else ""
        return f"{kind} {t}{alias} USING {self.index.name}" + (f" ({self.text})" if self.text else "")


class OneRow(Op):
    """沒有 FROM 的 SELECT：一列、沒有欄。"""
    columns = []

    def rows(self):
        yield ()

    def describe(self):
        return "OneRow"


# ---------------------------------------------------------------- 逐列處理
class Filter(Op):
    def __init__(self, child: Op, pred, text: str):
        self.child, self.pred, self.text, self.columns = child, pred, text, child.columns

    def rows(self):
        return (row for row in self.child if truth(self.pred(row)) == 1)

    def children(self):
        return [self.child]

    def describe(self):
        return f"Filter {self.text}"


class Project(Op):
    def __init__(self, child: Op, fns: list, names: list):
        self.child, self.fns, self.names = child, fns, names
        self.columns = list(names)

    def rows(self):
        return (tuple(f(row) for f in self.fns) for row in self.child)

    def children(self):
        return [self.child]

    def describe(self):
        return "Project " + ", ".join(self.names)


class Limit(Op):
    def __init__(self, child: Op, n, offset: int = 0):
        self.child, self.n, self.offset, self.columns = child, n, offset, child.columns

    def rows(self):
        if self.n is not None and self.n <= 0:
            return
        for i, row in enumerate(self.child):
            if i < self.offset:
                continue
            yield row
            if self.n is not None and i + 1 - self.offset >= self.n:
                return                               # 拿夠了就不再向下要

    def children(self):
        return [self.child]

    def describe(self):
        return f"Limit {self.n}" + (f" OFFSET {self.offset}" if self.offset else "")


class Distinct(Op):
    def __init__(self, child: Op):
        self.child, self.columns = child, child.columns

    def rows(self):
        seen = set()
        for row in self.child:
            if row not in seen:
                seen.add(row)
                yield row

    def children(self):
        return [self.child]

    def describe(self):
        return "Distinct"


# ---------------------------------------------------------------- join
class NestedLoopJoin(Op):
    """外層的每一列，都把內層從頭讀一遍。kind 是 'INNER' 或 'LEFT'。"""

    def __init__(self, left: Op, right: Op, pred, text: str, kind: str = "INNER"):
        self.left, self.right, self.pred, self.text, self.kind = left, right, pred, text, kind
        self.columns = left.columns + right.columns

    def rows(self):
        pad = (None,) * len(self.right.columns)
        for l in self.left:
            matched = False
            for r in self.right:
                if self.pred is None or truth(self.pred(l + r)) == 1:
                    matched = True
                    yield l + r
            if not matched and self.kind == "LEFT":
                yield l + pad

    def children(self):
        return [self.left, self.right]

    def describe(self):
        kind = "LeftNestedLoopJoin" if self.kind == "LEFT" else "NestedLoopJoin"
        return kind + (f" ON {self.text}" if self.text else "")


class IndexNestedLoopJoin(Op):
    """外層的每一列算出鍵，到內層表的索引找相等的項目（內層不必整張讀）。"""

    def __init__(self, left: Op, rel_no: int, rel, index, key_fns: list, residual, text: str, kind: str = "INNER"):
        self.left, self.rel_no, self.rel, self.index = left, rel_no, rel, index
        self.key_fns, self.residual, self.text, self.kind = key_fns, residual, text, kind
        self.columns = left.columns + [(rel_no, j) for j in range(len(rel.table.schema))]

    def rows(self):
        heap, pad = self.rel.table.heap, (None,) * len(self.rel.table.schema)
        for l in self.left:
            key = tuple(f(l) for f in self.key_fns)
            matched = False
            if None not in key:                      # NULL 的鍵永遠對不上
                for rid in self.index.tree.search(key):
                    row = l + heap.get(rid)
                    if self.residual is None or truth(self.residual(row)) == 1:
                        matched = True
                        yield row
            if not matched and self.kind == "LEFT":
                yield l + pad

    def children(self):
        return [self.left]

    def describe(self):
        kind = "LeftIndexNestedLoopJoin" if self.kind == "LEFT" else "IndexNestedLoopJoin"
        return f"{kind} {self.rel.table.name} USING {self.index.name} ON {self.text}"


class HashJoin(Op):
    """等值 join：先把右邊讀一次建成雜湊表（build），再讀左邊一次去查（probe）。"""

    def __init__(self, left: Op, right: Op, left_keys: list, right_keys: list, residual, text: str,
                 kind: str = "INNER"):
        self.left, self.right, self.left_keys, self.right_keys = left, right, left_keys, right_keys
        self.residual, self.text, self.kind = residual, text, kind
        self.columns = left.columns + right.columns

    def rows(self):
        # 練習 U08-E：HashJoin.rows（見本回的練習集）
        raise NotImplementedError("練習 U08-E：HashJoin.rows")

    def children(self):
        return [self.left, self.right]

    def describe(self):
        return ("LeftHashJoin" if self.kind == "LEFT" else "HashJoin") + f" ON {self.text}"


# ---------------------------------------------------------------- 彙總與排序
class HashAggregate(Op):
    """以雜湊表分組；每一組為每個彙總函數保留一個累積狀態。輸出：分組鍵, 彙總結果。"""

    def __init__(self, child: Op, key_fns: list, aggs: list, arg_fns: list, columns: list, text: str):
        self.child, self.key_fns, self.aggs, self.arg_fns = child, key_fns, aggs, arg_fns
        self.columns, self.text = columns, text

    def _state(self):
        return [Aggregate(a.name, arg is None, a.distinct) for a, arg in zip(self.aggs, self.arg_fns)]

    def rows(self):
        groups = {}
        for row in self.child:
            key = tuple(f(row) for f in self.key_fns)
            state = groups.get(key)
            if state is None:
                state = groups[key] = self._state()
            for acc, f in zip(state, self.arg_fns):
                acc.add(None if f is None else f(row))
        if not groups and not self.key_fns:          # 沒有 GROUP BY：空表也要輸出一列
            groups[()] = self._state()
        for key, state in groups.items():
            yield key + tuple(acc.result() for acc in state)

    def children(self):
        return [self.child]

    def describe(self):
        return "HashAggregate " + self.text


class Sort(Op):
    """排序（blocking：讀完下層才交出第一列）。資料超過 memory_pages 頁時用外部合併排序（第 7 章的命題 7.6.6）。"""

    def __init__(self, child: Op, key_fns: list, descending: list, text: str, memory_pages: int, page_size: int):
        self.child, self.key_fns, self.descending, self.text = child, key_fns, descending, text
        self.memory_pages, self.page_size, self.columns = memory_pages, page_size, child.columns
        self.sorter = None

    def key(self, row):
        return tuple(Desc(sort_key(f(row))) if d else sort_key(f(row))
                     for f, d in zip(self.key_fns, self.descending))

    def rows(self):
        self.sorter = ExternalSort(self.key, self.memory_pages, self.page_size)
        yield from self.sorter.sort(self.child)

    def children(self):
        return [self.child]

    def describe(self):
        return f"Sort {self.text}"


class TopN(Sort):
    """ORDER BY ... LIMIT n：只保留目前最小的 n 列（heap），不必把全部排好（PostgreSQL 的 top-N heapsort）。"""

    def __init__(self, child: Op, key_fns: list, descending: list, text: str, n: int):
        super().__init__(child, key_fns, descending, text, 0, 0)
        self.n = n

    def rows(self):
        yield from heapq.nsmallest(self.n, self.child, key=self.key)   # 相同的鍵保持原來的順序

    def describe(self):
        return f"TopN {self.n} BY {self.text}"
