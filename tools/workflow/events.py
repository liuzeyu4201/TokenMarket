"""Workflow event emission and aggregation.

Implements the v1 JSON Lines event contract defined in
``shared/contracts/repository-workflow/v1/workflow-event.schema.json``.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
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
