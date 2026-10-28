"""記錄（record）：把一列的值編成位元組，再從位元組讀回來。

第 6 章的定義 6.2.1（記錄的格式）：NULL bitmap（每欄 1 bit，第 j 欄在第 j // 8 個 byte 的第 j % 8 位），
接著依欄的順序放每個不是 NULL 的值：

    INTEGER  8 bytes 有號整數（>q）
    REAL     8 bytes 浮點數（>d）
    TEXT     2 bytes 長度（>H），接著 UTF-8 bytes
"""

import struct
from dataclasses import dataclass

TYPES = ("INTEGER", "REAL", "TEXT")
_INT, _REAL, _LEN = struct.Struct(">q"), struct.Struct(">d"), struct.Struct(">H")


@dataclass(frozen=True)
class Column:
    """綱目中的一欄（定義 6.2.1）：名稱、型別、是否 NOT NULL。"""
    name: str
    type: str                 # "INTEGER" | "REAL" | "TEXT"
    not_null: bool = False


class Schema:
    """一張表（或一個索引鍵）的欄，以及它們的編碼與解碼。"""

    def __init__(self, columns: list[Column]):
        for c in columns:
            if c.type not in TYPES:
                raise TypeError(f"不支援的型別 {c.type}；只有 {', '.join(TYPES)}")
        self.columns = list(columns)
        self.names = [c.name for c in columns]
        # 沒有 TEXT 欄時，每一列（沒有 NULL 的話）都是固定的格式，可以一次解開
        self._fixed = None if any(c.type == "TEXT" for c in columns) else \
            struct.Struct(">" + "".join("q" if c.type == "INTEGER" else "d" for c in columns))

    def __len__(self) -> int:
        return len(self.columns)

    def index_of(self, name: str) -> int:
        lowered = [n.lower() for n in self.names]
        if name.lower() not in lowered:
            raise KeyError(f"沒有欄 {name}")
        return lowered.index(name.lower())

    def check(self, values: tuple) -> tuple:
        """檢查並轉換一列的值：個數、NOT NULL、型別（INTEGER 欄不收 3.5），
        以及定義 6.2.1 的範圍：INTEGER 在 [-2**63, 2**63) 中，TEXT 的 UTF-8 編碼少於 2**16 個位元組。"""
        if len(values) != len(self.columns):
            raise ValueError(f"應有 {len(self.columns)} 個值，得到 {len(values)} 個")
        out = []
        for c, v in zip(self.columns, values):
            if v is None:
                if c.not_null:
                    raise ValueError(f"NOT NULL 約束：欄 {c.name} 不可為 NULL")
            elif c.type == "INTEGER":
                if isinstance(v, float) and v.is_integer():
                    v = int(v)
                if not isinstance(v, int) or isinstance(v, bool):
                    raise TypeError(f"欄 {c.name} 是 INTEGER，不能存 {v!r}")
                if not -2**63 <= v < 2**63:
                    raise ValueError(f"欄 {c.name} 的值 {v} 不在 INTEGER 的範圍中")
            elif c.type == "REAL":
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    raise TypeError(f"欄 {c.name} 是 REAL，不能存 {v!r}")
                v = float(v)
            elif not isinstance(v, str):
                raise TypeError(f"欄 {c.name} 是 TEXT，不能存 {v!r}")
            elif len(v.encode("utf-8")) >= 2**16:
                raise ValueError(f"欄 {c.name} 的 TEXT 太長：UTF-8 編碼要少於 65536 個位元組")
            out.append(v)
        return tuple(out)

    def encode(self, values: tuple) -> bytes:
        """一列 → 記錄的 bytes（定義 6.2.1）：NULL bitmap，接著依欄序的值。"""
        nulls = bytearray((len(self.columns) + 7) // 8)
        body = bytearray()
        for j, (c, v) in enumerate(zip(self.columns, values)):
            if v is None:
                nulls[j // 8] |= 1 << (j % 8)
            elif c.type == "INTEGER":
                body += _INT.pack(v)
            elif c.type == "REAL":
                body += _REAL.pack(v)
            else:
                b = v.encode("utf-8")
                body += _LEN.pack(len(b)) + b
        return bytes(nulls) + bytes(body)

    def decode(self, data: bytes) -> tuple:
        """記錄的 bytes → 一列（命題 6.2.2 的證明）；encode 的反函數。"""
        k = (len(self.columns) + 7) // 8
        if self._fixed is not None and not any(data[:k]):
            return self._fixed.unpack_from(data, k)
        pos, out = k, []
        for j, c in enumerate(self.columns):
            if data[j >> 3] >> (j & 7) & 1:
                out.append(None)
            elif c.type == "TEXT":
                n = _LEN.unpack_from(data, pos)[0]
                out.append(data[pos + 2:pos + 2 + n].decode("utf-8"))
                pos += 2 + n
            else:
                out.append((_INT if c.type == "INTEGER" else _REAL).unpack_from(data, pos)[0])
                pos += 8
        return tuple(out)

    def to_list(self) -> list:
        return [[c.name, c.type, c.not_null] for c in self.columns]

    @classmethod
    def from_list(cls, data: list) -> "Schema":
        return cls([Column(n, t, nn) for n, t, nn in data])


class AnyRow:
    """欄的型別事先不知道的列（例如排序時運算式的結果）：每個值前面加一個 byte 記型別。

    SQLite 的記錄格式也是每個值各記型別（serial type），所以同一欄可以放不同型別的值。"""

    _TAGS = {type(None): 0, int: 1, float: 2, str: 3}

    def encode(self, values) -> bytes:
        """一列 → bytes：每個值前面記著自己的型別，所以不需要 Schema。"""
        out = bytearray()
        for v in values:
            tag = self._TAGS[type(v)]
            out.append(tag)
            if tag == 1:
                out += _INT.pack(v)
            elif tag == 2:
                out += _REAL.pack(v)
            elif tag == 3:
                b = v.encode("utf-8")
                out += _LEN.pack(len(b)) + b
        return bytes(out)

    def decode(self, data) -> tuple:
        """bytes → 一列；encode 的反函數。"""
        out, pos = [], 0
        while pos < len(data):
            tag, pos = data[pos], pos + 1
            if tag == 0:
                out.append(None)
            elif tag == 1:
                out.append(_INT.unpack_from(data, pos)[0])
                pos += 8
            elif tag == 2:
                out.append(_REAL.unpack_from(data, pos)[0])
                pos += 8
            else:
                n = _LEN.unpack_from(data, pos)[0]
                out.append(data[pos + 2:pos + 2 + n].decode("utf-8"))
                pos += 2 + n
        return tuple(out)
