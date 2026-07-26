from __future__ import annotations

from sqlglot import exp, parse
from sqlglot.errors import ParseError

from app.config import settings
from app.schema import ALLOWED_TABLES

DENIED_NODES = (
    exp.Alter,
    exp.Command,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Merge,
    exp.Update,
)
DENIED_FUNCTIONS = {"pg_sleep", "pg_read_file", "pg_read_binary_file", "dblink"}


class UnsafeSQL(ValueError):
    pass


def validate_and_limit(sql: str) -> tuple[str, str]:
    try:
        statements = [statement for statement in parse(sql, read="postgres") if statement is not None]
    except ParseError as exc:
        raise UnsafeSQL(f"SQL 语法错误：{exc}") from exc

    if len(statements) != 1:
        raise UnsafeSQL("只允许一条 SQL 语句")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeSQL("只允许 SELECT 或 WITH 查询")
    if any(statement.find(node) is not None for node in DENIED_NODES):
        raise UnsafeSQL("检测到写入或结构变更语句")

    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        name = table.name.lower()
        schema = (table.db or "").lower()
        if name in cte_names:
            continue
        if name not in ALLOWED_TABLES or schema not in {"", settings.analytics_schema.lower()}:
            raise UnsafeSQL(f"无权访问表：{table.sql(dialect='postgres')}")

    for function in statement.find_all(exp.Func):
        function_name = str(getattr(function, "name", "") or function.sql_name()).lower()
        if function_name in DENIED_FUNCTIONS:
            raise UnsafeSQL(f"禁止调用函数：{function_name}")

    normalized = statement.sql(dialect="postgres")
    limited = f"SELECT * FROM ({normalized}) AS agent_result LIMIT {settings.max_result_rows}"
    return normalized, limited
