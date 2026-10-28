"""minidb：課程「資料庫管理」第 6–9 章的教學用關聯資料庫引擎（純 Python）。

    from minidb import Database
    db = Database("demo.db")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")

第 6、7 章只用到儲存與索引的模組（minidb.page、minidb.btree ...），不必載入 SQL 前端；
所以 Database 等名稱等到第一次用到時才載入（ANTLR 的 parser 載入要零點幾秒）。
"""

from .errors import (BindError, DeadlockError, Error, IntegrityError, NotSupported, SQLSyntaxError,
                     TransactionError)

__all__ = ["Database", "Connection", "Result", "Error", "SQLSyntaxError", "NotSupported", "BindError",
           "IntegrityError", "TransactionError", "DeadlockError"]


def __getattr__(name):
    if name in ("Database", "Connection", "Result"):
        from . import db
        return getattr(db, name)
    raise AttributeError(f"module 'minidb' has no attribute {name!r}")
