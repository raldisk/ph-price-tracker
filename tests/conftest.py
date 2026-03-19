"""
Shared pytest fixtures for ph-price-tracker test suite.

Fixture hierarchy
-----------------
Unit fixtures (no I/O):
  sample_raw_record      → RawPriceRecord with all fields populated
  sample_price_record    → PriceRecord with all fields populated
  multi_price_records    → list[PriceRecord] with 10 items

DuckDB fixtures (tmp file, no server required):
  tmp_db_path            → Path to a temporary DuckDB file in pytest's tmp_path

PostgreSQL fixtures (require live server, guarded by @requires_postgres):
  pg_database_url        → DSN from TRACKER_POSTGRES_DSN env var or CI default
  pg_loader              → PostgreSQLLoader connected to the test database

Markers:
  @pytest.mark.postgres  → skip unless TRACKER_POSTGRES_DSN is set or --run-postgres flag
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from price_tracker.models import PriceRecord, RawPriceRecord


# ── Unit fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_raw_record() -> RawPriceRecord:
    return RawPriceRecord(
        item_id="ITEM001",
        name='Test Laptop 15.6"',
        price="₱25,999",
        original_price="₱32,000",
        brand="TestBrand",
        category="Laptops",
        item_url="https://www.lazada.com.ph/products/test-laptop-i1234567-s9876543.html",
        image_url="https://ph-live.slatic.net/test.jpg",
        rating="4.7",
        review_count="312",
        location="Metro Manila",
        keyword="laptop",
        page=1,
    )


@pytest.fixture
def sample_price_record() -> PriceRecord:
    return PriceRecord(
        item_id="ITEM001",
        name='Test Laptop 15.6"',
        current_price=Decimal("25999"),
        original_price=Decimal("32000"),
        brand="TestBrand",
        category="Laptops",
        item_url="https://www.lazada.com.ph/products/test-laptop-i1234567-s9876543.html",
        rating=4.7,
        review_count=312,
        location="Metro Manila",
        keyword="laptop",
        page=1,
        scraped_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def multi_price_records() -> list[PriceRecord]:
    base = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    return [
        PriceRecord(
            item_id=f"ITEM{i:03d}",
            name=f"Product {i}",
            current_price=Decimal(str(1000 + i * 100)),
            original_price=Decimal(str(1500 + i * 100)),
            brand="BrandA",
            category="Electronics",
            item_url=f"https://www.lazada.com.ph/products/product-{i}.html",
            rating=4.0 + (i % 5) * 0.1,
            review_count=i * 10,
            keyword="smartphone",
            page=1,
            scraped_at=base,
        )
        for i in range(1, 11)
    ]


# ── DuckDB fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_prices.duckdb"


# ── PostgreSQL fixtures ───────────────────────────────────────────────────────

def _pg_dsn() -> str | None:
    """Return the PostgreSQL DSN if available, else None."""
    return os.environ.get(
        "TRACKER_POSTGRES_DSN",
        os.environ.get("DATABASE_URL"),
    )


requires_postgres = pytest.mark.skipif(
    _pg_dsn() is None,
    reason="PostgreSQL not available — set TRACKER_POSTGRES_DSN to run pg tests",
)


@pytest.fixture
def pg_database_url() -> str:
    dsn = _pg_dsn()
    if dsn is None:
        pytest.skip("TRACKER_POSTGRES_DSN not set")
    return dsn


@pytest.fixture
def pg_loader(pg_database_url: str):  # type: ignore[no-untyped-def]
    """
    PostgreSQLLoader connected to the CI test database.
    Cleans up raw.price_snapshots after each test to ensure isolation.
    """
    from price_tracker.loader import PostgreSQLLoader

    with PostgreSQLLoader(database_url=pg_database_url) as loader:
        yield loader
        # Teardown: truncate test data so tests don't bleed into each other
        with loader._conn.cursor() as cur:  # noqa: SLF001
            cur.execute("TRUNCATE TABLE raw.price_snapshots")
        loader._conn.commit()
