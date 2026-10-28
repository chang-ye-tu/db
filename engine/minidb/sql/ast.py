"""抽象語法樹（AST）：剖析樹（parse tree）去掉標點與文法細節之後，留下的語意結構。

第 8 章的定義 8.1.2（剖析樹）與 8.1.3（AST）說明兩者的差別。運算式的節點是 frozen dataclass，可以當 dict 的鍵
（GROUP BY 與彙總要比對「同一個運算式」）；敘述（statement）的節點是一般的 dataclass。
本檔也負責把 AST 印回 SQL（sql、to_sql）與印成關聯代數（to_ra）。
"""

import re
from dataclasses import dataclass, field

from .sqlite_parser.SQLiteLexer import SQLiteLexer


# ---------------------------------------------------------------- 運算式
@dataclass(frozen=True)
class Col:                        # 還沒解析的欄名：name 或 table.name
    table: str | None
    name: str
    quoted: bool = field(default=False, compare=False)   # 是否加了雙引號：不算在相等與雜湊之內


@dataclass(frozen=True)
class ColRef:                     # binder 解析過的欄：FROM 的第 rel 張表的第 col 欄
    rel: int
    col: int
    label: str


@dataclass(frozen=True)
class Lit:
    value: object                 # int | float | str | None


@dataclass(frozen=True)
class Param:                      # 參數 ?：執行時才代入值（U05 的參數化查詢）
    index: int


@dataclass(frozen=True)
class Star:
    table: str | None = None


@dataclass(frozen=True)
class Func:
    name: str
    args: tuple
    distinct: bool = False


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object                 # BETWEEN：(下界, 上界)；IN：(值, ...)


@dataclass(frozen=True)
class Unary:
    op: str                       # '-'、'+'、'NOT'、'IS NULL'、'IS NOT NULL'
    operand: object


@dataclass(frozen=True)
class Case:
    whens: tuple                  # ((條件, 結果), ...)
    default: object | None


AGGREGATES = {"COUNT", "SUM", "AVG", "MIN", "MAX"}


def is_aggregate(e) -> bool:
    """彙總函數的呼叫？MIN、MAX 有兩個以上的參數時是純量函數（SQLite 的寫法）。"""
    return (isinstance(e, Func) and e.name in AGGREGATES
            and (e.name not in ("MIN", "MAX") or len(e.args) == 1))


# ---------------------------------------------------------------- SELECT
@dataclass
class TableRef:
    name: str
    alias: str | None = None
    indexed_by: str | None = None  # SQLite 的 INDEXED BY：指定索引
    not_indexed: bool = False      # SQLite 的 NOT INDEXED：不用索引


@dataclass
class Join:
    kind: str                     # 'INNER' | 'LEFT' | 'CROSS'
    left: object
    right: object
    on: object | None = None


@dataclass
class Item:
    expr: object
    alias: str | None = None


@dataclass
class Order:
    expr: object
    desc: bool = False


@dataclass
class Select:
    items: list
    source: object | None
    where: object | None = None
    group_by: list = field(default_factory=list)
    having: object | None = None
    order_by: list = field(default_factory=list)
    limit: object | None = None
    offset: object | None = None
    distinct: bool = False


# ---------------------------------------------------------------- 其他敘述
@dataclass
class ColumnDef:
    name: str
    type: str                     # 'INTEGER' | 'REAL' | 'TEXT'
    not_null: bool = False
    primary_key: bool = False
    unique: bool = False


@dataclass
class CreateTable:
    name: str
    columns: list
    primary_key: list = field(default_factory=list)   # 欄名
    uniques: list = field(default_factory=list)       # [[欄名, ...], ...]
    if_not_exists: bool = False


@dataclass
class CreateIndex:
    name: str
    table: str
    columns: list
    unique: bool = False
    if_not_exists: bool = False


@dataclass
class Drop:
    kind: str                     # 'TABLE' | 'INDEX'
    name: str
    if_exists: bool = False


@dataclass
class Insert:
    table: str
    columns: list | None
    rows: list | None = None      # VALUES 的每一列：[運算式, ...]
    query: Select | None = None   # INSERT ... SELECT


@dataclass
class Update:
    table: TableRef
    assignments: list             # [(欄名, 運算式), ...]
    where: object | None = None


@dataclass
class Delete:
    table: TableRef
    where: object | None = None


@dataclass
class Begin:
    pass


@dataclass
class Commit:
    pass


@dataclass
class Rollback:
    pass


@dataclass
class Explain:
    stmt: object


# ---------------------------------------------------------------- 印回 SQL
# 關鍵字：文法的詞法規則中寫成一個字的 token（ABORT_ : 'ABORT'; 等），共 153 個，
# 即 SQLite 的 147 個關鍵字（〈SQLite Keywords〉）加上 TRUE、FALSE、ROWID、STORED、STRICT、WITHIN
KEYWORDS = frozenset(s.strip("'") for s in SQLiteLexer.literalNames if re.fullmatch(r"'[A-Z_]+'", s))


def ident(name: str) -> str:
    """識別字：關鍵字（KEYWORDS，不分大小寫）或不是一般名稱時加上雙引號，其中的雙引號寫兩次。"""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and name.upper() not in KEYWORDS:
        return name
    return '"' + name.replace('"', '""') + '"'


PREC = {"OR": 1, "AND": 2, "NOT": 3, "=": 4, "<>": 4, "!=": 4, "IS": 4, "IS NOT": 4,
        "<": 5, "<=": 5, ">": 5, ">=": 5, "+": 6, "-": 6, "*": 7, "/": 7, "%": 7, "||": 8}


def literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return repr(v)


def sql(e, parent: int = 0) -> str:
    """運算式 → SQL 文字；只在優先順序需要時加括號。"""
    if isinstance(e, Col):
        name = '"' + e.name.replace('"', '""') + '"' if e.quoted else ident(e.name)
        return f"{ident(e.table)}.{name}" if e.table else name
    if isinstance(e, ColRef):
        return e.label
    if isinstance(e, Star):
        return f"{ident(e.table)}.*" if e.table else "*"
    if isinstance(e, Lit):
        return literal(e.value)
    if isinstance(e, Param):
        return "?"
    if isinstance(e, Func):
        if e.name == "CAST":
            return f"CAST({sql(e.args[0])} AS {e.args[1].value})"
        return f"{e.name}({'DISTINCT ' if e.distinct else ''}{', '.join(sql(a) for a in e.args)})"
    if isinstance(e, Case):
        w = " ".join(f"WHEN {sql(c)} THEN {sql(v)}" for c, v in e.whens)
        return f"CASE {w}{' ELSE ' + sql(e.default) if e.default is not None else ''} END"
    if isinstance(e, Unary):
        if e.op in ("IS NULL", "IS NOT NULL"):
            return f"{sql(e.operand, 4)} {e.op}"
        p = 3 if e.op == "NOT" else 9
        inner = sql(e.operand, p)
        s = f"NOT {inner}" if e.op == "NOT" else f"{e.op}{' ' if inner[:1] in '-+' else ''}{inner}"
        return f"({s})" if p < parent else s       # "- -1" 不能寫成 "--1"：-- 是註解
    if isinstance(e, BinOp):
        if e.op.endswith("BETWEEN"):
            s, p = f"{sql(e.left, 5)} {e.op} {sql(e.right[0], 5)} AND {sql(e.right[1], 5)}", 4
        elif e.op.endswith("IN"):
            s, p = f"{sql(e.left, 5)} {e.op} ({', '.join(sql(v) for v in e.right)})", 4
        else:
            p = PREC.get(e.op, 4)
            s = f"{sql(e.left, p)} {e.op} {sql(e.right, p + 1)}"
        return f"({s})" if p < parent else s
    raise TypeError(f"不是運算式：{e!r}")


def source_sql(s) -> str:
    if isinstance(s, TableRef):
        hint = f" INDEXED BY {ident(s.indexed_by)}" if s.indexed_by else " NOT INDEXED" if s.not_indexed else ""
        return ident(s.name) + (f" AS {ident(s.alias)}" if s.alias else "") + hint
    j = {"INNER": "JOIN", "LEFT": "LEFT JOIN", "CROSS": "CROSS JOIN"}[s.kind]
    return f"{source_sql(s.left)} {j} {source_sql(s.right)}" + (f" ON {sql(s.on)}" if s.on is not None else "")


def to_sql(sel: Select) -> str:
    """SELECT 的 AST → SQL 文字（用來檢查 AST 保留了原句的意思）。"""
    out = "SELECT " + ("DISTINCT " if sel.distinct else "")
    out += ", ".join(sql(i.expr) + (f" AS {ident(i.alias)}" if i.alias else "") for i in sel.items)
    if sel.source:
        out += " FROM " + source_sql(sel.source)
    if sel.where is not None:
        out += " WHERE " + sql(sel.where)
    if sel.group_by:
        out += " GROUP BY " + ", ".join(sql(g) for g in sel.group_by)
    if sel.having is not None:
        out += " HAVING " + sql(sel.having)
    if sel.order_by:
        out += " ORDER BY " + ", ".join(sql(o.expr) + (" DESC" if o.desc else "") for o in sel.order_by)
    if sel.limit is not None:
        out += " LIMIT " + sql(sel.limit) + (f" OFFSET {sql(sel.offset)}" if sel.offset is not None else "")
    return out


# ---------------------------------------------------------------- 關聯代數
def aggregates_in(e, found: list) -> list:
    """運算式裡的彙總函數呼叫，依出現順序，不重複。"""
    if is_aggregate(e):
        if e not in found:
            found.append(e)
        return found
    for part in children(e):
        aggregates_in(part, found)
    return found


def children(e) -> list:
    """運算式的直接子運算式。"""
    if isinstance(e, Func):
        return list(e.args)
    if isinstance(e, BinOp):
        right = list(e.right) if isinstance(e.right, tuple) else [e.right]
        return [e.left] + right
    if isinstance(e, Unary):
        return [e.operand]
    if isinstance(e, Case):
        return [x for pair in e.whens for x in pair] + ([e.default] if e.default is not None else [])
    return []


def to_ra(sel: Select):
    """SELECT 的 AST → 關聯代數的運算子樹 (標籤, [子樹, ...])。
    邏輯順序：FROM（⋈）→ WHERE（σ）→ GROUP BY（γ）→ HAVING（σ）→ ORDER BY（τ）→ SELECT（π）→ LIMIT；
    有 DISTINCT 時先投影、去除重複，再排序（第 3 章的 SELECT 區塊的語意）。"""
    def src(s):
        if isinstance(s, TableRef):
            return (s.name + (f" AS {s.alias}" if s.alias else ""), [])
        sym = {"INNER": "⋈", "LEFT": "⟕", "CROSS": "×"}[s.kind]
        return (sym + (f"[{sql(s.on)}]" if s.on is not None else ""), [src(s.left), src(s.right)])

    node = src(sel.source) if sel.source else ("（一列）", [])
    if sel.where is not None:
        node = (f"σ[{sql(sel.where)}]", [node])
    aggs = []
    for e in [i.expr for i in sel.items] + [sel.having] + [o.expr for o in sel.order_by]:
        if e is not None:
            aggregates_in(e, aggs)
    if sel.group_by or aggs:
        node = (f"γ[{', '.join(sql(g) for g in sel.group_by)}; {', '.join(sql(a) for a in aggs)}]", [node])
    if sel.having is not None:
        node = (f"σ[{sql(sel.having)}]", [node])
    proj = ", ".join(sql(i.expr) + (f"→{i.alias}" if i.alias else "") for i in sel.items)
    tau = f"τ[{', '.join(sql(o.expr) + (' DESC' if o.desc else '') for o in sel.order_by)}]"
    if sel.distinct:                                 # τ(δ(π(T)))
        node = (f"δ π[{proj}]", [node])
        if sel.order_by:
            node = (tau, [node])
    else:                                            # 先排序，再逐列投影
        if sel.order_by:
            node = (tau, [node])
        node = (f"π[{proj}]", [node])
    if sel.limit is not None:
        node = (f"limit[{sql(sel.limit)}" + (f" offset {sql(sel.offset)}" if sel.offset is not None else "") + "]",
                [node])
    return node


def ra_lines(node, prefix: str = "", last: bool = True, top: bool = True) -> list[str]:
    """把運算子樹畫成文字樹。"""
    label, kids = node
    out = [label if top else prefix + ("└─ " if last else "├─ ") + label]
    ext = "" if top else prefix + ("   " if last else "│  ")
    for k, kid in enumerate(kids):
        out += ra_lines(kid, ext, k == len(kids) - 1, False)
    return out
