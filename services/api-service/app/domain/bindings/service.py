"""Provider Binding lifecycle, admit, and SF10 lookup."""

from __future__ import annotations

import logging
import uuid
from typing import Sequence

from app.domain.authorization.workspace import effective_role
from app.domain.bindings.codes import (
    BINDING_DEGRADED,
    BINDING_REPLACE_DENIED,
    BINDING_REQUIRED,
    BUYER_CONFIRMATION_REQUIRED,
    CONNECTION_REQUIRED,
    FORBIDDEN_ROLE,
    ILLEGAL_STATE_TRANSITION,
    IMMUTABLE_VERSION,
    MODE_MISMATCH,
    MODEL_NOT_ALLOWED,
    MODES,
    MSG,
    NOT_FOUND,
    PRICE_UNAVAILABLE,
    PROTOCOL_MISMATCH,
    PROTOCOLS,
    PUBLISH_CONFLICT,
    PUBLISHED,
    SDK_HINTS,
    STEP_UP_REQUIRED,
    VALIDATION,
)
from app.domain.bindings.models import BindingRecord, utcnow
from app.domain.bindings.ports import (
    CatalogPriceLookup,
    ConnectionLookup,
    EmptyConnectionLookup,
    PriceAvailability,
)
from app.domain.bindings.store import BindingStore, MemoryBindingStore, PublishConflict
from app.domain.projects.models import ProjectRecord
from app.domain.projects.store import MemoryProjectStore, ProjectStore

logger = logging.getLogger("api-service")

NON_MIGRATING = ("files", "batches", "caches", "fine_tuning", "operations")
IDLE_LIFECYCLES = frozenset({"listed", "verified"})


class BindingError(Exception):
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


class BindingService:
    def __init__(
        self,
        store: BindingStore | None = None,
        projects: ProjectStore | None = None,
        connections: ConnectionLookup | None = None,
        prices: PriceAvailability | None = None,
    ) -> None:
        self._store: BindingStore = store if store is not None else MemoryBindingStore()
        self._projects: ProjectStore = (
            projects if projects is not None else MemoryProjectStore()
        )
        self._connections: ConnectionLookup = (
            connections if connections is not None else EmptyConnectionLookup()
        )
        self._prices: PriceAvailability = (
            prices if prices is not None else CatalogPriceLookup()
        )

    def _require_buyer(self, role: str, workspace: str | None) -> None:
        if workspace is None:
            if role not in ("buyer", "both"):
                raise BindingError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)
            return
        if effective_role(role, workspace) != "buyer":
            raise BindingError(FORBIDDEN_ROLE, MSG[FORBIDDEN_ROLE], http_status=403)

    def _project(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> ProjectRecord:
        rec = self._projects.get(project_id)
        if (
            rec is None
            or rec.owner_account_id != owner_id
            or rec.deleted_at is not None
        ):
            raise BindingError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        return rec

    def _owned(self, binding_id: uuid.UUID, owner_id: uuid.UUID) -> BindingRecord:
        rec = self._store.get(binding_id)
        if rec is None or rec.owner_account_id != owner_id:
            raise BindingError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        return rec

    def has_enabled_binding(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        protocol: str,
    ) -> bool:
        for rec in self._store.list_by_project_protocol(project_id, protocol):
            if rec.owner_account_id != owner_id:
                continue
            if rec.status in ("active", "degraded"):
                return True
        return False

    def create(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        protocol: str,
        supply_mode: str,
        role: str,
        workspace: str | None,
        request_id: str,
        allowed_providers: Sequence[str] | None = None,
        allowed_models: Sequence[str] | None = None,
        allowed_regions: Sequence[str] | None = None,
        connection_id: uuid.UUID | None = None,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        if protocol not in PROTOCOLS or supply_mode not in MODES:
            raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
        project = self._project(project_id, owner_id)
        if project.status == "archived":
            raise BindingError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        if supply_mode != project.mode:
            raise BindingError(MODE_MISMATCH, MSG[MODE_MISMATCH], http_status=409)
        providers = list(allowed_providers or [protocol])
        models = list(allowed_models or [])
        regions = list(allowed_regions or [])
        if any(p != protocol or p not in PROTOCOLS for p in providers):
            raise BindingError(
                PROTOCOL_MISMATCH, MSG[PROTOCOL_MISMATCH], http_status=409
            )
        if supply_mode == "shared" and not models:
            raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
        if supply_mode == "dedicated":
            self._require_connection(connection_id, protocol)
        now = utcnow()
        rec = BindingRecord(
            binding_id=uuid.uuid4(),
            project_id=project_id,
            owner_account_id=owner_id,
            protocol=protocol,
            supply_mode=supply_mode,
            status="draft",
            version=0,
            allowed_providers=providers,
            allowed_models=models,
            allowed_regions=regions,
            connection_id=connection_id if supply_mode == "dedicated" else None,
            created_at=now,
            updated_at=now,
        )
        self._store.create(rec)
        return rec

    def _require_connection(
        self,
        connection_id: uuid.UUID | None,
        protocol: str,
        *,
        idle: bool = False,
    ) -> None:
        if connection_id is None:
            raise BindingError(
                CONNECTION_REQUIRED, MSG[CONNECTION_REQUIRED], http_status=409
            )
        fact = self._connections.get(connection_id)
        if (
            fact is None
            or not fact.usable
            or fact.supply_mode != "dedicated"
            or fact.provider != protocol
        ):
            raise BindingError(
                CONNECTION_REQUIRED, MSG[CONNECTION_REQUIRED], http_status=409
            )
        if idle and fact.lifecycle_state not in IDLE_LIFECYCLES:
            raise BindingError(
                CONNECTION_REQUIRED, MSG[CONNECTION_REQUIRED], http_status=409
            )

    def _assert_publishable(self, rec: BindingRecord) -> None:
        if rec.supply_mode == "shared":
            if not rec.allowed_models:
                raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
            if not self._prices.available(rec.protocol):
                raise BindingError(
                    PRICE_UNAVAILABLE, MSG[PRICE_UNAVAILABLE], http_status=409
                )
        else:
            self._require_connection(rec.connection_id, rec.protocol)

    def validate(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(binding_id, owner_id)
        if rec.status not in ("draft", "validated"):
            raise BindingError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        self._assert_publishable(rec)
        rec.status = "validated"
        rec.updated_at = utcnow()
        self._store.save(rec)
        return rec

    def publish(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(binding_id, owner_id)
        if rec.status in PUBLISHED:
            raise BindingError(
                IMMUTABLE_VERSION, MSG[IMMUTABLE_VERSION], http_status=409
            )
        project = self._project(rec.project_id, owner_id)
        if rec.supply_mode != project.mode:
            raise BindingError(MODE_MISMATCH, MSG[MODE_MISMATCH], http_status=409)
        self._assert_publishable(rec)
        rec.version = self._store.max_version(rec.project_id, rec.protocol) + 1
        rec.status = "active"
        rec.published_at = utcnow()
        rec.updated_at = rec.published_at
        try:
            self._store.publish_atomic(rec)
        except PublishConflict as exc:
            raise BindingError(
                PUBLISH_CONFLICT, MSG[PUBLISH_CONFLICT], http_status=409
            ) from exc
        self._store.audit(
            owner_id=owner_id,
            project_id=rec.project_id,
            binding_id=rec.binding_id,
            event_type="binding.published",
            request_id=request_id,
            payload={"protocol": rec.protocol, "version": rec.version},
        )
        logger.info(
            "binding_published",
            extra={
                "owner_account_id": str(owner_id),
                "project_id": str(rec.project_id),
                "binding_id": str(rec.binding_id),
                "request_id": request_id,
                "protocol": rec.protocol,
                "version": rec.version,
            },
        )
        if rec.supply_mode == "dedicated" and rec.connection_id is not None:
            marker = getattr(self._connections, "mark_bound", None)
            if callable(marker):
                marker(rec.connection_id, request_id)
        return rec

    def deactivate(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(binding_id, owner_id)
        if rec.status not in ("active", "degraded"):
            raise BindingError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        rec.status = "inactive"
        rec.updated_at = utcnow()
        self._store.save(rec)
        if rec.supply_mode == "dedicated" and rec.connection_id is not None:
            marker = getattr(self._connections, "mark_unbound", None)
            if callable(marker):
                marker(rec.connection_id, request_id)
        return rec

    def list_mine(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> list[BindingRecord]:
        self._require_buyer(role, workspace)
        self._project(project_id, owner_id)
        return self._store.list_by_project(project_id)

    def get(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        return self._owned(binding_id, owner_id)

    def sdk_hint(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> dict[str, str]:
        rec = self.get(
            binding_id=binding_id, owner_id=owner_id, role=role, workspace=workspace
        )
        hint = dict(SDK_HINTS[rec.protocol])
        return hint

    def active(
        self,
        *,
        project_id: uuid.UUID,
        protocol: str,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        self._project(project_id, owner_id)
        found = [
            r
            for r in self._store.list_by_project_protocol(project_id, protocol)
            if r.status in ("active", "degraded")
        ]
        if not found:
            raise BindingError(NOT_FOUND, MSG[NOT_FOUND], http_status=404)
        found.sort(key=lambda r: r.version, reverse=True)
        return found[0]

    def admit(
        self,
        *,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        protocol: str,
        provider: str,
        model: str | None,
        role: str,
        workspace: str | None,
    ) -> dict[str, object]:
        self._require_buyer(role, workspace)
        self._project(project_id, owner_id)
        if protocol not in PROTOCOLS or provider not in PROTOCOLS:
            raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
        if provider != protocol:
            raise BindingError(
                PROTOCOL_MISMATCH, MSG[PROTOCOL_MISMATCH], http_status=409
            )
        try:
            rec = self.active(
                project_id=project_id,
                protocol=protocol,
                owner_id=owner_id,
                role=role,
                workspace=workspace,
            )
        except BindingError as exc:
            if exc.code == NOT_FOUND:
                raise BindingError(
                    BINDING_REQUIRED, MSG[BINDING_REQUIRED], http_status=409
                ) from exc
            raise
        if rec.status == "degraded":
            raise BindingError(
                BINDING_DEGRADED,
                MSG[BINDING_DEGRADED],
                http_status=409,
                data={"fallback": None, "shared_pool": False},
            )
        if rec.protocol != protocol:
            raise BindingError(
                PROTOCOL_MISMATCH, MSG[PROTOCOL_MISMATCH], http_status=409
            )
        if (
            rec.supply_mode == "shared"
            and model
            and rec.allowed_models
            and model not in rec.allowed_models
        ):
            raise BindingError(
                MODEL_NOT_ALLOWED, MSG[MODEL_NOT_ALLOWED], http_status=409
            )
        return {
            "binding_id": str(rec.binding_id),
            "version": rec.version,
            "protocol": rec.protocol,
            "supply_mode": rec.supply_mode,
        }

    def replace_preview(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
    ) -> dict[str, object]:
        self._require_buyer(role, workspace)
        rec = self._owned(binding_id, owner_id)
        if rec.supply_mode != "dedicated":
            raise BindingError(
                BINDING_REPLACE_DENIED, MSG[BINDING_REPLACE_DENIED], http_status=409
            )
        return {
            "old_connection_id": str(rec.connection_id) if rec.connection_id else None,
            "non_migrating": list(NON_MIGRATING),
            "migrates": False,
        }

    def replace(
        self,
        *,
        binding_id: uuid.UUID,
        owner_id: uuid.UUID,
        role: str,
        workspace: str | None,
        request_id: str,
        new_connection_id: uuid.UUID,
        buyer_confirmed: bool,
        reason: str,
        step_up: bool,
    ) -> BindingRecord:
        self._require_buyer(role, workspace)
        rec = self._owned(binding_id, owner_id)
        if rec.supply_mode != "dedicated":
            raise BindingError(
                BINDING_REPLACE_DENIED, MSG[BINDING_REPLACE_DENIED], http_status=409
            )
        if rec.status not in ("active", "degraded"):
            raise BindingError(
                ILLEGAL_STATE_TRANSITION,
                MSG[ILLEGAL_STATE_TRANSITION],
                http_status=409,
            )
        if not buyer_confirmed:
            raise BindingError(
                BUYER_CONFIRMATION_REQUIRED,
                MSG[BUYER_CONFIRMATION_REQUIRED],
                http_status=409,
            )
        if not step_up:
            raise BindingError(STEP_UP_REQUIRED, MSG[STEP_UP_REQUIRED], http_status=409)
        if not str(reason).strip():
            raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
        if rec.connection_id == new_connection_id:
            raise BindingError(VALIDATION, MSG[VALIDATION], http_status=400)
        self._require_connection(new_connection_id, rec.protocol, idle=True)
        old = rec.connection_id
        rec.draining_connection_id = old
        rec.connection_id = new_connection_id
        rec.status = "active"
        rec.version = rec.version + 1
        rec.updated_at = utcnow()
        self._store.save(rec)
        if old is not None:
            drain = getattr(self._connections, "mark_draining", None)
            if callable(drain):
                drain(old, request_id)
        bound = getattr(self._connections, "mark_bound", None)
        if callable(bound):
            bound(new_connection_id, request_id)
        self._store.audit(
            owner_id=owner_id,
            project_id=rec.project_id,
            binding_id=rec.binding_id,
            event_type="binding.replaced",
            request_id=request_id,
            payload={
                "actor": str(owner_id),
                "buyer_confirmed": True,
                "step_up": True,
                "reason": str(reason).strip(),
                "before_connection_id": str(old) if old else None,
                "after_connection_id": str(new_connection_id),
            },
        )
        return rec

    def degrade_for_connection(self, connection_id: uuid.UUID, request_id: str) -> int:
        """Degrade dedicated bindings for a connection. Never fall back to shared."""
        changed = 0
        for rec in self._store.list_by_connection(connection_id):
            if rec.status != "active" or rec.supply_mode != "dedicated":
                continue
            rec.status = "degraded"
            rec.updated_at = utcnow()
            self._store.save(rec)
            self._store.audit(
                owner_id=rec.owner_account_id,
                project_id=rec.project_id,
                binding_id=rec.binding_id,
                event_type="binding.degraded",
                request_id=request_id,
                payload={"connection_id": str(connection_id)},
            )
            changed += 1
        return changed
