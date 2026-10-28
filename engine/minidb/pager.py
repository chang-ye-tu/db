"""Pager：資料庫檔案就是一頁接一頁的陣列；以頁號讀寫，並計算讀寫了幾頁。

第 6 章的定義 6.1.1；附錄 C 的命題 C.3.4：寫進檔案（write）只是交給作業系統的頁快取，
呼叫 sync（flush 再 fsync）之後，才保證資料已經在磁碟上。
"""

import os
from pathlib import Path

from .page import PAGE_SIZE


class Pager:
    """資料庫檔案（定義 6.1.1）：以頁號讀寫整頁，並數讀寫了幾頁、sync 了幾次。"""

    def __init__(self, path, page_size: int = PAGE_SIZE, fsync: bool = True):
        self.path, self.page_size, self.fsync = Path(path), page_size, fsync
        self.path.touch()
        self.file = open(self.path, "r+b")
        self.n_pages = self.path.stat().st_size // page_size
        self.reads = self.writes = self.syncs = 0

    def read(self, page_no: int) -> bytes:
        """讀第 page_no 頁（一次 I/O）。"""
        if not 0 <= page_no < self.n_pages:
            raise IndexError(f"沒有第 {page_no} 頁（檔案有 {self.n_pages} 頁）")
        self.reads += 1
        self.file.seek(page_no * self.page_size)
        return self.file.read(self.page_size).ljust(self.page_size, b"\0")  # 還沒寫過的頁全是 0

    def peek(self, page_no: int) -> bytes:
        """讀第 page_no 頁而不計入 reads（第 9 章：重新開啟時找出資料檔中最大的頁 LSN）。"""
        self.file.seek(page_no * self.page_size)
        return self.file.read(self.page_size).ljust(self.page_size, b"\0")

    def write(self, page_no: int, data: bytes) -> None:
        """把一整頁寫到第 page_no 頁（一次 I/O）；sync 之前不保證已在磁碟上。"""
        assert len(data) == self.page_size
        self.writes += 1
        self.file.seek(page_no * self.page_size)
        self.file.write(data)
        self.n_pages = max(self.n_pages, page_no + 1)

    def allocate(self) -> int:
        """在檔尾預留一頁，傳回頁號；內容由呼叫者寫入。"""
        page_no = self.n_pages
        self.n_pages += 1
        return page_no

    def extend(self, page_no: int) -> None:
        """確保第 page_no 頁存在（第 9 章的復原：日誌記得配置過、但當機前沒寫到檔案的頁）。"""
        self.n_pages = max(self.n_pages, page_no + 1)

    def sync(self) -> None:
        """把作業系統的頁快取寫到磁碟（fsync）。"""
        self.file.flush()
        if self.fsync:
            os.fsync(self.file.fileno())
        self.syncs += 1

    def close(self, sync: bool = True) -> None:
        if sync:
            self.sync()
        self.file.close()
