from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agent import AgentError, run_agent
from app.config import settings
from app.database import get_session, init_database, reader_engine
from app.models import Order, QueryTrace
from app.schema import public_schema
from app.seed import seed_if_empty

logging.basicConfig(
    level=settings.log_level,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    seed_if_empty()
    yield


app = FastAPI(title="SQL Analytics Agent", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class QueryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/analytics/schema")
def schema() -> dict:
    return public_schema()


@app.post("/api/analytics/query")
def analytics_query(payload: QueryRequest, session: Session = Depends(get_session)) -> dict:
    trace = QueryTrace(question=payload.question.strip(), status="running", attempts=0, row_count=0)
    session.add(trace)
    session.commit()
    try:
        result = run_agent(trace.question)
        trace.generated_sql = result["sql"]
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
        code = 503 if "DEEPSEEK_API_KEY" in str(exc) else 422
        raise HTTPException(status_code=code, detail={"message": str(exc), "trace_id": trace.id}) from exc
    except Exception as exc:
        logger.exception("analytics query failed")
        trace.status = "failed"
        trace.error = str(exc)[:1000]
        session.commit()
        raise HTTPException(status_code=500, detail={"message": "查询服务暂时不可用", "trace_id": trace.id}) from exc


@app.get("/api/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    with reader_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    order_count = session.scalar(select(func.count(Order.id))) or 0
    return {
        "status": "ok",
        "database": "ok",
        "read_only_database": "ok",
        "deepseek_configured": bool(settings.deepseek_api_key),
        "orders": order_count,
    }

