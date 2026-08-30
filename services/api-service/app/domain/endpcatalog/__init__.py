"""Endpoint Catalog 主版本门禁（权威匹配在 proxy-gateway）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CATALOG_MAJOR = 1


class CatalogError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _walk_catalog(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(8):
        candidate = (
            cur / "shared" / "contracts" / "endpoint-catalog" / "v1" / "catalog.json"
        )
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def catalog_path() -> Path:
    env = os.environ.get("TOKENMARKET_ENDPOINT_CATALOG", "").strip()
    if env:
        return Path(env)
    found = _walk_catalog(Path(__file__).resolve().parent)
    if found is None:
        raise CatalogError("CATALOG_LOAD_FAILED", "catalog file not found")
    return found


def expected_major() -> int:
    raw = os.environ.get("TOKENMARKET_CATALOG_MAJOR", "").strip()
    if not raw:
        return CATALOG_MAJOR
    try:
        return int(raw)
    except ValueError as exc:
        raise CatalogError(
            "CATALOG_VERSION_MISMATCH", "invalid TOKENMARKET_CATALOG_MAJOR"
        ) from exc


def load_catalog(
    path: Path | None = None, want_major: int | None = None
) -> dict[str, Any]:
    target = path or catalog_path()
    major = CATALOG_MAJOR if want_major is None else want_major
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError("CATALOG_LOAD_FAILED", "catalog file not found") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError("CATALOG_LOAD_FAILED", "invalid json") from exc
    if not isinstance(data, dict) or not data.get("records"):
        raise CatalogError("CATALOG_LOAD_FAILED", "empty catalog")
    if int(data.get("catalog_major", -1)) != major:
        raise CatalogError(
            "CATALOG_VERSION_MISMATCH",
            f"catalog_major {data.get('catalog_major')} != {major}",
        )
    return data


def must_load() -> dict[str, Any]:
    return load_catalog(want_major=expected_major())
