"""
Tests for price_tracker.loader — dual-backend.

Test classes:
  TestDuckDBLoader        → unit tests; no server required, uses tmp_path
  TestPostgreSQLLoader    → integration tests; guarded by @requires_postgres
  TestGetLoaderFactory    → factory routing tests; no I/O
"""

from __future__ import annotations

from pathlib import Path

import pytest

from price_tracker.loader import (
    AbstractWarehouseLoader,
    DuckDBLoader,
    PostgreSQLLoader,
    WarehouseLoader,
    get_loader,
)
from price_tracker.models import PriceRecord

from conftest import requires_postgres


# ── DuckDB (primary backend) ──────────────────────────────────────────────────

class TestDuckDBLoader:
    def test_bootstrap_creates_empty_schema(self, tmp_db_path: Path) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            assert loader.row_count() == 0

    def test_db_file_created_on_disk(self, tmp_db_path: Path) -> None:
        with DuckDBLoader(db_path=tmp_db_path):
            pass
        assert tmp_db_path.exists()

    def test_insert_single_record(
        self, tmp_db_path: Path, sample_price_record: PriceRecord
    ) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            inserted = loader.insert_records([sample_price_record])
            assert inserted == 1
            assert loader.row_count() == 1

    def test_insert_multiple_records(
        self, tmp_db_path: Path, multi_price_records: list[PriceRecord]
    ) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            inserted = loader.insert_records(multi_price_records)
            assert inserted == 10
            assert loader.row_count() == 10

    def test_insert_empty_list_returns_zero(self, tmp_db_path: Path) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            assert loader.insert_records([]) == 0

    def test_insert_is_cumulative(
        self,
        tmp_db_path: Path,
        sample_price_record: PriceRecord,
        multi_price_records: list[PriceRecord],
    ) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            loader.insert_records([sample_price_record])
            loader.insert_records(multi_price_records)
            assert loader.row_count() == 11

    def test_latest_snapshot_returns_polars_df(
        self, tmp_db_path: Path, multi_price_records: list[PriceRecord]
    ) -> None:
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            loader.insert_records(multi_price_records)
            df = loader.latest_snapshot()
        assert len(df) == 10
        assert "item_id" in df.columns
        assert "current_price" in df.columns

    def test_latest_snapshot_returns_one_row_per_item(
        self,
        tmp_db_path: Path,
        sample_price_record: PriceRecord,
    ) -> None:
        """Insert same item twice — latest_snapshot should return only one row."""
        import copy
        from datetime import datetime, timezone

        first = sample_price_record
        second = copy.copy(first)
        second = first.model_copy(
            update={"scraped_at": datetime(2024, 6, 2, 10, 0, 0, tzinfo=timezone.utc)}
        )
        with DuckDBLoader(db_path=tmp_db_path) as loader:
            loader.insert_records([first, second])
            df = loader.latest_snapshot()
        assert len(df) == 1

    def test_is_abstract_warehouse_loader_subclass(self) -> None:
        assert issubclass(DuckDBLoader, AbstractWarehouseLoader)

    def test_warehouse_loader_alias_is_duckdb(self) -> None:
        assert WarehouseLoader is DuckDBLoader


# ── PostgreSQL (CI/integration backend) ───────────────────────────────────────

class TestPostgreSQLLoader:
    @requires_postgres
    def test_bootstrap_creates_empty_schema(self, pg_loader: PostgreSQLLoader) -> None:
        # pg_loader fixture already calls __enter__ and bootstraps
        assert pg_loader.row_count() == 0

    @requires_postgres
    def test_insert_single_record(
        self, pg_loader: PostgreSQLLoader, sample_price_record: PriceRecord
    ) -> None:
        inserted = pg_loader.insert_records([sample_price_record])
        assert inserted == 1
        assert pg_loader.row_count() == 1

    @requires_postgres
    def test_insert_multiple_records(
        self, pg_loader: PostgreSQLLoader, multi_price_records: list[PriceRecord]
    ) -> None:
        inserted = pg_loader.insert_records(multi_price_records)
        assert inserted == 10
        assert pg_loader.row_count() == 10

    @requires_postgres
    def test_insert_empty_list_returns_zero(self, pg_loader: PostgreSQLLoader) -> None:
        assert pg_loader.insert_records([]) == 0

    @requires_postgres
    def test_latest_snapshot_returns_polars_df(
        self, pg_loader: PostgreSQLLoader, multi_price_records: list[PriceRecord]
    ) -> None:
        pg_loader.insert_records(multi_price_records)
        df = pg_loader.latest_snapshot()
        assert len(df) == 10
        assert "item_id" in df.columns

    @requires_postgres
    def test_decimal_values_insert_without_type_error(
        self, pg_loader: PostgreSQLLoader, sample_price_record: PriceRecord
    ) -> None:
        """
        Regression: psycopg2 requires float for NUMERIC columns, not Decimal.
        _to_row_dicts() must coerce Decimal → float before insert.
        """
        from decimal import Decimal

        record = sample_price_record.model_copy(
            update={
                "current_price": Decimal("25999.50"),
                "original_price": Decimal("32000.00"),
            }
        )
        # If Decimal coercion is missing, this raises psycopg2.errors.InvalidTextRepresentation
        inserted = pg_loader.insert_records([record])
        assert inserted == 1

    @requires_postgres
    def test_is_abstract_warehouse_loader_subclass(self) -> None:
        assert issubclass(PostgreSQLLoader, AbstractWarehouseLoader)


# ── Factory ────────────────────────────────────────────────────────────────────

class TestGetLoaderFactory:
    def test_duckdb_backend_returns_duckdb_loader(self) -> None:
        loader = get_loader(backend="duckdb")
        assert isinstance(loader, DuckDBLoader)

    def test_postgresql_backend_returns_pg_loader(self) -> None:
        loader = get_loader(backend="postgresql")
        assert isinstance(loader, PostgreSQLLoader)

    def test_postgres_alias_returns_pg_loader(self) -> None:
        loader = get_loader(backend="postgres")
        assert isinstance(loader, PostgreSQLLoader)

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            get_loader(backend="snowflake")

    def test_default_returns_duckdb_loader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRACKER_BACKEND", "duckdb")
        # Re-import settings to pick up monkeypatched env
        import importlib
        import price_tracker.config as cfg_module
        importlib.reload(cfg_module)
        from price_tracker.config import settings
        loader = get_loader(backend=settings.db_backend)
        assert isinstance(loader, DuckDBLoader)

    def test_returned_loader_implements_interface(self) -> None:
        loader = get_loader(backend="duckdb")
        assert isinstance(loader, AbstractWarehouseLoader)
        assert hasattr(loader, "insert_records")
        assert hasattr(loader, "row_count")
        assert hasattr(loader, "latest_snapshot")
