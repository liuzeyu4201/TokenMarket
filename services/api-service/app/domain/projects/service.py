"""Project lifecycle rules."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Sequence

from app.domain.authorization.workspace import effective_role
from app.domain.projects.admission import allows_new_proxy
from app.domain.projects.binding import BindingLookup, EmptyBindingLookup
from app.domain.projects.codes import (
    BLOCKER_KINDS,
    DELETE_BLOCKED,
    FORBIDDEN_ROLE,
    IDEMPOTENCY_CONFLICT,
    ILLEGAL_STATE_TRANSITION,
    MODE_IMMUTABLE,
    MODES,
    MSG,
    NAME_CONFLICT,
    NOT_FOUND,
    PROTOCOLS,
    PROVIDER_BINDING_REQUIRED,
    VALIDATION,
)
from app.domain.projects.models import ProjectRecord, ProtocolState, utcnow
from app.domain.projects.state import next_status
from app.domain.projects.store import MemoryProjectStore, NameConflict, ProjectStore

logger = logging.getLogger("api-service")


class ProjectError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int,
        data: object | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data
        super().__init__(message)


def normalize_name(display_name: str) -> str:
    return display_name.strip().lower()


def _digest(display_name: str, mode: str, protocols: Sequence[str]) -> str:
    joined = "|".join([normalize_name(display_name), mode, *sorted(protocols)])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class ProjectService:
    def __init__(
        self,
        store: ProjectStore | None = None,
        binding: BindingLookup | None = None,
    ) -> None:
        self._store: ProjectStore = store if store is not None else MemoryProjectStore()
        self._binding: BindingLookup = (
            binding if binding is not None else EmptyBindingLookup()
        )

    def _require_buyer(self, role: str, workspace: str | None) -> None:
        if workspace is None:
            if role not in ("buyer", "both"):
                raise ProjectError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)
            return
        if effective_role(role, workspace) != "buyer":
            raise ProjectError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)

    def _owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> ProjectRecord:
        rec = self._store.get(project_id)
        if (
            rec is None
            or rec.owner_account_id != owner_id
            or rec.deleted_at is not None
        ):
            raise ProjectError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        return rec

    def _validate_name(self, display_name: str) -> str:
        name = display_name.strip()
        if not name or len(name) > 128:
            raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
        return name

    def _validate_protocols(self, protocols: Sequence[str]) -> list[str]:
        seen: list[str] = []
        for p in protocols:
            if p not in PROTOCOLS:
                raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
            if p not in seen:
                seen.append(p)
        if not seen:
            raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
        return seen

    def create(
        self,
        *,
        owner_id: uuid.UUID,
        display_name: str,
        mode: str,
        enabled_protocols: Sequence[str],
        role: str,
        workspace: str | None,
        request_id: str,
        idempotency_key: str | None = None,
        preview_opt_in: bool = False,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        name = self._validate_name(display_name)
        if mode not in MODES:
            raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
        protos = self._validate_protocols(enabled_protocols)
        digest = _digest(name, mode, protos)
        if idempotency_key:
            existing = self._store.get_idempotency(owner_id, idempotency_key)
            if existing is not None:
                prev_digest, prev_id = existing
                if prev_digest != digest:
                    raise ProjectError(
                        IDEMPOTENCY_CONFLICT,
                        MSG[IDEMPOTENCY_CONFLICT],
                        http_status=409,
                    )
                if prev_id is not None:
                    rec = self._store.get(prev_id)
                    if rec is not None:
                        return rec
        now = utcnow()
        rec = ProjectRecord(
            project_id=uuid.uuid4(),
            owner_account_id=owner_id,
            display_name=name,
            name_normalized=normalize_name(name),
            mode=mode,
            status="draft",
            created_at=now,
            updated_at=now,
            preview_opt_in=bool(preview_opt_in),
            protocols=[
                ProtocolState(protocol=p, enabled=True, enabled_at=now) for p in protos
            ],
        )
        try:
            self._store.create(rec)
        except (NameConflict, RuntimeError) as exc:
            if isinstance(exc, NameConflict) or "unique" in str(exc).lower():
                raise ProjectError(
                    NAME_CONFLICT, MSG[NAME_CONFLICT], http_status=409
                ) from exc
            raise
        if idempotency_key:
            self._store.put_idempotency(
                owner_id, idempotency_key, digest, rec.project_id
            )
        self._store.audit(
            owner_id=owner_id,
            project_id=rec.project_id,
            event_type="project.created",
            request_id=request_id,
            payload={"mode": mode, "status": rec.status},
        )
        logger.info(
            "project_created",
            extra={
                "owner_account_id": str(owner_id),
                "project_id": str(rec.project_id),
                "request_id": request_id,
            },
        )
        return rec

    def get(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        return self._owned(project_id, owner_id)

    def list_mine(
        self, *, owner_id: uuid.UUID, role: str, workspace: str | None
    ) -> list[ProjectRecord]:
        self._require_buyer(role, workspace)
        items = self._store.list_by_owner(owner_id)
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items

    def rename(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        display_name: str,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(project_id, owner_id)
        name = self._validate_name(display_name)
        rec.display_name = name
        rec.name_normalized = normalize_name(name)
        rec.updated_at = utcnow()
        try:
            self._store.save(rec)
        except NameConflict as exc:
            raise ProjectError(
                NAME_CONFLICT, MSG[NAME_CONFLICT], http_status=409
            ) from exc
        except RuntimeError as exc:
            if "mode is immutable" in str(exc):
                raise ProjectError(
                    MODE_IMMUTABLE, MSG[MODE_IMMUTABLE], http_status=400
                ) from exc
            raise
        self._store.audit(
            owner_id=owner_id,
            project_id=project_id,
            event_type="project.renamed",
            request_id=request_id,
        )
        return rec

    def set_preview_opt_in(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        preview_opt_in: bool,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(project_id, owner_id)
        rec.preview_opt_in = bool(preview_opt_in)
        rec.updated_at = utcnow()
        self._store.save(rec)
        self._store.audit(
            owner_id=owner_id,
            project_id=project_id,
            event_type="project.preview_opt_in",
            request_id=request_id,
            payload={"preview_opt_in": rec.preview_opt_in},
        )
        return rec

    def reject_mode_change(self) -> None:
        raise ProjectError(MODE_IMMUTABLE, MSG[MODE_IMMUTABLE], http_status=400)

    def transition(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        action: str,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(project_id, owner_id)
        target = next_status(rec.status, action)
        if target is None:
            raise ProjectError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        rec.status = target
        rec.updated_at = utcnow()
        if action == "archive":
            rec.archived_at = rec.updated_at
        self._store.save(rec)
        event = f"project.{action}d" if action != "activate" else "project.activated"
        if action == "archive":
            event = "project.archived"
        self._store.audit(
            owner_id=owner_id,
            project_id=project_id,
            event_type=event,
            request_id=request_id,
            payload={"status": rec.status},
        )
        if action == "archive":
            logger.info(
                "project_archived",
                extra={
                    "owner_account_id": str(owner_id),
                    "project_id": str(project_id),
                    "request_id": request_id,
                },
            )
        return rec

    def admission(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> dict[str, object]:
        rec = self.get(
            project_id=project_id, owner_id=owner_id, role=role, workspace=workspace
        )
        return {
            "allows_new_proxy": allows_new_proxy(rec),
            "project_id": str(rec.project_id),
            "status": rec.status,
        }

    def enable_protocol(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        protocol: str,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        if protocol not in PROTOCOLS:
            raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
        rec = self._owned(project_id, owner_id)
        if rec.status == "archived":
            raise ProjectError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        current = next((p for p in rec.protocols if p.protocol == protocol), None)
        if current is not None and current.enabled:
            return rec
        if not self._binding.has_enabled_binding(
            owner_id=owner_id, project_id=project_id, protocol=protocol
        ):
            self._store.audit(
                owner_id=owner_id,
                project_id=project_id,
                event_type="project.protocol_enable_denied",
                request_id=request_id,
                payload={"protocol": protocol},
            )
            raise ProjectError(
                PROVIDER_BINDING_REQUIRED,
                MSG[PROVIDER_BINDING_REQUIRED],
                http_status=409,
            )
        now = utcnow()
        if current is None:
            rec.protocols.append(
                ProtocolState(protocol=protocol, enabled=True, enabled_at=now)
            )
        else:
            current.enabled = True
            current.enabled_at = now
            current.disabled_at = None
        rec.updated_at = now
        self._store.save(rec)
        return rec

    def disable_protocol(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        protocol: str,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> ProjectRecord:
        self._require_buyer(role, workspace)
        if protocol not in PROTOCOLS:
            raise ProjectError(VALIDATION, MSG[VALIDATION], http_status=400)
        rec = self._owned(project_id, owner_id)
        current = next((p for p in rec.protocols if p.protocol == protocol), None)
        if current is None:
            raise ProjectError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        if current.enabled:
            current.enabled = False
            current.disabled_at = utcnow()
            rec.updated_at = current.disabled_at
            self._store.save(rec)
        self._store.audit(
            owner_id=owner_id,
            project_id=project_id,
            event_type="project.protocol_disabled",
            request_id=request_id,
            payload={"protocol": protocol},
        )
        return rec

    def delete(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> None:
        self._require_buyer(role, workspace)
        rec = self._owned(project_id, owner_id)
        blockers = [
            b for b in self._store.blockers(project_id) if b.kind in BLOCKER_KINDS
        ]
        if blockers:
            payload = {
                "blockers": [
                    {"kind": b.kind, "reference_id": b.reference_id} for b in blockers
                ]
            }
            self._store.audit(
                owner_id=owner_id,
                project_id=project_id,
                event_type="project.delete_blocked",
                request_id=request_id,
                payload=payload,
            )
            raise ProjectError(
                DELETE_BLOCKED,
                MSG[DELETE_BLOCKED],
                http_status=409,
                data=payload,
            )
        rec.deleted_at = utcnow()
        rec.updated_at = rec.deleted_at
        self._store.save(rec)
        self._store.audit(
            owner_id=owner_id,
            project_id=project_id,
            event_type="project.deleted",
            request_id=request_id,
        )
        logger.info(
            "project_deleted",
            extra={
                "owner_account_id": str(owner_id),
                "project_id": str(project_id),
                "request_id": request_id,
            },
        )
