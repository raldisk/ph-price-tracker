"""
Configuration management via pydantic-settings.
All values can be overridden with environment variables or a .env file.
Prefix: TRACKER_
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRACKER_",
        extra="ignore",
    )

    # --- Backend selection ------------------------------------------------
    # "duckdb"     → DuckDBLoader (primary: OLAP, embedded, fast analytical scans)
    # "postgresql" → PostgreSQLLoader (CI/integration only: validates SQL portability)
    db_backend: str = Field(
        default="duckdb",
        description="Warehouse backend. 'duckdb' (default) or 'postgresql'.",
    )

    # --- DuckDB -----------------------------------------------------------
    db_path: Path = Field(
        default=Path("data/prices.duckdb"),
        description="Path to the DuckDB warehouse file.",
    )

    # --- PostgreSQL (CI/integration only) ---------------------------------
    postgres_dsn: str = Field(
        default="postgresql://tracker:tracker@localhost:5432/tracker",
        description="PostgreSQL DSN. Only used when db_backend='postgresql'.",
    )

    # --- Scraper ----------------------------------------------------------
    request_timeout: int = Field(default=30, description="HTTP timeout in seconds.")
    max_retries: int = Field(default=3, description="Max retry attempts per request.")
    retry_base_delay: float = Field(
        default=2.0, description="Base delay (seconds) for exponential backoff."
    )
    rate_limit_delay: float = Field(
        default=1.5, description="Polite delay between requests (seconds)."
    )

    # --- Pipeline ---------------------------------------------------------
    keywords: list[str] = Field(
        default=[
            "laptop",
            "smartphone",
            "headphones",
            "gaming monitor",
            "mechanical keyboard",
        ],
        description="Search keywords to track across Lazada PH.",
    )
    max_pages_per_keyword: int = Field(
        default=3,
        description="Max result pages to fetch per keyword.",
    )

    # --- User-agent pool --------------------------------------------------
    user_agents: list[str] = Field(
        default=[
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ],
    )


settings = Settings()
