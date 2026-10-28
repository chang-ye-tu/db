"""Binder：把 AST 裡的名稱對到 catalog 裡的表與欄，並檢查用法。

第 8 章的 8.2 節（定義 8.2.2 的 binder、8.2.3 的名稱解析、8.2.5 的分組的檢查、8.2.6 的邏輯計畫）。binder 做三件事：
  1. 解析名稱：欄的參照 Col(表, 欄) 換成 ColRef(FROM 的第幾張表, 第幾欄)；找不到或有歧義就報錯。
  2. 展開 *；ORDER BY 與 GROUP BY 可以用輸出欄的別名或序號（ORDER BY 2）。
  3. 檢查彙總：有 GROUP BY 或彙總函數時，SELECT、HAVING、ORDER BY 裡在彙總函數之外的欄，
     必須是分組的運算式。這是 PostgreSQL 與 SQL 標準的規則；SQLite 比較寬鬆，會隨便取組裡的一列。
"""

from dataclasses import dataclass, replace

from ..catalog import Catalog, TableInfo
from ..errors import BindError, NotSupported
from .ast import (BinOp, Case, Col, ColRef, Func, Join, Lit, Param, Select, Star, TableRef, Unary,
                  aggregates_in, children, sql)
from .expr import check_function, is_aggregate


@dataclass
class Rel:
    """FROM 裡的一張表。"""
    alias: str
    table: TableInfo
    indexed_by: str | None = None
    not_indexed: bool = False


@dataclass
class Query:
    rels: list            # [Rel, ...]，依 FROM 的順序
    joins: list           # joins[i]（i ≥ 1）：(種類, ON 的合取項)，第 i 張表怎樣接上前面的表
    where: list           # WHERE 拆開 AND 之後的合取項
    group_by: list
    aggregates: list      # 用到的彙總函數，不重複
    having: object | None
    items: list           # [(運算式, 輸出欄名), ...]
    order_by: list        # [(運算式, 是否 DESC), ...]
    distinct: bool = False
    limit: object | None = None
    offset: object | None = None

    @property
    def grouped(self) -> bool:
        return bool(self.group_by or self.aggregates)


def conjuncts(e) -> list:
    """把 a AND b AND c 拆成 [a, b, c]。"""
    if e is None:
        return []
    if isinstance(e, BinOp) and e.op == "AND":
        return conjuncts(e.left) + conjuncts(e.right)
    return [e]


class Scope:
    """名稱解析的範圍：目前看得到的表。"""

    def __init__(self, rels: list):
        self.rels = rels

    def has(self, name: str) -> bool:
        """看得到的表裡有沒有名稱是 name 的欄。"""
        return any(name.lower() in (n.lower() for n in r.table.schema.names) for r in self.rels)

    def resolve(self, col: Col) -> ColRef:
        """Col(表, 欄) → ColRef(第幾張表, 第幾欄)。沒寫表名時，所有看得到的表裡只能有一個這個欄名。"""
        if col.table is not None and not any(r.alias.lower() == col.table.lower() for r in self.rels):
            raise BindError(f"沒有表或別名 {col.table}")
        found = []
        for i, r in enumerate(self.rels):
            if col.table is not None and r.alias.lower() != col.table.lower():
                continue
            names = [n.lower() for n in r.table.schema.names]
            if col.name.lower() in names:
                j = names.index(col.name.lower())
                label = f"{r.alias}.{r.table.schema.names[j]}" if len(self.rels) > 1 else r.table.schema.names[j]
                found.append(ColRef(i, j, label))
        if not found:
            hint = "（雙引號括起來的是名稱；字串要用單引號）" if col.quoted else ""
            raise BindError(f"沒有欄 {sql(col)}{hint}")
        if len(found) > 1:
            raise BindError(f"欄 {col.name} 有歧義：{', '.join(r.label for r in found)} 都有；請寫成 表.{col.name}")
        return found[0]


def bind_expr(e, scope: Scope, allow_aggregates: bool = False):
    """把運算式裡的名稱換成 ColRef，並檢查函數與彙總的用法。"""
    if isinstance(e, Col):
        return scope.resolve(e)
    if isinstance(e, (Lit, Param, ColRef)):
        return e
    if isinstance(e, Star):
        raise BindError("* 只能用在 SELECT 清單或 COUNT(*)")
    if isinstance(e, Func):
        check_function(e)
        if is_aggregate(e):
            if not allow_aggregates:
                raise BindError(f"彙總函數 {sql(e)} 不能用在這裡（WHERE、GROUP BY、JOIN ON；條件請改用 HAVING）")
            if isinstance(e.args[0], Star):
                if e.name != "COUNT" or e.distinct:
                    raise BindError(f"{e.name}(*) 不合法")
                return e
            arg = bind_expr(e.args[0], scope)        # 彙總裡面不能再有彙總
            return replace(e, args=(arg,))
        if e.name == "CAST":
            return replace(e, args=(bind_expr(e.args[0], scope, allow_aggregates), e.args[1]))
        return replace(e, args=tuple(bind_expr(a, scope, allow_aggregates) for a in e.args))
    if isinstance(e, BinOp):
        right = (tuple(bind_expr(x, scope, allow_aggregates) for x in e.right) if isinstance(e.right, tuple)
                 else bind_expr(e.right, scope, allow_aggregates))
        return replace(e, left=bind_expr(e.left, scope, allow_aggregates), right=right)
    if isinstance(e, Unary):
        return replace(e, operand=bind_expr(e.operand, scope, allow_aggregates))
    if isinstance(e, Case):
        whens = tuple((bind_expr(w, scope, allow_aggregates), bind_expr(v, scope, allow_aggregates))
                      for w, v in e.whens)
        default = bind_expr(e.default, scope, allow_aggregates) if e.default is not None else None
        return Case(whens, default)
    raise NotSupported(f"不支援的運算式 {e!r}")


def check_grouped(e, group_by: list) -> None:
    """有分組時：e 裡在彙總函數之外的每個欄，都必須落在某個分組的運算式之內。"""
    if e in group_by or is_aggregate(e):
        return
    if isinstance(e, ColRef):
        raise BindError(f"欄 {e.label} 要放進 GROUP BY，或用彙總函數包起來")
    for part in children(e):
        check_grouped(part, group_by)


def bind_select(sel: Select, catalog: Catalog) -> Query:
    rels, joins = [], [None]
    for i, (kind, ref) in enumerate(_flatten(sel.source)):
        t = catalog.table(ref.name)
        alias = ref.alias or t.name
        if any(r.alias.lower() == alias.lower() for r in rels):
            raise BindError(f"FROM 裡的表名或別名 {alias} 重複了")
        if ref.indexed_by:
            ix = catalog.index(ref.indexed_by)
            if ix.table.lower() != t.name.lower():
                raise BindError(f"索引 {ix.name} 不是表 {t.name} 的索引")
        rels.append(Rel(alias, t, ref.indexed_by, ref.not_indexed))
        if i > 0:
            on = kind[1]
            joins.append((kind[0], [bind_expr(c, Scope(rels)) for c in conjuncts(on)]))
    scope = Scope(rels)

    items, aliases = [], []                          # aliases[k]：第 k 個輸出項的別名，與 items 逐項對齊
    for it in sel.items:
        if isinstance(it.expr, Star):
            chosen = [(i, r) for i, r in enumerate(rels)
                      if it.expr.table is None or r.alias.lower() == it.expr.table.lower()]
            if not chosen:
                raise BindError("SELECT * 需要 FROM" if not rels else f"沒有表或別名 {it.expr.table}")
            for i, r in chosen:
                for j, name in enumerate(r.table.schema.names):
                    label = f"{r.alias}.{name}" if len(rels) > 1 else name
                    items.append((ColRef(i, j, label), name))
                    aliases.append(None)             # * 展開的輸出項沒有別名
            continue
        e = bind_expr(it.expr, scope, allow_aggregates=True)
        name = it.alias or (it.expr.name if isinstance(it.expr, Col) else sql(it.expr))
        items.append((e, name))
        aliases.append(it.alias)

    def output_ref(e):
        """ORDER BY／GROUP BY 的整數序號或輸出欄別名 → 那個輸出欄的運算式；其他的照常解析。"""
        if isinstance(e, Lit) and isinstance(e.value, int):
            if not 1 <= e.value <= len(items):
                raise BindError(f"序號 {e.value} 超出 SELECT 清單的範圍（1 到 {len(items)}）")
            return items[e.value - 1][0]
        if isinstance(e, Col) and e.table is None:
            aliased = [x for x, alias in zip(items, aliases) if alias and alias.lower() == e.name.lower()]
            if aliased:
                return aliased[0][0]
        return None

    def no_alias(e, clause: str, allow_aggregates: bool = False):
        """WHERE、HAVING 只看得到輸入的欄，看不到輸出欄的別名（SQL 標準與 PostgreSQL；SQLite 看得到）：
        名稱解析失敗、而那個名稱是別名時，說明要寫出它代表的運算式。"""
        try:
            return bind_expr(e, scope, allow_aggregates)
        except BindError:
            for c in _bare_columns(e):
                named = [it.expr for it in sel.items if it.alias and it.alias.lower() == c.name.lower()]
                if named and not scope.has(c.name):
                    raise BindError(f"{clause} 不能用 SELECT 的別名 {c.name}（PostgreSQL 也不行）："
                                    f"請改寫成它代表的 {sql(named[0])}") from None
            raise

    where = [no_alias(c, "WHERE") for c in conjuncts(sel.where)]
    group_by = []
    for g in sel.group_by:                           # 名稱同時是別名與輸入的欄時，GROUP BY 取輸入的欄
        e = None if isinstance(g, Col) and g.table is None and scope.has(g.name) else output_ref(g)
        if e is None:
            e = bind_expr(g, scope)
        if aggregates_in(e, []):
            raise BindError("GROUP BY 不能用彙總函數")
        group_by.append(e)
    having = no_alias(sel.having, "HAVING", allow_aggregates=True) if sel.having is not None else None
    order_by = []
    for o in sel.order_by:
        e = output_ref(o.expr)
        order_by.append((e if e is not None else bind_expr(o.expr, scope, allow_aggregates=True), o.desc))

    aggs = []
    for e in [e for e, _ in items] + [having] + [e for e, _ in order_by]:
        if e is not None:
            aggregates_in(e, aggs)
    if having is not None and not (group_by or aggs):
        raise BindError("HAVING 要搭配 GROUP BY 或彙總函數")
    if group_by or aggs:
        for e in [e for e, _ in items] + [having] + [e for e, _ in order_by]:
            if e is not None:
                check_grouped(e, group_by)
    if sel.distinct:
        for e, _ in order_by:
            if e not in [x for x, _ in items]:
                raise BindError("SELECT DISTINCT 的 ORDER BY 只能用 SELECT 清單裡的運算式")

    empty = Scope([])
    return Query(rels, joins, where, group_by, aggs, having, items, order_by, sel.distinct,
                 bind_expr(sel.limit, empty) if sel.limit is not None else None,
                 bind_expr(sel.offset, empty) if sel.offset is not None else None)


def _bare_columns(e) -> list:
    """運算式（還沒解析）裡沒有寫表名的欄。"""
    if isinstance(e, Col):
        return [e] if e.table is None else []
    return [c for part in children(e) for c in _bare_columns(part)]


def _flatten(source) -> list:
    """FROM 的 Join 樹（向左長的）→ [((種類, ON), TableRef), ...]；第一個的種類是 None。"""
    if source is None:
        return []
    if isinstance(source, TableRef):
        return [((None, None), source)]
    if not isinstance(source.right, TableRef):
        raise NotSupported("FROM 不支援括號裡的 join")
    return _flatten(source.left) + [((source.kind, source.on), source.right)]
