"""
Lazada PH catalog scraper.

Targets the public catalog JSON endpoint:
  GET https://www.lazada.com.ph/catalog/?ajax=true&q={keyword}&page={page}

Uses httpx for async HTTP with tenacity for exponential-backoff retries.
Rate limiting is enforced between requests to respect the server.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx
from rich.console import Console
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from price_tracker.config import settings
from price_tracker.models import PriceRecord, RawPriceRecord

console = Console()

_CATALOG_URL = "https://www.lazada.com.ph/catalog/"

_DEFAULT_PARAMS: dict[str, str] = {
    "ajax": "true",
    "sort": "0",
}

_HEADERS_BASE: dict[str, str] = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.lazada.com.ph/",
}


def _build_headers() -> dict[str, str]:
    """Return headers with a random user-agent from the pool."""
    return {
        **_HEADERS_BASE,
        "User-Agent": random.choice(settings.user_agents),
    }


def _parse_listing(item: dict[str, Any], keyword: str, page: int) -> RawPriceRecord:
    """Map a raw API item dict onto a RawPriceRecord."""
    item_url = item.get("itemUrl", "")
    image_url = item.get("image", "")
    return RawPriceRecord(
        item_id=str(item.get("itemId") or item.get("nid") or ""),
        name=item.get("name") or item.get("title"),
        price=item.get("price") or item.get("priceShow"),
        original_price=item.get("originalPrice"),
        brand=item.get("brandName"),
        category=item.get("categoryName"),
        item_url="https:" + item_url if item_url.startswith("//") else item_url,
        image_url="https:" + image_url if image_url.startswith("//") else image_url,
        rating=item.get("ratingScore"),
        review_count=item.get("review"),
        location=item.get("location"),
        keyword=keyword,
        page=page,
    )


class LazadaScraper:
    """
    Async scraper for Lazada PH product listings.

    Usage:
        async with LazadaScraper() as scraper:
            records = await scraper.scrape_keyword("laptop")
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "LazadaScraper":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=settings.retry_base_delay, min=2, max=30),
        reraise=True,
    )
    async def _fetch_page(self, keyword: str, page: int) -> list[dict[str, Any]]:
        """
        Fetch a single page of results for a keyword.
        Returns a list of raw item dicts from the API response.
        """
        if self._client is None:
            raise RuntimeError("Client not initialised — use async context manager.")

        params = {**_DEFAULT_PARAMS, "q": keyword, "page": str(page)}
        response = await self._client.get(
            _CATALOG_URL,
            params=params,
            headers=_build_headers(),
        )
        response.raise_for_status()

        data = response.json()
        mods = data.get("mods") or {}
        return mods.get("listItems") or []

    async def scrape_keyword(self, keyword: str) -> list[PriceRecord]:
        """
        Scrape all configured pages for a keyword.
        Returns a list of validated PriceRecords.
        """
        records: list[PriceRecord] = []
        console.print(f"[bold cyan]→[/] Scraping keyword: [bold]{keyword!r}[/]")

        for page in range(1, settings.max_pages_per_keyword + 1):
            try:
                raw_items = await self._fetch_page(keyword, page)
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                console.print(f"  [yellow]⚠ Page {page} failed:[/] {exc}")
                break

            if not raw_items:
                console.print(f"  [dim]No items on page {page}, stopping.[/]")
                break

            page_records: list[PriceRecord] = []
            for item in raw_items:
                raw = _parse_listing(item, keyword=keyword, page=page)
                validated = PriceRecord.from_raw(raw)
                if validated:
                    page_records.append(validated)

            records.extend(page_records)
            console.print(f"  Page {page}: [green]{len(page_records)}[/] valid records")

            await asyncio.sleep(settings.rate_limit_delay)

        return records

    async def scrape_all(self) -> list[PriceRecord]:
        """Scrape all keywords defined in settings."""
        all_records: list[PriceRecord] = []
        for keyword in settings.keywords:
            records = await self.scrape_keyword(keyword)
            all_records.extend(records)
            await asyncio.sleep(settings.rate_limit_delay)
        console.print(f"\n[bold green]✓[/] Total valid records: [bold]{len(all_records)}[/]")
        return all_records
