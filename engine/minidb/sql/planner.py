"""Planner：把 binder 的 Query 變成運算子樹（查詢計畫）。

第 8 章的定義 8.4.4（引擎的規則）。這裡只用規則、不估計成本：
  R1 條件往下推：只用到一張表的條件，放在那張表的掃描上；用到幾張表的，放在它們都接上的那一步。
     LEFT JOIN 右邊那張表的 WHERE 條件不能往下推（會改變結果），只有 ON 的條件可以。
  R2 存取路徑：條件對上索引鍵的前綴（等值欄在前，最後可以有一個範圍）就用索引掃描；
     查詢用到的欄都在索引鍵裡，就連 heap 都不讀（index-only scan）。
  R3 join 的演算法：內層表在 join 欄上有索引 → index nested loop join；
     有等值條件 → hash join；否則 nested loop join。
  R4 索引已經依 ORDER BY 的順序交出各列時，省掉 Sort；有 LIMIT n 時，只保留最小的 n 列（top-N）。
join 的順序就是 FROM 的順序（向左長的樹）。PostgreSQL 依估計的成本挑順序與演算法，見第 8 章的 8.4 節。

我們的 B+ tree 不放鍵裡有 NULL 的列，所以索引只在「索引的每一欄都不會是 NULL」時可用：
那一欄宣告為 NOT NULL，或查詢的條件已經排除了 NULL（例如 x = 3、x > 3）。
"""

from dataclasses import dataclass

from ..errors import BindError
from .ast import BinOp, ColRef, Star, Unary, children, sql
from .binder import Query, Rel
from .expr import _and, compile_expr
from .operators import (Distinct, Filter, HashAggregate, HashJoin, IndexNestedLoopJoin, IndexScan, Limit,
                        NestedLoopJoin, OneRow, Project, SeqScan, Sort, TopN)

FLIP = {"=": "=", "<": ">", "<=": ">=", ">": "<", ">=": "<="}
NULL_REJECTING = {"=", "<>", "<", "<=", ">", ">=", "LIKE", "BETWEEN", "IN"}


def rels_of(e) -> set:
    """運算式用到哪幾張表（FROM 的序號）。"""
    if isinstance(e, ColRef):
        return {e.rel}
    out = set()
    for c in children(e):
        out |= rels_of(c)
    return out


def colrefs(e, out: set) -> set:
    if isinstance(e, ColRef):
        out.add((e.rel, e.col))
    for c in children(e):
        colrefs(c, out)
    return out


def text_of(conds: list) -> str:
    return " AND ".join(sql(c, 2) for c in conds)


def _slot_key(c):
    """同一欄不論寫成什麼標籤，都對到同一個位置。"""
    return (c.rel, c.col) if isinstance(c, ColRef) else c


def resolver(columns: list):
    """運算子的輸出欄 → 函數：運算式在輸出列的第幾欄（不在就是 None）。

    columns 的每一項是 (第幾張表, 第幾欄)，或是彙總之後的運算式（分組鍵、彙總函數）。"""
    where = {}
    for i, c in enumerate(columns):
        where.setdefault(_slot_key(c), i)

    def resolve(e):
        try:
            return where.get(_slot_key(e))
        except TypeError:                            # 不能當 dict 鍵的運算式
            return None
    return resolve


@dataclass
class Plan:
    root: object
    columns: list                                    # 輸出欄名

    def explain(self, analyze: bool = False) -> str:
        return "\n".join(self.root.explain(analyze))


class Planner:
    def __init__(self, catalog, params=(), sort_memory_pages: int = 64, page_size: int = 4096):
        self.catalog, self.params = catalog, params
        self.sort_memory_pages, self.page_size = sort_memory_pages, page_size

    def compile(self, e, columns: list):
        return compile_expr(e, resolver(columns), self.params)

    def const(self, e):
        return compile_expr(e, lambda x: None, self.params)(())

    # ------------------------------------------------------------- SELECT
    def plan(self, q: Query) -> Plan:
        self.rels = q.rels
        refs = set()
        for e in ([e for e, _ in q.items] + q.where + q.group_by + [q.having] + [e for e, _ in q.order_by]
                  + [c for j in q.joins[1:] for c in j[1]]):
            if e is not None:
                colrefs(e, refs)
        n = len(q.rels)
        nullable = [k > 0 and q.joins[k][0] == "LEFT" for k in range(n)]
        local = [[] for _ in range(n)]               # 推到第 k 張表的掃描上
        join_preds = [[] for _ in range(n)]          # 第 k 步 join 的條件
        after = [[] for _ in range(n)]               # 第 k 步 join 之後才能用的條件
        top = []                                     # 不用到任何表的條件

        def place(c, from_on_of=None):
            s = rels_of(c)
            if from_on_of is not None and nullable[from_on_of]:   # LEFT JOIN 的 ON
                (local if s == {from_on_of} else join_preds)[from_on_of].append(c)
                return
            if not s:
                top.append(c)
                return
            k = max(s)
            if nullable[k]:
                after[k].append(c)
            elif len(s) == 1:
                local[k].append(c)
            else:
                join_preds[k].append(c)

        for c in q.where:
            place(c)
        for k in range(1, n):
            for c in q.joins[k][1]:
                place(c, from_on_of=k)

        if n == 0:
            node, order_done = OneRow(), False
        else:
            node, order_done = self.access_path(0, q.rels[0], local[0], refs, q.order_by if n == 1 else None,
                                                q.grouped, q.limit is not None)
            for k in range(1, n):
                node = self.join(node, k, q.rels[k], q.joins[k][0], join_preds[k], local[k], refs)
                if after[k]:
                    node = Filter(node, self.compile_all(after[k], node.columns), text_of(after[k]))
        if top:
            node = Filter(node, self.compile_all(top, node.columns), text_of(top))

        if q.grouped:
            node = self.aggregate(node, q)
        top_n = self.top_n(q)
        if q.order_by and not q.distinct and not order_done:
            node = self.sort(node, [(e, d) for e, d in q.order_by], top_n)
        names = [name for _, name in q.items]
        node = Project(node, [self.compile(e, node.columns) for e, _ in q.items], names)
        if q.distinct:
            node = Distinct(node)
            if q.order_by:
                exprs = [e for e, _ in q.items]
                keys = [(exprs.index(e), d) for e, d in q.order_by]
                node = Sort(node, [(lambda row, i=i: row[i]) for i, _ in keys], [d for _, d in keys],
                            ", ".join(sql(e) + (" DESC" if d else "") for e, d in q.order_by),
                            self.sort_memory_pages, self.page_size)
        if q.limit is not None or q.offset is not None:
            limit = self.const(q.limit) if q.limit is not None else None
            offset = self.const(q.offset) if q.offset is not None else 0
            if not (limit is None or isinstance(limit, int)) or not isinstance(offset, int):
                raise BindError("LIMIT、OFFSET 要是整數")
            node = Limit(node, None if limit is not None and limit < 0 else limit, offset)
        return Plan(node, names)

    def compile_all(self, conds: list, columns: list):
        fns = [self.compile(c, columns) for c in conds]
        if len(fns) == 1:
            return fns[0]

        def all_of(row):
            v = 1
            for f in fns:
                v = _and(v, f(row))
                if v == 0:
                    return 0
            return v
        return all_of

    # ------------------------------------------------------------- R2：存取路徑
    def access_path(self, k: int, rel: Rel, conds: list, refs: set, order_by=None, grouped=False, limited=False):
        """第 k 張表的掃描（R2），以及它上面的 Filter。傳回 (運算子, 是否已經依 ORDER BY 排好)。"""
        op, rest, ordered = self.scan(k, rel, conds, refs, order_by, grouped, limited)
        if rest:
            op = Filter(op, self.compile_all(rest, op.columns), text_of(rest))
        return op, ordered

    def scan(self, k: int, rel: Rel, conds: list, refs: set, order_by=None, grouped=False, limited=False):
        """選一個掃描：傳回 (掃描運算子, 還要另外檢查的條件, 是否已經依 ORDER BY 排好)。
        limited：查詢有 LIMIT。只為了順序而用索引（R4）只在有 LIMIT 時才划算。"""
        candidates = [] if rel.not_indexed else self.indexes_of(rel)
        not_null = self.not_null_columns(k, rel, conds)
        best = None
        for ix in candidates:
            if not all(p in not_null for p in ix.positions):
                continue                             # 索引裡少了鍵為 NULL 的列
            m = self.match_index(k, rel, ix, conds)
            score = (len(m["eq"]), m["lower"] is not None or m["upper"] is not None, ix.unique)
            if (m["eq"] or m["lower"] or m["upper"] or rel.indexed_by) and (best is None or score > best[0]):
                best = (score, ix, m)
        wanted = [(e.col, d) for e, d in order_by or [] if isinstance(e, ColRef) and e.rel == k]
        if best is None and limited and order_by and not grouped and len(wanted) == len(order_by):
            for ix in candidates:                    # R4：沒有可用的條件，但索引的順序就是 ORDER BY
                if all(p in not_null for p in ix.positions) and self.gives_order(ix, 0, wanted):
                    best = ((0, False, ix.unique), ix, {"eq": [], "lower": None, "upper": None, "used": []})
                    break
        if best is None:
            if rel.indexed_by:
                raise BindError(f"INDEXED BY {rel.indexed_by}：這個查詢用不上這個索引")
            return SeqScan(k, rel), conds, False
        _, ix, m = best
        eq = [self.const(v) for v in m["eq"]]
        lo = hi = None
        lo_inc = hi_inc = True
        if m["eq"] or m["lower"]:
            lo = tuple(eq) + ((self.const(m["lower"][0]),) if m["lower"] else ())
            lo_inc = m["lower"][1] if m["lower"] else True
        if m["eq"] or m["upper"]:
            hi = tuple(eq) + ((self.const(m["upper"][0]),) if m["upper"] else ())
            hi_inc = m["upper"][1] if m["upper"] else True
        rest = [c for c in conds if not any(c is u for u in m["used"])]
        if None in (lo or ()) or None in (hi or ()):   # 和 NULL 比較：一列都不會符合
            lo, hi, lo_inc, hi_inc, rest = (), (), False, False, []
        mine = {c for r, c in refs if r == k}
        only = mine <= set(ix.positions)
        op = IndexScan(k, rel, ix, lo, hi, lo_inc, hi_inc, text_of(m["used"]), only)
        ordered = (bool(order_by) and not grouped and len(wanted) == len(order_by)
                   and self.gives_order(ix, len(m["eq"]), wanted))
        return op, rest, ordered

    def indexes_of(self, rel: Rel) -> list:
        from_catalog = self.catalog.indexes_on(rel.table.name)
        if rel.indexed_by:
            return [ix for ix in from_catalog if ix.name.lower() == rel.indexed_by.lower()]
        return list(from_catalog)

    @staticmethod
    def gives_order(ix, n_eq: int, wanted: list) -> bool:
        """前 n_eq 欄固定之後，索引的順序是不是 ORDER BY 要的順序（只支援由小到大）。"""
        rest = ix.positions[n_eq:]
        return (all(not d for _, d in wanted) and len(wanted) <= len(rest)
                and [c for c, _ in wanted] == rest[:len(wanted)])

    def not_null_columns(self, k: int, rel: Rel, conds: list) -> set:
        """一定不是 NULL 的欄：宣告為 NOT NULL，或條件裡出現在會排除 NULL 的比較中。"""
        out = {j for j, c in enumerate(rel.table.schema.columns) if c.not_null}
        for c in conds:
            if isinstance(c, BinOp) and c.op in NULL_REJECTING:
                for side in [c.left] + (list(c.right) if isinstance(c.right, tuple) else [c.right]):
                    if isinstance(side, ColRef) and side.rel == k:
                        out.add(side.col)
            if isinstance(c, Unary) and c.op == "IS NOT NULL" and isinstance(c.operand, ColRef):
                out.add(c.operand.col)
        return out

    def match_index(self, k: int, rel: Rel, ix, conds: list) -> dict:
        """條件對上索引鍵的前綴：前面幾欄是等值，下一欄可以有下界與上界。"""
        def column_vs_const(c):
            """c 是「第 k 張表的欄 比較 常數」嗎？是的話傳回 (欄, 運算子, 常數)。"""
            if not isinstance(c, BinOp):
                return None
            if c.op == "BETWEEN" and isinstance(c.left, ColRef) and c.left.rel == k \
                    and not rels_of(c.right[0]) and not rels_of(c.right[1]):
                return c.left.col, "BETWEEN", c.right
            if c.op not in FLIP:
                return None
            if isinstance(c.left, ColRef) and c.left.rel == k and not rels_of(c.right):
                return c.left.col, c.op, c.right
            if isinstance(c.right, ColRef) and c.right.rel == k and not rels_of(c.left):
                return c.right.col, FLIP[c.op], c.left
            return None

        typed = {j: col.type for j, col in enumerate(rel.table.schema.columns)}
        facts = []
        for c in conds:
            f = column_vs_const(c)
            if f and self.comparable(typed.get(f[0]), f[2]):
                facts.append((c, *f))
        out = {"eq": [], "lower": None, "upper": None, "used": []}
        for p in ix.positions:
            eq = next(((c, v) for c, col, op, v in facts if col == p and op == "="), None)
            if eq is not None:
                out["eq"].append(eq[1])
                out["used"].append(eq[0])
                continue
            for c, col, op, v in facts:              # 下一欄：範圍
                if col != p:
                    continue
                if op == "BETWEEN" and out["lower"] is None and out["upper"] is None:
                    out["lower"], out["upper"] = (v[0], True), (v[1], True)
                elif op in (">", ">=") and out["lower"] is None:
                    out["lower"] = (v, op == ">=")
                elif op in ("<", "<=") and out["upper"] is None:
                    out["upper"] = (v, op == "<=")
                else:
                    continue
                out["used"].append(c)
            break
        return out

    def same_kind(self, e, col_type) -> bool:
        """外層的運算式 e 與內層的欄型別相容嗎（數值對 INTEGER、REAL，字串對 TEXT）。只認外層的欄。"""
        if not isinstance(e, ColRef):
            return False
        t = self.rels[e.rel].table.schema.columns[e.col].type
        return (t == "TEXT") == (col_type == "TEXT")

    def comparable(self, col_type, e) -> bool:
        """常數和欄的型別相容才用索引（INTEGER、REAL 欄配數值，TEXT 欄配字串）。"""
        if isinstance(e, tuple):
            return all(self.comparable(col_type, x) for x in e)
        v = self.const(e)
        if v is None:
            return True                              # 和 NULL 比較：結果是空的，scan 會處理
        return isinstance(v, str) if col_type == "TEXT" else isinstance(v, (int, float))

    # ------------------------------------------------------------- R3：join
    def join(self, left, k: int, rel: Rel, kind: str, preds: list, local: list, refs: set):
        kind = "LEFT" if kind == "LEFT" else "INNER"
        equi = []                                    # (左邊的運算式, 右邊的運算式, 條件)
        for c in preds:
            if isinstance(c, BinOp) and c.op == "=":
                a, b = rels_of(c.left), rels_of(c.right)
                if b == {k} and a and k not in a:
                    equi.append((c.left, c.right, c))
                elif a == {k} and b and k not in b:
                    equi.append((c.right, c.left, c))
        # 1. index nested loop join：內層表的索引鍵前綴都由等值條件決定
        if not rel.not_indexed:
            not_null = self.not_null_columns(k, rel, local + [c for _, _, c in equi])
            best = None
            for ix in self.indexes_of(rel):
                if not all(p in not_null for p in ix.positions):
                    continue
                bound = []
                for p in ix.positions:
                    hit = next(((l, c) for l, r, c in equi if isinstance(r, ColRef) and r.col == p
                                and self.same_kind(l, rel.table.schema.columns[p].type)), None)
                    if hit is None:
                        break
                    bound.append(hit)
                if bound and (best is None or len(bound) > len(best[1])):
                    best = (ix, bound)
            if best is not None:
                ix, bound = best
                used = [c for _, c in bound]
                residual = [c for c in preds if not any(c is u for u in used)] + local
                columns = left.columns + [(k, j) for j in range(len(rel.table.schema))]
                key_fns = [self.compile(l, left.columns) for l, _ in bound]
                return IndexNestedLoopJoin(left, k, rel, ix, key_fns,
                                           self.compile_all(residual, columns) if residual else None,
                                           text_of(used + residual), kind)
        right, _ = self.access_path(k, rel, local, refs)
        columns = left.columns + right.columns
        # 2. hash join：有等值條件
        if equi:
            residual = [c for c in preds if not any(c is u for _, _, u in equi)]
            return HashJoin(left, right, [self.compile(l, left.columns) for l, _, _ in equi],
                            [self.compile(r, right.columns) for _, r, _ in equi],
                            self.compile_all(residual, columns) if residual else None, text_of(preds), kind)
        # 3. nested loop join
        return NestedLoopJoin(left, right, self.compile_all(preds, columns) if preds else None,
                              text_of(preds), kind)

    # ------------------------------------------------------------- 彙總與排序
    def aggregate(self, node, q: Query):
        key_fns = [self.compile(g, node.columns) for g in q.group_by]
        arg_fns = [None if isinstance(a.args[0], Star) else self.compile(a.args[0], node.columns)
                   for a in q.aggregates]
        text = (f"BY {', '.join(sql(g) for g in q.group_by)}" if q.group_by else "（整張表一組）") + \
            (": " + ", ".join(sql(a) for a in q.aggregates) if q.aggregates else "")
        node = HashAggregate(node, key_fns, q.aggregates, arg_fns, list(q.group_by) + list(q.aggregates), text)
        if q.having is not None:
            node = Filter(node, self.compile(q.having, node.columns), sql(q.having))
        return node

    def top_n(self, q: Query):
        """ORDER BY 之後只要前 n 列（LIMIT + OFFSET）時傳回 n；n 很大時照常排序。"""
        if q.limit is None:
            return None
        limit, offset = self.const(q.limit), self.const(q.offset) if q.offset is not None else 0
        if isinstance(limit, int) and isinstance(offset, int) and 0 <= limit and limit + offset <= 1000:
            return limit + offset
        return None

    def sort(self, node, order: list, top_n=None):
        keys, desc = [self.compile(e, node.columns) for e, _ in order], [d for _, d in order]
        text = ", ".join(sql(e) + (" DESC" if d else "") for e, d in order)
        if top_n is not None:
            return TopN(node, keys, desc, text, top_n)
        return Sort(node, keys, desc, text, self.sort_memory_pages, self.page_size)
