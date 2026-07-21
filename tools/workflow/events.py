"""Workflow event emission and aggregation.

Implements the v1 JSON Lines event contract defined in
``shared/contracts/repository-workflow/v1/workflow-event.schema.json`` and the
v2 standard-envelope contract defined in
``shared/contracts/repository-workflow/v2/workflow-event.schema.json``.

The v1 API (``emit_event``/``EventLog``/``aggregate_status``/``stable_codes``)
is immutable SF01 history and stays the runtime behavior until the make-workflow
v2 activation gate passes. The v2 API (``emit_event_v2``/``EventLogV2``/
``aggregate_status_v2``/``stable_codes_v2``) emits the standard envelope with
unique UUID event IDs, stable type/version/producer, UTC RFC 3339 timestamps,
per-lifecycle-run correlation IDs, strict dependency payloads, WAITING
semantics, stable SF02 diagnostics, bounded messages, and value redaction. No
dual JSONL stream exists: consumers migrate to the v2 reader before activation.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class DiagnosticCode(str, Enum):
    OK = "OK"
    INVALID_USAGE = "INVALID_USAGE"
    TOOL_MISSING = "TOOL_MISSING"
    TOOL_VERSION_UNSUPPORTED = "TOOL_VERSION_UNSUPPORTED"
    INVALID_CONFIG = "INVALID_CONFIG"
    INVALID_MODE = "INVALID_MODE"
    PROD_APPROVAL_REQUIRED = "PROD_APPROVAL_REQUIRED"
    SF02_NOT_READY = "SF02_NOT_READY"
    COMPONENT_NOT_INITIALIZED = "COMPONENT_NOT_INITIALIZED"
    NO_TESTS_EXECUTED = "NO_TESTS_EXECUTED"
    STEP_FAILED = "STEP_FAILED"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"
    MIGRATION_INVALID = "MIGRATION_INVALID"
    SECRET_DETECTED = "SECRET_DETECTED"


# Patterns that look like secret or high-entropy credential values.
_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{16,}"),
    re.compile(
        r"[a-zA-Z0-9_-]*(?:api[_-]?key|apikey|secret|token|password)[\s]*[=:\s][\s]*[^\s\"']{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
]


def _redact(message: str) -> str:
    """Redact secret-like values from a message while keeping variable names."""
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub("[REDACTED]", message)
    return message


def emit_event(
    *,
    action: str,
    component: str,
    phase: str,
    status: str,
    code: DiagnosticCode,
    duration_ms: int,
    message: str,
    run_id: str,
) -> dict[str, Any]:
    """Create a single workflow event dict satisfying the v1 schema."""
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "action": action,
        "component": component,
        "phase": phase,
        "status": status,
        "code": code.value,
        "duration_ms": max(0, int(duration_ms)),
        "message": _redact(message)[:1000],
    }


def to_jsonl(event: dict[str, Any]) -> str:
    """Serialize an event to a single JSON Lines string."""
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def stable_codes() -> set[str]:
    """Return the set of stable diagnostic codes defined by the contract."""
    return {member.value for member in DiagnosticCode}


def aggregate_status(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute final aggregate status from a sequence of step events."""
    passed = sum(1 for e in events if e.get("status") == "PASSED")
    failed = sum(1 for e in events if e.get("status") == "FAILED")
    skipped = sum(1 for e in events if e.get("status") == "SKIPPED")

    if failed:
        code = DiagnosticCode.STEP_FAILED
        status = "FAILED"
    elif skipped and passed == 0:
        code = DiagnosticCode.STEP_FAILED
        status = "FAILED"
    else:
        code = DiagnosticCode.OK
        status = "PASSED"

    return {
        "status": status,
        "code": code.value,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


@dataclass
class EventLog:
    """Ordered log of workflow step events for a single run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: list[dict[str, Any]] = field(default_factory=list)

    def start(self, action: str, component: str, phase: str) -> None:
        self.events.append(
            emit_event(
                action=action,
                component=component,
                phase=phase,
                status="STARTED",
                code=DiagnosticCode.OK,
                duration_ms=0,
                message=f"{action} started for {component}",
                run_id=self.run_id,
            )
        )

    def finish(
        self,
        action: str,
        component: str,
        phase: str,
        *,
        status: str,
        code: DiagnosticCode | None = None,
        message: str = "",
        duration_ms: int = 0,
    ) -> None:
        if code is None:
            code = DiagnosticCode.OK if status == "PASSED" else DiagnosticCode.STEP_FAILED
        self.events.append(
            emit_event(
                action=action,
                component=component,
                phase=phase,
                status=status,
                code=code,
                duration_ms=duration_ms,
                message=message or f"{action} {status.lower()} for {component}",
                run_id=self.run_id,
            )
        )

    def skip(self, action: str, component: str, phase: str, *, reason: str) -> None:
        self.events.append(
            emit_event(
                action=action,
                component=component,
                phase=phase,
                status="SKIPPED",
                code=DiagnosticCode.STEP_FAILED,
                duration_ms=0,
                message=reason,
                run_id=self.run_id,
            )
        )


class DiagnosticCodeV2(str, Enum):
    """Stable v2 diagnostic codes: the v1 set plus the SF02 categories."""

    OK = "OK"
    INVALID_USAGE = "INVALID_USAGE"
    TOOL_MISSING = "TOOL_MISSING"
    TOOL_VERSION_UNSUPPORTED = "TOOL_VERSION_UNSUPPORTED"
    INVALID_CONFIG = "INVALID_CONFIG"
    INVALID_MODE = "INVALID_MODE"
    PROD_APPROVAL_REQUIRED = "PROD_APPROVAL_REQUIRED"
    SF02_NOT_READY = "SF02_NOT_READY"
    COMPONENT_NOT_INITIALIZED = "COMPONENT_NOT_INITIALIZED"
    NO_TESTS_EXECUTED = "NO_TESTS_EXECUTED"
    STEP_FAILED = "STEP_FAILED"
    CONTRACT_DRIFT = "CONTRACT_DRIFT"
    MIGRATION_INVALID = "MIGRATION_INVALID"
    SECRET_DETECTED = "SECRET_DETECTED"
    IMAGE_UNAVAILABLE = "IMAGE_UNAVAILABLE"
    PORT_CONFLICT = "PORT_CONFLICT"
    DEPENDENCY_NOT_READY = "DEPENDENCY_NOT_READY"
    OPERATION_IN_PROGRESS = "OPERATION_IN_PROGRESS"
    RESOURCE_OWNERSHIP_CONFLICT = "RESOURCE_OWNERSHIP_CONFLICT"


EVENT_TYPE_V2 = "workflow.step"
SCHEMA_VERSION_V2 = "2.0.0"
PRODUCER_V2 = "repository-workflow"

_COMPONENTS_V2 = frozenset(
    {
        "repository",
        "proxy-gateway",
        "api-service",
        "billing-service",
        "admin-service",
        "frontend",
        "shared",
        "infra",
        "ops",
    }
)
_DEPENDENCIES = frozenset({"postgres", "redis", "grafana"})
_DEPENDENCY_COMPONENTS = frozenset({"repository", "infra"})
_DEPENDENCY_SCOPED_ACTIONS = frozenset({"dev", "dev-down"})
_DEPENDENCY_SCOPED_PHASES = frozenset(
    {"image-pull", "image-verify", "reconcile", "liveness", "readiness", "stopping"}
)
_DEPENDENCY_SCOPED_CODES = frozenset(
    {
        DiagnosticCodeV2.IMAGE_UNAVAILABLE,
        DiagnosticCodeV2.PORT_CONFLICT,
        DiagnosticCodeV2.DEPENDENCY_NOT_READY,
    }
)
_STATUSES_V2 = frozenset({"STARTED", "WAITING", "PASSED", "FAILED", "SKIPPED"})

_KEBAB_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_MESSAGE_MAX = 1000
_CORRELATION_ID_MAX = 128

# v2-only redaction: the local synthetic-secret grammar, URL user-info, and
# absolute workspace/runtime paths must never survive serialization.
_LOCAL_SECRET_RE = re.compile(r"tm_local_[A-Za-z0-9_-]{8,}")
_URL_USERINFO_RE = re.compile(r"://[^/\s@\"']+@")
_ABSOLUTE_UNSAFE_PATH_RE = re.compile(
    r"/(?:Users|home)/[^\s\"']+|/(?:private/)?(?:var|tmp|run)/[^\s\"']+"
)


def _redact_v2(message: str) -> str:
    """Redact v2-classified values: v1 secrets plus user-info URLs and paths."""
    message = _URL_USERINFO_RE.sub("://", message)
    message = _redact(message)
    message = _LOCAL_SECRET_RE.sub("[REDACTED]", message)
    return _ABSOLUTE_UNSAFE_PATH_RE.sub("[REDACTED_PATH]", message)


def _utc_now_rfc3339() -> str:
    """Return the current UTC time as an RFC 3339 timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_v2_payload(
    *,
    action: str,
    component: str,
    phase: str,
    status: str,
    code: DiagnosticCodeV2,
    dependency: str | None,
) -> None:
    """Enforce the strict v2 payload rules before an envelope is created."""
    if not _KEBAB_RE.match(action):
        raise ValueError(f"action must match ^[a-z][a-z0-9-]*$: {action!r}")
    if component not in _COMPONENTS_V2:
        raise ValueError(f"unknown component: {component!r}")
    if not _KEBAB_RE.match(phase):
        raise ValueError(f"phase must match ^[a-z][a-z0-9-]*$: {phase!r}")
    if status not in _STATUSES_V2:
        raise ValueError(f"unknown status: {status!r}")
    if status in ("WAITING", "PASSED") and code is not DiagnosticCodeV2.OK:
        raise ValueError(f"{status} payloads must carry code OK, got {code.value}")
    if status in ("FAILED", "SKIPPED") and code is DiagnosticCodeV2.OK:
        raise ValueError(f"{status} payloads must not carry code OK")
    if dependency is not None:
        if dependency not in _DEPENDENCIES:
            raise ValueError(f"unknown dependency: {dependency!r}")
        if component not in _DEPENDENCY_COMPONENTS:
            raise ValueError(
                "dependency-scoped payloads must use repository/infra component, "
                f"got {component!r}"
            )
    elif (action in _DEPENDENCY_SCOPED_ACTIONS and phase in _DEPENDENCY_SCOPED_PHASES) or (
        code in _DEPENDENCY_SCOPED_CODES
    ):
        raise ValueError(
            f"payload with action={action!r} phase={phase!r} code={code.value!r} "
            "requires the dependency field"
        )


def emit_event_v2(
    *,
    action: str,
    component: str,
    phase: str,
    status: str,
    code: DiagnosticCodeV2 | str,
    duration_ms: int,
    message: str,
    correlation_id: str,
    dependency: str | None = None,
) -> dict[str, Any]:
    """Create one v2 standard-envelope event dict satisfying the v2 schema.

    Raises ValueError when any field violates the strict payload contract.
    Messages are redacted and bounded before serialization.
    """
    code = DiagnosticCodeV2(code)
    _validate_v2_payload(
        action=action,
        component=component,
        phase=phase,
        status=status,
        code=code,
        dependency=dependency,
    )
    if not (1 <= len(correlation_id) <= _CORRELATION_ID_MAX):
        raise ValueError("correlation_id must be 1..128 characters")
    if not message:
        raise ValueError("message must be non-empty")
    safe_message = _redact_v2(message)[:_MESSAGE_MAX]
    if not safe_message:
        raise ValueError("message must remain non-empty after redaction")

    payload: dict[str, Any] = {
        "action": action,
        "component": component,
        "phase": phase,
        "status": status,
        "code": code.value,
        "duration_ms": max(0, int(duration_ms)),
        "message": safe_message,
    }
    if dependency is not None:
        payload["dependency"] = dependency

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_TYPE_V2,
        "schema_version": SCHEMA_VERSION_V2,
        "timestamp": _utc_now_rfc3339(),
        "producer": PRODUCER_V2,
        "correlation_id": correlation_id,
        "payload": payload,
    }


def stable_codes_v2() -> set[str]:
    """Return the set of stable v2 diagnostic codes defined by the contract."""
    return {member.value for member in DiagnosticCodeV2}


def aggregate_status_v2(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute final aggregate status from v2 standard-envelope payloads.

    Partial dependency success never makes the aggregate PASSED: any FAILED,
    unresolved WAITING, or an all-SKIPPED run aggregates to FAILED.
    """
    statuses = [event["payload"]["status"] for event in events]
    passed = statuses.count("PASSED")
    failed = statuses.count("FAILED")
    skipped = statuses.count("SKIPPED")
    waiting = statuses.count("WAITING")

    if failed or waiting or (skipped and passed == 0):
        code = DiagnosticCodeV2.STEP_FAILED
        status = "FAILED"
    else:
        code = DiagnosticCodeV2.OK
        status = "PASSED"

    return {
        "status": status,
        "code": code.value,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "waiting": waiting,
    }


@dataclass
class EventLogV2:
    """Ordered v2 standard-envelope log for a single lifecycle run."""

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: list[dict[str, Any]] = field(default_factory=list)

    def start(
        self, action: str, component: str, phase: str, *, dependency: str | None = None
    ) -> None:
        self.events.append(
            emit_event_v2(
                action=action,
                component=component,
                phase=phase,
                status="STARTED",
                code=DiagnosticCodeV2.OK,
                duration_ms=0,
                message=f"{action} started for {dependency or component}",
                correlation_id=self.correlation_id,
                dependency=dependency,
            )
        )

    def wait(
        self,
        action: str,
        component: str,
        phase: str,
        *,
        dependency: str | None = None,
        message: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.events.append(
            emit_event_v2(
                action=action,
                component=component,
                phase=phase,
                status="WAITING",
                code=DiagnosticCodeV2.OK,
                duration_ms=duration_ms,
                message=message or f"{action} waiting for {dependency or component} during {phase}",
                correlation_id=self.correlation_id,
                dependency=dependency,
            )
        )

    def finish(
        self,
        action: str,
        component: str,
        phase: str,
        *,
        status: str,
        code: DiagnosticCodeV2 | None = None,
        message: str = "",
        duration_ms: int = 0,
        dependency: str | None = None,
    ) -> None:
        if code is None:
            code = (
                DiagnosticCodeV2.OK
                if status in ("PASSED", "WAITING")
                else DiagnosticCodeV2.STEP_FAILED
            )
        self.events.append(
            emit_event_v2(
                action=action,
                component=component,
                phase=phase,
                status=status,
                code=code,
                duration_ms=duration_ms,
                message=message or f"{action} {status.lower()} for {dependency or component}",
                correlation_id=self.correlation_id,
                dependency=dependency,
            )
        )

    def skip(
        self,
        action: str,
        component: str,
        phase: str,
        *,
        reason: str,
        dependency: str | None = None,
    ) -> None:
        self.events.append(
            emit_event_v2(
                action=action,
                component=component,
                phase=phase,
                status="SKIPPED",
                code=DiagnosticCodeV2.STEP_FAILED,
                duration_ms=0,
                message=reason,
                correlation_id=self.correlation_id,
                dependency=dependency,
            )
        )
