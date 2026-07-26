from __future__ import annotations

import csv
import io
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agent import AgentError, run_agent
from app.config import settings
from app.database import get_session, init_database, reader_engine
from app.models import QueryTrace
from app.schema import catalog, public_schema, validate_data_source_config
from app.security import COOKIE_NAME, create_session, read_session, validate_security_config, verify_login
from app.seed import seed_if_empty

logging.basicConfig(
    level=settings.log_level,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
rate_buckets: dict[str, deque[float]] = defaultdict(deque)
rate_lock = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_security_config()
    validate_data_source_config()
    init_database()
    if settings.seed_demo_data:
        seed_if_empty()
    catalog()
    yield


app = FastAPI(title="SQL Analytics Agent", version="2.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


def current_user(session_token: str | None = Cookie(default=None, alias=COOKIE_NAME)) -> str:
    username = read_session(session_token) if session_token else None
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return username


def query_user(username: str = Depends(current_user)) -> str:
    now = time.monotonic()
    with rate_lock:
        bucket = rate_buckets[username]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= settings.query_rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="查询过于频繁，请一分钟后再试")
        bucket.append(now)
    return username


def owned_trace(trace_id: int, username: str, session: Session) -> QueryTrace:
    trace = session.scalar(
        select(QueryTrace).where(QueryTrace.id == trace_id, QueryTrace.user_name == username)
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="查询记录不存在")
    return trace


def trace_public(trace: QueryTrace, include_result: bool = False) -> dict:
    value = {
        "id": trace.id,
        "question": trace.question,
        "sql": trace.generated_sql,
        "summary": trace.summary,
        "status": trace.status,
        "execution_ms": trace.execution_ms,
        "row_count": trace.row_count,
        "attempts": trace.attempts,
        "error": trace.error,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
    }
    if include_result:
        value["columns"] = trace.result_columns or []
        value["rows"] = trace.result_rows or []
    return value


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict:
    if not verify_login(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    response.set_cookie(
        COOKIE_NAME,
        create_session(payload.username),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )
    return {"user": {"username": payload.username}}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
def me(username: str = Depends(current_user)) -> dict:
    return {"user": {"username": username}}


@app.get("/api/analytics/schema")
def schema(_: str = Depends(current_user)) -> dict:
    return public_schema()


@app.post("/api/analytics/query")
def analytics_query(
    payload: QueryRequest,
    username: str = Depends(query_user),
    session: Session = Depends(get_session),
) -> dict:
    trace = QueryTrace(
        user_name=username,
        question=payload.question.strip(),
        status="running",
        attempts=0,
        row_count=0,
        result_columns=[],
        result_rows=[],
    )
    session.add(trace)
    session.commit()
    try:
        result = run_agent(trace.question)
        trace.generated_sql = result["sql"]
        trace.summary = result["summary"]
        trace.result_columns = result["columns"]
        trace.result_rows = result["rows"]
        trace.status = "success"
        trace.execution_ms = result["execution_ms"]
        trace.row_count = len(result["rows"])
        trace.attempts = result["attempts"]
        session.commit()
        return {**result, "trace_id": trace.id}
    except AgentError as exc:
        trace.generated_sql = exc.sql
        trace.status = "failed"
        trace.attempts = exc.attempts
        trace.error = str(exc)[:1000]
        session.commit()
        code = 503 if "模型服务" in str(exc) or "DEEPSEEK_API_KEY" in str(exc) else 422
        raise HTTPException(status_code=code, detail={"message": str(exc), "trace_id": trace.id}) from exc
    except Exception as exc:
        logger.exception("analytics query failed")
        trace.status = "failed"
        trace.error = str(exc)[:1000]
        session.commit()
        raise HTTPException(
            status_code=500,
            detail={"message": "查询服务暂时不可用，请提供 Trace ID 给管理员", "trace_id": trace.id},
        ) from exc


@app.get("/api/analytics/history")
def history(
    limit: int = 20,
    username: str = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    safe_limit = min(max(limit, 1), 100)
    traces = session.scalars(
        select(QueryTrace)
        .where(QueryTrace.user_name == username)
        .order_by(QueryTrace.created_at.desc())
        .limit(safe_limit)
    ).all()
    return {"history": [trace_public(trace) for trace in traces]}


@app.get("/api/analytics/history/{trace_id}")
def history_detail(
    trace_id: int,
    username: str = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    return {"trace": trace_public(owned_trace(trace_id, username, session), include_result=True)}


@app.get("/api/analytics/history/{trace_id}/csv")
def history_csv(
    trace_id: int,
    username: str = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    trace = owned_trace(trace_id, username, session)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(trace.result_columns or [])
    writer.writerows(trace.result_rows or [])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="sql-agent-trace-{trace.id}.csv"'},
    )


@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    with reader_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
        "read_only_database": "ok",
        "deepseek_configured": bool(settings.deepseek_api_key),
        "analytics_schema": settings.analytics_schema,
        "analytics_tables": len(catalog()),
        "authentication": "enabled",
        "version": app.version,
    }
