"""頁（page）：固定大小的位元組陣列，以 slotted page 的格式存放記錄。

第 6 章的定義 6.2.3（slotted page）。標頭 13 bytes（big-endian）：

    kind   B   頁的種類：HEAP（資料頁）、LEAF（B+ tree 的葉）、INNER（內部節點）
    n      H   槽數
    start  H   記錄區的起點；記錄從頁尾往前放
    next   I   HEAP：下一頁；LEAF：右邊的葉；INNER：最左邊的子節點；沒有時為 NONE
    lsn    I   最後一次修改這一頁的日誌序號（第 9 章）

標頭之後是槽陣列，每個槽 4 bytes：(位置, 長度)；長度 0 表示這個槽是空的。

資料頁與索引頁用同一種格式，差別在槽的用法：
  * 資料頁的槽號是記錄編號的一部分，必須穩定：刪除只把槽標成空的（insert、delete、compact）；
  * 索引頁的槽依鍵排序，插入與刪除要搬動槽陣列（insert_at、remove_at）。
"""

import struct

PAGE_SIZE = 4096
HEAP, LEAF, INNER = 1, 2, 3
NONE = 0xFFFFFFFF                      # 「沒有下一頁」

_HEADER = struct.Struct(">BHHII")
_SLOT = struct.Struct(">HH")
HEADER, SLOT = _HEADER.size, _SLOT.size
EMPTY_SLOT = bytes(SLOT)               # 空的槽：(位置, 長度) = (0, 0)
_FIELDS = [(0, struct.Struct(">B")), (1, struct.Struct(">H")), (3, struct.Struct(">H")),
           (5, struct.Struct(">I")), (9, struct.Struct(">I"))]   # 標頭各欄的位置與格式


class SlottedPage:
    """slotted page（定義 6.2.3）：包住一個 bytearray，直接修改它（不複製）。"""

    def __init__(self, data: bytearray):
        self.data = data

    @classmethod
    def new(cls, kind: int, size: int = PAGE_SIZE) -> "SlottedPage":
        data = bytearray(size)
        _HEADER.pack_into(data, 0, kind, 0, size, NONE, 0)
        return cls(data)

    # ------------------------------------------------------------- 標頭
    def _get(self, field: int) -> int:
        offset, fmt = _FIELDS[field]
        return fmt.unpack_from(self.data, offset)[0]

    def _set(self, field: int, value: int) -> None:
        offset, fmt = _FIELDS[field]
        fmt.pack_into(self.data, offset, value)

    kind = property(lambda self: self._get(0))
    n_slots = property(lambda self: self._get(1))
    start = property(lambda self: self._get(2))
    next = property(lambda self: self._get(3), lambda self, v: self._set(3, v))
    lsn = property(lambda self: self._get(4), lambda self, v: self._set(4, v))

    # ------------------------------------------------------------- 槽
    def slot(self, i: int) -> tuple[int, int]:
        """第 i 個槽的 (位置, 長度)。"""
        return _SLOT.unpack_from(self.data, HEADER + i * SLOT)

    def _set_slot(self, i: int, pos: int, length: int) -> None:
        _SLOT.pack_into(self.data, HEADER + i * SLOT, pos, length)

    def free_space(self) -> int:
        """槽陣列與記錄區之間連續的空白 bytes。"""
        return self.start - (HEADER + self.n_slots * SLOT)

    def holes(self) -> int:
        """刪除留下、還沒整理的空洞 bytes。"""
        used = sum(self.slot(i)[1] for i in range(self.n_slots))
        return len(self.data) - self.start - used

    def get(self, i: int) -> bytes | None:
        """第 i 個槽的記錄；空的槽或不存在的槽傳回 None。"""
        if not 0 <= i < self.n_slots:
            return None
        pos, length = self.slot(i)
        return bytes(self.data[pos:pos + length]) if length else None

    def records(self) -> list[tuple[int, bytes]]:
        """所有還在的記錄：[(槽號, bytes), ...]，依槽號。"""
        return [(i, rec) for i in range(self.n_slots) if (rec := self.get(i)) is not None]

    def _place(self, rec: bytes) -> int:
        """把記錄放進記錄區的最前面，傳回位置；呼叫者負責確認放得下。"""
        pos = self.start - len(rec)
        self.data[pos:pos + len(rec)] = rec
        self._set(2, pos)
        return pos

    # ------------------------------------------------- 資料頁：槽號穩定
    def _empty_slot(self) -> int | None:
        """第一個空的槽，沒有就是 None。在槽陣列的 bytes 裡找「對齊在槽的開頭」的 4 個 0。"""
        slots = bytes(self.data[HEADER:HEADER + self.n_slots * SLOT])
        i = slots.find(EMPTY_SLOT)
        while i != -1 and i % SLOT:
            i = slots.find(EMPTY_SLOT, i + 1)
        return None if i == -1 else i // SLOT

    def insert(self, rec: bytes) -> int:
        """插入（演算法 6.2.8）：傳回槽號；優先重用號碼最小的空的槽。

        放不下則拋出 ValueError。"""
        n = self.n_slots
        empty = self._empty_slot()
        need = len(rec) + (0 if empty is not None else SLOT)
        if self.free_space() < need:
            self.compact()
            if self.free_space() < need:
                raise ValueError("這一頁放不下")
        pos = self._place(rec)
        if empty is None:
            empty = n
            self._set(1, n + 1)
        self._set_slot(empty, pos, len(rec))
        return empty

    def delete(self, i: int) -> None:
        """刪除（演算法 6.2.4）：只把第 i 個槽標成空的，記錄成為空洞；其他槽號不變。"""
        self._set_slot(i, 0, 0)

    def compact(self) -> None:
        """整理（演算法 6.2.6）：依位置由大到小把記錄搬到頁尾排緊，更新槽與記錄區的起點；槽號不變，空的槽保持 (0, 0)。"""
        live = sorted(((self.slot(i)[0], i) for i in range(self.n_slots) if self.slot(i)[1]),
                      reverse=True)                  # 從最靠頁尾的記錄開始搬
        end = len(self.data)
        for pos, i in live:
            length = self.slot(i)[1]
            rec = bytes(self.data[pos:pos + length])
            end -= length
            self.data[end:end + length] = rec        # 往頁尾移，不會蓋到還沒搬的記錄
            self._set_slot(i, end, length)
        self._set(2, end)

    def put(self, i: int, rec: bytes | None) -> None:
        """放回（第 9 章的演算法 9.4.7）：把第 i 槽直接設成 rec（None 表示清空）；槽數不夠就補上空的槽。

        第 9 章的復原用：重做 insert、撤銷 delete 時，記錄必須回到日誌記下的那一個槽。
        整理之後仍放不下時，先去掉槽陣列末端、在第 i 個之後的空的槽：撤銷一筆刪除之前，
        同一個交易之後的插入可能加長了槽陣列，那些插入撤銷之後，留下的空的槽佔著空間
        （放得下的條件是命題 9.4.8；撤銷時一定放得下是引理 9.4.15 的 (2)）。"""
        n = self.n_slots
        if i < n:
            self._set_slot(i, 0, 0)                  # 原來的記錄先成為空洞
        if rec is None:
            return
        need = len(rec) + max(0, i + 1 - n) * SLOT
        if self.free_space() < need:
            self.compact()
            if self.free_space() < need:
                keep = max([i + 1] + [k + 1 for k in range(n) if self.slot(k)[1]])
                if keep < n:                         # 末端的空的槽不是任何一列的 RID
                    self._set(1, keep)
                    n = keep
                    need = len(rec)
                if self.free_space() < need:
                    raise ValueError("這一頁放不下")
        for k in range(n, i + 1):                    # 補上空的槽
            self._set_slot(k, 0, 0)
        self._set(1, max(n, i + 1))
        self._set_slot(i, self._place(rec), len(rec))

    # ------------------------------------------------- 索引頁：槽依鍵排序
    def insert_at(self, i: int, rec: bytes) -> None:
        """InsertAt（演算法 6.2.12）：在第 i 個位置插入記錄，第 i 個以後的槽往後移一格。

        放不下則拋出 ValueError。"""
        if self.free_space() < len(rec) + SLOT:
            self.compact()
            if self.free_space() < len(rec) + SLOT:
                raise ValueError("這一頁放不下")
        n = self.n_slots
        a, b = HEADER + i * SLOT, HEADER + n * SLOT
        self.data[a + SLOT:b + SLOT] = self.data[a:b]  # 槽陣列往後移一格
        pos = self._place(rec)
        self._set(1, n + 1)
        self._set_slot(i, pos, len(rec))

    def remove_at(self, i: int) -> None:
        """RemoveAt（演算法 6.2.12）：移除第 i 個槽，後面的槽往前移一格；記錄成為空洞。"""
        n = self.n_slots
        a, b = HEADER + (i + 1) * SLOT, HEADER + n * SLOT
        self.data[a - SLOT:b - SLOT] = self.data[a:b]
        self._set(1, n - 1)

    def clear(self) -> None:
        """清空所有槽與記錄；kind、next、lsn 保留（B+ tree 分裂時重寫一頁用）。"""
        self._set(1, 0)
        self._set(2, len(self.data))

    def fits(self, rec: bytes) -> bool:
        """演算法 6.3.2 第 1 行的條件：可用空間加上空洞，是否放得下這筆記錄與一個新槽。"""
        need, free = len(rec) + SLOT, self.free_space()
        return free >= need or free + self.holes() >= need


def picture(page: SlottedPage, width: int = 64) -> str:
    """把一頁畫成字元圖：H 標頭、s 槽、. 空白、x 空洞、數字是第幾槽的記錄。"""
    n, start = page.n_slots, page.start
    cells = ["."] * len(page.data)
    cells[:HEADER] = "H" * HEADER
    cells[HEADER:HEADER + n * SLOT] = "s" * (n * SLOT)
    cells[start:] = "x" * (len(page.data) - start)
    for i in range(n):
        pos, length = page.slot(i)
        if length:
            cells[pos:pos + length] = str(i % 10) * length
    text = "".join(cells)
    return "\n".join(text[k:k + width] for k in range(0, len(text), width))
