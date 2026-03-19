"""Tests for price_tracker.models."""

from __future__ import annotations

from decimal import Decimal

import pytest

from price_tracker.models import PriceRecord, RawPriceRecord


class TestRawPriceRecord:
    def test_instantiation_minimal(self) -> None:
        raw = RawPriceRecord(keyword="laptop", page=1)
        assert raw.item_id is None
        assert raw.keyword == "laptop"

    def test_all_fields_populated(self, sample_raw_record: RawPriceRecord) -> None:
        assert sample_raw_record.item_id == "ITEM001"
        assert sample_raw_record.brand == "TestBrand"
        assert sample_raw_record.page == 1


class TestPriceRecord:
    def test_currency_parsing_peso_symbol(self) -> None:
        record = PriceRecord(
            item_id="X1",
            name="Product",
            current_price="₱1,299.00",  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.current_price == Decimal("1299.00")

    def test_currency_parsing_plain_string(self) -> None:
        record = PriceRecord(
            item_id="X2",
            name="Product",
            current_price="4500",  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.current_price == Decimal("4500")

    def test_currency_parsing_float(self) -> None:
        record = PriceRecord(
            item_id="X2b",
            name="Product",
            current_price=1250.50,  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.current_price == Decimal("1250.5")

    def test_discount_pct_computed(self) -> None:
        record = PriceRecord(
            item_id="X3",
            name="Product",
            current_price=Decimal("750"),
            original_price=Decimal("1000"),
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.discount_pct == 25.0

    def test_no_discount_when_prices_equal(self) -> None:
        record = PriceRecord(
            item_id="X4",
            name="Product",
            current_price=Decimal("1000"),
            original_price=Decimal("1000"),
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.discount_pct is None

    def test_no_discount_when_price_higher_than_original(self) -> None:
        record = PriceRecord(
            item_id="X4b",
            name="Product",
            current_price=Decimal("1200"),
            original_price=Decimal("1000"),
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        # current > original means no discount was computed
        assert record.discount_pct is None

    def test_invalid_price_raises(self) -> None:
        with pytest.raises(Exception):
            PriceRecord(
                item_id="X5",
                name="Product",
                current_price="NOT_A_PRICE",  # type: ignore[arg-type]
                item_url="https://example.com",
                keyword="test",
                page=1,
            )

    def test_from_raw_valid(self, sample_raw_record: RawPriceRecord) -> None:
        record = PriceRecord.from_raw(sample_raw_record)
        assert record is not None
        assert record.item_id == "ITEM001"
        assert record.current_price == Decimal("25999")
        assert record.discount_pct == pytest.approx(18.75, abs=0.01)

    def test_from_raw_missing_item_id_returns_none(self) -> None:
        incomplete = RawPriceRecord(
            name="Test",
            price="₱500",
            item_url="https://example.com",
            keyword="laptop",
            page=1,
        )
        assert PriceRecord.from_raw(incomplete) is None

    def test_from_raw_missing_price_returns_none(self) -> None:
        incomplete = RawPriceRecord(
            item_id="X99",
            name="Test",
            item_url="https://example.com",
            keyword="laptop",
            page=1,
        )
        assert PriceRecord.from_raw(incomplete) is None

    def test_from_raw_all_missing_returns_none(self) -> None:
        assert PriceRecord.from_raw(RawPriceRecord(keyword="laptop", page=1)) is None

    def test_rating_parsed_from_string(self) -> None:
        record = PriceRecord(
            item_id="X6",
            name="Product",
            current_price=Decimal("500"),
            rating="4.5",  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.rating == 4.5

    def test_rating_invalid_string_returns_none(self) -> None:
        record = PriceRecord(
            item_id="X6b",
            name="Product",
            current_price=Decimal("500"),
            rating="N/A",  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.rating is None

    def test_review_count_strips_non_digits(self) -> None:
        record = PriceRecord(
            item_id="X7",
            name="Product",
            current_price=Decimal("500"),
            review_count="1,234",  # type: ignore[arg-type]
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.review_count == 1234

    def test_scraped_at_defaults_to_utc_now(self) -> None:
        from datetime import timezone

        record = PriceRecord(
            item_id="X8",
            name="Product",
            current_price=Decimal("500"),
            item_url="https://example.com",
            keyword="test",
            page=1,
        )
        assert record.scraped_at.tzinfo == timezone.utc
