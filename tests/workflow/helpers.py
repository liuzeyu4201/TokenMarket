"""Shared helpers for repository workflow tests.

All helpers operate on repository-relative paths and avoid depending on the
caller's working directory. They are intentionally small and use only the
Python standard library so the workflow test suite can run before the
repository workflow tooling itself is fully implemented.

The v2 section below is the repository-owned JSONL reader for the SF02
workflow-event standard envelope
(``shared/contracts/repository-workflow/v2/workflow-event.schema.json``).
Strict v1 fixture assertions remain in ``test_events.py`` as explicit v1
regression coverage; new consumers use the v2 reader here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def find_repo_root() -> Path:
    """Return the repository root by locating the nearest `.git` directory."""
    path = Path(__file__).resolve()
    for parent in [path, *path.parents]:
        if (parent / ".git").is_dir():
            return parent
    raise RuntimeError("Could not locate repository root (.git directory not found)")


def repo_path(*parts: str) -> Path:
    """Resolve a path relative to the repository root."""
    return find_repo_root().joinpath(*parts)


def load_json(*parts: str) -> Any:
    """Load a JSON file from a repository-relative path."""
    with repo_path(*parts).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_text(*parts: str) -> str:
    """Load a text file from a repository-relative path."""
    with repo_path(*parts).open("r", encoding="utf-8") as fh:
        return fh.read()


def run(
    args: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the completed process.

    The command output is captured and returned as text. Secrets must never be
    passed through this helper.
    """
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


EVENT_SCHEMA_V2_PARTS = (
    "shared",
    "contracts",
    "repository-workflow",
    "v2",
    "workflow-event.schema.json",
)

_ENVELOPE_KEYS_V2 = {
    "event_id",
    "event_type",
    "schema_version",
    "timestamp",
    "producer",
    "correlation_id",
    "payload",
}
_PAYLOAD_REQUIRED_V2 = {
    "action",
    "component",
    "phase",
    "status",
    "code",
    "duration_ms",
    "message",
}
_PAYLOAD_ALLOWED_V2 = _PAYLOAD_REQUIRED_V2 | {"dependency"}
_DEPENDENCIES_V2 = {"postgres", "redis", "grafana"}
_DEPENDENCY_COMPONENTS_V2 = {"repository", "infra"}
_DEPENDENCY_SCOPED_PHASES_V2 = {
    "image-pull",
    "image-verify",
    "reconcile",
    "liveness",
    "readiness",
    "stopping",
}
_DEPENDENCY_SCOPED_CODES_V2 = {
    "IMAGE_UNAVAILABLE",
    "PORT_CONFLICT",
    "DEPENDENCY_NOT_READY",
}
_KEBAB_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def load_event_schema_v2() -> dict[str, Any]:
    """Load the published v2 workflow-event schema from the runtime contract copy."""
    schema = load_json(*EVENT_SCHEMA_V2_PARTS)
    if not isinstance(schema, dict):
        raise AssertionError("workflow event v2 schema must be a JSON object")
    return schema


def parse_jsonl_line(line: str) -> dict[str, Any]:
    """Parse one JSON Lines record into an event dict."""
    parsed = json.loads(line)
    if not isinstance(parsed, dict):
        raise AssertionError(f"JSONL record must be a JSON object: {line!r}")
    return parsed


def validate_event_v2(event: dict[str, Any]) -> None:
    """Strict v2 standard-envelope consumer validation.

    This is the repository-owned v2 reader: it accepts only envelopes that
    satisfy the published v2 schema and raises AssertionError otherwise, so a
    v1-shaped dict is rejected instead of silently misparsed. Consts and enums
    are read from the contract file so schema drift fails the consumer tests.
    """
    schema = load_event_schema_v2()
    envelope_props = schema["properties"]
    payload_props = envelope_props["payload"]["properties"]

    assert set(event.keys()) == _ENVELOPE_KEYS_V2, "v2 envelope allows no additional fields"
    assert isinstance(event["event_id"], str), "event_id must be a string"
    try:
        uuid.UUID(event["event_id"])
    except ValueError as exc:
        raise AssertionError(f"event_id must be a UUID: {event['event_id']!r}") from exc
    assert event["event_type"] == envelope_props["event_type"]["const"]
    assert event["schema_version"] == envelope_props["schema_version"]["const"]
    assert event["producer"] == envelope_props["producer"]["const"]
    assert isinstance(event["timestamp"], str), "timestamp must be a string"
    assert _RFC3339_RE.match(
        event["timestamp"]
    ), f"timestamp must be RFC 3339: {event['timestamp']!r}"
    parsed_ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    assert parsed_ts.utcoffset() == timedelta(0), "timestamp must be UTC"
    assert isinstance(event["correlation_id"], str), "correlation_id must be a string"
    assert 1 <= len(event["correlation_id"]) <= 128, "correlation_id must be 1..128 chars"

    payload = event["payload"]
    assert isinstance(payload, dict), "payload must be an object"
    assert _PAYLOAD_REQUIRED_V2 <= set(payload.keys()), "payload misses required fields"
    assert set(payload.keys()) <= _PAYLOAD_ALLOWED_V2, "payload allows no additional fields"
    assert isinstance(payload["action"], str) and _KEBAB_RE.match(payload["action"])
    assert payload["component"] in payload_props["component"]["enum"]
    assert isinstance(payload["phase"], str) and _KEBAB_RE.match(payload["phase"])
    assert payload["status"] in payload_props["status"]["enum"]
    assert payload["code"] in payload_props["code"]["enum"]
    assert isinstance(payload["duration_ms"], int) and payload["duration_ms"] >= 0
    assert isinstance(payload["message"], str), "message must be a string"
    assert 1 <= len(payload["message"]) <= 1000, "message must be 1..1000 chars"

    if "dependency" in payload:
        assert payload["dependency"] in _DEPENDENCIES_V2
        assert (
            payload["component"] in _DEPENDENCY_COMPONENTS_V2
        ), "dependency-scoped payloads must use repository/infra component"
    if payload["action"] in ("dev", "dev-down") and payload["phase"] in (
        _DEPENDENCY_SCOPED_PHASES_V2
    ):
        assert "dependency" in payload, "dependency-scoped phases require the dependency field"
    if payload["code"] in _DEPENDENCY_SCOPED_CODES_V2:
        assert "dependency" in payload, "dependency-specific failure codes require dependency"
    if payload["status"] in ("WAITING", "PASSED"):
        assert payload["code"] == "OK", "WAITING/PASSED payloads must carry code OK"
    if payload["status"] in ("FAILED", "SKIPPED"):
        assert payload["code"] != "OK", "FAILED/SKIPPED payloads must not carry OK"


def read_events_v2_jsonl(text: str) -> list[dict[str, Any]]:
    """Read a JSONL stream, returning only schema-valid v2 envelopes."""
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = parse_jsonl_line(line)
        validate_event_v2(event)
        events.append(event)
    return events
