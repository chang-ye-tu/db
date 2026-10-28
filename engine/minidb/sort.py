"""外部合併排序（external merge sort）：要排序的資料比記憶體大。

第 7 章的演算法 7.6.5 與命題 7.6.6 推導成本。資料有 N 頁、記憶體有 B 頁：

  * 第 0 趟：每次讀進 B 頁，在記憶體裡排好，寫成一個 run；共 ⌈N/B⌉ 個 run。
  * 合併：每一趟把 B − 1 個 run 合併成一個（B − 1 頁當輸入緩衝區，1 頁當輸出緩衝區），
    共 ⌈log_{B−1}⌈N/B⌉⌉ 趟。
  * 每一趟讀、寫各 N 頁；最後一趟的結果直接交給下一個運算子，不寫回。
    所以連同讀入原始資料，共讀寫 N(2⌈log_{B−1}⌈N/B⌉⌉ + 1) 頁。

run 存在暫存檔裡，每一頁是一個 slotted page，以 Pager 讀寫，所以讀寫的頁數可以直接數。
列的編碼預設用 AnyRow（每個值自帶型別），也可以傳入一張表的 Schema。
"""

import tempfile
from pathlib import Path

from .page import HEAP, PAGE_SIZE, SlottedPage
from .pager import Pager
from .record import AnyRow

_END = object()                   # run 讀完的記號


class ExternalSort:
    """演算法 ExternalSort：第 0 趟寫出 run，再以 MergeK 每趟合併 B − 1 個 run。"""

    def __init__(self, key, memory_pages: int, page_size: int = PAGE_SIZE, codec=None):
        if memory_pages < 3:
            raise ValueError("記憶體至少要 3 頁：合併時 2 頁輸入、1 頁輸出")
        self.key, self.B, self.page_size = key, memory_pages, page_size
        self.codec = codec or AnyRow()
        self.input_pages = 0        # 第 0 趟讀進的頁數，即 N
        self.runs_after_pass = []   # 每一趟寫完之後有幾個 run
        self.used = False           # 一個物件只排序一次：排完就刪除暫存檔，stats() 也只屬於那一次
        self._tmp = tempfile.TemporaryDirectory(prefix="minidb-sort-")
        self.pager = Pager(Path(self._tmp.name) / "runs", page_size)

    def sort(self, rows):
        """依 key 排序後依序產生 rows 的每一列；rows 可以是任何 iterable（例如下層的運算子）。"""
        if self.used:
            raise RuntimeError("這個 ExternalSort 已經排序過一次；每次排序請建一個新的 ExternalSort")
        self.used = True
        try:
            runs = []
            for load, pages, more in self._memory_loads(rows):
                self.input_pages += pages
                if not runs and not more:            # 放得進記憶體：不必寫 run
                    yield from load
                    return
                runs.append(self._write_run(load))   # 寫成 run 之後才讀下一批：記憶體裡一次只有一批
            if not runs:
                return
            self.runs_after_pass.append(len(runs))
            k = self.B - 1
            while len(runs) > k:                     # 中間的合併趟：結果寫回暫存檔
                runs = [self._write_run(self._merge(runs[i:i + k])) for i in range(0, len(runs), k)]
                self.runs_after_pass.append(len(runs))
            yield from self._merge(runs)             # 最後一趟：直接交出去
        finally:
            self.close()

    def stats(self) -> dict:
        """讀寫的頁數：N（第 0 趟讀入）、run 的讀寫、每一趟之後的 run 數與總 I/O。"""
        return {"N": self.input_pages, "B": self.B, "runs_after_pass": self.runs_after_pass,
                "passes": len(self.runs_after_pass) + 1,
                "run_reads": self.pager.reads, "run_writes": self.pager.writes,
                "total_io": self.input_pages + self.pager.reads + self.pager.writes}

    def close(self) -> None:
        """關閉並刪除存放 run 的暫存檔。"""
        if not self.pager.file.closed:
            self.pager.close(sync=False)
            self._tmp.cleanup()

    # ------------------------------------------------------------- 第 0 趟
    def _memory_loads(self, rows):
        """第 0 趟：每次讀進至多 B 頁的列（以 slotted page 計算），排好後交出 (這一批, 頁數, 後面還有沒有列)。"""
        load, page, pages = [], SlottedPage.new(HEAP, self.page_size), 1
        for row in rows:
            rec = self.codec.encode(row)
            if not page.fits(rec):
                if pages == self.B:                  # 記憶體滿了：這一列留給下一批
                    yield sorted(load, key=self.key), pages, True
                    load, pages = [], 0
                page, pages = SlottedPage.new(HEAP, self.page_size), pages + 1
            page.insert(rec)
            load.append(row)
        if load:
            yield sorted(load, key=self.key), pages, False

    # ------------------------------------------------------------- run 的讀寫
    def _write_run(self, rows) -> list[int]:
        """把已排序的列寫成一個 run，傳回它的頁號；記憶體裡只用一頁當輸出緩衝區。"""
        pages, page = [], SlottedPage.new(HEAP, self.page_size)
        for row in rows:
            rec = self.codec.encode(row)
            if not page.fits(rec):
                pages.append(self._write_page(page))
                page = SlottedPage.new(HEAP, self.page_size)
            page.insert(rec)
        if page.n_slots:
            pages.append(self._write_page(page))
        return pages

    def _write_page(self, page: SlottedPage) -> int:
        no = self.pager.allocate()
        self.pager.write(no, page.data)
        return no

    def _read_run(self, pages: list[int]):
        """依序讀一個 run 的每一頁；這個 run 在記憶體裡一次只佔一頁。"""
        for no in pages:
            page = SlottedPage(bytearray(self.pager.read(no)))
            for _, rec in page.records():
                yield self.codec.decode(rec)

    # ------------------------------------------------------------- 合併
    def _merge(self, runs: list[list[int]]):
        """合併幾個已排序的 run：每次從各 run 目前的第一列中取最小的交出。

        相同的鍵先交出前面的 run 的列，所以排序是穩定的。"""
        streams = [self._read_run(r) for r in runs]
        heads = [next(s, _END) for s in streams]
        while True:
            live = [i for i, h in enumerate(heads) if h is not _END]
            if not live:
                return
            i = min(live, key=lambda j: self.key(heads[j]))
            yield heads[i]
            heads[i] = next(streams[i], _END)
