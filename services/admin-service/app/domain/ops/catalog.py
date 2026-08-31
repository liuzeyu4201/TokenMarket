"""Virtual paginated ops catalog. Never materializes the full table."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

from app.domain.admin.errors import MSG, NOT_FOUND, VALIDATION, AdminError
from app.domain.admin.redact import redact

KINDS = (
    "user",
    "session",
    "connection",
    "project",
    "price",
    "route",
    "ledger",
    "alert",
    "audit",
)

KIND_ACTION: dict[str, str] = {
    "user": "user.lookup",
    "session": "user.lookup",
    "connection": "connection.view_health",
    "project": "project.lookup",
    "price": "price.read",
    "route": "route.read",
    "ledger": "ledger.read",
    "alert": "alert.read",
    "audit": "audit.read",
}

TOTALS: dict[str, int] = {
    "user": 5_000,
    "session": 2_000,
    "connection": 100_000,
    "project": 8_000,
    "price": 200,
    "route": 200,
    "ledger": 10_000,
    "alert": 500,
    "audit": 3_000,
}

PREFIX: dict[str, str] = {
    "user": "user",
    "session": "sess",
    "connection": "conn",
    "project": "proj",
    "price": "price",
    "route": "route",
    "ledger": "led",
    "alert": "alrt",
    "audit": "aud",
}

CONNECTION_TOTAL = TOTALS["connection"]
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
STALE_AFTER = timedelta(minutes=5)

_SECRET_PARTS = (
    "secret",
    "password",
    "token",
    "credential",
    "api_key",
    "apikey",
    "plaintext",
    "authorization",
    "cookie",
)

_PROTOCOLS = ("openai", "anthropic", "vertex")
_EXPORT_CONN = frozenset({"id", "fingerprint", "capabilities", "health", "freshness", "protocol"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(kind: str, index: int) -> str:
    material = f"{kind}:{index}:v1".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _item_id(kind: str, index: int) -> str:
    return f"{PREFIX[kind]}-{index:06d}"


def _parse_index(kind: str, item_id: str) -> int:
    prefix = PREFIX[kind] + "-"
    if not item_id.startswith(prefix):
        raise AdminError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
    try:
        index = int(item_id.removeprefix(prefix))
    except ValueError as exc:
        raise AdminError(NOT_FOUND, MSG[NOT_FOUND], http_status=404) from exc
    if index < 0 or index >= TOTALS[kind]:
        raise AdminError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
    return index


def _offset(cursor: str) -> int:
    if not cursor:
        return 0
    try:
        value = int(cursor)
    except ValueError as exc:
        raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400) from exc
    if value < 0:
        raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
    return value


def _strip_secrets(value: Any) -> Any:
    cleaned = redact(value)
    if isinstance(cleaned, dict):
        out: dict[str, Any] = {}
        for key, item in cleaned.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SECRET_PARTS):
                continue
            out[key] = _strip_secrets(item)
        return out
    if isinstance(cleaned, list):
        return [_strip_secrets(item) for item in cleaned]
    if isinstance(cleaned, str):
        lowered = cleaned.lower()
        if any(part in lowered for part in ("sk-", "plaintext", "begin private")):
            return "[redacted]"
    return cleaned


@dataclass
class OpsPage:
    kind: str
    items: list[dict[str, Any]]
    next_cursor: str | None
    total: int
    freshness: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "items": self.items,
            "next_cursor": self.next_cursor,
            "total": self.total,
            "freshness": self.freshness,
        }


class OpsCatalog:
    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        stale_after: timedelta = STALE_AFTER,
    ) -> None:
        self._now = now or _now
        self._stale_after = stale_after
        self._probes: dict[str, datetime] = {}
        self._poison: dict[tuple[str, str], dict[str, Any]] = {}

    def poison(self, kind: str, item_id: str, extra: dict[str, Any]) -> None:
        self._poison[(kind, item_id)] = dict(extra)

    def mark_probe(self, item_id: str, at: datetime) -> None:
        self._probes[item_id] = at

    def action_for(self, kind: str) -> str:
        if kind not in KIND_ACTION:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        return KIND_ACTION[kind]

    def list_page(
        self,
        kind: str,
        *,
        cursor: str = "",
        limit: int = DEFAULT_LIMIT,
        q: str = "",
    ) -> OpsPage:
        if kind not in KIND_ACTION:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        size = DEFAULT_LIMIT if limit < 1 else min(int(limit), MAX_LIMIT)
        total = TOTALS[kind]
        if q.strip():
            items = self._search(kind, q.strip(), size)
            return OpsPage(
                kind=kind,
                items=items,
                next_cursor=None,
                total=len(items),
                freshness="live",
            )
        start = _offset(cursor)
        end = min(start + size, total)
        items = [self._item(kind, index) for index in range(start, end)]
        nxt = str(end) if end < total else None
        return OpsPage(
            kind=kind,
            items=items,
            next_cursor=nxt,
            total=total,
            freshness="live",
        )

    def get(self, kind: str, item_id: str) -> dict[str, Any]:
        index = _parse_index(kind, item_id)
        item = self._item(kind, index)
        return {
            "item": item,
            "status": item.get("status") or item.get("health"),
            "version": 1,
            "related": self._related(kind, item_id),
            "alerts": self._alerts(kind, item),
            "audit": self._timeline(kind, item_id),
            "freshness": item.get("freshness", "live"),
        }

    def export(self, kind: str, item_id: str) -> dict[str, Any]:
        item = self.get(kind, item_id)["item"]
        if kind == "connection":
            return {k: item[k] for k in _EXPORT_CONN if k in item}
        return cast(dict[str, Any], _strip_secrets(item))

    def _search(self, kind: str, q: str, limit: int) -> list[dict[str, Any]]:
        prefix = PREFIX[kind] + "-"
        if q.startswith(prefix):
            try:
                index = _parse_index(kind, q)
            except AdminError:
                return []
            return [self._item(kind, index)]
        return [][:limit]

    def _item(self, kind: str, index: int) -> dict[str, Any]:
        item_id = _item_id(kind, index)
        fp = _fingerprint(kind, index)
        if kind == "connection":
            item = self._connection(index, item_id, fp)
        elif kind == "user":
            item = {
                "id": item_id,
                "phone_masked": "*******0000",
                "role": "buyer" if index % 2 == 0 else "seller",
                "status": "active",
                "freshness": "live",
            }
        elif kind == "session":
            item = {
                "id": item_id,
                "user_id": _item_id("user", index % TOTALS["user"]),
                "status": "active",
                "freshness": "live",
            }
        elif kind == "project":
            item = {
                "id": item_id,
                "mode": "shared" if index % 2 == 0 else "dedicated",
                "status": "active",
                "freshness": "live",
            }
        elif kind == "price":
            item = {
                "id": item_id,
                "version": 1,
                "status": "active",
                "buyer_bps": 10000,
                "freshness": "live",
            }
        elif kind == "route":
            item = {
                "id": item_id,
                "version": 1,
                "status": "active",
                "freshness": "live",
            }
        elif kind == "ledger":
            item = {
                "id": item_id,
                "state": "unresolved" if index % 11 == 0 else "settled",
                "amount": (index % 97) + 1,
                "freshness": "live",
            }
        elif kind == "alert":
            item = {
                "id": item_id,
                "severity": "info" if index % 3 else "warn",
                "status": "open",
                "freshness": "live",
            }
        else:
            item = {
                "id": item_id,
                "action": "audit.read",
                "result": "ok",
                "freshness": "live",
            }
        extra = self._poison.get((kind, item_id))
        if extra:
            item = {**item, **extra}
        return cast(dict[str, Any], _strip_secrets(item))

    def _connection(self, index: int, item_id: str, fingerprint: str) -> dict[str, Any]:
        probed = self._probes.get(item_id)
        if probed is None:
            probed = self._now() - timedelta(seconds=(index % 17) * 60)
        age = self._now() - probed
        stale = age > self._stale_after
        if stale:
            health = "unknown"
            freshness = "stale"
        else:
            health = "degraded" if index % 5 == 0 else "healthy"
            freshness = "live"
        return {
            "id": item_id,
            "fingerprint": fingerprint,
            "capabilities": ["chat"],
            "health": health,
            "freshness": freshness,
            "protocol": _PROTOCOLS[index % 3],
        }

    def _related(self, kind: str, item_id: str) -> list[dict[str, str]]:
        if kind == "connection":
            return [{"kind": "project", "id": "proj-000000"}]
        if kind == "project":
            return [{"kind": "connection", "id": "conn-000000"}]
        return [{"kind": kind, "id": item_id}]

    def _alerts(self, kind: str, item: dict[str, Any]) -> list[dict[str, str]]:
        if item.get("freshness") in {"stale", "unknown"}:
            return [{"id": "alrt-stale", "summary": "健康探测过期"}]
        if kind == "ledger" and item.get("state") == "unresolved":
            return [{"id": "alrt-unresolved", "summary": "账本未决"}]
        return []

    def _timeline(self, kind: str, item_id: str) -> list[dict[str, str]]:
        return [
            {
                "at": self._now().isoformat(),
                "action": KIND_ACTION[kind],
                "target": item_id,
                "result": "ok",
            }
        ]
