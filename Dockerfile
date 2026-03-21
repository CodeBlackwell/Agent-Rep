FROM python:3.12-slim

# uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY scripts/ scripts/

EXPOSE 7860

CMD ["uv", "run", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "7860"]
