FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

# postgresql-client provides pg_isready, used by entrypoint.sh to wait for
# the database instead of an arbitrary sleep.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first, separately from app code, so this layer is
# cached and reused as long as pyproject.toml/uv.lock don't change.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY . .
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
