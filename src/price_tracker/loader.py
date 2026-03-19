"""
Warehouse loader — dual-backend implementation.

Architecture
------------
AbstractWarehouseLoader   base class defining the public contract
DuckDBLoader              primary backend (OLAP, embedded, dev + prod)
PostgreSQLLoader          CI/integration backend (client-server, testing)
get_loader()              factory — selects backend from TRACKER_BACKEND env var

Why dual-backend?
-----------------
DuckDB is the right tool for this workload: columnar storage, embedded
(zero network latency), native Parquet/Arrow support, extremely fast
analytical scans. PostgreSQL is the right tool for CI: it validates that
the schema and SQL are portable, and it exercises the psycopg2 path that
a production multi-user deployment would use.

The key design principle: program to AbstractWarehouseLoader, not to either
concrete implementation. Callers (pipeline.py, tests) depend only on the
three public methods: insert_records(), row_count(), latest_snapshot().
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Any

import polars as pl
from rich.console import Console

from price_tracker.config import settings
from price_tracker.models import PriceRecord

console = Console()

# ── DDL ──────────────────────────────────────────────────────────────────────

_DDL_CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS raw;"

_DDL_CREATE_TABLE_DUCKDB = """
CREATE TABLE IF NOT EXISTS raw.price_snapshots (
    item_id         VARCHAR        NOT NULL,
    name            VARCHAR        NOT NULL,
    current_price   DECIMAL(12,2)  NOT NULL,
    original_price  DECIMAL(12,2),
    discount_pct    DOUBLE,
    brand           VARCHAR,
    category        VARCHAR,
    item_url        VARCHAR        NOT NULL,
    rating          DOUBLE,
    review_count    INTEGER,
    location        VARCHAR,
    keyword         VARCHAR        NOT NULL,
    page            INTEGER        NOT NULL,
    scraped_at      TIMESTAMPTZ    NOT NULL
);
"""

_DDL_CREATE_TABLE_PG = """
CREATE TABLE IF NOT EXISTS raw.price_snapshots (
    item_id         TEXT              NOT NULL,
    name            TEXT              NOT NULL,
    current_price   NUMERIC(12,2)     NOT NULL,
    original_price  NUMERIC(12,2),
    discount_pct    DOUBLE PRECISION,
    brand           TEXT,
    category        TEXT,
    item_url        TEXT              NOT NULL,
    rating          DOUBLE PRECISION,
    review_count    INTEGER,
    location        TEXT,
    keyword         TEXT              NOT NULL,
    page            INTEGER           NOT NULL,
    scraped_at      TIMESTAMPTZ       NOT NULL
);
"""

_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_snapshots_item_id ON raw.price_snapshots (item_id);",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_scraped_at ON raw.price_snapshots (scraped_at);",
]

_LATEST_SNAPSHOT_SQL = """
SELECT DISTINCT ON (item_id)
    item_id, name, current_price, original_price,
    discount_pct, brand, category, scraped_at
FROM raw.price_snapshots
ORDER BY item_id, scraped_at DESC
"""


def _to_row_dicts(records: list[PriceRecord]) -> list[dict[str, Any]]:
    """Convert PriceRecord list to plain dicts suitable for bulk insert."""
    return [
        {
            "item_id": r.item_id,
            "name": r.name,
            "current_price": float(r.current_price),
            "original_price": float(r.original_price) if r.original_price else None,
            "discount_pct": r.discount_pct,
            "brand": r.brand,
            "category": r.category,
            "item_url": r.item_url,
            "rating": r.rating,
            "review_count": r.review_count,
            "location": r.location,
            "keyword": r.keyword,
            "page": r.page,
            "scraped_at": r.scraped_at,
        }
        for r in records
    ]


# ── Abstract base ──────────────────────────────────────────────────────────────

class AbstractWarehouseLoader(abc.ABC):
    """
    Public contract shared by all warehouse backend implementations.
    Callers should depend only on this interface — never on DuckDB or psycopg2 directly.
    """

    @abc.abstractmethod
    def __enter__(self) -> "AbstractWarehouseLoader":
        ...

    @abc.abstractmethod
    def __exit__(self, *args: Any) -> None:
        ...

    @abc.abstractmethod
    def insert_records(self, records: list[PriceRecord]) -> int:
        """Bulk insert records. Returns count inserted."""
        ...

    @abc.abstractmethod
    def row_count(self) -> int:
        """Return total rows in raw.price_snapshots."""
        ...

    @abc.abstractmethod
    def latest_snapshot(self) -> pl.DataFrame:
        """Return the most recent price for each item_id as a Polars DataFrame."""
        ...


# ── DuckDB backend (primary) ───────────────────────────────────────────────────

class DuckDBLoader(AbstractWarehouseLoader):
    """
    Primary warehouse backend using DuckDB.

    Chosen for:
    - Columnar storage → fast GROUP BY / window function scans
    - Embedded (in-process) → zero network overhead, zero server management
    - Native Polars/Arrow integration → zero-copy bulk inserts
    - OLAP-optimised → exactly what analytical pipelines need

    Not chosen for:
    - Multi-user concurrent writes (not needed in this pipeline)
    - PostGIS / pgvector extensions (not needed here)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.db_path
        self._conn: Any = None

    def __enter__(self) -> "DuckDBLoader":
        import duckdb

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        self._bootstrap()
        console.print(f"[dim]DuckDB warehouse:[/] {self._db_path}")
        return self

    def __exit__(self, *_: Any) -> None:
        if self._conn:
            self._conn.close()

    def _bootstrap(self) -> None:
        self._conn.execute(_DDL_CREATE_SCHEMA)
        self._conn.execute(_DDL_CREATE_TABLE_DUCKDB)
        for idx in _DDL_INDEXES:
            self._conn.execute(idx)

    def insert_records(self, records: list[PriceRecord]) -> int:
        if not records:
            return 0
        df = pl.DataFrame(_to_row_dicts(records))
        self._conn.register("_staging", df)
        self._conn.execute("INSERT INTO raw.price_snapshots SELECT * FROM _staging")
        self._conn.unregister("_staging")
        console.print(f"[bold green]✓[/] DuckDB: inserted [bold]{len(records)}[/] rows")
        return len(records)

    def row_count(self) -> int:
        result = self._conn.execute(
            "SELECT COUNT(*) FROM raw.price_snapshots"
        ).fetchone()
        return int(result[0]) if result else 0

    def latest_snapshot(self) -> pl.DataFrame:
        return self._conn.execute(_LATEST_SNAPSHOT_SQL).pl()


# ── PostgreSQL backend (CI / integration testing) ─────────────────────────────

class PostgreSQLLoader(AbstractWarehouseLoader):
    """
    PostgreSQL backend — used for CI/integration testing only.

    Why PostgreSQL for CI:
    - Validates SQL portability and schema correctness against a
      client-server RDBMS (catches DuckDB-specific dialect drift early)
    - Exercises the psycopg2 path that a production multi-user
      deployment would use
    - GitHub Actions provides a free postgres:16 service container

    Not used as primary because:
    - Row-based storage is slower for large analytical GROUP BY scans
    - Requires server process management (deployment overhead)
    - median() not native — needs PERCENTILE_CONT via dbt macro
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._dsn = database_url or settings.postgres_dsn
        self._conn: Any = None

    def __enter__(self) -> "PostgreSQLLoader":
        import psycopg2

        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = False
        self._bootstrap()
        host = self._dsn.split("@")[-1] if "@" in self._dsn else self._dsn
        console.print(f"[dim]PostgreSQL warehouse:[/] {host}")
        return self

    def __exit__(self, *_: Any) -> None:
        if self._conn:
            self._conn.close()

    def _bootstrap(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_DDL_CREATE_SCHEMA)
            cur.execute(_DDL_CREATE_TABLE_PG)
            for idx in _DDL_INDEXES:
                cur.execute(idx)
        self._conn.commit()

    def insert_records(self, records: list[PriceRecord]) -> int:
        if not records:
            return 0
        import psycopg2.extras

        rows = _to_row_dicts(records)
        cols = list(rows[0].keys())
        values = [[r[c] for c in cols] for r in rows]
        insert_sql = f"""
            INSERT INTO raw.price_snapshots ({', '.join(cols)})
            VALUES %s
        """
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, insert_sql, values, page_size=500)
        self._conn.commit()
        console.print(f"[bold green]✓[/] PostgreSQL: inserted [bold]{len(records)}[/] rows")
        return len(records)

    def row_count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw.price_snapshots")
            result = cur.fetchone()
        return int(result[0]) if result else 0

    def latest_snapshot(self) -> pl.DataFrame:
        with self._conn.cursor() as cur:
            cur.execute(_LATEST_SNAPSHOT_SQL)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return pl.DataFrame(rows, schema=cols, orient="row")


# ── Factory ────────────────────────────────────────────────────────────────────

def get_loader(
    backend: str | None = None,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> AbstractWarehouseLoader:
    """
    Return the correct loader implementation for the requested backend.

    backend defaults to settings.db_backend ("duckdb" or "postgresql").
    Controlled via TRACKER_BACKEND env var.

    Example:
        with get_loader() as loader:
            loader.insert_records(records)
    """
    resolved = (backend or settings.db_backend).lower()
    if resolved == "duckdb":
        return DuckDBLoader(db_path=db_path)
    elif resolved in ("postgresql", "postgres"):
        return PostgreSQLLoader(database_url=database_url)
    else:
        raise ValueError(
            f"Unknown backend {resolved!r}. "
            "Expected 'duckdb' or 'postgresql'."
        )


# Backward-compat alias — existing code importing WarehouseLoader still works
WarehouseLoader = DuckDBLoader
