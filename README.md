# ph-price-tracker

**End-to-end e-commerce price tracking pipeline for the Philippine market.**

Scrapes Lazada PH product listings on a daily schedule, validates and loads them into a DuckDB warehouse, then runs dbt transformations to produce analytics-ready marts covering price history, top movers, category trends, and daily deals.

[![CI](https://github.com/raldisk/ph-price-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/raldisk/ph-price-tracker/actions/workflows/ci.yml)
[![Scheduled Pipeline](https://github.com/raldisk/ph-price-tracker/actions/workflows/pipeline.yml/badge.svg)](https://github.com/raldisk/ph-price-tracker/actions/workflows/pipeline.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![dbt](https://img.shields.io/badge/dbt-duckdb-orange.svg)](https://docs.getdbt.com/)
[![uv](https://img.shields.io/badge/package%20manager-uv-purple.svg)](https://docs.astral.sh/uv/)
[![version](https://img.shields.io/badge/version-0.2.0-green.svg)]()

---

## Architecture

![Architecture](docs/architecture.svg)

---

## dbt Model Lineage

![dbt Lineage](docs/dbt-lineage.svg)

---

## Sample Output

### Category Summary Dashboard

![Dashboard Preview](docs/dashboard-preview.svg)

### Price History — Single Item (marts.price_history)

![Price History Chart](docs/price-history-chart.svg)

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| HTTP client | [httpx](https://www.python-httpx.org/) | Async, modern, type-safe |
| Retry logic | [tenacity](https://tenacity.readthedocs.io/) | Exponential backoff with jitter |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) | Fast, strict, self-documenting |
| DataFrames | [Polars](https://pola.rs/) | Faster than pandas for bulk inserts |
| Primary warehouse | [DuckDB](https://duckdb.org/) | Embedded OLAP, zero-config, fast analytical scans |
| CI warehouse | [PostgreSQL 16](https://www.postgresql.org/) | Validates SQL portability via psycopg2 |
| Transforms | [dbt-duckdb](https://github.com/duckdb/dbt-duckdb) | SQL-first, version-controlled analytics |
| CLI | [Typer](https://typer.tiangolo.com/) | Clean UX, `--help` out of the box |
| Package mgmt | [uv](https://docs.astral.sh/uv/) | 10–100× faster than pip |
| CI/CD | GitHub Actions | Lint → test-duckdb ∥ test-postgres → dbt-validate → daily cron |
| Container | Docker (multi-stage) | Non-root, reproducible runtime image |

---

## Dual-Backend Design

DuckDB is the **primary warehouse** for this project. It is columnar, embedded (zero network overhead), and optimised for the analytical scans that dbt models require. PostgreSQL is the **CI/integration backend** only — it validates that the schema and SQL are portable, and exercises the psycopg2 path that a production multi-user deployment would use.

The loader layer follows the interface-first pattern:

```
AbstractWarehouseLoader   ← callers depend only on this
  ├── DuckDBLoader        ← primary (dev + prod)
  └── PostgreSQLLoader    ← CI only (GitHub Actions postgres:16)

get_loader(backend="duckdb" | "postgresql")  ← factory
```

Backend is selected via the `TRACKER_DB_BACKEND` environment variable. The default is `duckdb`. No code changes are required to run against PostgreSQL — only the env var changes.

---

## Quickstart

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/)

```bash
# Clone and install
git clone https://github.com/raldisk/ph-price-tracker.git
cd ph-price-tracker
uv sync --extra dev

# Configure (optional — all defaults work out of the box)
cp .env.example .env

# Run the full pipeline once
uv run price-tracker run

# Check warehouse status
uv run price-tracker status

# Run dbt transforms only (if data already loaded)
uv run price-tracker transform
```

**Run with Docker:**

```bash
# Default run (DuckDB backend)
docker compose up tracker

# Check status
docker compose --profile status up tracker-status

# Start PostgreSQL for local integration testing
docker compose --profile postgres up postgres
```

**Target a specific keyword:**

```bash
uv run price-tracker run --keyword laptop --keyword "gaming chair"
```

**Run against PostgreSQL backend:**

```bash
TRACKER_DB_BACKEND=postgresql \
TRACKER_POSTGRES_DSN=postgresql://tracker:tracker@localhost:5432/tracker \
uv run price-tracker run
```

---

## How to Use

### Step 1 — Let it run automatically

The pipeline runs every day at 16:00 PHT via GitHub Actions with no action required from you. Each run scrapes Lazada PH, loads new price snapshots into DuckDB, and refreshes all dbt marts.

### Step 2 — Run it manually

```bash
# Full pipeline — scrape → load → transform
uv run price-tracker run

# Scrape specific products only
uv run price-tracker run --keyword laptop --keyword headphones

# Skip the scrape — just re-run dbt transforms on existing data
uv run price-tracker transform

# Check how much data is in the warehouse
uv run price-tracker status
```

### Step 3 — Query the marts directly

Open the DuckDB warehouse at `data/prices.duckdb` with any SQL client (DuckDB CLI, DBeaver, Harlequin) and query the marts directly:

```sql
-- What dropped in price today?
SELECT product_name, prev_price, current_price, price_change_pct, item_url
FROM marts.price_movers
WHERE snapshot_date = current_date
  AND price_direction = 'decreased'
ORDER BY price_change_pct ASC
LIMIT 10;

-- What are today's best deals?
SELECT deal_rank, product_name, category, current_price, discount_pct, is_fresh_drop
FROM marts.daily_deals
WHERE snapshot_date = current_date
ORDER BY deal_rank;

-- Which category is getting cheaper over time?
SELECT snapshot_date, category, avg_price, median_price
FROM marts.category_summary
ORDER BY snapshot_date DESC, category;
```

### Step 4 — Customise what gets tracked

Edit `TRACKER_KEYWORDS` in your `.env` file to track different products:

```env
TRACKER_KEYWORDS=["gaming laptop","mechanical keyboard","4k monitor","airpods"]
```

Then run `uv run price-tracker run` to scrape the new keywords immediately.



```
ph-price-tracker/
├── src/price_tracker/
│   ├── config.py        # Pydantic settings — all env-configurable (TRACKER_ prefix)
│   ├── models.py        # RawPriceRecord + PriceRecord — Pydantic v2 domain models
│   ├── scraper.py       # Async Lazada PH scraper with tenacity retry
│   ├── loader.py        # AbstractWarehouseLoader + DuckDBLoader + PostgreSQLLoader
│   │                    # + get_loader() factory + WarehouseLoader alias
│   └── pipeline.py      # Typer CLI: run | transform | status
│
├── transforms/          # dbt-duckdb project
│   ├── macros/
│   │   └── median.sql   # Cross-database median() macro (DuckDB + PostgreSQL)
│   ├── models/
│   │   ├── staging/
│   │   │   ├── _sources.yaml
│   │   │   ├── _staging.yaml
│   │   │   └── stg_prices.sql        # view: clean, trim, price_tier
│   │   └── marts/
│   │       ├── _marts.yaml
│   │       ├── price_history.sql     # table: LAG price change detection
│   │       ├── price_movers.sql      # table: top-20 drops/spikes per day
│   │       ├── category_summary.sql  # table: avg/median/min/max per category
│   │       └── daily_deals.sql       # table: top-10 deals (≥30% off, ≥50 reviews)
│   ├── dbt_project.yml
│   └── profiles.yml     # dev (DuckDB) · ci (DuckDB in-memory) · ci-postgres
│
├── tests/
│   ├── conftest.py      # fixtures + requires_postgres marker
│   ├── test_models.py   # Pydantic model unit tests
│   └── test_loader.py   # TestDuckDBLoader · TestPostgreSQLLoader · TestGetLoaderFactory
│
├── docs/                # SVG diagrams — rendered in GitHub README
│   ├── architecture.svg
│   ├── dbt-lineage.svg
│   ├── dashboard-preview.svg
│   └── price-history-chart.svg
│
├── prompts/
│   └── 001-prompt-data-engineer-pipeline.md  # Structured prompt template
│
├── .github/workflows/
│   ├── ci.yml           # lint → test-duckdb ∥ test-postgres → dbt-validate
│   └── pipeline.yml     # Daily cron 08:00 UTC + workflow_dispatch
│
├── Dockerfile           # Multi-stage, non-root tracker user
├── docker-compose.yml   # tracker + postgres (behind --profile ci)
├── pyproject.toml       # uv-managed, v0.2.0
├── uv.lock
└── .env.example
```

---

## dbt Models

### `staging.stg_prices` (view)
Cleaned view over `raw.price_snapshots`. Null filtering, string trimming, and a derived `price_tier` column (`full_price` / `minor_discount` / `on_sale` / `deep_discount`) based on discount depth.

### `marts.price_history` (table)
Full price history per item with period-over-period change detection using `LAG()` window functions. Exposes `price_change_abs`, `price_change_pct`, and `price_direction` (`decreased` / `increased` / `unchanged` / `first_seen`) for every snapshot.

### `marts.price_movers` (table)
Top 20 price drops and spikes per day, ranked by absolute price change using `RANK()`. Useful for deal-alert and anomaly detection downstream.

### `marts.category_summary` (table)
Aggregated statistics per category per day: `avg_price`, `median_price`, `min_price`, `max_price`, `avg_discount_pct`, and `total_reviews`. Uses the `{{ median() }}` macro for ANSI portability across DuckDB and PostgreSQL.

### `marts.daily_deals` (table) — new in v0.2.0
Top 10 deals per day filtered to items with `discount_pct >= 30` and `review_count >= 50`, ranked by discount depth. Includes an `is_fresh_drop` boolean flag that marks items that dropped 10%+ in price on a given day, making this mart directly consumable by alert or notification systems.

---

## Configuration

All settings are environment-variable driven (prefix: `TRACKER_`). Every value has a working default.

| Variable | Default | Description |
|---|---|---|
| `TRACKER_DB_BACKEND` | `duckdb` | Warehouse backend: `duckdb` or `postgresql` |
| `TRACKER_DB_PATH` | `data/prices.duckdb` | DuckDB file location |
| `TRACKER_POSTGRES_DSN` | `postgresql://tracker:tracker@localhost:5432/tracker` | PostgreSQL DSN (CI only) |
| `TRACKER_MAX_PAGES_PER_KEYWORD` | `3` | Pages scraped per keyword (~50 items/page) |
| `TRACKER_RATE_LIMIT_DELAY` | `1.5` | Seconds between requests |
| `TRACKER_MAX_RETRIES` | `3` | Retry attempts per failed request |
| `TRACKER_RETRY_BASE_DELAY` | `2.0` | Exponential backoff base (seconds) |
| `TRACKER_REQUEST_TIMEOUT` | `30` | HTTP timeout (seconds) |

---

## Testing

```bash
# All tests (DuckDB only — no server required)
uv run pytest

# With PostgreSQL integration tests
TRACKER_POSTGRES_DSN=postgresql://tracker:tracker@localhost:5432/tracker \
uv run pytest -m postgres

# Skip PostgreSQL tests explicitly
uv run pytest -m "not postgres"

# Coverage report
uv run pytest --cov=price_tracker --cov-report=html
open htmlcov/index.html
```

---

## CI Pipeline

Four jobs run on every push and pull request:

```
lint  ───────────────────────────────────────────────────────────
         │
         ├──── test-duckdb (Python 3.11 + 3.12, no service)
         │
         └──── test-postgres (Python 3.11, postgres:16-alpine service)
                    │              │
                    └──────────────┘
                          │
                    dbt-validate (parse + compile, in-memory DuckDB)
```

The scheduled pipeline runs daily at 08:00 UTC (16:00 PHT), caches the DuckDB file across runs, and uploads the warehouse as a 30-day GitHub Actions artifact.

---

## What I'd Improve With More Time

- **Proxy rotation** — a rotating pool would make the scraper resilient to IP-based rate limiting at scale, currently the primary production risk.
- **Incremental dbt models** — current marts are full refreshes. Adding `unique_key` on `(item_id, scraped_at)` with `incremental` materialisation would cut transform time substantially as the dataset grows past a few million rows.
- **Alert layer** — `daily_deals` with `is_fresh_drop = true` is shaped exactly for a Telegram or email notification. The mart already exists; the notification consumer is the natural next layer.
- **Data quality monitoring** — integrating [Elementary](https://www.elementary-data.com/) on top of the dbt test suite would add automated anomaly detection and a browsable quality dashboard.
- **Streamlit / Evidence.dev dashboard** — the four mart tables are sized and shaped for a live front-end. `category_summary` + `price_movers` + `daily_deals` together make a coherent consumer product.

---

## License

MIT
