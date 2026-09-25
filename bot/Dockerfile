FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first, separately from app code, so this layer is
# cached and reused as long as pyproject.toml/uv.lock don't change.
# Production images pass UV_SYNC_FLAGS=--no-dev to leave out test tooling.
ARG UV_SYNC_FLAGS=""
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project ${UV_SYNC_FLAGS}

COPY . .

CMD ["uv", "run", "python", "-m", "app.main"]
