"""Workflow event emission, schema and aggregation tests (T017, SF02 T016).

The v1 tests below are explicit SF01 Make/event regression coverage: they pin
the immutable v1 emission API, v1 schema 1.0.0 shape, and v1 diagnostic set.
The SF02 T016 additions migrate the repository-owned JSONL reader/fixture
assertions to the v2 standard envelope defined in
``shared/contracts/repository-workflow/v2/workflow-event.schema.json`` via the
shared v2 reader in ``tests/workflow/helpers.py``.
"""

from __future__ import annotations

# The implementation under test is intentionally absent at the start of T017.
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from .helpers import load_json, read_events_v2_jsonl, repo_path, validate_event_v2


def _events_module() -> Any:
    try:
        return importlib.import_module("workflow.events")
    except ImportError as exc:
        pytest.fail(f"workflow.events has not been implemented yet (T030): {exc}")


def _emit_event(**kwargs) -> dict[str, Any]:
    """Emit a v1 historical event for immutable SF01 regression coverage."""
    mod = _events_module()
    emitter = getattr(mod, "emit_event_v1", None) or getattr(mod, "emit_event")
    return emitter(**kwargs)


def _to_jsonl(event: dict[str, Any]) -> str:
    return getattr(_events_module(), "to_jsonl")(event)


def _aggregate_status(events: list[dict[str, Any]]) -> dict[str, Any]:
    return getattr(_events_module(), "aggregate_status")(events)


def _stable_codes() -> set[str]:
    return getattr(_events_module(), "stable_codes")()


def _diagnostic_code(value: str) -> Any:
    return getattr(_events_module(), "DiagnosticCode")(value)


def _event_log(run_id: str) -> Any:
    return getattr(_events_module(), "EventLog")(run_id)


SCHEMA_PATH = (
    Path("shared") / "contracts" / "repository-workflow" / "v1" / "workflow-event.schema.json"
)

COMPONENTS = [
    "repository",
    "proxy-gateway",
    "api-service",
    "billing-service",
    "admin-service",
    "frontend",
    "shared",
    "infra",
    "ops",
]

VALID_STATUSES = {"STARTED", "PASSED", "FAILED", "SKIPPED"}
VALID_CODES = {
    "OK",
    "INVALID_USAGE",
    "TOOL_MISSING",
    "TOOL_VERSION_UNSUPPORTED",
    "INVALID_CONFIG",
    "INVALID_MODE",
    "PROD_APPROVAL_REQUIRED",
    "SF02_NOT_READY",
    "COMPONENT_NOT_INITIALIZED",
    "NO_TESTS_EXECUTED",
    "STEP_FAILED",
    "CONTRACT_DRIFT",
    "MIGRATION_INVALID",
    "SECRET_DETECTED",
}


def load_event_schema() -> dict[str, Any]:
    """Load the published workflow-event schema from the runtime contract copy."""
    return load_json(str(SCHEMA_PATH))


def validate_event_against_schema(event: dict[str, Any]) -> None:
    """Manual schema validation using the published event schema.

    Keeps the test self-contained without adding a jsonschema dependency.
    """
    schema = load_event_schema()

    assert event["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert isinstance(event["run_id"], str) and 1 <= len(event["run_id"]) <= 128
    assert isinstance(event["action"], str) and event["action"]
    assert event["action"][0].islower()
    assert event["component"] in COMPONENTS
    assert isinstance(event["phase"], str) and event["phase"]
    assert event["phase"][0].islower()
    assert event["status"] in VALID_STATUSES
    assert event["code"] in VALID_CODES
    assert isinstance(event["duration_ms"], int) and event["duration_ms"] >= 0
    assert isinstance(event["message"], str) and 1 <= len(event["message"]) <= 1000

    if event["status"] == "PASSED":
        assert event["code"] == "OK", "PASSED events must carry code OK"
    if event["status"] in ("FAILED", "SKIPPED"):
        assert event["code"] != "OK", "FAILED/SKIPPED events must not carry OK"


def test_event_module_exports_stable_symbols() -> None:
    """workflow.events must expose the event types and helpers used by the CLI."""
    mod = _events_module()
    assert callable(getattr(mod, "emit_event"))
    assert callable(getattr(mod, "emit_event_v1"))
    assert callable(getattr(mod, "to_jsonl"))
    assert callable(getattr(mod, "aggregate_status"))
    assert set(_stable_codes()) == VALID_CODES


def test_public_emit_event_defaults_to_v2_envelope_after_activation() -> None:
    """T074: public emit_event produces the v2 standard envelope."""
    mod = _events_module()
    event = mod.emit_event(
        action="test",
        component="repository",
        phase="phase-one",
        status="PASSED",
        code=mod.DiagnosticCode.OK,
        duration_ms=12,
        message="step completed",
        run_id="run-001",
    )
    assert event["schema_version"] == "2.0.0"
    assert event["event_type"] == "workflow.step"
    assert event["producer"] == "repository-workflow"
    assert event["correlation_id"] == "run-001"
    assert event["payload"]["status"] == "PASSED"
    assert event["payload"]["code"] == "OK"


def test_emit_event_produces_schema_valid_dict() -> None:
    """A freshly emitted event dict must satisfy the v1 schema."""
    event = _emit_event(
        action="test",
        component="repository",
        phase="phase-one",
        status="PASSED",
        code=_diagnostic_code("OK"),
        duration_ms=12,
        message="step completed",
        run_id="run-001",
    )
    validate_event_against_schema(event)
    assert event["action"] == "test"
    assert event["component"] == "repository"
    assert event["status"] == "PASSED"
    assert event["code"] == "OK"


def test_to_jsonl_emits_single_valid_json_object() -> None:
    """to_jsonl must return one parseable JSON object per event with no extra keys."""
    event = _emit_event(
        action="lint",
        component="api-service",
        phase="execution",
        status="FAILED",
        code=_diagnostic_code("STEP_FAILED"),
        duration_ms=34,
        message="lint exited with 1",
        run_id="run-002",
    )
    line = _to_jsonl(event)
    assert isinstance(line, str)
    assert line.count("{") == line.count("}")
    parsed = json.loads(line)
    validate_event_against_schema(parsed)
    assert parsed["component"] == "api-service"
    assert parsed["status"] == "FAILED"


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    """Public EventLog emits v2 envelopes after T074; unwrap for assertions."""
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else event


def test_event_log_records_step_order() -> None:
    """STARTED events must precede terminal events for the same component/action."""
    log = _event_log(run_id="run-003")
    log.start("bootstrap", "proxy-gateway", "setup")
    log.finish("bootstrap", "proxy-gateway", "setup", status="PASSED")

    events = log.events
    assert len(events) == 2
    assert _payload(events[0])["status"] == "STARTED"
    assert _payload(events[1])["status"] == "PASSED"
    assert _payload(events[0])["action"] == _payload(events[1])["action"] == "bootstrap"
    assert (
        _payload(events[0])["component"]
        == _payload(events[1])["component"]
        == "proxy-gateway"
    )


def test_event_log_skips_remaining_steps_after_failure() -> None:
    """After any required step fails, remaining required steps must be SKIPPED."""
    log = _event_log(run_id="run-004")
    steps = [
        ("bootstrap", "repository"),
        ("fmt", "proxy-gateway"),
        ("lint", "api-service"),
        ("test", "billing-service"),
    ]

    for action, component in steps[:2]:
        log.start(action, component, "execution")
        log.finish(action, component, "execution", status="PASSED")

    log.start("lint", "api-service", "execution")
    log.finish(
        "lint",
        "api-service",
        "execution",
        status="FAILED",
        code=_diagnostic_code("STEP_FAILED"),
        message="flake8 reported errors",
    )

    # Remaining required steps should be recorded as SKIPPED, not silently omitted.
    log.skip("test", "billing-service", "execution", reason="previous step failed")

    events = log.events
    statuses = [_payload(e)["status"] for e in events]
    assert statuses == [
        "STARTED",
        "PASSED",
        "STARTED",
        "PASSED",
        "STARTED",
        "FAILED",
        "SKIPPED",
    ]

    skipped = _payload(events[-1])
    assert skipped["status"] == "SKIPPED"
    assert skipped["code"] != "OK"
    assert "previous step failed" in skipped["message"]


def test_aggregate_status_passes_when_all_steps_pass() -> None:
    """Final aggregate status is PASSED only if every required step passed."""
    log = _event_log(run_id="run-005")
    for component in ("proxy-gateway", "api-service"):
        log.start("test", component, "execution")
        log.finish("test", component, "execution", status="PASSED")

    result = _aggregate_status(log.events)
    assert result["status"] == "PASSED"
    assert result["code"] == "OK"
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["skipped"] == 0


def test_aggregate_status_fails_when_any_step_fails() -> None:
    """A single FAILED step makes the aggregate FAILED and counts SKIPPED steps."""
    log = _event_log(run_id="run-006")
    log.start("fmt", "frontend", "execution")
    log.finish("fmt", "frontend", "execution", status="PASSED")
    log.start("lint", "frontend", "execution")
    log.finish(
        "lint",
        "frontend",
        "execution",
        status="FAILED",
        code=_diagnostic_code("STEP_FAILED"),
        message="ESLint error",
    )
    log.skip("test", "frontend", "execution", reason="lint failed")

    result = _aggregate_status(log.events)
    assert result["status"] == "FAILED"
    assert result["code"] != "OK"
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1


def test_diagnostic_codes_are_stable_contract_set() -> None:
    """DiagnosticCode enum/string set must exactly match the published contract."""
    codes = _stable_codes()
    DiagnosticCode = getattr(_events_module(), "DiagnosticCode")
    assert isinstance(codes, set)
    assert codes == VALID_CODES
    assert DiagnosticCode.OK == "OK"
    assert DiagnosticCode.SF02_NOT_READY == "SF02_NOT_READY"
    assert DiagnosticCode.COMPONENT_NOT_INITIALIZED == "COMPONENT_NOT_INITIALIZED"


def test_messages_do_not_contain_secret_values() -> None:
    """Event messages must redact values classified as secret before serialization."""
    sensitive_value = "sk-1234567890abcdef"
    event = _emit_event(
        action="config-check",
        component="repository",
        phase="preflight",
        status="FAILED",
        code=_diagnostic_code("INVALID_CONFIG"),
        duration_ms=0,
        message=f"variable DATABASE_URL contains {sensitive_value}",
        run_id="run-007",
    )
    line = _to_jsonl(event)
    assert sensitive_value not in line
    assert "DATABASE_URL" in line or "variable" in line


def _emit_event_v2(**kwargs: Any) -> dict[str, Any]:
    return getattr(_events_module(), "emit_event_v2")(**kwargs)


def _diagnostic_code_v2(value: str) -> Any:
    return getattr(_events_module(), "DiagnosticCodeV2")(value)


V2_SCHEMA_PATH = (
    Path("shared") / "contracts" / "repository-workflow" / "v2" / "workflow-event.schema.json"
)


class TestV2ConsumerMigration:
    """Repository-owned JSONL readers migrated to the v2 standard envelope.

    The shared v2 reader in ``tests/workflow/helpers.py`` accepts emitted v2
    envelopes and rejects v1-shaped dicts, so v1 remains explicit regression
    history rather than a silently misparsed stream.
    """

    def test_v2_schema_runtime_copy_published(self) -> None:
        schema = load_json(str(V2_SCHEMA_PATH))
        assert schema["properties"]["schema_version"]["const"] == "2.0.0"
        assert schema["properties"]["event_type"]["const"] == "workflow.step"
        assert schema["properties"]["producer"]["const"] == "repository-workflow"

    def test_v2_reader_accepts_emitted_envelope(self) -> None:
        event = _emit_event_v2(
            action="dev",
            component="repository",
            phase="preflight",
            status="PASSED",
            code=_diagnostic_code_v2("OK"),
            duration_ms=3,
            message="preflight completed",
            correlation_id="corr-migration-1",
        )
        events = read_events_v2_jsonl(_to_jsonl(event))
        assert events == [event]
        validate_event_v2(events[0])

    def test_v2_reader_accepts_event_log_v2_stream(self) -> None:
        log = getattr(_events_module(), "EventLogV2")(correlation_id="corr-migration-2")
        log.start("dev", "repository", "preflight")
        log.wait(
            "dev",
            "infra",
            "readiness",
            dependency="postgres",
            message="postgres starting",
        )
        log.finish(
            "dev",
            "infra",
            "readiness",
            dependency="postgres",
            status="PASSED",
            message="postgres ready",
        )
        stream = "\n".join(_to_jsonl(event) for event in log.events)
        events = read_events_v2_jsonl(stream)
        assert [event["payload"]["status"] for event in events] == [
            "STARTED",
            "WAITING",
            "PASSED",
        ]
        assert {event["correlation_id"] for event in events} == {"corr-migration-2"}
        assert len({event["event_id"] for event in events}) == 3

    def test_v2_reader_rejects_v1_event_dicts(self) -> None:
        v1_event = _emit_event(
            action="lint",
            component="api-service",
            phase="execution",
            status="FAILED",
            code=_diagnostic_code("STEP_FAILED"),
            duration_ms=5,
            message="v1 history event",
            run_id="run-v1-reader",
        )
        with pytest.raises(AssertionError):
            validate_event_v2(v1_event)

    def test_v2_reader_rejects_v1_jsonl_stream(self) -> None:
        v1_event = _emit_event(
            action="test",
            component="repository",
            phase="execution",
            status="PASSED",
            code=_diagnostic_code("OK"),
            duration_ms=1,
            message="v1 regression event",
            run_id="run-v1-stream",
        )
        with pytest.raises(AssertionError):
            read_events_v2_jsonl(_to_jsonl(v1_event))
