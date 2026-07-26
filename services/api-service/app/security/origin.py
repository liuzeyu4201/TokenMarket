"""Browser Origin allowlist checks for auth write endpoints."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_origin(origin: str) -> str | None:
    """Return scheme://host[:port] or None if malformed / null."""
    if not origin or not isinstance(origin, str):
        return None
    text = origin.strip()
    if not text or text.lower() == "null":
        return None
    if "://" not in text:
        return None
    try:
        parsed = urlparse(text)
    except Exception:  # noqa: BLE001
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.hostname:
        return None
    # Reject wildcards and userinfo.
    if "*" in text or parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower()
    port = parsed.port
    if port is None:
        return f"{parsed.scheme}://{host}"
    return f"{parsed.scheme}://{host}:{port}"


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    """Exact match against allowlist after normalization."""
    normalized = normalize_origin(origin or "")
    if normalized is None:
        return False
    allowed_set = {normalize_origin(a) for a in allowed if a}
    allowed_set.discard(None)
    return normalized in allowed_set
