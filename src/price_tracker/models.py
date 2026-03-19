"""
Domain models for price records.

RawPriceRecord  — what comes off the wire, loosely typed.
PriceRecord     — validated, typed, ready for the warehouse.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator
from rich.console import Console

console = Console()


def _strip_currency(value: str | float | None) -> Decimal | None:
    """Parse '₱1,299.00' or '1299' into a Decimal."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    cleaned = re.sub(r"[₱,\s]", "", str(value))
    try:
        return Decimal(cleaned)
    except Exception:
        return None


class RawPriceRecord(BaseModel):
    """
    Loosely typed model representing a single product listing
    as returned by the Lazada PH catalog API.
    Fields are Optional because the API is not always consistent.
    """

    item_id: str | None = None
    name: str | None = None
    price: str | None = None
    original_price: str | None = None
    brand: str | None = None
    category: str | None = None
    item_url: str | None = None
    image_url: str | None = None
    rating: str | None = None
    review_count: str | None = None
    location: str | None = None
    keyword: str = ""
    page: int = 1


class PriceRecord(BaseModel):
    """
    Validated, typed record ready for insertion into DuckDB.
    """

    item_id: str
    name: str
    current_price: Decimal
    original_price: Decimal | None = None
    discount_pct: float | None = None
    brand: str | None = None
    category: str | None = None
    item_url: str
    rating: float | None = None
    review_count: int | None = None
    location: str | None = None
    keyword: str
    page: int
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("current_price", mode="before")
    @classmethod
    def parse_current_price(cls, v: str | float | Decimal) -> Decimal:
        result = _strip_currency(v)  # type: ignore[arg-type]
        if result is None:
            raise ValueError(f"Cannot parse price: {v!r}")
        return result

    @field_validator("original_price", mode="before")
    @classmethod
    def parse_original_price(cls, v: str | float | Decimal | None) -> Decimal | None:
        return _strip_currency(v)  # type: ignore[arg-type]

    @field_validator("rating", mode="before")
    @classmethod
    def parse_rating(cls, v: str | float | None) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @field_validator("review_count", mode="before")
    @classmethod
    def parse_review_count(cls, v: str | int | None) -> int | None:
        if v is None:
            return None
        cleaned = re.sub(r"[^\d]", "", str(v))
        return int(cleaned) if cleaned else None

    @model_validator(mode="after")
    def compute_discount(self) -> "PriceRecord":
        if (
            self.original_price
            and self.original_price > 0
            and self.current_price < self.original_price
        ):
            self.discount_pct = round(
                float(
                    (self.original_price - self.current_price)
                    / self.original_price
                    * 100
                ),
                2,
            )
        return self

    @classmethod
    def from_raw(cls, raw: RawPriceRecord) -> "PriceRecord | None":
        """
        Convert a RawPriceRecord to a validated PriceRecord.
        Returns None if the record is missing required fields.
        """
        if not raw.item_id or not raw.name or not raw.price or not raw.item_url:
            return None
        try:
            return cls(
                item_id=raw.item_id,
                name=raw.name,
                current_price=raw.price,  # type: ignore[arg-type]
                original_price=raw.original_price,
                brand=raw.brand,
                category=raw.category,
                item_url=raw.item_url,
                rating=raw.rating,
                review_count=raw.review_count,
                location=raw.location,
                keyword=raw.keyword,
                page=raw.page,
            )
        except Exception as exc:
            console.print(
                f"[yellow]⚠ Validation failed for item {raw.item_id!r}:[/] {exc}"
            )
            return None
