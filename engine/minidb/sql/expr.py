"""運算式求值：把 binder 解析過的運算式編譯成 Python 函數 row → 值。

第 2 章的定義 2.4.2 說明 SQL 的三值邏輯：比較的一邊是 NULL，結果是 UNKNOWN（這裡用 None 表示）；
WHERE 只留下結果為 TRUE 的列。真假值用 1 與 0 表示。

值的規則仿照 SQLite（運算、函數、字串轉數值），對照的是建置用的 SQLite 3.45.1；所以比較的兩邊型別相同時，
引擎的結果可以和它逐列比較（差分測試）。與 SQLite 不同的有三處：
  * 比較依第 2 章的定義 2.2.5 的 (1)–(3)，但不做 (4) 的親和轉換。一邊是欄、另一邊是別種型別的值時，
    SQLite 先轉換再比（TEXT 欄的 '1' 與常數 1 相等），引擎不轉換，依 (2) 數小於字串（'1' > 1 為真）。
  * 實數轉成文字（CAST、||）用 Python 的 repr，例如 '1e+20'；SQLite（3.45.1 與 3.37.2）印 15 位有效數字，例如 '1.0e+20'。
  * 整數的運算不會溢位（Python 的整數）；SQLite 溢位時改用實數。
SQLite 的版本之間也不同：ROUND 照 3.45.1 的做法，依實數的二進位值捨入；3.37.2（Ubuntu 22.04 的版本）這類舊版
依十進位的近似值捨入，例如 ROUND(1.005, 2) 在 3.37.2 是 1.01，在 3.45.1 與引擎是 1.0。
"""

import re
import string
from decimal import ROUND_HALF_UP, Context, Decimal
from functools import lru_cache, total_ordering

from ..errors import BindError, NotSupported
from .ast import BinOp, Case, ColRef, Func, Lit, Param, Unary, is_aggregate, sql


# ---------------------------------------------------------------- 值的規則
def truth(v):
    """值 → 1（TRUE）、0（FALSE）或 None（UNKNOWN）。數值非 0 為真；字串先轉成數值。"""
    if v is None:
        return None
    return 1 if _num(v) != 0 else 0


def _num(v):
    """字串轉數值：取最長的數值前綴，沒有就是 0（SQLite 的規則）。"""
    if not isinstance(v, str):
        return v
    m = re.match(r"\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", v)
    if not m:
        return 0
    text = m.group(0)
    return float(text) if any(c in text for c in ".eE") else int(text)


def sort_key(v):
    """跨型別的排序：NULL < 數值 < 字串（SQLite 的規則）。"""
    if v is None:
        return (0, 0)
    return (2, v) if isinstance(v, str) else (1, v)


@total_ordering
class Desc:
    """把排序反過來（ORDER BY ... DESC）：字串不能取負號，所以包一層、比較時交換左右。"""
    __slots__ = ("k",)

    def __init__(self, k):
        self.k = k

    def __eq__(self, other):
        return self.k == other.k

    def __lt__(self, other):
        return other.k < self.k


def compare(a, b):
    """-1、0、1；任一邊是 NULL 時傳回 None。"""
    if a is None or b is None:
        return None
    ka, kb = sort_key(a), sort_key(b)
    return (ka > kb) - (ka < kb)


def to_text(v):
    if v is None or isinstance(v, str):
        return v
    return repr(v) if isinstance(v, float) else str(v)


def like(value, pattern):
    """LIKE：% 配任意長度、_ 配一個字元；只有 ASCII 的英文字母不分大小寫（SQLite 的預設），é 與 É 不同。"""
    if value is None or pattern is None:
        return None
    return 1 if _like_rx(to_text(pattern)).fullmatch(to_text(value)) else 0


@lru_cache(maxsize=256)
def _like_rx(pattern: str):
    rx = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in pattern)
    return re.compile(rx, re.IGNORECASE | re.ASCII | re.DOTALL)     # ASCII：不分大小寫只用在 a–z、A–Z


def _arith(op, a, b):
    if a is None or b is None:
        return None
    a, b = _num(a), _num(b)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "%" and not (isinstance(a, int) and isinstance(b, int)):
        r = _arith("%", int(a), int(b))              # SQLite：% 先把兩邊向 0 取整；有實數時結果是實數
        return None if r is None else float(r)
    if b == 0:
        return None                                  # SQLite：除以 0 得到 NULL（PostgreSQL 會報錯）
    if isinstance(a, int) and isinstance(b, int):    # 整數除法向 0 取整，餘數與被除數同號
        q, r = abs(a) // abs(b), abs(a) % abs(b)
        if op == "/":
            return q if (a >= 0) == (b >= 0) else -q
        return r if a >= 0 else -r
    return a / b


def _and(a, b):
    a, b = truth(a), truth(b)
    if a == 0 or b == 0:
        return 0
    return None if a is None or b is None else 1


def _or(a, b):
    a, b = truth(a), truth(b)
    if a == 1 or b == 1:
        return 1
    return None if a is None or b is None else 0


def _not(a):
    a = truth(a)
    return None if a is None else 1 - a


def _in(v, values):
    if v is None:
        return None
    found = [compare(v, x) for x in values]
    if 0 in found:
        return 1
    return None if None in found else 0


# ---------------------------------------------------------------- 純量函數
def _round(x, digits=0):
    """ROUND，照 SQLite 3.45.1 的做法（3.37.2 這類舊版不同，見本檔開頭）：digits 限在 0 到 30；
    digits 是 0 時加減 0.5 再向 0 取整，否則把 x 的二進位值（不是 repr 印出的十進位近似）四捨五入到 digits 位，.5 遠離 0。"""
    if x is None or digits is None:
        return None
    x, n = float(_num(x)), min(max(int(_num(digits)), 0), 30)
    if abs(x) >= 2.0 ** 52:                          # 這樣大的實數都是整數，沒有小數可捨入
        return x
    if n == 0:
        return float(int(x + 0.5 if x >= 0 else x - 0.5))
    q = Decimal(1).scaleb(-n)
    return float(Decimal(x).quantize(q, ROUND_HALF_UP, Context(prec=60)))    # Decimal(x) 是 x 的精確值


def _substr(s, start, length=None):
    if s is None or start is None:
        return None
    s, n = to_text(s), len(to_text(s))
    begin = start - 1 if start > 0 else n + start if start < 0 else -1
    end = n if length is None else begin + length
    if length is not None and length < 0:
        begin, end = begin + length, begin
    begin = max(begin, 0)
    return s[begin:max(end, begin)]


def _cast(v, target):
    if v is None:
        return None
    if target == "TEXT":
        return to_text(v)
    v = _num(v)
    if target == "INTEGER":
        return int(v)                                # 向 0 取整
    return float(v)


def _nullif(a, b):
    return None if compare(a, b) == 0 else a


def _scalar_min(*args):
    return None if None in args else min(args, key=sort_key)


def _scalar_max(*args):
    return None if None in args else max(args, key=sort_key)


ASCII_UPPER = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)   # SQLite 的 UPPER、LOWER
ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)   # 只轉換 ASCII 的英文字母

FUNCTIONS = {   # 名稱: (函數, 最少參數, 最多參數)；遇到 NULL 的規則各自處理
    "ABS": (lambda x: None if x is None else abs(_num(x)), 1, 1),
    "LENGTH": (lambda x: None if x is None else len(to_text(x)), 1, 1),
    "LOWER": (lambda x: None if x is None else to_text(x).translate(ASCII_LOWER), 1, 1),
    "UPPER": (lambda x: None if x is None else to_text(x).translate(ASCII_UPPER), 1, 1),
    "SUBSTR": (_substr, 2, 3),
    "COALESCE": (lambda *xs: next((x for x in xs if x is not None), None), 2, 99),
    "IFNULL": (lambda a, b: b if a is None else a, 2, 2),
    "NULLIF": (_nullif, 2, 2),
    "ROUND": (_round, 1, 2),
    "MIN": (_scalar_min, 2, 99),                      # 兩個以上的參數：純量函數；一個參數：彙總
    "MAX": (_scalar_max, 2, 99),
}


def check_function(e: Func) -> None:
    if is_aggregate(e):
        if len(e.args) != 1:
            raise BindError(f"{e.name} 要剛好一個參數")
        return
    if e.name == "CAST":
        return
    if e.name not in FUNCTIONS:
        raise NotSupported(f"不支援函數 {e.name}")
    _, lo, hi = FUNCTIONS[e.name]
    if not lo <= len(e.args) <= hi:
        raise BindError(f"{e.name} 的參數個數不對")


# ---------------------------------------------------------------- 編譯
def compile_expr(e, resolve, params=()):
    """運算式 → 函數 row → 值。

    resolve(node) 傳回 node 在輸入列的第幾欄，不在輸入列時傳回 None：
    彙總之前只有 ColRef 在輸入列裡；彙總之後，分組的運算式與彙總函數也各佔一欄。"""
    pos = resolve(e)
    if pos is not None:
        return lambda row: row[pos]
    if isinstance(e, ColRef):
        raise BindError(f"欄 {e.label} 不在這一步的輸入裡")
    if is_aggregate(e):
        raise BindError(f"彙總函數 {sql(e)} 不能用在這裡（例如 WHERE；請改用 HAVING）")
    if isinstance(e, Lit):
        v = e.value
        return lambda row: v
    if isinstance(e, Param):
        if e.index >= len(params):
            raise BindError(f"參數不夠：第 {e.index + 1} 個 ? 沒有值")
        v = params[e.index]
        return lambda row: v

    def c(x):
        return compile_expr(x, resolve, params)

    if isinstance(e, Unary):
        f = c(e.operand)
        if e.op == "IS NULL":
            return lambda row: 1 if f(row) is None else 0
        if e.op == "IS NOT NULL":
            return lambda row: 0 if f(row) is None else 1
        if e.op == "NOT":
            return lambda row: _not(f(row))
        if e.op == "-":
            return lambda row: None if (v := f(row)) is None else -_num(v)
        return f                                     # 正號
    if isinstance(e, BinOp):
        op = e.op
        if op.endswith("BETWEEN"):
            x, lo, hi = c(e.left), c(e.right[0]), c(e.right[1])
            neg = op.startswith("NOT")

            def between(row):
                v = x(row)
                cl, ch = compare(v, lo(row)), compare(v, hi(row))
                r = _and(None if cl is None else int(cl >= 0), None if ch is None else int(ch <= 0))
                return _not(r) if neg else r
            return between
        if op.endswith("IN"):
            x, vals = c(e.left), [c(v) for v in e.right]
            if op.startswith("NOT"):
                return lambda row: _not(_in(x(row), [f(row) for f in vals]))
            return lambda row: _in(x(row), [f(row) for f in vals])
        a, b = c(e.left), c(e.right)
        if op == "AND":
            return lambda row: _and(a(row), b(row))
        if op == "OR":
            return lambda row: _or(a(row), b(row))
        if op in ("+", "-", "*", "/", "%"):
            return lambda row: _arith(op, a(row), b(row))
        if op == "||":
            return lambda row: None if (x := a(row)) is None or (y := b(row)) is None else to_text(x) + to_text(y)
        if op.endswith("LIKE"):
            if op.startswith("NOT"):
                return lambda row: _not(like(a(row), b(row)))
            return lambda row: like(a(row), b(row))
        if op in ("IS", "IS NOT"):                   # 把 NULL 當成一個值來比較，結果不會是 UNKNOWN
            def is_same(row):
                x, y = a(row), b(row)
                same = (x is None and y is None) or (x is not None and y is not None and compare(x, y) == 0)
                return int(same == (op == "IS"))
            return is_same
        tests = {"=": lambda k: k == 0, "<>": lambda k: k != 0, "<": lambda k: k < 0,
                 "<=": lambda k: k <= 0, ">": lambda k: k > 0, ">=": lambda k: k >= 0}
        if op in tests:
            t = tests[op]
            return lambda row: None if (k := compare(a(row), b(row))) is None else int(t(k))
        raise NotSupported(f"不支援運算子 {op}")
    if isinstance(e, Case):
        whens = [(c(w), c(v)) for w, v in e.whens]
        default = c(e.default) if e.default is not None else (lambda row: None)

        def case(row):
            for w, v in whens:
                if truth(w(row)) == 1:
                    return v(row)
            return default(row)
        return case
    if isinstance(e, Func):
        if e.name == "CAST":
            f, target = c(e.args[0]), e.args[1].value
            return lambda row: _cast(f(row), target)
        fn = FUNCTIONS[e.name][0]
        args = [c(a) for a in e.args]
        return lambda row: fn(*(g(row) for g in args))
    raise NotSupported(f"不支援的運算式 {e!r}")


# ---------------------------------------------------------------- 彙總
class Aggregate:
    """一個彙總函數在一組裡的累積狀態（第 8 章的演算法 8.3.18：彙總的初值、累加、結束三步）。"""

    def __init__(self, name: str, star: bool, distinct: bool):
        self.name, self.star, self.distinct = name, star, distinct
        self.n, self.total, self.best, self.seen = 0, 0, None, set()

    def add(self, v) -> None:
        if self.star:                                # COUNT(*)：連 NULL 的列也算
            self.n += 1
            return
        if v is None:                                # 其餘的彙總都跳過 NULL
            return
        if self.distinct:
            if v in self.seen:
                return
            self.seen.add(v)
        self.n += 1
        if self.name in ("SUM", "AVG"):
            self.total += _num(v)
        elif self.name in ("MIN", "MAX"):
            k, best = sort_key(v), None if self.best is None else sort_key(self.best)
            if best is None or (k < best if self.name == "MIN" else k > best):
                self.best = v

    def result(self):
        if self.name == "COUNT":
            return self.n
        if self.n == 0:
            return None                              # 沒有非 NULL 的值：SUM、AVG、MIN、MAX 都是 NULL
        if self.name == "SUM":
            return self.total
        if self.name == "AVG":
            return self.total / self.n
        return self.best
