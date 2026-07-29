from __future__ import annotations

import csv
import io
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import AgentError, run_agent
from app.config import settings
from app.database import get_session, init_database, reader_engine
from app.importing import (
    ImportValidationError,
    TABLE_SPECS,
    parse_dataset_archive,
    parse_import,
    preview_rows,
    replace_dataset,
    table_metadata,
    upsert_rows,
    validate_rows,
)
from app.models import ImportJob, QueryTrace
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


app = FastAPI(title="SQL Analytics Agent", version="2.1.0", lifespan=lifespan)
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


def admin_user(username: str = Depends(current_user)) -> str:
    if settings.app_role != "admin" or not settings.admin_import_enabled:
        raise HTTPException(status_code=403, detail="需要管理员权限")
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


def import_public(job: ImportJob) -> dict:
    return {
        "id": job.id,
        "filename": job.filename,
        "target_table": job.target_table,
        "row_count": job.row_count,
        "status": job.status,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


async def read_import_file(file: UploadFile) -> tuple[str, bytes]:
    safe_name = re.split(r"[/\\]", file.filename or "upload")[-1]
    content = await file.read(settings.max_import_bytes + 1)
    await file.close()
    if len(content) > settings.max_import_bytes:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_import_bytes // 1024 // 1024} MB")
    return safe_name, content


def parsed_rows(table_name: str, filename: str, content: bytes) -> list[dict]:
    try:
        headers, raw_rows = parse_import(filename, content)
        return validate_rows(table_name, headers, raw_rows)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    return {"user": {"username": payload.username, "role": settings.app_role}}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
def me(username: str = Depends(current_user)) -> dict:
    return {"user": {"username": username, "role": settings.app_role}}


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


@app.get("/api/admin/import/tables")
def import_tables(_: str = Depends(admin_user)) -> dict:
    return {
        "tables": table_metadata(),
        "formats": [".csv", ".xlsx"],
        "max_bytes": settings.max_import_bytes,
        "max_rows": settings.max_import_rows,
        "recommended_order": list(TABLE_SPECS),
    }


@app.get("/api/admin/import/template/{table_name}")
def import_template(table_name: str, _: str = Depends(admin_user)) -> Response:
    spec = TABLE_SPECS.get(table_name)
    if spec is None:
        raise HTTPException(status_code=404, detail="目标表不存在")
    output = io.StringIO()
    csv.writer(output).writerow(spec.columns)
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{table_name}-template.csv"'},
    )


@app.post("/api/admin/import/preview")
async def import_preview(
    target_table: str = Form(...),
    file: UploadFile = File(...),
    _: str = Depends(admin_user),
) -> dict:
    filename, content = await read_import_file(file)
    rows = parsed_rows(target_table, filename, content)
    return {
        "filename": filename,
        "target_table": target_table,
        "row_count": len(rows),
        "columns": list(TABLE_SPECS[target_table].columns),
        "preview": preview_rows(rows),
    }


@app.post("/api/admin/import/execute")
async def import_execute(
    target_table: str = Form(...),
    file: UploadFile = File(...),
    username: str = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict:
    filename, content = await read_import_file(file)
    rows = parsed_rows(target_table, filename, content)
    job = ImportJob(
        user_name=username,
        filename=filename,
        target_table=target_table,
        row_count=0,
        status="running",
    )
    session.add(job)
    session.commit()
    try:
        upsert_rows(session, target_table, rows)
        job.status = "success"
        job.row_count = len(rows)
        session.commit()
        return {"import": import_public(job)}
    except IntegrityError as exc:
        session.rollback()
        job = session.get(ImportJob, job.id)
        job.status = "failed"
        job.error = "外键、唯一性或字段约束不满足"
        session.commit()
        raise HTTPException(status_code=409, detail=f"导入失败：{job.error}") from exc
    except Exception as exc:
        session.rollback()
        job = session.get(ImportJob, job.id)
        job.status = "failed"
        job.error = str(exc)[:500]
        session.commit()
        raise


@app.post("/api/admin/import/dataset/preview")
async def dataset_preview(
    file: UploadFile = File(...),
    _: str = Depends(admin_user),
) -> dict:
    filename, content = await read_import_file(file)
    try:
        dataset = parse_dataset_archive(filename, content)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "filename": filename,
        "tables": [{"name": name, "row_count": len(rows)} for name, rows in dataset.items()],
        "total_rows": sum(len(rows) for rows in dataset.values()),
    }


@app.post("/api/admin/import/dataset/replace")
async def dataset_replace(
    confirmation: str = Form(...),
    file: UploadFile = File(...),
    username: str = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict:
    if confirmation != "REPLACE":
        raise HTTPException(status_code=422, detail="必须明确确认替换整套分析数据")
    filename, content = await read_import_file(file)
    try:
        dataset = parse_dataset_archive(filename, content)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = ImportJob(
        user_name=username,
        filename=filename,
        target_table="all (replace)",
        row_count=0,
        status="running",
    )
    session.add(job)
    session.commit()
    try:
        replace_dataset(session, dataset)
        job.status = "success"
        job.row_count = sum(len(rows) for rows in dataset.values())
        session.commit()
        return {"import": import_public(job)}
    except IntegrityError as exc:
        session.rollback()
        job = session.get(ImportJob, job.id)
        job.status = "failed"
        job.error = "整套数据的外键、唯一性或字段约束不满足，原数据未改变"
        session.commit()
        raise HTTPException(status_code=409, detail=f"替换失败：{job.error}") from exc
    except Exception as exc:
        session.rollback()
        job = session.get(ImportJob, job.id)
        job.status = "failed"
        job.error = str(exc)[:500]
        session.commit()
        raise


@app.get("/api/admin/import/history")
def import_history(
    limit: int = 20,
    _: str = Depends(admin_user),
    session: Session = Depends(get_session),
) -> dict:
    safe_limit = min(max(limit, 1), 100)
    jobs = session.scalars(
        select(ImportJob).order_by(ImportJob.created_at.desc()).limit(safe_limit)
    ).all()
    return {"imports": [import_public(job) for job in jobs]}


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
