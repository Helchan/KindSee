from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .base import EmptyPositionIndex, ParseResult, TreeNode
from ..sql_keywords import SQL_KEYWORDS

try:
    import sqlglot
    from sqlglot.errors import ParseError as SqlGlotParseError
except ImportError:
    sqlglot = None

    class SqlGlotParseError(Exception):
        pass


MAX_SQL_CHECK_CHARS = 500_000
SQLGLOT_DIALECT = "mysql"
SQL_CONTENT_RE = re.compile(
    r"\b(?:select|insert|update|delete|create|alter|drop|with|merge|truncate)\b"
    r".*\b(?:from|into|set|table|view|database|values|as)\b",
    re.IGNORECASE | re.DOTALL,
)
NUMBER_LITERAL_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
LINE_BREAK_BEFORE = {"from", "where", "group", "having", "order", "limit", "union", "join", "left", "right", "inner", "outer", "set", "values"}
CLAUSE_KEYWORDS = {"from", "where", "group", "having", "order", "limit", "union", "join", "left", "right", "inner", "outer", "set", "values"}
EXPRESSION_CONNECTORS = {"and", "or"}
EXPRESSION_WORD_OPERATORS = {"between", "in", "is", "like", "not"}
EXPRESSION_SYMBOL_OPERATORS = {"=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", "%"}
SYMBOL_TOKENS = {"(", ")", ",", ";", ".", "=", "<", ">", "<=", ">=", "<>", "!=", "+", "-", "*", "/", "%"}


@dataclass(frozen=True)
class SqlToken:
    value: str
    kind: str
    start: int
    line: int
    column: int


class BasicSqlSyntaxValidator:
    def validate(self, text: str) -> str:
        error = _check_sql_balance(text)
        if error:
            return error
        return _check_sql_statement_shape(text)


class SqlGlotSyntaxValidator:
    def available(self) -> bool:
        return sqlglot is not None

    def validate(self, text: str) -> str:
        if sqlglot is None:
            return BasicSqlSyntaxValidator().validate(text)
        try:
            sqlglot.parse(text, read=SQLGLOT_DIALECT)
        except SqlGlotParseError as exc:
            return _sqlglot_error_message(exc)
        except Exception as exc:
            return f"语法错误：{exc}"
        return ""

    def format_text(self, text: str, uppercase_keywords: bool = True) -> str:
        if sqlglot is None:
            return _format_sql_text(text, uppercase_keywords=uppercase_keywords)
        formatted = _sqlglot_transpile_pretty(text, uppercase_keywords)
        statements = [_apply_keyword_case(item.rstrip(";"), uppercase_keywords) for item in formatted if item.strip()]
        result = ";\n\n".join(statements)
        if result and text.strip().endswith(";"):
            result += ";"
        return _separate_formatted_statements(result)


class SqlDocumentType:
    type_id = "sql"
    display_name = "SQL 文件"
    default_extension = ".sql"
    file_dialog_patterns = ("*.sql",)
    view_mode = "text"
    parse_on_change = True
    supports_format = True
    supports_compact = False
    empty_status = "请输入 SQL 内容"

    def matches_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".sql"

    def matches_content(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped or len(stripped) > MAX_SQL_CHECK_CHARS:
            return False
        return bool(SQL_CONTENT_RE.search(stripped))

    def parse(self, text: str) -> ParseResult:
        if not text.strip():
            return ParseResult(None, EmptyPositionIndex(), self.empty_status, False)
        if len(text) > MAX_SQL_CHECK_CHARS:
            return ParseResult(None, EmptyPositionIndex(), "", False)
        error = _check_token_quality(_sql_tokens(text))
        if not error:
            error = SqlGlotSyntaxValidator().validate(text)
        if error:
            return ParseResult(None, EmptyPositionIndex(), error, True)
        return ParseResult(None, EmptyPositionIndex(), "", False)

    def format_text(self, text: str, uppercase_keywords: bool = True) -> str:
        result = self.parse(text)
        if result.error:
            raise ValueError(result.status)
        return SqlGlotSyntaxValidator().format_text(text, uppercase_keywords=uppercase_keywords)

    def compact_text(self, text: str) -> str:
        raise ValueError("SQL 文件暂不支持压缩")

    def copy_node(self, node: TreeNode) -> str:
        return ""

    def copy_node_value(self, node: TreeNode) -> str:
        return ""

    def copy_node_path(self, node: TreeNode) -> str:
        return ""


def _check_sql_balance(text: str) -> str:
    stack: list[tuple[str, int, int]] = []
    pairs = {"(": ")", "[": "]"}
    closers = {value: key for key, value in pairs.items()}
    line = 1
    column = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if ch == "-" and nxt == "-":
            i, line, column = _skip_line_comment(text, i, line, column)
            continue
        if ch == "/" and nxt == "*":
            skipped = _skip_block_comment(text, i, line, column)
            if skipped is None:
                return f"语法错误：第 {line} 行，第 {column} 列，块注释未闭合"
            i, line, column = skipped
            continue
        if ch in ("'", '"', "`"):
            skipped = _skip_quoted(text, i, line, column, ch)
            if skipped is None:
                return f"语法错误：第 {line} 行，第 {column} 列，字符串未闭合"
            i, line, column = skipped
            continue
        if ch == "[":
            skipped = _skip_bracket_identifier(text, i, line, column)
            if skipped is None:
                return f"语法错误：第 {line} 行，第 {column} 列，方括号标识符未闭合"
            i, line, column = skipped
            continue
        if ch in pairs:
            stack.append((ch, line, column))
        elif ch in closers:
            if not stack or stack[-1][0] != closers[ch]:
                return f"语法错误：第 {line} 行，第 {column} 列，括号不匹配"
            stack.pop()
        i += 1
        column += 1
    if stack:
        opener, opener_line, opener_column = stack[-1]
        return f"语法错误：第 {opener_line} 行，第 {opener_column} 列，'{opener}' 未闭合"
    return ""


def _check_sql_statement_shape(text: str) -> str:
    tokens = _sql_tokens(text)
    if not tokens:
        return ""
    error = _check_token_quality(tokens)
    if error:
        return error
    statements = _split_statements(tokens)
    for statement in statements:
        if not statement:
            continue
        first = statement[0].value.lower()
        if first == "select":
            error = _check_select_statement(statement)
        elif first == "insert":
            error = _require_keyword(statement, "into", "INSERT 语句缺少 INTO")
        elif first == "update":
            error = _require_keyword(statement, "set", "UPDATE 语句缺少 SET")
        elif first == "delete":
            error = _require_keyword(statement, "from", "DELETE 语句缺少 FROM")
        else:
            error = ""
        if error:
            return error
    return ""


def _check_select_statement(tokens: list[SqlToken]) -> str:
    from_index = _find_top_level_keyword(tokens, "from", 1)
    if from_index < 0:
        for token in tokens[1:]:
            lower = token.value.lower()
            if token.kind == "word" and lower.startswith("from") and lower != "from":
                return _syntax_message(token, "SELECT 查询字段后应使用 FROM 关键字")
        return _syntax_message(tokens[-1], "SELECT 语句缺少 FROM")
    if from_index == 1:
        return _syntax_message(tokens[from_index], "SELECT 语句缺少查询字段")
    if from_index + 1 >= len(tokens) or tokens[from_index + 1].value == ";":
        return _syntax_message(tokens[from_index], "FROM 后缺少表名")
    for token in tokens[1:from_index]:
        lower = token.value.lower()
        if token.kind == "word" and lower.startswith("from") and lower != "from":
            return _syntax_message(token, "SELECT 查询字段后应使用 FROM 关键字")
    where_index = _find_top_level_keyword(tokens, "where", from_index + 1)
    if where_index >= 0:
        where_end = _find_next_clause_index(tokens, where_index + 1, {"group", "having", "order", "limit", "union"})
        error = _check_expression(tokens[where_index + 1 : where_end], "WHERE")
        if error:
            return error
    return ""


def _check_token_quality(tokens: list[SqlToken]) -> str:
    for token in tokens:
        if token.kind == "number" and not NUMBER_LITERAL_RE.fullmatch(token.value):
            return _syntax_message(token, "数字字面量不合法")
        if token.kind == "symbol" and token.value not in SYMBOL_TOKENS:
            return _syntax_message(token, "无法识别的 SQL 符号")
    return ""


def _check_expression(tokens: list[SqlToken], clause_name: str) -> str:
    if not tokens:
        return _syntax_message(SqlToken(clause_name, "word", 0, 1, 1), f"{clause_name} 后缺少条件")
    expect_operand = True
    depth = 0
    previous_operand: SqlToken | None = None
    for token in tokens:
        lower = token.value.lower()
        if expect_operand:
            if token.value == "(":
                depth += 1
                previous_operand = None
                continue
            if lower == "not":
                previous_operand = None
                continue
            if token.value == ")":
                return _syntax_message(token, f"{clause_name} 条件缺少表达式")
            if _is_expression_operator(token) or lower in EXPRESSION_CONNECTORS:
                return _syntax_message(token, f"{clause_name} 条件缺少操作数")
            if token.kind in {"word", "number", "string"}:
                expect_operand = False
                previous_operand = token
                continue
            return _syntax_message(token, f"{clause_name} 条件包含无法识别的表达式")
        if token.value == ")":
            if depth <= 0:
                return _syntax_message(token, f"{clause_name} 条件括号不匹配")
            depth -= 1
            previous_operand = token
            continue
        if _is_expression_operator(token):
            expect_operand = True
            previous_operand = None
            continue
        if lower in EXPRESSION_CONNECTORS:
            expect_operand = True
            previous_operand = None
            continue
        if token.kind in {"word", "number", "string"}:
            message = f"{clause_name} 条件缺少运算符或逻辑连接符"
            if previous_operand and previous_operand.kind == "number" and token.kind == "word":
                message = f"{clause_name} 条件中数字和标识符之间缺少运算符"
            return _syntax_message(token, message)
        return _syntax_message(token, f"{clause_name} 条件包含无法识别的表达式")
    if expect_operand:
        return _syntax_message(tokens[-1], f"{clause_name} 条件缺少操作数")
    if depth > 0:
        return _syntax_message(tokens[-1], f"{clause_name} 条件括号未闭合")
    return ""


def _is_expression_operator(token: SqlToken) -> bool:
    return token.value in EXPRESSION_SYMBOL_OPERATORS or token.value.lower() in EXPRESSION_WORD_OPERATORS


def _require_keyword(tokens: list[SqlToken], keyword: str, message: str) -> str:
    if _find_top_level_keyword(tokens, keyword, 1) >= 0:
        return ""
    return _syntax_message(tokens[0], message)


def _find_top_level_keyword(tokens: list[SqlToken], keyword: str, start: int) -> int:
    depth = 0
    for index, token in enumerate(tokens[start:], start):
        if token.value == "(":
            depth += 1
        elif token.value == ")" and depth > 0:
            depth -= 1
        elif depth == 0 and token.value.lower() == keyword:
            return index
    return -1


def _find_next_clause_index(tokens: list[SqlToken], start: int, keywords: set[str]) -> int:
    depth = 0
    for index, token in enumerate(tokens[start:], start):
        if token.value == "(":
            depth += 1
        elif token.value == ")" and depth > 0:
            depth -= 1
        elif depth == 0 and token.kind == "word" and token.value.lower() in keywords:
            return index
    return len(tokens)


def _split_statements(tokens: list[SqlToken]) -> list[list[SqlToken]]:
    statements: list[list[SqlToken]] = []
    current: list[SqlToken] = []
    depth = 0
    for token in tokens:
        if token.value == "(":
            depth += 1
        elif token.value == ")" and depth > 0:
            depth -= 1
        if token.value == ";" and depth == 0:
            if current:
                statements.append(current)
                current = []
            continue
        current.append(token)
    if current:
        statements.append(current)
    return statements


def _syntax_message(token: SqlToken, message: str) -> str:
    return f"语法错误：第 {token.line} 行，第 {token.column} 列，{message}"


def _sqlglot_error_message(exc: SqlGlotParseError) -> str:
    errors = getattr(exc, "errors", None)
    if errors:
        first = errors[0]
        line = first.get("line") or 1
        column = first.get("col") or first.get("column") or 1
        description = first.get("description") or str(exc)
        return f"语法错误：第 {line} 行，第 {column} 列，{description}"
    return f"语法错误：{exc}"


def _sqlglot_transpile_pretty(text: str, uppercase_keywords: bool) -> list[str]:
    kwargs = {
        "read": SQLGLOT_DIALECT,
        "write": SQLGLOT_DIALECT,
        "pretty": True,
        "normalize": uppercase_keywords,
    }
    try:
        return sqlglot.transpile(text, **kwargs)
    except TypeError:
        kwargs.pop("normalize", None)
        return sqlglot.transpile(text, **kwargs)


def _format_sql_text(text: str, uppercase_keywords: bool = True) -> str:
    tokens = _sql_tokens(text, include_comments=True)
    if not tokens:
        return ""
    lines: list[str] = []
    current = ""
    indent = 0
    previous = ""
    for token in tokens:
        value = _format_token_value(token, uppercase_keywords)
        lower = token.value.lower()
        if token.kind == "comment":
            if current.strip():
                lines.append(current.rstrip())
                current = ""
            lines.append(("  " * indent) + value)
            previous = token.value
            continue
        if value == ";":
            current = current.rstrip() + ";"
            lines.append(current.rstrip())
            lines.append("")
            current = ""
            previous = value
            continue
        if lower in LINE_BREAK_BEFORE and current.strip():
            lines.append(current.rstrip())
            current = "  " * indent
        if value == "(":
            current = _append_sql_part(current, value, previous)
            indent += 1
            previous = value
            continue
        if value == ")":
            indent = max(0, indent - 1)
            current = current.rstrip() + ")"
            previous = value
            continue
        if value == ",":
            current = current.rstrip() + ","
            lines.append(current.rstrip())
            current = "  " * indent
            previous = value
            continue
        if not current:
            current = "  " * indent
        current = _append_sql_part(current, value, previous)
        previous = value
    if current.strip():
        lines.append(current.rstrip())
    return _separate_formatted_statements("\n".join(lines))


def _append_sql_part(current: str, value: str, previous: str) -> str:
    if not current or current.endswith((" ", "\n", "(")):
        return current + value
    if value in {".", ")"} or previous == ".":
        return current + value
    return current + " " + value


def _format_token_value(token: SqlToken, uppercase_keywords: bool = True) -> str:
    lower = token.value.lower()
    if token.kind == "word" and lower in SQL_KEYWORDS:
        return lower.upper() if uppercase_keywords else lower
    return token.value


def _apply_keyword_case(text: str, uppercase_keywords: bool) -> str:
    tokens = _sql_tokens(text, include_comments=True)
    if not tokens:
        return text
    parts: list[str] = []
    offset = 0
    for token in tokens:
        parts.append(text[offset : token.start])
        parts.append(_format_token_value(token, uppercase_keywords))
        offset = token.start + len(token.value)
    parts.append(text[offset:])
    return "".join(parts)


def _separate_formatted_statements(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    tokens = _sql_tokens(stripped, include_comments=True)
    if not any(token.value == ";" for token in tokens):
        return stripped
    parts: list[str] = []
    offset = 0
    for token in tokens:
        if token.value != ";":
            continue
        next_offset = _next_nonspace_offset(stripped, token.start + len(token.value))
        if next_offset >= len(stripped):
            continue
        parts.append(stripped[offset : token.start + 1].rstrip())
        parts.append("\n\n")
        offset = next_offset
    parts.append(stripped[offset:].strip())
    return "".join(parts).strip()


def _next_nonspace_offset(text: str, offset: int) -> int:
    while offset < len(text) and text[offset].isspace():
        offset += 1
    return offset


def _sql_tokens(text: str, include_comments: bool = False) -> list[SqlToken]:
    tokens: list[SqlToken] = []
    line = 1
    column = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch in " \t\r":
            i += 1
            column += 1
            continue
        if ch == "\n":
            i += 1
            line += 1
            column = 1
            continue
        if ch == "-" and nxt == "-":
            start, start_line, start_column = i, line, column
            i, line, column = _skip_line_comment(text, i, line, column)
            if include_comments:
                tokens.append(SqlToken(text[start:i], "comment", start, start_line, start_column))
            continue
        if ch == "/" and nxt == "*":
            start, start_line, start_column = i, line, column
            skipped = _skip_block_comment(text, i, line, column)
            if skipped is None:
                tokens.append(SqlToken(text[start:], "comment", start, start_line, start_column))
                break
            i, line, column = skipped
            if include_comments:
                tokens.append(SqlToken(text[start:i], "comment", start, start_line, start_column))
            continue
        if ch in ("'", '"', "`"):
            start, start_line, start_column = i, line, column
            skipped = _skip_quoted(text, i, line, column, ch)
            i, line, column = skipped if skipped is not None else (n, line, column + n - i)
            tokens.append(SqlToken(text[start:i], "string", start, start_line, start_column))
            continue
        if ch == "[":
            start, start_line, start_column = i, line, column
            skipped = _skip_bracket_identifier(text, i, line, column)
            i, line, column = skipped if skipped is not None else (n, line, column + n - i)
            tokens.append(SqlToken(text[start:i], "string", start, start_line, start_column))
            continue
        if ch.isalpha() or ch == "_":
            start, start_column = i, column
            i += 1
            column += 1
            while i < n and (text[i].isalnum() or text[i] in "_$"):
                i += 1
                column += 1
            tokens.append(SqlToken(text[start:i], "word", start, line, start_column))
            continue
        if ch.isdigit():
            start, start_column = i, column
            i += 1
            column += 1
            while i < n and (text[i].isalnum() or text[i] in "._"):
                i += 1
                column += 1
            tokens.append(SqlToken(text[start:i], "number", start, line, start_column))
            continue
        start, start_column = i, column
        if ch in "<>!=" and nxt in "=>":
            tokens.append(SqlToken(text[i : i + 2], "symbol", start, line, start_column))
            i += 2
            column += 2
            continue
        tokens.append(SqlToken(ch, "symbol", start, line, start_column))
        i += 1
        column += 1
    return tokens


def _skip_line_comment(text: str, start: int, line: int, column: int) -> tuple[int, int, int]:
    i = start + 2
    column += 2
    while i < len(text) and text[i] != "\n":
        i += 1
        column += 1
    return i, line, column


def _skip_block_comment(text: str, start: int, line: int, column: int) -> tuple[int, int, int] | None:
    i = start + 2
    column += 2
    while i < len(text):
        if text[i] == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if text[i] == "*" and i + 1 < len(text) and text[i + 1] == "/":
            return i + 2, line, column + 2
        i += 1
        column += 1
    return None


def _skip_quoted(text: str, start: int, line: int, column: int, quote: str) -> tuple[int, int, int] | None:
    i = start + 1
    column += 1
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if ch == quote:
            if nxt == quote:
                i += 2
                column += 2
                continue
            return i + 1, line, column + 1
        i += 1
        column += 1
    return None


def _skip_bracket_identifier(text: str, start: int, line: int, column: int) -> tuple[int, int, int] | None:
    i = start + 1
    column += 1
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch == "\n":
            line += 1
            column = 1
            i += 1
            continue
        if ch == "]":
            if nxt == "]":
                i += 2
                column += 2
                continue
            return i + 1, line, column + 1
        i += 1
        column += 1
    return None
