from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.database import execute_read_only
from app.schema import schema_description
from app.sql_safety import UnsafeSQL, validate_and_limit

logger = logging.getLogger(__name__)

RUN_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": "Execute one read-only PostgreSQL analytics query.",
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "One SELECT or WITH query."}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
}


class AgentError(RuntimeError):
    def __init__(self, message: str, sql: str | None = None, attempts: int = 0):
        super().__init__(message)
        self.sql = sql
        self.attempts = attempts


def client() -> OpenAI:
    if not settings.deepseek_api_key:
        raise AgentError("尚未配置 DEEPSEEK_API_KEY，请先编辑 .env")
    return OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, timeout=30)


def model_options() -> dict[str, Any]:
    return {
        "model": settings.deepseek_model,
        "extra_body": {"thinking": {"type": "disabled"}},
    }


def call_model(llm: OpenAI, **kwargs):
    try:
        return llm.chat.completions.create(**model_options(), **kwargs)
    except APIStatusError as exc:
        raise AgentError(f"模型服务请求失败（HTTP {exc.status_code}），请检查模型、额度或账号权限") from exc
    except APIConnectionError as exc:
        raise AgentError("无法连接模型服务，请检查网络和代理") from exc


def run_agent(question: str) -> dict[str, Any]:
    validate_question(question)
    llm = client()
    system = (
        "你是电商 SQL 数据分析 Agent。必须调用 run_sql 获取真实数据，不能编造结果。"
        "只生成 PostgreSQL SELECT/WITH，一次一条，不得访问给定 schema 之外的对象。"
        "字段不确定时以 schema 为准。金额保留两位小数，趋势结果按时间升序。"
        "如果工具返回错误，修正 SQL 后最多再调用一次。\n\n"
        f"{schema_description()}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    attempts = 0
    last_sql: str | None = None
    last_error: str | None = None

    while attempts < 2:
        response = call_model(
            llm,
            messages=messages,
            tools=[RUN_SQL_TOOL],
            tool_choice={"type": "function", "function": {"name": "run_sql"}},
            temperature=0,
        )
        message = response.choices[0].message
        calls = message.tool_calls or []
        if not calls:
            raise AgentError("模型没有生成 SQL 工具调用", last_sql, attempts)

        call = calls[0]
        attempts += 1
        try:
            arguments = json.loads(call.function.arguments)
            candidate = str(arguments["sql"]).strip()
            normalized, executable = validate_and_limit(candidate)
            last_sql = normalized
            columns, rows, execution_ms = execute_read_only(executable)
            summary = summarize(llm, question, normalized, columns, rows)
            return {
                "sql": normalized,
                "columns": columns,
                "rows": rows,
                "summary": summary,
                "chart": choose_chart(columns, rows),
                "execution_ms": execution_ms,
                "attempts": attempts,
            }
        except (KeyError, TypeError, ValueError, UnsafeSQL, DBAPIError) as exc:
            last_error = clean_error(exc)
            logger.info("SQL attempt %s rejected: %s", attempts, last_error)
            if attempts >= 2:
                break
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": "run_sql", "arguments": call.function.arguments},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": last_error}, ensure_ascii=False)},
                ]
            )

    raise AgentError(f"SQL 执行失败：{last_error or '未知错误'}", last_sql, attempts)


def summarize(llm: OpenAI, question: str, sql: str, columns: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "查询成功，但当前条件下没有匹配数据。"
    sample = {"columns": columns, "rows": rows[:50], "total_returned_rows": len(rows)}
    try:
        response = call_model(
            llm,
            messages=[
                {
                    "role": "system",
                    "content": "根据真实 SQL 结果给出两到四句简洁中文分析。不得添加结果中没有的数据，说明关键数值和趋势。",
                },
                {
                    "role": "user",
                    "content": f"问题：{question}\nSQL：{sql}\n结果：{json.dumps(sample, ensure_ascii=False)}",
                },
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or f"查询成功，共返回 {len(rows)} 行。"
    except Exception:
        logger.exception("summary generation failed")
        return f"查询成功，共返回 {len(rows)} 行；摘要生成暂时失败，请查看数据表。"


def choose_chart(columns: list[str], rows: list[list[object]]) -> dict[str, Any] | None:
    if not rows or len(columns) < 2:
        return None
    numeric_indexes = [
        index
        for index in range(len(columns))
        if any(isinstance(row[index], (int, float)) and not isinstance(row[index], bool) for row in rows)
    ]
    if not numeric_indexes:
        return None
    y_index = numeric_indexes[-1]
    label_indexes = [
        index
        for index in range(len(columns))
        if index != y_index
        and not columns[index].lower().endswith("_id")
        and any(not isinstance(row[index], (int, float)) for row in rows)
    ]
    x_index = label_indexes[0] if label_indexes else next(
        (index for index in range(len(columns)) if index != y_index), None
    )
    if x_index is None:
        return None
    x_name = columns[x_index]
    chart_type = "line" if any(word in x_name.lower() for word in ("date", "month", "day", "week", "year", "time")) else "bar"
    return {"type": chart_type, "x": x_name, "y": columns[y_index], "title": f"{columns[y_index]} 按 {x_name}"}


def validate_question(question: str) -> None:
    lowered = question.lower()
    sensitive_objects = ("pg_catalog", "information_schema", "app.", "query_traces", "pg_roles")
    destructive = re.compile(
        r"\b(delete|update|insert|drop|truncate|alter|grant|revoke|copy)\b|"
        r"(删除|删掉|清空|写入|插入|建表|删表|授权)|"
        r"(更新|修改).{0,4}(为|成)"
    )
    if any(value in lowered for value in sensitive_objects) or destructive.search(lowered):
        raise AgentError("请求包含写入、越权或系统对象访问意图，已拒绝执行")


def clean_error(exc: Exception) -> str:
    text = str(getattr(exc, "orig", exc)).replace("\n", " ").strip()
    return text[:500]
