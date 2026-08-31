"""Append-only hash-chained admin audit."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain.admin.errors import IMMUTABLE_AUDIT, MSG, AdminError
from app.domain.admin.redact import redact


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class AuditRecord:
    event_id: str
    actor_id: str
    role: str
    action: str
    target: str
    reason: str
    request_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    result: str
    source: str
    prev_hash: str
    record_hash: str
    created_at: datetime = field(default_factory=_now)


class AuditLog:
    def __init__(self) -> None:
        self._rows: list[AuditRecord] = []
        self._tip = "0" * 64

    def append(
        self,
        *,
        actor_id: str,
        role: str,
        action: str,
        target: str,
        reason: str,
        request_id: str,
        result: str,
        source: str = "admin-service",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditRecord:
        payload = {
            "actor_id": actor_id,
            "role": role,
            "action": action,
            "target": target,
            "reason": reason,
            "request_id": request_id,
            "before": redact(before or {}),
            "after": redact(after or {}),
            "result": result,
            "source": source,
            "prev_hash": self._tip,
        }
        material = (self._tip + _canonical(payload)).encode("utf-8")
        digest = hashlib.sha256(material).hexdigest()
        rec = AuditRecord(
            event_id=str(uuid.uuid4()),
            actor_id=actor_id,
            role=role,
            action=action,
            target=target,
            reason=reason,
            request_id=request_id,
            before=payload["before"],
            after=payload["after"],
            result=result,
            source=source,
            prev_hash=self._tip,
            record_hash=digest,
        )
        self._rows.append(rec)
        self._tip = digest
        return rec

    def list(self) -> list[AuditRecord]:
        return list(self._rows)

    def mutate(self, event_id: str) -> None:
        raise AdminError(IMMUTABLE_AUDIT, MSG[IMMUTABLE_AUDIT], http_status=409)

    def delete(self, event_id: str) -> None:
        raise AdminError(IMMUTABLE_AUDIT, MSG[IMMUTABLE_AUDIT], http_status=409)

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for rec in self._rows:
            payload = {
                "actor_id": rec.actor_id,
                "role": rec.role,
                "action": rec.action,
                "target": rec.target,
                "reason": rec.reason,
                "request_id": rec.request_id,
                "before": rec.before,
                "after": rec.after,
                "result": rec.result,
                "source": rec.source,
                "prev_hash": rec.prev_hash,
            }
            material = (prev + _canonical(payload)).encode("utf-8")
            digest = hashlib.sha256(material).hexdigest()
            if rec.prev_hash != prev or rec.record_hash != digest:
                return False
            prev = rec.record_hash
        return True
