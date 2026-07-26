from __future__ import annotations

import re
from functools import lru_cache

from sqlalchemy import inspect

from app.config import settings

IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
ALLOWED_TABLES = set(settings.analytics_allowed_tables)


def validate_data_source_config() -> None:
    identifiers = (settings.analytics_schema, *settings.analytics_allowed_tables)
    if not settings.analytics_allowed_tables or any(not IDENTIFIER.fullmatch(value) for value in identifiers):
        raise RuntimeError("ANALYTICS_SCHEMA and ANALYTICS_ALLOWED_TABLES must contain safe PostgreSQL identifiers")


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    from app.database import reader_engine

    inspector = inspect(reader_engine)
    tables = []
    for table_name in settings.analytics_allowed_tables:
        columns = inspector.get_columns(table_name, schema=settings.analytics_schema)
        if not columns:
            raise RuntimeError(f"Configured analytics table does not exist: {settings.analytics_schema}.{table_name}")
        tables.append(
            {
                "name": table_name,
                "columns": [{"name": column["name"], "type": str(column["type"])} for column in columns],
            }
        )
    return tables


def glossary() -> str:
    path = settings.business_glossary_file
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def schema_description() -> str:
    lines = [f"Only query schema {settings.analytics_schema}.", "", "Tables:"]
    for table in catalog():
        columns = ", ".join(f'{column["name"]} {column["type"]}' for column in table["columns"])
        lines.append(f'{settings.analytics_schema}.{table["name"]}({columns})')
    business_rules = glossary()
    if business_rules:
        lines.extend(["", "Business definitions:", business_rules])
    return "\n".join(lines)


def public_schema() -> dict:
    return {
        "schema": settings.analytics_schema,
        "tables": catalog(),
        "business_glossary": glossary(),
    }
