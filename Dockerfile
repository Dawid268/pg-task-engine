# Adapted from touchpoint-taxonomy; public dependencies only.
FROM python:3.13-slim-bookworm AS base

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/
ENV UV_LINK_MODE=copy \
    UV_NO_MANAGED_PYTHON=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/pg-task-engine
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --group api --no-editable

FROM base AS runtime
ENV PATH="/opt/pg-task-engine/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    LOG_LEVEL=info \
    RELOAD=false
WORKDIR /opt/pg-task-engine
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY --from=builder /opt/pg-task-engine/.venv ./.venv
COPY app ./app
COPY run.py ./run.py
USER 10001:10001
EXPOSE 8080
CMD ["python", "run.py"]
