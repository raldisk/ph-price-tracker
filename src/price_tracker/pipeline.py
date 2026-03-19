"""
Pipeline entry point.

Commands:
  price-tracker run       — full scrape → load → dbt run cycle
  price-tracker transform — run dbt models only
  price-tracker status    — print warehouse row counts
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from price_tracker.config import settings
from price_tracker.loader import get_loader
from price_tracker.models import PriceRecord
from price_tracker.scraper import LazadaScraper

app = typer.Typer(
    name="price-tracker",
    help="PH E-commerce Price Tracking Pipeline — Lazada PH → DuckDB → dbt",
    no_args_is_help=True,
)
console = Console()


def _run_dbt(command: str = "run") -> None:
    """Execute a dbt command inside the transforms/ directory, streaming output live."""
    console.print(f"\n[bold cyan]→[/] Running dbt {command}...")
    result = subprocess.run(
        ["dbt", command, "--profiles-dir", ".", "--project-dir", "."],
        cwd=Path("transforms"),
        # capture_output=False lets dbt stream directly to the terminal in real time.
        # Users see model-by-model progress instead of a silent hang then a wall of text.
        capture_output=False,
    )
    if result.returncode != 0:
        console.print(f"[bold red]✗ dbt {command} failed (exit {result.returncode})[/]")
        raise typer.Exit(code=1)
    console.print(f"[bold green]✓[/] dbt {command} complete")


@app.command()
def run(
    keywords: list[str] = typer.Option(
        None, "--keyword", "-k", help="Override keywords from config."
    ),
    skip_dbt: bool = typer.Option(False, "--skip-dbt", help="Skip dbt transforms after load."),
    backend: str | None = typer.Option(
        None, "--backend", help="Warehouse backend: 'duckdb' (default) or 'postgresql'."
    ),
) -> None:
    """Full pipeline: scrape → validate → load → transform."""
    if keywords:
        settings.keywords = keywords

    console.rule("[bold]PH Price Tracker — Full Run[/]")

    async def _scrape() -> list[PriceRecord]:
        async with LazadaScraper() as scraper:
            return await scraper.scrape_all()

    records = asyncio.run(_scrape())

    if not records:
        console.print("[bold yellow]⚠ No records scraped. Exiting.[/]")
        raise typer.Exit(code=0)

    with get_loader(backend=backend) as loader:
        loader.insert_records(records)
        total = loader.row_count()
        console.print(f"  Warehouse total rows: [bold]{total}[/]")

    if not skip_dbt:
        _run_dbt("run")
        _run_dbt("test")

    console.rule("[bold green]Pipeline complete[/]")


@app.command()
def transform(
    backend: str | None = typer.Option(
        None, "--backend", help="Warehouse backend for dbt profile selection."
    ),
) -> None:
    """Run dbt models only (warehouse must already have data)."""
    _run_dbt("run")
    _run_dbt("test")


@app.command()
def status(
    backend: str | None = typer.Option(
        None, "--backend", help="Warehouse backend to query."
    ),
) -> None:
    """Print current warehouse statistics."""
    with get_loader(backend=backend) as loader:
        total = loader.row_count()
        latest = loader.latest_snapshot()

    table = Table(title="Warehouse Status", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Total snapshots", str(total))
    table.add_row("Unique items (latest)", str(len(latest)))

    console.print(table)


if __name__ == "__main__":
    app()
