"""Supply-mode lifecycle for Provider Connections (SF16)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Protocol

from app.domain.connections.models import ConnectionRecord, utcnow
from app.domain.connections.service import ConnectionError, ConnectionService
from app.domain.connections.store import ConnectionStore, VersionConflict

logger = logging.getLogger("api-service")

LIFECYCLES = frozenset(
    {
        "draft",
        "verified",
        "listed",
        "bound",
        "paused",
        "draining",
        "retired",
    }
)
LIVE = frozenset({"listed", "bound"})
MODE_OPEN = frozenset({"draft", "verified"})

ALLOWED = frozenset(
    {
        ("draft", "verified"),
        ("draft", "retired"),
        ("verified", "listed"),
        ("verified", "retired"),
        ("listed", "bound"),
        ("listed", "paused"),
        ("listed", "draining"),
        ("bound", "paused"),
        ("bound", "draining"),
        ("bound", "listed"),
        ("paused", "listed"),
        ("paused", "bound"),
        ("paused", "draining"),
        ("paused", "retired"),
        ("draining", "retired"),
    }
)


class DependencyLookup(Protocol):
    def blockers(self, connection_id: uuid.UUID) -> list[dict[str, str]]: ...


class EmptyDependencies:
    def blockers(self, connection_id: uuid.UUID) -> list[dict[str, str]]:
        return []


class CompositeDependencies:
    def __init__(self, *parts: DependencyLookup) -> None:
        self._parts = parts

    def blockers(self, connection_id: uuid.UUID) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for part in self._parts:
            out.extend(part.blockers(connection_id))
        return out


class BindingDependencies:
    def __init__(self, bindings: Any) -> None:
        self._bindings = bindings

    def blockers(self, connection_id: uuid.UUID) -> list[dict[str, str]]:
        if self._bindings is None:
            return []
        rows = self._bindings.list_by_connection(connection_id)
        active = [r for r in rows if r.status in ("active", "degraded")]
        if not active:
            return []
        return [
            {
                "code": "BINDING_ACTIVE",
                "detail": str(active[0].binding_id),
            }
        ]


class ScriptedDependencies:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, list[dict[str, str]]] = {}

    def blockers(self, connection_id: uuid.UUID) -> list[dict[str, str]]:
        return list(self.by_id.get(connection_id, []))


def transition(current: str, target: str) -> str:
    if current == target:
        return current
    if (current, target) not in ALLOWED:
        raise ConnectionError(
            "ILLEGAL_STATE_TRANSITION",
            "非法的生命周期转换",
            http_status=409,
        )
    return target


def admits_new(rec: ConnectionRecord) -> bool:
    return (
        rec.usable()
        and rec.lifecycle_state in LIVE
        and rec.health_state == "healthy"
        and rec.capability_version > 0
    )


class LifecycleService:
    def __init__(
        self,
        connections: ConnectionService,
        *,
        dependencies: DependencyLookup | None = None,
    ) -> None:
        self._conn = connections
        self._store: ConnectionStore = connections._store
        self._deps: DependencyLookup = (
            dependencies if dependencies is not None else EmptyDependencies()
        )

    def _persist(self, rec: ConnectionRecord, expected: str, request_id: str) -> None:
        rec.updated_at = utcnow()
        try:
            self._store.save_lifecycle(rec, expected)
        except VersionConflict as exc:
            raise ConnectionError(
                "VERSION_CONFLICT", "生命周期冲突，请重试", http_status=409
            ) from exc
        self._store.audit(
            seller_id=rec.seller_account_id,
            connection_id=rec.connection_id,
            event_type="connection.lifecycle",
            request_id=request_id,
            payload={
                "lifecycle_state": rec.lifecycle_state,
                "supply_mode": rec.supply_mode,
            },
        )

    def mark_verified(self, rec: ConnectionRecord, request_id: str) -> ConnectionRecord:
        if rec.lifecycle_state != "draft":
            return rec
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "verified")
        self._persist(rec, expected, request_id)
        return rec

    def set_mode(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        supply_mode: str,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        if rec.lifecycle_state not in MODE_OPEN:
            raise ConnectionError(
                "MODE_LOCKED", "上架后不可更改供给模式", http_status=409
            )
        if supply_mode not in ("shared", "dedicated"):
            raise ConnectionError("VALIDATION", "请求参数不合法", http_status=400)
        expected = rec.lifecycle_state
        rec.supply_mode = supply_mode
        self._persist(rec, expected, request_id)
        return rec

    def list_supply(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        if rec.lifecycle_state != "verified":
            raise ConnectionError(
                "ILLEGAL_STATE_TRANSITION",
                "仅已验证连接可上架",
                http_status=409,
            )
        if rec.health_state != "healthy" or rec.capability_version < 1:
            raise ConnectionError(
                "ILLEGAL_STATE_TRANSITION",
                "健康且具备能力快照后才能上架",
                http_status=409,
            )
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "listed")
        self._persist(rec, expected, request_id)
        return rec

    def pause(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "paused")
        started = time.monotonic()
        self._persist(rec, expected, request_id)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "connection_paused",
            extra={
                "connection_id": str(connection_id),
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            },
        )
        return rec

    def resume(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        target = (
            "bound"
            if rec.supply_mode == "dedicated" and rec.lifecycle_state == "paused"
            else "listed"
        )
        # paused dedicated without active binding should resume to listed
        deps = self._deps.blockers(connection_id)
        if rec.supply_mode == "dedicated" and any(
            b.get("code") == "BINDING_ACTIVE" for b in deps
        ):
            target = "bound"
        else:
            target = "listed"
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, target)
        self._persist(rec, expected, request_id)
        return rec

    def drain(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "draining")
        self._persist(rec, expected, request_id)
        return rec

    def retire(
        self,
        *,
        connection_id: uuid.UUID,
        seller_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ConnectionRecord:
        rec = self._conn.get(
            connection_id=connection_id,
            seller_id=seller_id,
            role=role,
            workspace=workspace,
        )
        blockers = self._deps.blockers(connection_id)
        if blockers:
            raise ConnectionError(
                blockers[0]["code"],
                "存在未解除的依赖",
                http_status=409,
                data={"blockers": blockers},
            )
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "retired")
        self._persist(rec, expected, request_id)
        return rec

    def ensure_deletable(self, connection_id: uuid.UUID) -> None:
        rec = self._store.get(connection_id)
        if rec is None:
            return
        if rec.lifecycle_state in LIVE | {"paused", "draining"}:
            blockers = self._deps.blockers(connection_id)
            if rec.lifecycle_state in LIVE | {"paused", "draining"}:
                blockers = blockers or [
                    {
                        "code": "ILLEGAL_STATE",
                        "detail": rec.lifecycle_state,
                    }
                ]
            if blockers:
                raise ConnectionError(
                    blockers[0]["code"],
                    "存在未解除的依赖",
                    http_status=409,
                    data={"blockers": blockers},
                )

    def mark_bound(self, connection_id: uuid.UUID, request_id: str) -> None:
        rec = self._store.get(connection_id)
        if rec is None or rec.supply_mode != "dedicated":
            return
        if rec.lifecycle_state == "listed":
            expected = rec.lifecycle_state
            rec.lifecycle_state = transition(expected, "bound")
            rec.seller_account_id = rec.seller_account_id
            self._persist(rec, expected, request_id)

    def mark_unbound(self, connection_id: uuid.UUID, request_id: str) -> None:
        rec = self._store.get(connection_id)
        if rec is None or rec.lifecycle_state != "bound":
            return
        expected = rec.lifecycle_state
        rec.lifecycle_state = transition(expected, "listed")
        self._persist(rec, expected, request_id)

    def list_routable(self, supply_mode: str) -> list[ConnectionRecord]:
        if supply_mode not in ("shared", "dedicated"):
            return []
        out: list[ConnectionRecord] = []
        for rec in self._store.list_all_active():
            if rec.supply_mode != supply_mode:
                continue
            if not admits_new(rec):
                continue
            out.append(rec)
        return out
