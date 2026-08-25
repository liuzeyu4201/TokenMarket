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
# Harden OS packages and CPython tooling that Trivy flags (not application deps).
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade \
      "pip>=25.3" \
      "setuptools>=80" \
      "wheel>=0.46.2" \
      "jaraco.context>=6.1.0" \
    && rm -rf /root/.cache/pip

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/app /app/app

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=/app
ENV PORT=8002

# Trivy reports these in the copied venv / ensurepip wheels, not apt:
# CVE-2025-47273 setuptools 70.3.0; GHSA-6v7p-g79w-8964 msgpack 1.1.2.
RUN pip install --no-cache-dir --upgrade \
      "setuptools>=80" \
      "msgpack>=1.2.1" \
    && pip install --no-cache-dir --upgrade --target /app/.venv/lib/python3.11/site-packages \
      "setuptools>=80" \
      "msgpack>=1.2.1" \
    && rm -rf /usr/lib/python3.11/ensurepip /usr/local/lib/python3.11/ensurepip \
    && rm -rf /root/.cache/pip

RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -m uvicorn --version >/dev/null 2>&1 && python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health/live')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
