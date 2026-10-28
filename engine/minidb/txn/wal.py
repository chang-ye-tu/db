"""預寫日誌（write-ahead log，WAL）。

完整內容第 9 章的定義 9.4.1。日誌是只往後加的檔案（資料庫檔名加上 -wal），每一行是一筆 JSON 紀錄：

    {"lsn": 7, "txn": 2, "type": "insert", "table": "account", "rid": [3, 0], "after": [1, "A", 100]}

type 是 begin、commit、abort、insert、delete、newpage、checkpoint 之一。
撤銷時寫的補償紀錄（CLR）多一欄 "undoes"：它撤銷的是哪一筆。

WAL 的兩條規則（定義 9.4.2）：
  1. dirty 的頁寫回之前，LSN 不大於它的頁 LSN 的紀錄都已寫到磁碟（buffer pool 寫回前呼叫 flush(頁的 lsn)）；
  2. COMMIT 傳回之前，到它的 commit 紀錄為止的日誌都已寫到磁碟（commit 時呼叫 flush()）。
append 只把紀錄放進記憶體裡的緩衝區；flush 才寫進檔案並 fsync。當機時，緩衝區裡的紀錄就沒了。
fsync=False 時只寫進作業系統的頁快取、不等磁碟（示範時省時間；程式當掉不受影響，整台電腦當機就不保證了）。
"""

import json
import os
import threading
from pathlib import Path


class WAL:
    """預寫日誌（定義 9.4.2；日誌與紀錄是定義 9.4.1）：記憶體中的緩衝區，加上磁碟上只往後加的檔案。"""

    def __init__(self, path, fsync: bool = True):
        self.path, self.fsync = Path(path), fsync
        self.lock = threading.Lock()                 # 保護緩衝區的 latch（定義 9.2.1）
        self.buffer: list[dict] = []                 # 還沒寫到磁碟的紀錄
        self.flushes = 0
        durable = self.records()
        self.next_lsn = durable[-1]["lsn"] + 1 if durable else 1
        self.flushed_lsn = self.next_lsn - 1
        self.file = open(self.path, "a", encoding="utf-8")

    def continue_after(self, lsn: int) -> None:
        """新的 LSN 要大於 lsn（重新開啟時傳入資料檔中最大的頁 LSN；定理 9.4.16 的前提 (g)）。"""
        with self.lock:
            if lsn >= self.next_lsn:
                self.next_lsn = lsn + 1
                self.flushed_lsn = lsn

    def append(self, txn: int, type: str, **fields) -> dict:
        """加一筆紀錄（只到緩衝區），傳回這筆紀錄（含 lsn）。"""
        with self.lock:
            rec = {"lsn": self.next_lsn, "txn": txn, "type": type, **fields}
            self.next_lsn += 1
            self.buffer.append(rec)
            return rec

    def flush(self, upto: int | None = None) -> None:
        """把緩衝區的紀錄寫進檔案並 fsync。upto 已經在磁碟上時什麼都不做。"""
        with self.lock:
            if not self.buffer or (upto is not None and upto <= self.flushed_lsn):
                return
            self.file.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.buffer))
            self.file.flush()
            if self.fsync:
                os.fsync(self.file.fileno())
            self.flushed_lsn = self.buffer[-1]["lsn"]
            self.buffer.clear()
            self.flushes += 1

    def records(self) -> list[dict]:
        """磁碟上的所有紀錄。最後一行若不完整（當機時只寫了一半），就把它截掉。"""
        if not self.path.exists():
            return []
        out, good = [], 0
        with open(self.path, "rb") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    break
                good += len(line)
        if good < self.path.stat().st_size:
            os.truncate(self.path, good)
        return out

    def restart_from(self, rec: dict) -> None:
        """checkpoint 時沒有進行中的交易（定義 9.4.5）：之前的紀錄都用不到了，日誌從這一筆重新開始。
        以改名取代舊的檔案（附錄 C 的註）：新檔先 fsync 再改名，改名之後再 fsync 目錄。"""
        with self.lock:
            assert not self.buffer
            self.file.close()
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                if self.fsync:
                    os.fsync(f.fileno())             # 改名之前，新檔的內容已在磁碟上
            os.replace(tmp, self.path)
            if self.fsync:
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)                     # 改名之後，目錄的修改也在磁碟上
                finally:
                    os.close(fd)
            self.file = open(self.path, "a", encoding="utf-8")

    def crash(self) -> None:
        """模擬當機：緩衝區裡還沒寫到磁碟的紀錄消失。"""
        with self.lock:
            self.buffer.clear()
            self.file.close()

    def close(self) -> None:
        self.flush()
        self.file.close()
