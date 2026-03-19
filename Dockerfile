# ── Stage 1: dependency resolution ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv for fast, reproducible dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.4.20 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev --no-editable


# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user — never run pipeline containers as root
RUN groupadd --gid 1001 tracker \
    && useradd --uid 1001 --gid tracker --no-create-home tracker

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy source and dbt project
COPY src/ ./src/
COPY transforms/ ./transforms/

# Data directory — override with volume mount in production
RUN mkdir -p /app/data && chown tracker:tracker /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRACKER_DB_PATH=/app/data/prices.duckdb

USER tracker

VOLUME ["/app/data"]

ENTRYPOINT ["price-tracker"]
CMD ["--help"]
