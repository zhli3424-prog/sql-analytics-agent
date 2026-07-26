from __future__ import annotations

import os
from dataclasses import dataclass


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
    query_timeout_ms: int = int(os.getenv("QUERY_TIMEOUT_MS", "5000"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "200"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()

