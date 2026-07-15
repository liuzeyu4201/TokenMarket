# Build stage
FROM python:3.11.15-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv==0.11.3 && uv sync --frozen --no-dev

COPY app ./app

# Runtime stage
FROM python:3.11.15-slim

WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/app /app/app

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=/app
ENV PORT=8000

RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -m uvicorn --version >/dev/null 2>&1 && python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
