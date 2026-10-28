"""Heap file：一張表的資料存在一串 heap 頁裡，頁與頁以標頭的 next 串成鏈結串列（附錄 B 的定義 B.6.2）。

第 6 章的定義 6.3.1：一列的 RID（row identifier）= (頁號, 槽號)。
新記錄放進最後一頁，放不下就配置新的一頁接在鏈尾。

第 9 章：交易 txn 不是 None 時，每次修改都寫一筆日誌（定義 9.4.1），並把日誌序號記在被改的頁的 lsn（頁 LSN）：
  insert  {rid, after}         把一列放進 rid
  delete  {rid, before}        把 rid 的列刪掉
  newpage {prev, page}         配置新的一頁，接在 prev 之後
apply 把一筆日誌的效果直接寫到頁上，復原（redo）與撤銷（undo）都用它。
"""

from .buffer import BufferPool
from .page import HEADER, HEAP, NONE, SLOT, SlottedPage
from .record import Schema

RID = tuple[int, int]


class HeapFile:
    """heap file（定義 6.3.1，放置是演算法 6.3.2）：slotted page 串成一條頁鏈，新的列放在鏈尾的頁，RID 是 (頁號, 槽號)。"""

    def __init__(self, pool: BufferPool, first_page: int, schema: Schema, name: str = "", wal=None):
        self.pool, self.first, self.schema, self.name, self.wal = pool, first_page, schema, name, wal
        self._last = None                            # 鏈尾的頁號；第一次用到時才找

    @staticmethod
    def create(pool: BufferPool) -> int:
        """配置一張空表的第一頁，傳回頁號。"""
        f = pool.new_page(HEAP)
        pool.unpin(f.page_no)
        return f.page_no

    # ------------------------------------------------------------- 讀
    def page_numbers(self):
        """依鏈結串列的順序走過每一頁的頁號。"""
        no = self.first
        while no != NONE:
            with self.pool.page(no) as p:
                nxt = p.next
            yield no
            no = nxt

    def scan(self):
        """全表掃描（演算法 6.3.4）：依序產生 (RID, 一列的值)。每一頁只讀一次：取出這一頁的列，也記下下一頁。"""
        no = self.first
        while no != NONE:
            with self.pool.page(no) as p:
                rows = [((no, i), self.schema.decode(rec)) for i, rec in p.records()]
                nxt = p.next
            yield from rows
            no = nxt

    def get(self, rid: RID) -> tuple | None:
        """RID 指到的那一列；那個槽已刪除時傳回 None。"""
        with self.pool.page(rid[0]) as p:
            rec = p.get(rid[1])
        return None if rec is None else self.schema.decode(rec)

    # ------------------------------------------------------------- 寫
    def insert(self, values: tuple, txn=None) -> RID:
        """檢查型別與記錄的長度之後，把一列放進鏈尾的頁（放不下就接一頁），傳回它的 RID。"""
        values = self.schema.check(tuple(values))
        rec = self.schema.encode(values)
        if len(rec) + SLOT > self.pool.pager.page_size - HEADER:     # 演算法 6.3.2 的前置條件
            raise ValueError(f"記錄長 {len(rec)} 個位元組，一頁空的頁也放不下（引擎沒有溢位頁）")
        no = self._last_page()
        with self.pool.page(no, dirty=True) as p:
            if p.fits(rec):
                slot = p.insert(rec)
                self._log([p], txn, "insert", rid=[no, slot], after=list(values))
                return no, slot
        f = self.pool.new_page(HEAP)                 # 放不下：接一頁在鏈尾
        try:
            with self.pool.page(no, dirty=True) as tail:
                tail.next = f.page_no
                self._log([tail, SlottedPage(f.data)], txn, "newpage", prev=no, page=f.page_no)
            p = SlottedPage(f.data)
            slot = p.insert(rec)
            self._log([p], txn, "insert", rid=[f.page_no, slot], after=list(values))
        finally:
            self.pool.unpin(f.page_no, dirty=True)
        self._last = f.page_no
        return f.page_no, slot

    def delete(self, rid: RID, txn=None) -> tuple:
        """刪除 RID 指到的那一列，傳回它原來的值；沒有這一列時引發 KeyError。"""
        with self.pool.page(rid[0], dirty=True) as p:
            rec = p.get(rid[1])
            if rec is None:
                raise KeyError(f"沒有記錄 {rid}")
            old = self.schema.decode(rec)
            p.delete(rid[1])
            self._log([p], txn, "delete", rid=list(rid), before=list(old))
        return old

    def update(self, rid: RID, values: tuple, txn=None) -> RID:
        """修改一列：刪掉舊的、插入新的；傳回新的 RID（可能不同）。新的列先依 insert 的條件檢查，
        不合格時拋出例外，舊的列還在。"""
        rec = self.schema.encode(self.schema.check(tuple(values)))
        if len(rec) + SLOT > self.pool.pager.page_size - HEADER:     # 演算法 6.3.2 的前置條件
            raise ValueError(f"記錄長 {len(rec)} 個位元組，一頁空的頁也放不下（引擎沒有溢位頁）")
        self.delete(rid, txn)
        return self.insert(values, txn)

    # ------------------------------------------------------------- 內部
    def _last_page(self) -> int:
        if self._last is None:
            for no in self.page_numbers():
                self._last = no
        return self._last

    def _log(self, pages, txn, kind, **fields) -> None:
        if txn is None or self.wal is None:
            return
        rec = self.wal.append(txn.id, kind, table=self.name, **fields)
        txn.records.append(rec)
        for p in pages:
            p.lsn = rec["lsn"]

    # ------------------------------------------------------------- 復原
    def apply(self, rec: dict) -> None:
        """把一筆日誌的效果寫到頁上，不再寫日誌。頁的 lsn 不小於這筆日誌的序號時，
        表示效果已經在頁上（當機前已經寫回磁碟），這一頁就不動。"""
        lsn = rec["lsn"]
        if rec["type"] == "newpage":
            self.pool.pager.extend(rec["page"])      # 新的一頁可能還沒寫到檔案裡
            with self.pool.page(rec["page"], dirty=True) as p:
                if p.lsn < lsn:
                    p.data[:] = SlottedPage.new(HEAP, len(p.data)).data
                    p.lsn = lsn
            with self.pool.page(rec["prev"], dirty=True) as p:
                if p.lsn < lsn:
                    p.next, p.lsn = rec["page"], lsn
            self._last = None
            return
        no, slot = rec["rid"]
        with self.pool.page(no, dirty=True) as p:
            if p.lsn < lsn:
                after = rec["after"] if rec["type"] == "insert" else None
                p.put(slot, None if after is None else self.schema.encode(tuple(after)))
                p.lsn = lsn
