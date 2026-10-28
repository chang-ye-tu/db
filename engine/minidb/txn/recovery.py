"""當機復原（第 9 章的演算法 9.4.10）：重做（redo）日誌裡的每一筆修改，再撤銷（undo）沒有完成的交易。

演算法與 DSC 的復原演算法相同，另外借用 ARIES 的頁 LSN 與補償紀錄（CLR）：
  1. 重做（repeat history）：從最後一個 checkpoint 往後讀，把每一筆修改（包括 CLR）重做到頁上；
     頁的 lsn 不小於紀錄的 lsn 時，表示效果已經在頁上，跳過（HeapFile.apply）。
     同時找出沒有 commit 也沒有 abort 的交易：未完成的交易。
  2. 撤銷：從日誌尾端往前，把未完成的交易的修改反過來做，每做一筆寫一筆 CLR；
     已經被 CLR 撤銷過的紀錄跳過；遇到它的 begin 就寫一筆 abort，把它移出未完成的交易。
索引的修改沒有寫進日誌（為了簡單）：復原之後，索引由 heap 重建。正確性是定理 9.4.16 與命題 9.4.17。
"""

UPDATES = ("insert", "delete", "newpage")


def compensate(wal, heap, rec: dict, txn: int) -> dict:
    """撤銷一筆 insert 或 delete（演算法 9.4.10 的撤銷）：寫一筆做相反動作的 CLR，並把它套用到頁上。傳回這筆 CLR。"""
    if rec["type"] == "insert":
        clr = wal.append(txn, "delete", table=rec["table"], rid=rec["rid"], before=rec["after"], undoes=rec["lsn"])
    else:
        clr = wal.append(txn, "insert", table=rec["table"], rid=rec["rid"], after=rec["before"], undoes=rec["lsn"])
    heap.apply(clr)
    return clr


def redo(records: list, heap_of) -> set:
    """重做（演算法 9.4.10 的第一個迴圈）：重做最後一個 checkpoint 之後的每一筆修改；傳回未完成的交易的集合。

    heap_of(表名) 傳回那張表的 HeapFile。"""
    start, losers = 0, set()
    for i, r in enumerate(records):
        if r["type"] == "checkpoint":
            start, losers = i + 1, set(r["active"])
    for r in records[start:]:
        if r["type"] == "begin":
            losers.add(r["txn"])
        elif r["type"] in ("commit", "abort"):
            losers.discard(r["txn"])
        elif r["type"] in UPDATES:
            heap_of(r["table"]).apply(r)
    return losers


def undo(records: list, losers: set, heap_of, wal) -> list:
    """撤銷（演算法 9.4.10 的第二個迴圈）：由後往前撤銷 losers 的修改（每一筆寫一筆 CLR），遇到 begin 寫 abort；傳回寫下的 CLR。"""
    done = {r["undoes"] for r in records if "undoes" in r}
    clrs, losers = [], set(losers)
    for r in reversed(records):
        if not losers:
            break
        if r["txn"] not in losers:
            continue
        if r["type"] in ("insert", "delete") and "undoes" not in r and r["lsn"] not in done:
            clrs.append(compensate(wal, heap_of(r["table"]), r, r["txn"]))
        elif r["type"] == "begin":
            wal.append(r["txn"], "abort")
            losers.discard(r["txn"])
    return clrs
