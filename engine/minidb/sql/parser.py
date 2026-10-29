"""剖析：SQL 文字 → 剖析樹（ANTLR 產生的 parser）→ AST（本檔的 Visitor）。

parser 由 ANTLR 4.13.2 依 grammars-v4 的 SQLite 文法產生（sqlite_parser/，授權見其中的 LICENSE-grammar.txt）。
第 8 章的 8.1 節說明文法檔、剖析樹與 Visitor（定義 8.1.1–8.1.4、命題 8.1.5）。這裡的 Visitor 只接受引擎支援的子集，
其餘的語法拋出 NotSupported，並說明是哪一種語法。
"""

from antlr4 import CommonTokenStream, InputStream
from antlr4.atn.PredictionMode import PredictionMode
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.ErrorStrategy import BailErrorStrategy, DefaultErrorStrategy
from antlr4.error.Errors import ParseCancellationException
from antlr4.tree.Tree import TerminalNode

from ..errors import NotSupported, SQLSyntaxError
from .ast import (BinOp, Begin, Case, Col, ColumnDef, Commit, CreateIndex, CreateTable, Delete, Drop,
                  Explain, Func, Insert, Item, Join, Lit, Order, Param, Rollback, Select, Star, TableRef,
                  Unary, Update)
from .sqlite_parser.SQLiteLexer import SQLiteLexer
from .sqlite_parser.SQLiteParser import SQLiteParser
from .sqlite_parser.SQLiteParserVisitor import SQLiteParserVisitor

P = SQLiteParser


def parse(text: str) -> list:
    """把一段 SQL（可以有多句，以 ; 分隔）剖析成 AST 的串列。"""
    return AstBuilder().visit(parse_tree(text))


def parse_tree(text: str):
    """SQL 文字 → ANTLR 的剖析樹。先用較快的 SLL 模式；失敗再用完整的 LL 模式，並回報第一個錯誤。"""
    lexer = SQLiteLexer(InputStream(text))
    errors = _Errors(text)
    lexer.removeErrorListeners()
    lexer.addErrorListener(errors)
    tokens = CommonTokenStream(lexer)
    parser = SQLiteParser(tokens)
    parser.removeErrorListeners()
    parser._interp.predictionMode = PredictionMode.SLL
    parser._errHandler = BailErrorStrategy()
    try:
        tree = parser.parse()
    except ParseCancellationException:
        tokens.seek(0)
        parser.reset()
        parser.addErrorListener(errors)
        parser._interp.predictionMode = PredictionMode.LL
        parser._errHandler = DefaultErrorStrategy()
        tree = parser.parse()
    if errors.messages:
        raise SQLSyntaxError(errors.messages[0])
    return tree


class _Errors(ErrorListener):
    """把 ANTLR 的錯誤改寫成「第幾行第幾欄、原句、^ 指出位置」。"""

    def __init__(self, text: str):
        self.lines, self.messages = text.splitlines(), []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        src = self.lines[line - 1] if 0 < line <= len(self.lines) else ""
        got = offendingSymbol.text if offendingSymbol is not None else src[column:column + 1]
        got = "（句子結束）" if got == "<EOF>" else repr(got)
        self.messages.append(f"第 {line} 行第 {column + 1} 欄附近不合文法：{got}\n    {src}\n    {' ' * column}^")


def unquote(name: str) -> str:
    if name[:1] == "'":                              # 'alias'：用字串常數寫的別名
        return name[1:-1].replace("''", "'")
    if name[:1] in "\"`[" and len(name) > 1:
        return name[1:-1].replace('""', '"') if name[0] == '"' else name[1:-1]
    return name


def fold_and(conds: list):
    node = conds[0]
    for c in conds[1:]:
        node = BinOp("AND", node, c)
    return node


def _rightmost_name(src) -> str:
    while isinstance(src, Join):
        src = src.right
    return src.alias or src.name


def column_type(declared: str) -> str:
    """宣告的型別 → 引擎的三種型別。規則仿照 SQLite 的型別親和性（type affinity）。"""
    t = declared.upper()
    if "INT" in t or "BOOL" in t:
        return "INTEGER"
    if any(w in t for w in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if any(w in t for w in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    raise NotSupported(f"不支援的型別 {declared or '（沒有寫型別）'}：只有 INTEGER、REAL、TEXT")


class AstBuilder(SQLiteParserVisitor):
    def __init__(self):
        self.n_params = 0                            # 這一句已經出現幾個 ?

    # ------------------------------------------------------------- 敘述
    def visitParse(self, ctx):                       # parse: sql_stmt_list EOF
        return [self.visit(s) for s in ctx.sql_stmt_list().sql_stmt()]

    def visitSql_stmt(self, ctx):
        self.n_params = 0
        stmt = next(ch for ch in ctx.children if not isinstance(ch, TerminalNode))
        name = type(stmt).__name__.removesuffix("Context").lower()
        handled = {"select_stmt", "create_table_stmt", "create_index_stmt", "drop_stmt", "insert_stmt",
                   "update_stmt", "delete_stmt", "begin_stmt", "commit_stmt", "rollback_stmt"}
        if name not in handled:
            raise NotSupported(f"不支援 {name.removesuffix('_stmt').upper().replace('_', ' ')} 敘述")
        node = self.visit(stmt)
        return Explain(node) if ctx.EXPLAIN_() else node

    def visitCreate_table_stmt(self, ctx):
        if ctx.TEMP_() or ctx.TEMPORARY_() or ctx.schema_name() or ctx.AS_() or ctx.table_options():
            raise NotSupported("CREATE TABLE 只支援 CREATE TABLE 名稱 (欄的定義, ...)")
        stmt = CreateTable(unquote(ctx.table_name().getText()), [self.visit(c) for c in ctx.column_def()],
                           if_not_exists=ctx.IF_() is not None)
        stmt.primary_key = [c.name for c in stmt.columns if c.primary_key]
        stmt.uniques = [[c.name] for c in stmt.columns if c.unique]
        for tc in ctx.table_constraint():
            if tc.CHECK_() or tc.FOREIGN_() or tc.conflict_clause():
                raise NotSupported("表的約束只支援 PRIMARY KEY (...) 與 UNIQUE (...)")
            cols = [self._plain_column(ic) for ic in tc.indexed_column()]
            if tc.PRIMARY_():
                if stmt.primary_key:
                    raise NotSupported("一張表只能有一個 PRIMARY KEY")
                stmt.primary_key = cols
            else:
                stmt.uniques.append(cols)
        if len([c for c in stmt.columns if c.primary_key]) > 1:
            raise NotSupported("一張表只能有一個 PRIMARY KEY；複合主鍵請寫成 PRIMARY KEY (a, b)")
        return stmt

    def visitColumn_def(self, ctx):
        tn = ctx.type_name()
        col = ColumnDef(unquote(ctx.column_name().getText()),
                        column_type(" ".join(n.getText() for n in tn.name()) if tn else ""))
        for cc in ctx.column_constraint():
            if cc.PRIMARY_() and not (cc.conflict_clause() or cc.AUTOINCREMENT_()):
                col.primary_key = True
            elif cc.NULL_() and not cc.conflict_clause() and not cc.DEFAULT_():
                col.not_null = cc.NOT_() is not None
            elif cc.UNIQUE_() and not cc.conflict_clause():
                col.unique = True
            else:
                raise NotSupported(f"欄的約束只支援 PRIMARY KEY、NOT NULL、UNIQUE（{cc.getText()}）")
        return col

    def _plain_column(self, ic) -> str:
        """indexed_column 必須只是一個欄名（不支援 COLLATE、DESC、運算式）。"""
        e = self.visit(ic.expr())
        if not isinstance(e, Col) or e.table or ic.COLLATE_() or ic.asc_desc():
            raise NotSupported(f"索引與約束裡只能寫欄名（{ic.getText()}）")
        return e.name

    def visitCreate_index_stmt(self, ctx):
        if ctx.schema_name() or ctx.WHERE_():
            raise NotSupported("不支援部分索引（CREATE INDEX ... WHERE）")
        return CreateIndex(unquote(ctx.index_name().getText()), unquote(ctx.table_name().getText()),
                           [self._plain_column(ic) for ic in ctx.indexed_column()],
                           unique=ctx.UNIQUE_() is not None, if_not_exists=ctx.IF_() is not None)

    def visitDrop_stmt(self, ctx):
        if not (ctx.TABLE_() or ctx.INDEX_()) or ctx.schema_name():
            raise NotSupported("DROP 只支援 DROP TABLE 與 DROP INDEX")
        return Drop("TABLE" if ctx.TABLE_() else "INDEX", unquote(ctx.any_name().getText()),
                    if_exists=ctx.IF_() is not None)

    def visitInsert_stmt(self, ctx):
        if (ctx.with_clause() or ctx.REPLACE_() or ctx.OR_() or ctx.schema_name() or ctx.table_alias()
                or ctx.DEFAULT_() or ctx.upsert_clause() or ctx.returning_clause()):
            raise NotSupported("INSERT 只支援 INSERT INTO 表 [(欄, ...)] VALUES ... 或 SELECT ...")
        stmt = Insert(unquote(ctx.table_name().getText()),
                      [unquote(c.getText()) for c in ctx.column_name()] or None)
        sel = ctx.select_stmt()
        values = sel.select_core(0).values_clause() if len(sel.select_core()) == 1 else None
        if values is not None and not (sel.with_clause() or sel.order_clause() or sel.limit_clause()):
            stmt.rows = [[self.visit(e) for e in row.expr()] for row in values.value_row()]
        else:
            stmt.query = self.visit(sel)
        return stmt

    def _target(self, q) -> TableRef:
        if q.schema_name() or q.alias():
            raise NotSupported("UPDATE、DELETE 的表不能加 schema 或別名")
        return TableRef(unquote(q.table_name().getText()), None,
                        unquote(q.index_name().getText()) if q.INDEXED_() and q.BY_() else None,
                        q.NOT_() is not None)

    def visitUpdate_stmt(self, ctx):
        if (ctx.with_clause() or ctx.OR_() or ctx.column_name_list() or ctx.FROM_() or ctx.returning_clause()
                or ctx.order_clause() or ctx.limit_clause()):
            raise NotSupported("UPDATE 只支援 UPDATE 表 SET 欄 = 運算式, ... [WHERE ...]")
        names = [unquote(c.getText()) for c in ctx.column_name()]
        exprs = [self.visit(e) for e in ctx.expr()]
        return Update(self._target(ctx.qualified_table_name()), list(zip(names, exprs)),
                      exprs[len(names)] if ctx.WHERE_() else None)

    def visitDelete_stmt(self, ctx):
        if ctx.with_clause() or ctx.returning_clause() or ctx.order_clause() or ctx.limit_clause():
            raise NotSupported("DELETE 只支援 DELETE FROM 表 [WHERE ...]")
        return Delete(self._target(ctx.qualified_table_name()), self.visit(ctx.expr()) if ctx.WHERE_() else None)

    def visitBegin_stmt(self, ctx):
        if ctx.DEFERRED_() or ctx.IMMEDIATE_() or ctx.EXCLUSIVE_():
            raise NotSupported("BEGIN 不支援 DEFERRED、IMMEDIATE、EXCLUSIVE")
        return Begin()

    def visitCommit_stmt(self, ctx):
        return Commit()

    def visitRollback_stmt(self, ctx):
        if ctx.TO_():
            raise NotSupported("不支援 savepoint")
        return Rollback()

    # ------------------------------------------------------------- SELECT
    def visitSelect_stmt(self, ctx):                 # select_core (compound select_core)* order? limit?
        if ctx.with_clause():
            raise NotSupported("不支援 WITH（CTE）")
        if len(ctx.select_core()) != 1:
            raise NotSupported("不支援 UNION、INTERSECT、EXCEPT")
        sel = self.visit(ctx.select_core(0))
        if ctx.order_clause():
            sel.order_by = [self._ordering(t) for t in ctx.order_clause().ordering_term()]
        if ctx.limit_clause():
            lim = ctx.limit_clause()
            e = [self.visit(x) for x in lim.expr()]
            if lim.COMMA():                          # LIMIT offset, count
                sel.offset, sel.limit = e
            else:
                sel.limit, sel.offset = e[0], (e[1] if len(e) > 1 else None)
        return sel

    def _ordering(self, t):
        if t.COLLATE_() or t.NULLS_():
            raise NotSupported("ORDER BY 不支援 COLLATE、NULLS FIRST／LAST")
        return Order(self.visit(t.expr()), t.asc_desc() is not None and t.asc_desc().DESC_() is not None)

    def visitSelect_core(self, ctx):
        if ctx.values_clause():
            raise NotSupported("VALUES 只能用在 INSERT")
        if ctx.WINDOW_():
            raise NotSupported("不支援 WINDOW")
        return Select(
            items=[self.visit(rc) for rc in ctx.result_column()],
            source=self.visit(ctx.join_clause()) if ctx.join_clause() else None,
            where=self.visit(ctx.where_expr) if ctx.where_expr else None,
            group_by=[self.visit(e) for e in ctx.group_by_expr],
            having=self.visit(ctx.having_expr) if ctx.having_expr else None,
            distinct=ctx.DISTINCT_() is not None,
        )

    def visitResult_column(self, ctx):
        if ctx.STAR():
            return Item(Star(unquote(ctx.table_name().getText()) if ctx.table_name() else None))
        alias = unquote(ctx.column_alias().getText()) if ctx.column_alias() else None
        return Item(self.visit(ctx.expr()), alias)

    def visitJoin_clause(self, ctx):                 # t (join_operator t join_constraint?)*
        tree, kind = None, None
        for ch in ctx.children:
            if isinstance(ch, P.Table_or_subqueryContext):
                t = self.visit(ch)
                tree = t if tree is None else Join(kind, tree, t)
            elif isinstance(ch, P.Join_operatorContext):
                words = [c.getText().upper() for c in ch.children]
                if {"NATURAL", "RIGHT", "FULL"} & set(words):
                    raise NotSupported(f"不支援 {' '.join(words)}")
                kind = ("CROSS" if words == [","] or "CROSS" in words
                        else "LEFT" if "LEFT" in words else "INNER")
            elif isinstance(ch, P.Join_constraintContext):
                if ch.ON_():
                    tree.on = self.visit(ch.expr())
                else:                                # USING (a, b) → 左.a = 右.a AND 左.b = 右.b
                    cols = [unquote(c.getText()) for c in ch.column_name()]
                    lt, rt = _rightmost_name(tree.left), _rightmost_name(tree.right)
                    tree.on = fold_and([BinOp("=", Col(lt, c), Col(rt, c)) for c in cols])
        return tree

    def visitTable_or_subquery(self, ctx):
        if ctx.table_name() is None:
            raise NotSupported("FROM 只支援表名（不支援子查詢、表函數、括號）")
        if ctx.schema_name():
            raise NotSupported("不支援 schema 名稱")
        alias = ctx.table_alias() or ctx.table_alias_excluding_joins()
        return TableRef(unquote(ctx.table_name().getText()), unquote(alias.getText()) if alias else None,
                        unquote(ctx.index_name().getText()) if ctx.INDEXED_() and ctx.BY_() else None,
                        ctx.NOT_() is not None)

    # ------------------------------------------------------------- 運算式
    # 每一層優先順序的規則都是「運算元 (運算子 運算元)*」，同一個由左往右的 fold 就能處理
    def _fold(self, ctx):
        it = iter(ctx.children)
        node = self.visit(next(it))
        for op in it:
            text = op.getText().upper()
            if text in ("<<", ">>", "&", "|", "->", "->>"):
                raise NotSupported(f"不支援運算子 {text}")
            node = BinOp(text, node, self.visit(next(it)))
        return node

    visitExpr_or = visitExpr_and = visitExpr_comparison = visitExpr_bitwise = _fold
    visitExpr_addition = visitExpr_multiplication = visitExpr_string = _fold

    def visitExpr(self, ctx):
        return self.visit(ctx.expr_or())

    def visitExpr_not(self, ctx):                    # NOT* expr_binary
        node = self.visit(ctx.expr_binary())
        for _ in ctx.NOT_():
            node = Unary("NOT", node)
        return node

    def visitExpr_binary(self, ctx):                 # comparison (= / IS / BETWEEN / IN / LIKE ...)*
        ch = ctx.children
        node, i = self.visit(ch[0]), 1
        while i < len(ch):
            words = []
            while isinstance(ch[i], TerminalNode) and ch[i].getText().upper() in ("NOT", "IS", "DISTINCT", "FROM"):
                words.append(ch[i].getText().upper())
                i += 1
            tok = ch[i].getText().upper() if isinstance(ch[i], TerminalNode) else None
            neg = "NOT " if "NOT" in words else ""
            if words and words[0] == "IS":           # IS [NOT] x
                if "DISTINCT" in words:
                    raise NotSupported("不支援 IS DISTINCT FROM")
                right = self.visit(ch[i])
                if right == Lit(None):               # x IS NULL、x IS NOT NULL
                    node = Unary("IS NOT NULL" if neg else "IS NULL", node)
                else:
                    node = BinOp(" ".join(words), node, right)
                i += 1
            elif tok in ("=", "==", "!=", "<>"):
                node, i = BinOp({"==": "=", "!=": "<>"}.get(tok, tok), node, self.visit(ch[i + 1])), i + 2
            elif tok == "BETWEEN":                   # x [NOT] BETWEEN lo AND hi
                node = BinOp(neg + "BETWEEN", node, (self.visit(ch[i + 1]), self.visit(ch[i + 3])))
                i += 4
            elif tok == "IN":                        # x [NOT] IN (值, ...)
                if not (isinstance(ch[i + 1], TerminalNode) and ch[i + 1].getText() == "("):
                    raise NotSupported("IN 後面只支援 (值, ...)")
                j, vals = i + 2, []
                while not (isinstance(ch[j], TerminalNode) and ch[j].getText() == ")"):
                    if isinstance(ch[j], P.Select_stmtContext):
                        raise NotSupported("不支援 IN (子查詢)")
                    if not isinstance(ch[j], TerminalNode):
                        vals.append(self.visit(ch[j]))
                    j += 1
                node, i = BinOp(neg + "IN", node, tuple(vals)), j + 1
            elif tok == "LIKE":
                if i + 2 < len(ch) and isinstance(ch[i + 2], TerminalNode) and ch[i + 2].getText().upper() == "ESCAPE":
                    raise NotSupported("不支援 LIKE ... ESCAPE")
                node, i = BinOp(neg + "LIKE", node, self.visit(ch[i + 1])), i + 2
            elif tok in ("ISNULL", "NOTNULL", "NULL"):
                node, i = Unary("IS NOT NULL" if tok == "NOTNULL" or neg else "IS NULL", node), i + 1
            else:
                raise NotSupported(f"不支援運算子 {tok}")
        return node

    def visitExpr_collate(self, ctx):
        if ctx.COLLATE_():
            raise NotSupported("不支援 COLLATE")
        return self.visit(ctx.expr_unary())

    def visitExpr_unary(self, ctx):                  # (- | + | ~)* base
        node = self.visit(ctx.expr_base())
        for op in reversed(ctx.children[:-1]):
            if op.getText() == "~":
                raise NotSupported("不支援運算子 ~")
            if op.getText() == "-" and isinstance(node, Lit) and isinstance(node.value, (int, float)):
                node = Lit(-node.value)              # -3 是常數，不是「負號作用在 3」
            else:
                node = Unary(op.getText(), node)
        return node

    def visitExpr_base(self, ctx):
        if ctx.literal_value():
            return self.visit(ctx.literal_value())
        if ctx.BIND_PARAMETER():
            if ctx.getText() != "?":
                raise NotSupported("參數只支援 ?（不支援 ?NNN、:name）")
            self.n_params += 1
            return Param(self.n_params - 1)
        if ctx.column_name_excluding_string():
            raw = ctx.column_name_excluding_string().getText()
            return Col(None, unquote(raw), raw[:1] in "\"`[")
        if ctx.column_name():                        # table.column
            if ctx.schema_name():
                raise NotSupported("不支援 schema 名稱")
            return Col(unquote(ctx.table_name().getText()), unquote(ctx.column_name().getText()))
        if ctx.expr_recursive():
            return self.visit(ctx.expr_recursive())
        raise NotSupported("不支援子查詢、EXISTS、RAISE")

    def visitExpr_recursive(self, ctx):
        if ctx.function_name():
            if ctx.over_clause() or ctx.filter_clause() or ctx.order_clause() or ctx.percentile_clause():
                raise NotSupported("不支援視窗函數、FILTER、函數內的 ORDER BY")
            name = ctx.function_name().getText().upper()
            args = (Star(),) if ctx.STAR() else tuple(self.visit(e) for e in ctx.expr())
            return Func(name, args, ctx.DISTINCT_() is not None)
        if ctx.CAST_():
            target = column_type(ctx.type_name().getText())
            return Func("CAST", (self.visit(ctx.expr(0)), Lit(target)))
        if ctx.CASE_():
            es = [self.visit(e) for e in ctx.expr()]
            if len(ctx.WHEN_()) * 2 != len(es) - (1 if ctx.ELSE_() else 0):
                raise NotSupported("不支援 CASE x WHEN ...；請寫成 CASE WHEN x = ... THEN ...")
            default = es.pop() if ctx.ELSE_() else None
            return Case(tuple(zip(es[0::2], es[1::2])), default)
        if len(ctx.expr()) == 1:                     # ( expr )
            return self.visit(ctx.expr(0))
        raise NotSupported("不支援 row value (a, b)")

    def visitLiteral_value(self, ctx):
        t = ctx.getText()
        if ctx.NUMERIC_LITERAL():
            if t[:2].lower() == "0x":
                return Lit(int(t, 16))
            return Lit(float(t) if any(c in t for c in ".eE") else int(t))
        if ctx.STRING_LITERAL():
            return Lit(t[1:-1].replace("''", "'"))
        if ctx.NULL_():
            return Lit(None)
        if ctx.TRUE_() or ctx.FALSE_():
            return Lit(1 if t.upper() == "TRUE" else 0)  # 和 SQLite 一樣：TRUE 是 1
        raise NotSupported(f"不支援 {t}")
