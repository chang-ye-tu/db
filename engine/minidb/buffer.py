"""Buffer pool：記憶體裡只放得下 capacity 頁；要用的頁不在記憶體裡就從磁碟讀進來，
滿了就依 LRU 換出最久沒用、而且沒有被 pin 住的頁；被改過（dirty）的頁換出前先寫回。

第 6 章的演算法 6.4.3 與 6.4.7。最近使用的順序用一條雙向鏈結串列記錄（附錄 B 的定義 B.6.2）：
頭端是最近用過的頁，尾端是最久沒用的頁。

第 9 章的 WAL 規則 1（定義 9.4.2）：dirty 的頁寫回磁碟之前，LSN 不大於它的頁 LSN 的日誌必須先寫到磁碟；
所以寫回前呼叫 wal.flush(頁的 lsn)。buffer pool 可以換出含有未提交修改的頁（steal），提交時不寫回（no-force，定義 9.4.3）。
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

from .page import SlottedPage
from .pager import Pager


@dataclass(eq=False)
class Frame:
    """buffer pool 的一個 frame（定義 6.4.1）：頁號、內容、pin 的次數、dirty，與 LRU 串列中的鄰居。"""
    page_no: int
    data: bytearray
    pins: int = 0
    dirty: bool = False
    prev: "Frame | None" = field(default=None, repr=False)   # LRU 串列中較新的一個
    next: "Frame | None" = field(default=None, repr=False)   # LRU 串列中較舊的一個


class LRUList:
    """LRU 串列（演算法 6.4.7）：雙向鏈結串列，head 是最近被要求的 frame，tail 是最久沒被要求的。"""

    def __init__(self):
        self.head: Frame | None = None
        self.tail: Frame | None = None

    def push_front(self, f: Frame) -> None:
        f.prev, f.next = None, self.head
        if self.head is not None:
            self.head.prev = f
        self.head = f
        if self.tail is None:
            self.tail = f

    def remove(self, f: Frame) -> None:
        if f.prev is not None:
            f.prev.next = f.next
        else:
            self.head = f.next
        if f.next is not None:
            f.next.prev = f.prev
        else:
            self.tail = f.prev
        f.prev = f.next = None

    def touch(self, f: Frame) -> None:
        """f 剛被使用：移到頭端。"""
        self.remove(f)
        self.push_front(f)

    def victim(self) -> Frame | None:
        """演算法 6.4.7 第 2 行：由尾端往頭端，傳回第一個沒有被 pin 住的 frame；都被 pin 住（或串列是空的）時傳回 None。"""
        # 練習 U06-B：LRU 的淘汰 victim（見本回的練習集）
        raise NotImplementedError("練習 U06-B：LRU 的淘汰 victim")


class BufferPool:
    """buffer pool（定義 6.4.1）：記憶體裡至多 capacity 頁，依 LRU 換出沒有被 pin 住的頁。"""

    def __init__(self, pager: Pager, capacity: int, wal=None):
        if capacity < 2:                            # heap file 接新頁、B+ tree 分裂時，同時 pin 住兩頁
            raise ValueError(f"buffer pool 至少要 2 個 frame，得到 {capacity}：接新頁或分裂時同時 pin 住兩頁")
        self.pager, self.capacity, self.wal = pager, capacity, wal
        self.frames: dict[int, Frame] = {}          # 頁號 → Frame（page table）
        self.lru = LRUList()
        self.hits = self.misses = 0
        self.latch = threading.RLock()              # 保護 frame 與頁表的 latch（定義 9.2.1）

    def fetch(self, page_no: int) -> Frame:
        """要求一頁（演算法 6.4.3）：取得一頁並 pin 住；用完一定要 unpin。"""
        with self.latch:
            f = self.frames.get(page_no)
            if f is not None:
                self.hits += 1
                self.lru.touch(f)
            else:
                self.misses += 1
                self._make_room()
                f = Frame(page_no, bytearray(self.pager.read(page_no)))
                self.frames[page_no] = f
                self.lru.push_front(f)
            f.pins += 1
            return f

    def new_page(self, kind: int) -> Frame:
        """要求新的一頁（演算法 6.4.3）：配置新的一頁（已初始化、pin 住、標成 dirty）。"""
        with self.latch:
            self._make_room()
            page_no = self.pager.allocate()
            f = Frame(page_no, SlottedPage.new(kind, self.pager.page_size).data, pins=1, dirty=True)
            self.frames[page_no] = f
            self.lru.push_front(f)
            return f

    def unpin(self, page_no: int, dirty: bool = False) -> None:
        """放開一頁：pin 的次數減 1；dirty=True 表示內容改過，換出前要寫回。"""
        with self.latch:
            f = self.frames[page_no]
            assert f.pins > 0, f"第 {page_no} 頁沒有被 pin 住"
            f.pins -= 1
            f.dirty = f.dirty or dirty

    @contextmanager
    def page(self, page_no: int, dirty: bool = False):
        """with pool.page(no) as p: ...——自動 pin 與 unpin；要修改就傳 dirty=True。"""
        f = self.fetch(page_no)
        try:
            yield SlottedPage(f.data)
        finally:
            self.unpin(page_no, dirty)

    def _make_room(self) -> None:
        if len(self.frames) < self.capacity:
            return
        victim = self.lru.victim()
        if victim is None:
            raise RuntimeError("所有頁都被 pin 住，沒有頁可以換出")
        self.lru.remove(victim)
        del self.frames[victim.page_no]
        if victim.dirty:
            self._write_back(victim)

    def _write_back(self, f: Frame) -> None:
        if self.wal is not None:
            self.wal.flush(SlottedPage(f.data).lsn)   # WAL 的規則 1：日誌先寫
        self.pager.write(f.page_no, f.data)
        f.dirty = False

    def flush_all(self) -> None:
        """把所有髒頁寫回（checkpoint 與關閉時用）。"""
        with self.latch:
            for f in self.frames.values():
                if f.dirty:
                    self._write_back(f)

    def drop_all(self) -> None:
        """模擬當機：記憶體裡的頁全部消失，沒寫回的修改也跟著消失。"""
        with self.latch:
            self.frames.clear()
            self.lru = LRUList()

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses,
                "reads": self.pager.reads, "writes": self.pager.writes}
