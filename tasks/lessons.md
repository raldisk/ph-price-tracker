# Lessons Learned

> Updated after each correction. These rules prevent the same mistake from recurring.
> Review at session start for any project in this repo.

---

## Lesson 001 — Phantom Directories from Shell Brace Expansion in mkdir -p

**What happened:** Running `mkdir -p /path/{dir1,dir2,dir3}` inside the container
created *both* the correctly expanded directories AND a literal directory named
`{dir1,dir2,dir3}` — i.e., a folder whose name is the unexpanded brace string.
This happened twice across sessions: once in v0.1.0, once in v0.2.0.

**Why it matters:** These phantom folders show up in 7-Zip / Finder when the user
extracts the ZIP, look confusing, and undermine confidence in the whole project.

**Root cause:** The bash brace expansion works correctly in the shell, but somewhere
in the container execution the literal string also gets created as a directory.

**Fix applied:** After any `mkdir` with brace expansion, immediately run:
```bash
find . -type d -name '{*' -exec rm -rf {} + 2>/dev/null
```
Then verify before packaging:
```bash
find . -type d -name '{*' | wc -l  # must be 0
```

**Rule going forward:** Never use brace expansion in a single `mkdir -p` call.
Instead, use one `mkdir -p` per directory:
```bash
mkdir -p /path/dir1
mkdir -p /path/dir2
mkdir -p /path/dir3
```
Or use a loop:
```bash
for dir in dir1 dir2 dir3; do mkdir -p "/path/$dir"; done
```

---

## Lesson 002 — Always Run Integrity Checks Before Packaging

**What happened:** The first ZIP packaging in v0.1.0 was done without a verification
pass, which meant the phantom dirs shipped. In v0.2.0 a 16-point check was run
before zipping, which caught everything before packaging.

**Rule going forward:** For any project ZIP export, always run a named checklist
*before* the `zip` command. Never package on the first pass. The sequence must be:

1. Write all files
2. Run integrity checks (file existence, symbol presence, no phantom dirs)
3. Fix any failures
4. Then and only then: `zip`

---

## Lesson 003 — todo.md Items Must Be Marked Complete As You Go, Not At The End

**What happened:** The todo.md was written at the start with `[ ]` items, all
phases were completed, but the items were never marked `[x]` during execution.
The user had to ask "are all done?" to trigger the update.

**Rule going forward:** Mark each `[ ]` → `[x]` in todo.md immediately after
completing that phase, not at the end of the session. The todo.md is a live
document, not a retrospective one.

---

## Lesson 004 — lessons.md Must Be Created, Not Just Referenced

**What happened:** The workflow spec requires `tasks/lessons.md` to be updated
after corrections. The file was listed in `todo.md` as a deliverable but was
never actually created during the session.

**Rule going forward:** `tasks/lessons.md` is a required file for every project
that uses this workflow. Create it at session start alongside `tasks/todo.md`,
even if it's initially empty. Never list it as a deliverable without creating it.

---

## Lesson 005 — Phantom db/ Subpackage from Early-Generation Code

**What happened:** During an early generation of loader.py, code was written that
placed the abstract base, DuckDB loader, and PostgreSQL loader into a subpackage
at `src/price_tracker/db/` (with `base.py`, `duckdb_loader.py`, `postgres_loader.py`,
`factory.py`). This was then consolidated into a single `loader.py`. But the
`pipeline.py` file was not updated — it still had:
```python
from price_tracker.db.factory import get_loader  # phantom import
```
This would have caused an `ImportError` at runtime.

**Rule going forward:** When consolidating modules, always grep for import references
to the old path before considering the refactor complete:
```bash
grep -r "price_tracker.db\|from .db\|from db." src/ tests/
```
Any hits are broken imports that must be fixed before packaging.

---

## Lesson 006 — category_summary.sql: DuckDB-Native median() Is Not ANSI SQL

**What happened:** The original v0.1.0 `category_summary.sql` used DuckDB's
native `median()` function directly. This runs fine against the DuckDB target
but fails against the PostgreSQL CI target, which requires
`PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col)`.

**Fix applied:** Created `transforms/macros/median.sql` as a cross-database
dispatch macro:
```sql
{% if target.type == 'duckdb' %}
  median({{ column }})
{% elif target.type == 'postgres' %}
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {{ column }})
{% endif %}
```
All models now call `{{ median('col') }}` instead of `median(col)` directly.

**Rule going forward:** Before writing any aggregate function in a dbt model,
check the [dbt cross-database macro list](https://docs.getdbt.com/docs/build/jinja-macros).
If the function is dialect-specific (median, percentile, array_agg, etc.), write
a macro first, then use it everywhere.

---

## Lesson 007 — pydantic-settings Derives Env Var Names from Field Names, Not Custom Strings

**What happened:** `config.py` had a field named `db_backend` with `env_prefix="TRACKER_"`.
pydantic-settings derives the env var as `TRACKER_DB_BACKEND`. The `.env.example` shipped
`TRACKER_BACKEND=duckdb` — which pydantic-settings silently ignores. Any user following
the documented example to switch to PostgreSQL saw zero effect and zero error.

**Why it's dangerous:** Silent misconfiguration with no feedback. The default (DuckDB) still
works, so the bug is invisible in normal usage and only surfaces when someone explicitly tries
to override the backend.

**Rule going forward:** After adding any field to `Settings`, immediately derive the correct
env var name: `TRACKER_` + field name in uppercase. Write it in `.env.example` and verify it
matches. Pattern: field `db_backend` → env var `TRACKER_DB_BACKEND`, not `TRACKER_BACKEND`.

---

## Lesson 008 — `assert` Is Disabled in Production; Use `RuntimeError` for Runtime Guards

**What happened:** `scraper.py` used `assert self._client is not None` to guard against
calling `_fetch_page` outside the async context manager. Python disables all `assert`
statements when the interpreter runs with `-O` or `-OO` (optimised mode). Production Docker
images commonly set `PYTHONOPTIMIZE=1`, making this guard a no-op — the check disappears
entirely and the failure becomes an `AttributeError` with a useless traceback.

**Rule going forward:** Never use `assert` for runtime guards in production code. Use
explicit `if` + `raise RuntimeError(...)` (or a domain-specific exception) for any check
that must hold at runtime. `assert` is only appropriate for debugging invariants in test
code or internal consistency checks during development.

---

## Lesson 009 — `except Exception: return None` Without Logging Is a Data Loss Black Hole

**What happened:** `PriceRecord.from_raw()` had a bare `except Exception: return None`.
When Lazada's API returned unexpected field shapes, every validation failure was silently
discarded — no log, no counter, no way to distinguish "API returned 150 items and 12 failed
validation" from "API returned 150 items and all 150 were valid". Over thousands of scraped
records this is a black hole for diagnosing data quality regressions.

**Rule going forward:** Any `except` clause that swallows an exception and returns a
sentinel (`None`, `[]`, `False`) must log the exception before doing so. At minimum:
```python
except Exception as exc:
    console.print(f"[yellow]⚠ {context}:[/] {exc}")
    return None
```
The only acceptable bare swallow is in a low-level utility parser (like `_strip_currency`)
where the call site handles `None` and the failure mode is fully expected.

---

## Lesson 010 — `str = None` as a Default Is a mypy Strict Violation; Use `str | None`

**What happened:** Three Typer CLI commands in `pipeline.py` declared:
```python
backend: str = typer.Option(None, ...)
```
Assigning `None` to a `str`-annotated parameter is an `Incompatible default for argument`
error under `mypy --strict`. Since `pyproject.toml` sets `strict = true`, this means
`mypy src/` was failing in CI every single run — silently undermining the entire
strict-mode type-safety investment without anyone noticing until the code review.

**Rule going forward:** Optional CLI parameters that default to `None` must be typed
`str | None` (Python 3.10+ syntax, already the project standard at 3.11+):
```python
backend: str | None = typer.Option(None, "--backend", help="...")
```
After writing any new Typer command: run `mypy src/` locally before committing.
A strict-mode mypy failure in CI means every subsequent push is untrustworthy.

---

## Lesson 011 — Placeholder `uv.lock` Breaks CI; Never Commit It

**What happened:** A placeholder `uv.lock` was committed to the repo with only a comment
and `version = 1` — no real package entries. When GitHub Actions ran `uv sync --extra dev`,
uv read the invalid lockfile and failed within 7 seconds. All downstream CI jobs (test,
dbt-validate) were skipped as a result.

**Why it's a trap:** The intent was to "make CI pass `--frozen` validation on first run" —
but CI wasn't using `--frozen` at all. The placeholder solved a non-existent problem while
creating a real one.

**Fix applied:** Added `uv.lock` to `.gitignore`. CI now runs `uv sync --extra dev` without
a lockfile present — uv resolves and generates it fresh on each run.

**Rule going forward:** Never commit a placeholder `uv.lock`. Two valid approaches only:
1. **Don't commit it** — add to `.gitignore`, let CI generate fresh (simpler, this project's choice)
2. **Commit the real one** — run `uv lock` locally first, commit the fully resolved lockfile

A half-committed lockfile is worse than none at all. If you're not running `uv lock` locally
first, add `uv.lock` to `.gitignore`.

---

*Last updated: 2026-03-20 · Session: ph-price-tracker post-push fixes*
