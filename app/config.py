from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://analytics_owner:change-this-owner-password@localhost:5432/analytics_agent",
    )
    analytics_read_url: str = os.getenv(
        "ANALYTICS_READ_URL",
        "postgresql+psycopg://analytics_reader:change-this-reader-password@localhost:5432/analytics_agent",
    )
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    analytics_schema: str = os.getenv("ANALYTICS_SCHEMA", "analytics")
    analytics_allowed_tables: tuple[str, ...] = _csv_env(
        "ANALYTICS_ALLOWED_TABLES",
        "categories,customers,products,orders,order_items,payments,refunds",
    )
    business_glossary_file: Path = Path(os.getenv("BUSINESS_GLOSSARY_FILE", "config/business_glossary.md"))
    seed_demo_data: bool = _bool_env("SEED_DEMO_DATA", True)
    query_timeout_ms: int = int(os.getenv("QUERY_TIMEOUT_MS", "5000"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "200"))
    query_rate_limit_per_minute: int = int(os.getenv("QUERY_RATE_LIMIT_PER_MINUTE", "20"))
    app_username: str = os.getenv("APP_USERNAME", "analyst")
    app_role: str = os.getenv("APP_ROLE", "admin")
    app_password: str = os.getenv("APP_PASSWORD", "change-this-app-password")
    allow_weak_local_password: bool = _bool_env("ALLOW_WEAK_LOCAL_PASSWORD")
    session_secret: str = os.getenv("SESSION_SECRET", "change-this-session-secret")
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    cookie_secure: bool = _bool_env("COOKIE_SECURE")
    admin_import_enabled: bool = _bool_env("ADMIN_IMPORT_ENABLED", True)
    max_import_bytes: int = int(os.getenv("MAX_IMPORT_BYTES", str(10 * 1024 * 1024)))
    max_import_rows: int = int(os.getenv("MAX_IMPORT_ROWS", "100000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
