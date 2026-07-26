from __future__ import annotations

import time
from collections.abc import Generator
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

owner_engine = create_engine(settings.database_url, pool_pre_ping=True)
reader_engine = create_engine(settings.analytics_read_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=owner_engine, expire_on_commit=False)


def init_database(max_wait_seconds: int = 45) -> None:
    deadline = time.monotonic() + max_wait_seconds
    while True:
        try:
            with owner_engine.begin() as connection:
                connection.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
                connection.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
            Base.metadata.create_all(owner_engine)
            with owner_engine.begin() as connection:
                connection.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader"))
                connection.execute(text("REVOKE ALL ON SCHEMA app FROM analytics_reader"))
            return
        except OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def execute_read_only(sql: str) -> tuple[list[str], list[list[object]], float]:
    started = time.perf_counter()
    with reader_engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text(f"SET LOCAL statement_timeout = {settings.query_timeout_ms}"))
            result = connection.execute(text(sql))
            columns = list(result.keys())
            rows = [[json_value(value) for value in row] for row in result.fetchall()]
    return columns, rows, round((time.perf_counter() - started) * 1000, 2)


def json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

