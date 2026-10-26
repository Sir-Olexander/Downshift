# Downshift API. Build from the repo root:  docker build -f server/Dockerfile -t downshift-api .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY sdk ./sdk
COPY server ./server
COPY demo_agent ./demo_agent
RUN uv sync --frozen --no-dev --all-packages
ENV PATH="/app/.venv/bin:$PATH" \
    DOWNSHIFT_DATA_DIR=/data \
    DOWNSHIFT_SEED_PATH=/app/server/seed/seed.json.gz \
    PORT=8000
VOLUME ["/data"]
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir server --host 0.0.0.0 --port ${PORT}"]
