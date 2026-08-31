"""Price/route config pipeline. Active records are never patched in place."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.admin.errors import (
    APPROVAL_REQUIRED,
    MSG,
    PATCH_ACTIVE_DENIED,
    SIMULATE_FAILED,
    SIMULATE_REQUIRED,
    VALIDATION,
    AdminError,
)

PIPELINE_KINDS = frozenset({"price", "route"})
WRITE_ACTION = {
    "price": "price.publish",
    "route": "route.rollback",
}
READ_ACTION = {
    "price": "price.read",
    "route": "route.read",
}


@dataclass
class ConfigDraft:
    draft_id: str
    kind: str
    payload: dict[str, Any]
    status: str
    active_unchanged: bool = True
    sim_ok: bool = False
    version: int = 0
    base_version: int = 0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "kind": self.kind,
            "payload": self.payload,
            "status": self.status,
            "active_unchanged": self.active_unchanged,
            "sim_ok": self.sim_ok,
            "version": self.version,
            "base_version": self.base_version,
            "error": self.error,
        }


@dataclass
class ActiveConfig:
    version: int
    payload: dict[str, Any] = field(default_factory=dict)


class ConfigPipeline:
    def __init__(self) -> None:
        self._active: dict[str, ActiveConfig] = {
            "price": ActiveConfig(
                1, {"buyer_bps": 10000, "seller_max_bps": 8000}
            ),
            "route": ActiveConfig(
                1, {"weights": {"health": 40, "latency": 30, "price": 30}}
            ),
        }
        self._history: dict[str, list[ActiveConfig]] = {
            kind: [ActiveConfig(cfg.version, dict(cfg.payload))]
            for kind, cfg in self._active.items()
        }
        self._drafts: dict[str, ConfigDraft] = {}

    def active_version(self, kind: str) -> int:
        self._require_kind(kind)
        return self._active[kind].version

    def active(self, kind: str) -> dict[str, Any]:
        self._require_kind(kind)
        cfg = self._active[kind]
        return {"kind": kind, "version": cfg.version, "payload": dict(cfg.payload)}

    def create_draft(self, kind: str, payload: dict[str, Any]) -> ConfigDraft:
        self._require_kind(kind)
        if not isinstance(payload, dict):
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)
        draft = ConfigDraft(
            draft_id=str(uuid.uuid4()),
            kind=kind,
            payload=dict(payload),
            status="draft",
            base_version=self._active[kind].version,
        )
        self._drafts[draft.draft_id] = draft
        return draft

    def get(self, draft_id: str) -> ConfigDraft:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=404)
        return draft

    def diff(self, draft_id: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        before = self._active[draft.kind].payload
        after = draft.payload
        keys = sorted(set(before) | set(after))
        changes = []
        for key in keys:
            left = before.get(key)
            right = after.get(key)
            if left != right:
                changes.append({"path": key, "before": left, "after": right})
        return {
            "kind": draft.kind,
            "from_version": draft.base_version,
            "changes": changes,
        }

    def simulate(self, draft_id: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        ok, reason = self._simulate_ok(draft)
        draft.sim_ok = ok
        if ok:
            draft.status = "simulated"
            draft.error = ""
        else:
            draft.status = "failed"
            draft.error = reason
        return {
            "ok": ok,
            "reason": reason,
            "active_version": self.active_version(draft.kind),
            "active_unchanged": True,
        }

    def approve(self, draft_id: str) -> ConfigDraft:
        draft = self.get(draft_id)
        if not draft.sim_ok or draft.status not in {"simulated", "approved"}:
            raise AdminError(SIMULATE_REQUIRED, MSG[SIMULATE_REQUIRED], http_status=409)
        draft.status = "approved"
        return draft

    def publish(self, draft_id: str) -> dict[str, Any]:
        draft = self.get(draft_id)
        if draft.status == "failed" or not draft.sim_ok:
            raise AdminError(SIMULATE_FAILED, MSG[SIMULATE_FAILED], http_status=409)
        if draft.status != "approved":
            raise AdminError(APPROVAL_REQUIRED, MSG[APPROVAL_REQUIRED], http_status=409)
        current = self._active[draft.kind]
        nxt = ActiveConfig(current.version + 1, dict(draft.payload))
        self._history[draft.kind].append(nxt)
        self._active[draft.kind] = nxt
        draft.status = "published"
        draft.version = nxt.version
        draft.active_unchanged = False
        return self.active(draft.kind)

    def rollback(self, kind: str, to_version: int) -> dict[str, Any]:
        self._require_kind(kind)
        match = next(
            (snap for snap in self._history[kind] if snap.version == to_version),
            None,
        )
        if match is None:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=404)
        restored = ActiveConfig(match.version, dict(match.payload))
        self._active[kind] = restored
        return self.active(kind)

    def patch_active(self, kind: str, payload: dict[str, Any]) -> None:
        _ = (kind, payload)
        raise AdminError(PATCH_ACTIVE_DENIED, MSG[PATCH_ACTIVE_DENIED], http_status=409)

    def _require_kind(self, kind: str) -> None:
        if kind not in PIPELINE_KINDS:
            raise AdminError(VALIDATION, MSG[VALIDATION], http_status=400)

    def _simulate_ok(self, draft: ConfigDraft) -> tuple[bool, str]:
        payload = draft.payload
        if payload.get("invalid") is True:
            return False, "invalid payload"
        if draft.kind == "price":
            buyer = int(payload.get("buyer_bps", -1))
            seller = int(payload.get("seller_max_bps", 0))
            if buyer < 0 or buyer > 10000 or seller < 0 or seller > 10000:
                return False, "bps out of range"
            if buyer < seller:
                return False, "buyer_bps below seller_max_bps"
        if draft.kind == "route" and "weights" not in payload:
            return False, "missing weights"
        return True, "ok"
