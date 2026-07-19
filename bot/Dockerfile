FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first, separately from app code, so this layer is
# cached and reused as long as pyproject.toml/uv.lock don't change.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY . .

CMD ["uv", "run", "python", "app/main.py"]
