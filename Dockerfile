# Single-stage - unlike the frontend's multi-stage build, there's no
# separate compile step to discard afterward (no node_modules/dist split
# to trim); uv's own venv is the only thing that needs to end up in the
# final image.
FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY scripts ./scripts

# fastapi run - the production CLI mode (uvicorn under the hood, no
# auto-reload/dev-only behavior), not `fastapi dev` which local dev uses.
CMD ["uv", "run", "fastapi", "run", "src/bank_platform/main.py", "--host", "0.0.0.0", "--port", "8000"]
