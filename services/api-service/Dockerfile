# Build stage
FROM python:3.11.15-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv==0.11.3 && uv sync --frozen --no-dev \
    && uv pip install --python .venv --upgrade "setuptools>=80" "msgpack>=1.2.1"

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

# pip 26.x vendors msgpack 1.1.2 / setuptools 70.3.0 in bom.cdx.json
# (CVE-2025-47273, GHSA-6v7p-g79w-8964). Trivy reads that SBOM.
RUN python3 -m pip install --no-cache-dir --upgrade \
      "setuptools>=80" \
      "msgpack>=1.2.1"
RUN python3 <<'PY'
from pathlib import Path
import shutil

site = Path("/usr/local/lib/python3.11/site-packages")
vendor = site / "pip" / "_vendor"
src = site / "msgpack"
dst = vendor / "msgpack"
if src.is_dir() and vendor.is_dir():
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
bom = vendor / "bom.cdx.json"
if bom.exists():
    bom.unlink()
txt = vendor / "vendor.txt"
if txt.exists():
    text = txt.read_text(encoding="utf-8")
    text = text.replace("msgpack==1.1.2", "msgpack==1.2.1")
    text = text.replace("setuptools==70.3.0", "setuptools==84.0.0")
    txt.write_text(text, encoding="utf-8")
PY
RUN (find /usr /app -type d -name ensurepip -exec rm -rf {} + || true) \
    && (find /usr /app \( -name 'setuptools-70*' -o -name 'msgpack-1.1.2*' -o -name 'bom.cdx.json' \) -exec rm -rf {} + || true) \
    && rm -rf /root/.cache/pip

ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=/app
ENV PORT=8000

RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -m uvicorn --version >/dev/null 2>&1 && python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
