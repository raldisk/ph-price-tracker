# ph-price-tracker v0.2.0 — Build Plan

## Objective
Upgrade from v0.1.0 (single DuckDB backend) to v0.2.0 (dual-backend + new mart + SVG previews).
Apply 001 prompt template structure. Export clean zip with SVGs for GitHub README.

## Phase 1 — Core Python Package ✅
- [x] pyproject.toml (v0.2.0: psycopg2-binary, dbt-postgres added)
- [x] src/price_tracker/__init__.py (bump to 0.2.0)
- [x] src/price_tracker/config.py (add db_backend, postgres_dsn; remove pool fields)
- [x] src/price_tracker/models.py (unchanged from v0.1.0)
- [x] src/price_tracker/scraper.py (unchanged from v0.1.0)
- [x] src/price_tracker/loader.py (dual-backend: Abstract + DuckDB + PostgreSQL + factory)
- [x] src/price_tracker/pipeline.py (fix import: get_loader from loader, not db.factory)

## Phase 2 — dbt Transforms ✅
- [x] transforms/dbt_project.yml
- [x] transforms/profiles.yml (dev/ci/ci-postgres targets)
- [x] transforms/macros/median.sql (DuckDB vs PostgreSQL dispatch)
- [x] transforms/models/staging/_sources.yaml
- [x] transforms/models/staging/_staging.yaml
- [x] transforms/models/staging/stg_prices.sql
- [x] transforms/models/marts/_marts.yaml (includes daily_deals schema tests)
- [x] transforms/models/marts/price_history.sql
- [x] transforms/models/marts/price_movers.sql
- [x] transforms/models/marts/category_summary.sql (uses {{ median() }} macro)
- [x] transforms/models/marts/daily_deals.sql (NEW: top 10 deals/day, is_fresh_drop flag)

## Phase 3 — Tests ✅
- [x] tests/conftest.py (v0.2.0: pg fixtures, requires_postgres marker)
- [x] tests/test_models.py (14 test cases)
- [x] tests/test_loader.py (v0.2.0: TestDuckDBLoader, TestPostgreSQLLoader, TestGetLoaderFactory)

## Phase 4 — Infrastructure ✅
- [x] .github/workflows/ci.yml (lint → test-duckdb ∥ test-postgres → dbt-validate)
- [x] .github/workflows/pipeline.yml (daily cron 08:00 UTC + workflow_dispatch)
- [x] Dockerfile (multi-stage, non-root tracker user)
- [x] docker-compose.yml (postgres:16-alpine behind profiles: ["ci","postgres"])
- [x] .env.example
- [x] .gitignore

## Phase 5 — SVG Preview Files ✅
- [x] docs/architecture.svg (13,446 bytes — full pipeline diagram)
- [x] docs/dbt-lineage.svg (8,582 bytes — raw → staging → 4 marts)
- [x] docs/dashboard-preview.svg (10,495 bytes — category summary + daily_deals table)
- [x] docs/price-history-chart.svg (11,128 bytes — 14-day price history with LAG annotations)

## Phase 6 — Docs & Prompts ✅
- [x] README.md (v0.2.0: dual-backend section, 4 SVGs embedded, daily_deals documented)
- [x] prompts/001-prompt-data-engineer-pipeline.md (merged prompt template)
- [x] tasks/todo.md (this file)
- [x] tasks/lessons.md

## Phase 7 — Package & Export ✅
- [x] uv.lock (placeholder)
- [x] Zero phantom directories verified (removed brace-expansion artifacts)
- [x] Exported as ph-price-tracker-v0.2.0.zip (49 files, 62,166 bytes)
- [x] 16/16 integrity checks passed

---

## Phase 8 — Code Review Fixes (external review by colleague) ✅
- [x] Fix 1 CRITICAL: `.env.example` — `TRACKER_BACKEND` → `TRACKER_DB_BACKEND` (pydantic-settings derives from field name; old name silently ignored)
- [x] Fix 2 WARNING: `scraper.py:84` — `assert self._client` → `raise RuntimeError(...)` (assert disabled under `-O` flag in production Docker)
- [x] Fix 3 WARNING: `models.py from_raw` — log `exc` before `return None` (silent data loss with no observability)
- [x] Fix 4 WARNING: `pipeline.py` — `backend: str = None` → `backend: str | None` on all 3 CLI commands (mypy strict failure)
- [x] Fix 5 WARNING: `conftest.py` — cursor leak in pg teardown fixed with context manager
- [x] Fix 6 MEDIUM: `price_history.sql` — `lag()` evaluated 4× → computed once in `with_lag`, referenced in `with_changes` CTE
- [x] Fix 7 MEDIUM: `pipeline.py _run_dbt` — `capture_output=True` → `capture_output=False` (streams output live, no silent hang)
- [x] Rebuilt and verified ZIP: 50 files, 0 phantom dirs, 36/36 disk-ZIP match

---

## Results Summary

| Metric | Value |
|--------|-------|
| Total files | 50 |
| Phantom dirs | 0 |
| Integrity checks | 7/7 fixes + 16/16 structural ✅ |
| ZIP size | 65,006 bytes |
| New mart models | 1 (daily_deals) |
| SVG diagrams | 4 |
| Backend coverage | DuckDB primary + PostgreSQL CI |
| GitHub username | raldisk |

---

## Phase 9 — Post-Push Fixes ✅
- [x] Fix CI: `uv.lock` placeholder causing lint job to fail after 7s — removed from repo, added to `.gitignore`
- [x] Add `LICENSE` file (MIT, 2026, raldisk)
- [x] Remove `## Prompts` section from `README.md`
- [x] Rebuilt ZIP with all three changes

---

## Remaining (future sessions)
- [ ] Project 2: OFW remittance pipeline (ph-remittance-tracker)
- [ ] Project 3: PSA data pipeline (ph-psa-tracker)
- [ ] Analysis agent layer (Claude Code subagents on top of warehouse)
- [ ] scraper.py test coverage (respx already in dev deps — `_fetch_page` + `scrape_keyword` paths need tests per code review architectural note)
