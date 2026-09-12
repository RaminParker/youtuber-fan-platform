# The one build: the same image runs web and worker, locally and in production.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first: they change far less often than the source, so this layer
# survives most rebuilds.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY src ./src
RUN uv sync --locked --no-dev

# Overridden by compose and by the hosting platform; a sensible default for
# `docker run`.
CMD ["uv", "run", "uvicorn", "app.web.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
