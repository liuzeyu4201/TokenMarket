"""Connection verify, catalog intersection, health hysteresis, probe budget."""

from __future__ import annotations

import logging
import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.domain.connections.models import (
    CapabilitySnapshot,
    ConnectionRecord,
    utcnow,
)
from app.domain.connections.service import ConnectionError, ConnectionService
from app.domain.connections.store import ConnectionStore
from app.domain.endpcatalog import CatalogError, load_catalog

logger = logging.getLogger("api-service")

SUCCESS_THRESHOLD = 2
FAIL_THRESHOLD = 3
DEFAULT_BUDGET = 8
DEFAULT_INTERVAL_S = 60.0
DEFAULT_JITTER_S = 15.0

AUTH_FAIL = frozenset({"invalid_credential", "forbidden", "region_mismatch"})
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]+)|Bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+", re.I
)


def redact_detail(text: str) -> str:
    clipped = (text or "")[:240]
    return _SECRET_RE.sub("[redacted]", clipped)


@dataclass
class ProbeOutcome:
    category: str
    discovered: list[dict[str, str]] = field(default_factory=list)
    quota_hint: str | None = None
    redacted_detail: str = ""


@dataclass(frozen=True)
class HealthFact:
    connection_id: uuid.UUID
    health_state: str
    reason: str | None
    checked_at: datetime | None
    capability_version: int
    routable: bool
    lifecycle_state: str = "draft"
    admits_new: bool = False


class VendorProbe(Protocol):
    def probe(
        self,
        *,
        provider: str,
        secret: str,
        base_url: str,
        region: str | None,
        location: str | None,
        project_number: str | None,
        request_id: str,
    ) -> ProbeOutcome: ...


class FailClosedProbe:
    def probe(
        self,
        *,
        provider: str,
        secret: str,
        base_url: str,
        region: str | None,
        location: str | None,
        project_number: str | None,
        request_id: str,
    ) -> ProbeOutcome:
        return ProbeOutcome(
            category="unavailable",
            redacted_detail="probe_unavailable",
        )


class ScriptedProbe:
    def __init__(self) -> None:
        self.by_secret: dict[str, ProbeOutcome] = {}

    def probe(
        self,
        *,
        provider: str,
        secret: str,
        base_url: str,
        region: str | None,
        location: str | None,
        project_number: str | None,
        request_id: str,
    ) -> ProbeOutcome:
        return self.by_secret.get(
            secret,
            ProbeOutcome(category="unavailable", redacted_detail="unscripted"),
        )


def catalog_stable_paths(
    provider: str, catalog: dict[str, Any] | None = None
) -> set[str]:
    try:
        data = catalog if catalog is not None else load_catalog()
    except CatalogError:
        return set()
    allowed: set[str] = set()
    for rec in data.get("records") or []:
        if not isinstance(rec, dict):
            continue
        if rec.get("provider") != provider:
            continue
        if rec.get("stability") != "stable":
            continue
        tags = rec.get("capability_tags") or []
        if "control_plane" in tags:
            continue
        path = rec.get("path_template")
        if isinstance(path, str) and path:
            allowed.add(path)
    return allowed


def intersect_catalog(
    provider: str,
    discovered: list[dict[str, str]],
    catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    allowed = catalog_stable_paths(provider, catalog)
    out: list[dict[str, Any]] = []
    for item in discovered:
        path = item.get("path_template") or item.get("endpoint") or ""
        if path not in allowed:
            continue
        out.append(
            {
                "protocol": item.get("protocol") or provider,
                "path_template": path,
                "model": item.get("model"),
                "region": item.get("region"),
            }
        )
    return out


def apply_health(
    rec: ConnectionRecord,
    category: str,
    *,
    immediate: bool,
    now: datetime | None = None,
) -> None:
    stamp = now or utcnow()
    rec.health_reason = category
    rec.health_checked_at = stamp
    rec.last_probe_at = stamp
    if category == "ok":
        rec.consecutive_successes += 1
        rec.consecutive_failures = 0
        if immediate or rec.consecutive_successes >= SUCCESS_THRESHOLD:
            rec.health_state = "healthy"
        elif rec.health_state == "unhealthy":
            rec.health_state = "degraded"
    elif category == "rate_limited":
        rec.consecutive_successes = 0
        rec.health_state = "degraded"
    elif category in AUTH_FAIL:
        rec.consecutive_successes = 0
        rec.consecutive_failures += 1
        rec.health_state = "unhealthy"
    elif category == "unavailable":
        if rec.health_state != "healthy":
            rec.health_state = "unknown"
        rec.health_reason = "unavailable"
    else:
        rec.consecutive_successes = 0
        rec.consecutive_failures += 1
        if immediate or rec.consecutive_failures >= FAIL_THRESHOLD:
            rec.health_state = "unhealthy"
        elif rec.health_state == "healthy":
            rec.health_state = "degraded"


def schedule_next(
    rec: ConnectionRecord,
    *,
    now: datetime | None = None,
    interval_s: float = DEFAULT_INTERVAL_S,
    jitter_s: float = DEFAULT_JITTER_S,
) -> None:
    stamp = now or utcnow()
    delay = interval_s + random.uniform(0, max(0.0, jitter_s))
    rec.next_probe_at = stamp + timedelta(seconds=delay)


class HealthService:
    def __init__(
        self,
        connections: ConnectionService,
        probe: VendorProbe | None = None,
        *,
        budget: int = DEFAULT_BUDGET,
        catalog: dict[str, Any] | None = None,
    ) -> None:
        self._conn = connections
        self._probe: VendorProbe = probe if probe is not None else FailClosedProbe()
        self._store: ConnectionStore = connections._store
        self._budget = max(1, budget)
        self._catalog = catalog

    def verify(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
        immediate: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        secret = self._conn.unwrap(
            connection_id=connection_id,
            purpose="verify",
            request_id=request_id,
            actor_seller_id=seller_id,
        )
        outcome = self._probe.probe(
            provider=rec.provider,
            secret=secret,
            base_url=rec.base_url,
            region=rec.region,
            location=rec.location,
            project_number=rec.project_number,
            request_id=request_id,
        )
        apply_health(rec, outcome.category, immediate=immediate, now=now)
        schedule_next(rec, now=now or utcnow())
        caps: list[dict[str, Any]] = []
        if outcome.category == "ok":
            caps = intersect_catalog(rec.provider, outcome.discovered, self._catalog)
            ver = self._store.max_snapshot_version(rec.connection_id) + 1
            self._store.save_snapshot(
                connection_id=rec.connection_id,
                version=ver,
                capabilities=caps,
            )
            rec.capability_version = ver
        rec.updated_at = utcnow()
        self._store.save_health(rec)
        if outcome.category == "ok" and rec.lifecycle_state == "draft":
            rec.lifecycle_state = "verified"
            self._store.save_lifecycle(rec, "draft")
        detail = redact_detail(outcome.redacted_detail)
        self._store.audit(
            seller_id=seller_id,
            connection_id=connection_id,
            event_type="connection.verified",
            request_id=request_id,
            payload={
                "category": outcome.category,
                "health_state": rec.health_state,
                "source": "manual" if immediate else "scheduled",
                "detail": detail,
            },
        )
        logger.info(
            "connection_verified",
            extra={
                "connection_id": str(connection_id),
                "request_id": request_id,
                "category": outcome.category,
                "health_state": rec.health_state,
            },
        )
        return {
            "connection": rec,
            "category": outcome.category,
            "capabilities": caps,
            "health_state": rec.health_state,
            "health_reason": rec.health_reason,
            "detail": detail,
        }

    def list_snapshots(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> list[CapabilitySnapshot]:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        return self._store.list_snapshots(rec.connection_id)

    def health_fact(self, connection_id: uuid.UUID) -> HealthFact | None:
        rec = self._store.get(connection_id)
        if rec is None or rec.status == "deleted":
            return None
        routable = rec.health_state == "healthy" and rec.capability_version > 0
        from app.domain.connections.lifecycle import admits_new

        return HealthFact(
            connection_id=rec.connection_id,
            health_state=rec.health_state,
            reason=rec.health_reason,
            checked_at=rec.health_checked_at,
            capability_version=rec.capability_version,
            routable=routable,
            lifecycle_state=rec.lifecycle_state,
            admits_new=admits_new(rec),
        )

    def public_health(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> dict[str, Any]:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        fact = self.health_fact(rec.connection_id)
        if fact is None:
            raise ConnectionError("NOT_FOUND", "资源不存在", http_status=404)
        return {
            "connection_id": str(fact.connection_id),
            "health_state": fact.health_state,
            "reason": fact.reason,
            "checked_at": fact.checked_at.isoformat() if fact.checked_at else None,
            "capability_version": fact.capability_version,
            "routable": fact.routable,
            "lifecycle_state": fact.lifecycle_state,
            "admits_new": fact.admits_new,
        }

    def tick(self, now: datetime | None = None) -> int:
        stamp = now or datetime.now(timezone.utc)
        due = self._store.list_probe_due(stamp, limit=self._budget)
        processed = 0
        for rec in due[: self._budget]:
            try:
                self.verify(
                    connection_id=rec.connection_id,
                    seller_id=rec.seller_account_id,
                    role="seller",
                    workspace="seller",
                    request_id=f"sched-{rec.connection_id}",
                    immediate=False,
                    now=stamp,
                )
            except ConnectionError:
                schedule_next(rec, now=stamp)
                self._store.save_health(rec)
            processed += 1
        return processed
