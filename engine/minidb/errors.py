"""引擎的例外。名稱仿照 Python DB-API（PEP 249）。"""


class Error(Exception):
    """引擎所有例外的共同基底。"""


class SQLSyntaxError(Error):
    """SQL 文字不合文法。"""


class NotSupported(Error):
    """合乎 SQL 文法，但超出這個引擎支援的子集。"""


class BindError(Error):
    """名稱找不到、有歧義，或用法不對（例如沒有放進 GROUP BY 的欄）。"""


class IntegrityError(Error):
    """違反約束：NOT NULL、PRIMARY KEY、UNIQUE。"""


class TransactionError(Error):
    """交易的用法不對，例如沒有 BEGIN 就 COMMIT。"""


class DeadlockError(TransactionError):
    """發生死結，這個交易被選為犧牲者，已經 rollback。"""
