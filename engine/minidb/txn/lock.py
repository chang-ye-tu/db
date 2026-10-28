"""Lock manager：嚴謹兩階段鎖定（rigorous 2PL）與死結偵測。

完整內容第 9 章：引擎的表鎖（定義 9.2.2）、兩階段鎖定（定義 9.2.3）、等待圖與死結偵測（定義 9.3.1、演算法 9.3.3、命題 9.3.4）。
資源（resource）可以是任何能當 dict 鍵的值；引擎鎖的是整張表，資源是 ("table", 表名)。
兩種模式：S（共享鎖，讀）與 X（排他鎖，寫）。相容表（第 5 章的定義 5.3.4）：

          S    X
    S     ✓    ✗
    X     ✗    ✗

交易拿到的鎖一直留到 commit 或 rollback 才一起放掉（嚴謹 2PL）：別的交易看不到還沒 commit 的修改。

等不到鎖時，交易在條件變數上等待（附錄 C 的定義 C.4.3）；它在等待圖上有一條邊指向擋住它的每個交易。
開始等待時（以及被叫醒而仍要等時）由它沿著等待圖找環：找到經過它的環就是死結，它成為犧牲者，拋出 DeadlockError。
等待累計超過 timeout 秒，這一句以 TransactionError 失敗（定義 9.2.9）。
"""

import threading
import time

from ..errors import DeadlockError, TransactionError

S, X = "S", "X"


def compatible(held: str, wanted: str) -> bool:
    """別的交易持有 held 模式時，能不能再給 wanted 模式：只有 S 與 S 相容。"""
    return held == S and wanted == S


class LockManager:
    """鎖表（定義 9.2.2）：每個資源由哪些交易以什麼模式持有，以及每個交易在等哪一個鎖。"""

    def __init__(self, timeout: float = 10.0):
        self.cond = threading.Condition()   # 保護鎖表的互斥鎖，以及等鎖用的條件變數
        self.held: dict = {}          # 資源 → {交易: 模式}
        self.waiting: dict = {}       # 交易 → (資源, 模式)：正在等的鎖
        self.timeout = timeout
        self.log: list = []           # (交易, 動作, 資源, 模式)：給示範看的紀錄

    def acquire(self, txn, resource, mode: str) -> None:
        """取得鎖，拿不到就等；死結時拋出 DeadlockError，逾時拋出 TransactionError。"""
        with self.cond:
            mine = self.held.get(resource, {}).get(txn)
            if mine == X or mine == mode:
                return                               # 已經有一樣強或更強的鎖
            deadline = time.monotonic() + self.timeout   # 逾時以截止的時刻計，被叫醒幾次都一樣
            while True:
                if not self.blockers(txn, resource, mode):
                    self.held.setdefault(resource, {})[txn] = mode   # S 升級成 X 也走這裡
                    self.waiting.pop(txn, None)
                    self.log.append((txn, "取得", resource, mode))
                    return
                first = txn not in self.waiting
                self.waiting[txn] = (resource, mode)
                cycle = self.find_cycle(txn)
                if cycle:
                    del self.waiting[txn]
                    self.log.append((txn, "死結", resource, mode))
                    raise DeadlockError("死結：" + " → ".join(f"T{t}" for t in cycle + [txn])
                                        + f"；T{txn} 被選為犧牲者")
                if first:
                    self.log.append((txn, "等待", resource, mode))
                left = deadline - time.monotonic()
                if left <= 0 or not self.cond.wait(left):
                    if self.blockers(txn, resource, mode):   # 逾時的那一刻仍被擋住
                        del self.waiting[txn]
                        self.log.append((txn, "逾時", resource, mode))
                        what = resource[1] if isinstance(resource, tuple) else resource
                        raise TransactionError(f"T{txn} 等 {what} 的 {mode} 鎖超過 {self.timeout} 秒")

    def blockers(self, txn, resource, mode: str) -> set:
        """擋住這個請求的交易：持有 resource、而且模式與 mode 不相容的其他交易。"""
        # 練習 U09-A：鎖的相容性 blockers（見本回的練習集）
        raise NotImplementedError("練習 U09-A：鎖的相容性 blockers")

    def release_all(self, txn) -> None:
        """交易結束（commit 或 rollback）：放掉它所有的鎖，叫醒等待的交易。"""
        with self.cond:
            for resource in list(self.held):
                if self.held[resource].pop(txn, None) is not None:
                    self.log.append((txn, "放掉", resource, None))
                if not self.held[resource]:
                    del self.held[resource]
            self.waiting.pop(txn, None)
            self.cond.notify_all()

    def wait_for_graph(self) -> dict:
        """等待圖（定義 9.3.1）：等待中的交易 → 擋住它的交易的集合。"""
        return {t: self.blockers(t, r, m) for t, (r, m) in self.waiting.items()}

    def find_cycle(self, start) -> list | None:
        """由 start 沿著等待圖的邊做深度優先搜尋（演算法 B.9.8），走得回 start 就是死結：
        傳回環上的交易（由 start 開始），沒有經過 start 的環時傳回 None。"""
        # 練習 U09-B：死結偵測 find_cycle（見本回的練習集）
        raise NotImplementedError("練習 U09-B：死結偵測 find_cycle")


class NoLocks:
    """不加鎖（第 9 章的示範：沒有鎖時會出現哪些異常；也用來在練習集裡準備資料）。"""

    def __init__(self):
        self.log: list = []
        self.held: dict = {}
        self.waiting: dict = {}

    def acquire(self, txn, resource, mode) -> None:
        pass

    def release_all(self, txn) -> None:
        pass
