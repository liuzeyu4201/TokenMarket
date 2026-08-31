"""Project test-quota budget, admit, guide, and usage filters."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from app.domain.authorization.workspace import effective_role
from app.domain.budget.errors import (
    FORBIDDEN_ROLE,
    HARD_LIMIT,
    MSG,
    VALIDATION,
    BudgetError,
)
from app.domain.budget.ports import LedgerView, MemoryLedgerView, UsageRow
from app.domain.budget.samples import CHECKLIST, SAMPLES
from app.domain.projects.service import ProjectService


@dataclass
class BudgetPolicy:
    project_id: str
    hard_minor: int
    soft_minor: int
    key_id: str | None = None


class BudgetService:
    def __init__(
        self,
        ledger: LedgerView | None = None,
        projects: ProjectService | None = None,
        bindings: object | None = None,
        keys: object | None = None,
    ) -> None:
        self._ledger: LedgerView = ledger if ledger is not None else MemoryLedgerView()
        self._projects = projects
        self._bindings = bindings
        self._keys = keys
        self._policies: dict[tuple[str, str | None], BudgetPolicy] = {}
        self._pending: dict[str, int] = {}
        self._lock = threading.RLock()

    def _require_buyer(self, role: str, workspace: str | None) -> None:
        if workspace is None:
            if role not in ("buyer", "both"):
                raise BudgetError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)
            return
        if effective_role(role, workspace) != "buyer":
            raise BudgetError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)

    def _owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        if self._projects is None:
            return
        rec = self._projects._owned(project_id, owner_id)
        _ = rec

    def put_policy(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        hard_minor: int,
        soft_minor: int,
        key_id: str | None = None,
    ) -> BudgetPolicy:
        self._require_buyer(role, workspace)
        self._owned(project_id, owner_id)
        if hard_minor < 0 or soft_minor < 0 or soft_minor > hard_minor:
            raise BudgetError(VALIDATION, MSG[VALIDATION], http_status=400)
        pol = BudgetPolicy(
            project_id=str(project_id),
            hard_minor=hard_minor,
            soft_minor=soft_minor,
            key_id=key_id,
        )
        self._policies[(str(project_id), key_id)] = pol
        return pol

    def overview(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        key_id: str | None = None,
    ) -> dict[str, object]:
        self._require_buyer(role, workspace)
        self._owned(project_id, owner_id)
        view = self._ledger.overview(str(project_id))
        pol = self._policy(str(project_id), key_id)
        used = view.reserved + view.settled + view.unresolved
        warning = None
        if pol is not None and view.available <= pol.soft_minor:
            warning = "SOFT_LIMIT"
        return {
            "available": view.available,
            "reserved": view.reserved,
            "settled": view.settled,
            "unresolved": view.unresolved,
            "hard_minor": pol.hard_minor if pol else None,
            "soft_minor": pol.soft_minor if pol else None,
            "used": used,
            "warning": warning,
            "note": "预算不是最终成本上限；reservation 之后可能异步调整。未决不是 0 成本。",
        }

    def admit(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        amount_minor: int,
        key_id: str | None = None,
    ) -> dict[str, object]:
        self._require_buyer(role, workspace)
        self._owned(project_id, owner_id)
        if amount_minor <= 0:
            raise BudgetError(VALIDATION, MSG[VALIDATION], http_status=400)
        pid = str(project_id)
        with self._lock:
            view = self._ledger.overview(pid)
            pol = self._policy(pid, key_id)
            pending = self._pending.get(pid, 0)
            booked = view.reserved + view.settled + view.unresolved + pending
            ledger_room = view.available - pending
            hard_room = ledger_room
            if pol is not None:
                hard_room = pol.hard_minor - booked
            room = min(ledger_room, hard_room)
            if amount_minor > room:
                raise BudgetError(HARD_LIMIT, MSG[HARD_LIMIT])
            self._pending[pid] = pending + amount_minor
            remaining_after = room - amount_minor
            warning = None
            if pol is not None and remaining_after <= pol.soft_minor:
                warning = "SOFT_LIMIT"
            return {
                "admitted": True,
                "amount_minor": amount_minor,
                "warning": warning,
            }

    def usage(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        key_id: str | None = None,
        status: str | None = None,
    ) -> list[UsageRow]:
        self._require_buyer(role, workspace)
        self._owned(project_id, owner_id)
        rows = self._ledger.overview(str(project_id)).requests
        out: list[UsageRow] = []
        for row in rows:
            if key_id and row.key_id != key_id:
                continue
            if status and row.status != status:
                continue
            out.append(row)
        return out

    def guide(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> dict[str, object]:
        self._require_buyer(role, workspace)
        self._owned(project_id, owner_id)
        binding_done = False
        if self._bindings is not None:
            fn = getattr(self._bindings, "has_enabled_binding", None)
            if callable(fn):
                binding_done = any(
                    fn(owner_id=owner_id, project_id=project_id, protocol=p)
                    for p in ("openai", "anthropic", "vertex")
                )
        key_done = False
        if self._keys is not None:
            listed = getattr(self._keys, "list_mine", None)
            if callable(listed):
                try:
                    items = listed(buyer_id=owner_id, role=role)
                except TypeError:
                    items = []
                key_done = any(
                    str(getattr(i, "project_id", "")) == str(project_id) for i in items
                )
            elif isinstance(self._keys, list):
                key_done = bool(self._keys)
        view = self._ledger.overview(str(project_id))
        result_done = view.settled > 0 or any(
            r.status == "consumed" for r in view.requests
        )
        steps = []
        done_map = {
            "binding": binding_done,
            "key": key_done,
            "sample": binding_done and key_done,
            "result": result_done,
        }
        for sid, title in CHECKLIST:
            steps.append({"id": sid, "title": title, "done": done_map[sid]})
        return {
            "checklist": steps,
            "samples": SAMPLES,
            "disclaimer": "测试额度不可购买、转让、兑换或提现。",
        }

    def _policy(self, project_id: str, key_id: str | None) -> BudgetPolicy | None:
        if key_id and (project_id, key_id) in self._policies:
            return self._policies[(project_id, key_id)]
        return self._policies.get((project_id, None))
