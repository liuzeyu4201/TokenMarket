"""SF02 workflow event v2 standard-envelope tests (T009).

These tests cover the v2 event contract in
``shared/contracts/repository-workflow/v2/workflow-event.schema.json``:
unique UUID event IDs, stable type/version/producer, UTC RFC 3339 timestamps,
per-lifecycle-run correlation IDs, strict payloads, the dependency field,
WAITING-state semantics, stable SF02 diagnostic codes, emission ordering,
value redaction, and the strict-consumer migration between v1 and v2.

They fail until T015 implements the v2 emission API in
``tools/workflow/events.py`` alongside the preserved v1 history.
"""

from __future__ import annotations

import importlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from .helpers import load_json

SCHEMA_V2_PATH = (
    Path("shared") / "contracts" / "repository-workflow" / "v2" / "workflow-event.schema.json"
)
SCHEMA_V1_PATH = (
    Path("shared") / "contracts" / "repository-workflow" / "v1" / "workflow-event.schema.json"
)

ENVELOPE_KEYS = {
    "event_id",
    "event_type",
    "schema_version",
    "timestamp",
    "producer",
    "correlation_id",
    "payload",
}
PAYLOAD_REQUIRED_KEYS = {
    "action",
    "component",
    "phase",
    "status",
    "code",
    "duration_ms",
    "message",
}
PAYLOAD_ALLOWED_KEYS = PAYLOAD_REQUIRED_KEYS | {"dependency"}

COMPONENTS = {
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
DEPENDENCIES = {"postgres", "redis", "grafana"}
DEPENDENCY_COMPONENTS = {"repository", "infra"}
DEPENDENCY_SCOPED_PHASES = {
    "image-pull",
    "image-verify",
    "reconcile",
    "liveness",
    "readiness",
    "stopping",
}
DEPENDENCY_SCOPED_CODES = {
    "IMAGE_UNAVAILABLE",
    "PORT_CONFLICT",
    "DEPENDENCY_NOT_READY",
}
V1_CODES = {
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
SF02_CODES = {
    "IMAGE_UNAVAILABLE",
    "PORT_CONFLICT",
    "DEPENDENCY_NOT_READY",
    "OPERATION_IN_PROGRESS",
    "RESOURCE_OWNERSHIP_CONFLICT",
}
V2_CODES = V1_CODES | SF02_CODES
V1_STATUSES = {"STARTED", "PASSED", "FAILED", "SKIPPED"}
V2_STATUSES = V1_STATUSES | {"WAITING"}

_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_KEBAB_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def _events_module() -> Any:
    try:
        return importlib.import_module("workflow.events")
    except ImportError as exc:
        pytest.fail(f"workflow.events has not been implemented yet (T015): {exc}")


def _symbol(name: str) -> Any:
    symbol = getattr(_events_module(), name, None)
    if symbol is None:
        pytest.fail(f"workflow.events does not provide `{name}` yet (T015)")
    return symbol


def _emit_event_v2(**kwargs: Any) -> dict[str, Any]:
    return _symbol("emit_event_v2")(**kwargs)


def _event_log_v2(*args: Any, **kwargs: Any) -> Any:
    return _symbol("EventLogV2")(*args, **kwargs)


def _diagnostic_code_v2(value: str) -> Any:
    return _symbol("DiagnosticCodeV2")(value)


def _to_jsonl(event: dict[str, Any]) -> str:
    return _symbol("to_jsonl")(event)


def _v2_kwargs(**overrides: Any) -> dict[str, Any]:
    """Return baseline keyword arguments for one valid v2 emission."""
    kwargs: dict[str, Any] = {
        "action": "dev",
        "component": "repository",
        "phase": "preflight",
        "status": "PASSED",
        "code": _diagnostic_code_v2("OK"),
        "duration_ms": 5,
        "message": "preflight completed",
        "correlation_id": "corr-0001",
    }
    kwargs.update(overrides)
    return kwargs


def load_event_schema_v2() -> dict[str, Any]:
    """Load the published v2 event schema from the runtime contract copy."""
    return load_json(str(SCHEMA_V2_PATH))


def validate_event_v2(event: dict[str, Any]) -> None:
    """Strict v2 consumer validation against the published schema.

    Manual validation keeps the suite self-contained without a jsonschema
    dependency; consts and enums are cross-checked with the contract file so
    schema drift breaks these tests.
    """
    schema = load_event_schema_v2()

    assert set(event.keys()) == ENVELOPE_KEYS, "v2 envelope allows no additional fields"
    assert isinstance(event["event_id"], str)
    uuid.UUID(event["event_id"])
    assert event["event_type"] == schema["properties"]["event_type"]["const"]
    assert event["schema_version"] == schema["properties"]["schema_version"]["const"]
    assert event["producer"] == schema["properties"]["producer"]["const"]
    assert isinstance(event["timestamp"], str) and _RFC3339_RE.match(event["timestamp"])
    parsed_ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    assert parsed_ts.utcoffset() == timedelta(0), "timestamp must be UTC"
    assert isinstance(event["correlation_id"], str)
    assert 1 <= len(event["correlation_id"]) <= 128

    payload = event["payload"]
    assert isinstance(payload, dict)
    assert PAYLOAD_REQUIRED_KEYS <= set(payload.keys()), "payload misses required fields"
    assert set(payload.keys()) <= PAYLOAD_ALLOWED_KEYS, "payload allows no additional fields"
    assert isinstance(payload["action"], str) and _KEBAB_RE.match(payload["action"])
    assert (
        payload["component"] in schema["properties"]["payload"]["properties"]["component"]["enum"]
    )
    assert isinstance(payload["phase"], str) and _KEBAB_RE.match(payload["phase"])
    assert payload["status"] in schema["properties"]["payload"]["properties"]["status"]["enum"]
    assert payload["code"] in schema["properties"]["payload"]["properties"]["code"]["enum"]
    assert isinstance(payload["duration_ms"], int) and payload["duration_ms"] >= 0
    assert isinstance(payload["message"], str)
    assert 1 <= len(payload["message"]) <= 1000

    if "dependency" in payload:
        assert payload["dependency"] in DEPENDENCIES
        assert (
            payload["component"] in DEPENDENCY_COMPONENTS
        ), "dependency-scoped payloads must use repository/infra component"
    if payload["action"] in ("dev", "dev-down") and payload["phase"] in DEPENDENCY_SCOPED_PHASES:
        assert "dependency" in payload, "dependency-scoped phases require the dependency field"
    if payload["code"] in DEPENDENCY_SCOPED_CODES:
        assert "dependency" in payload, "dependency-specific failure codes require dependency"
    if payload["status"] in ("WAITING", "PASSED"):
        assert payload["code"] == "OK", "WAITING/PASSED payloads must carry code OK"
    if payload["status"] in ("FAILED", "SKIPPED"):
        assert payload["code"] != "OK", "FAILED/SKIPPED payloads must not carry OK"


def strict_v1_reader_accepts(event: dict[str, Any]) -> bool:
    """Mimic a strict v1 consumer: v1 schema root keys, no additional fields."""
    v1_schema = load_json(str(SCHEMA_V1_PATH))
    required = set(v1_schema["required"])
    if set(event.keys()) != required:
        return False
    if event["schema_version"] != v1_schema["properties"]["schema_version"]["const"]:
        return False
    if event["status"] not in v1_schema["properties"]["status"]["enum"]:
        return False
    return event["code"] in v1_schema["properties"]["code"]["enum"]


class TestV2ModuleExports:
    """The v2 emission API must exist next to the preserved v1 API."""

    def test_v2_symbols_exist(self) -> None:
        assert callable(_symbol("emit_event_v2"))
        assert callable(_symbol("EventLogV2"))
        assert callable(_symbol("stable_codes_v2"))
        assert callable(_symbol("aggregate_status_v2"))
        assert callable(_symbol("DiagnosticCodeV2"))

    def test_v1_symbols_preserved(self) -> None:
        for name in (
            "emit_event",
            "EventLog",
            "aggregate_status",
            "stable_codes",
            "to_jsonl",
        ):
            assert callable(getattr(_events_module(), name, None)), f"v1 API missing: {name}"


class TestEnvelopeIdentity:
    """Envelope-level identity: UUIDs, stable consts, UTC timestamps, correlation."""

    def test_event_ids_are_unique_v4_uuids(self) -> None:
        events = [_emit_event_v2(**_v2_kwargs()) for _ in range(8)]
        ids = [event["event_id"] for event in events]
        assert len(set(ids)) == len(ids), "event_id must be unique per emission"
        for event_id in ids:
            assert uuid.UUID(event_id).version == 4

    def test_envelope_has_stable_type_version_producer(self) -> None:
        event = _emit_event_v2(**_v2_kwargs())
        assert event["event_type"] == "workflow.step"
        assert event["schema_version"] == "2.0.0"
        assert event["producer"] == "repository-workflow"
        validate_event_v2(event)

    def test_timestamp_is_utc_rfc3339_emission_time(self) -> None:
        before = datetime.now(timezone.utc) - timedelta(seconds=5)
        event = _emit_event_v2(**_v2_kwargs())
        after = datetime.now(timezone.utc) + timedelta(seconds=5)
        timestamp = event["timestamp"]
        assert _RFC3339_RE.match(timestamp), f"not RFC 3339: {timestamp!r}"
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed.utcoffset() == timedelta(0), "timestamp must be UTC"
        assert before <= parsed <= after, "timestamp must be the emission time"

    def test_correlation_id_shared_within_one_lifecycle_run(self) -> None:
        log = _event_log_v2(correlation_id="lifecycle-run-1")
        log.start("dev", "repository", "preflight")
        log.wait(
            "dev",
            "infra",
            "readiness",
            dependency="postgres",
            message="waiting for probe",
        )
        log.finish("dev", "repository", "preflight", status="PASSED")
        correlation_ids = {event["correlation_id"] for event in log.events}
        assert correlation_ids == {"lifecycle-run-1"}

    def test_default_correlation_ids_differ_between_runs(self) -> None:
        first = _event_log_v2()
        second = _event_log_v2()
        first.start("dev", "repository", "preflight")
        second.start("dev", "repository", "preflight")
        assert first.events[0]["correlation_id"] != second.events[0]["correlation_id"]
        assert first.events[0]["event_id"] != second.events[0]["event_id"]

    @pytest.mark.parametrize("bad", ["", "x" * 129])
    def test_correlation_id_length_validated(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(correlation_id=bad))


class TestStrictPayload:
    """The payload must reject anything the strict schema forbids."""

    def test_envelope_and_payload_have_no_additional_fields(self) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                component="infra",
                phase="readiness",
                dependency="redis",
                message="redis authenticated PING/PONG passed",
            )
        )
        validate_event_v2(event)

    @pytest.mark.parametrize("status", sorted(V2_STATUSES))
    def test_all_contract_statuses_emit_schema_valid_payloads(self, status: str) -> None:
        code = _diagnostic_code_v2(
            "OK" if status in ("STARTED", "WAITING", "PASSED") else "STEP_FAILED"
        )
        event = _emit_event_v2(**_v2_kwargs(status=status, code=code))
        validate_event_v2(event)
        assert event["payload"]["status"] == status

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(status="RUNNING"))

    def test_unknown_component_rejected(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(component="database"))

    @pytest.mark.parametrize("action", ["Dev", "DEV", "_dev", "1dev", "dev_down"])
    def test_invalid_action_pattern_rejected(self, action: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(action=action))

    @pytest.mark.parametrize("phase", ["Preflight", "_lock", "image pull"])
    def test_invalid_phase_pattern_rejected(self, phase: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(phase=phase))

    @pytest.mark.parametrize("status", ["FAILED", "SKIPPED"])
    def test_failed_and_skipped_reject_ok_code(self, status: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(status=status, code=_diagnostic_code_v2("OK")))

    @pytest.mark.parametrize("status", ["WAITING", "PASSED"])
    def test_waiting_and_passed_require_ok_code(self, status: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(status=status, code=_diagnostic_code_v2("STEP_FAILED")))

    def test_empty_message_rejected(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(**_v2_kwargs(message=""))

    def test_message_bounded_to_contract_maximum(self) -> None:
        event = _emit_event_v2(**_v2_kwargs(message="x" * 5000))
        assert 1 <= len(event["payload"]["message"]) <= 1000
        validate_event_v2(event)

    def test_negative_duration_never_emitted(self) -> None:
        event = _emit_event_v2(**_v2_kwargs(duration_ms=-10))
        assert event["payload"]["duration_ms"] >= 0


class TestDependencyField:
    """Dependency-scoped phases and codes require the dependency field."""

    @pytest.mark.parametrize("phase", sorted(DEPENDENCY_SCOPED_PHASES))
    @pytest.mark.parametrize("action", ["dev", "dev-down"])
    def test_dependency_scoped_phase_requires_dependency(self, action: str, phase: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(
                **_v2_kwargs(
                    action=action,
                    component="infra",
                    phase=phase,
                    status="FAILED",
                    code=_diagnostic_code_v2("STEP_FAILED"),
                    message="scoped phase without dependency must fail",
                )
            )

    @pytest.mark.parametrize("code", sorted(DEPENDENCY_SCOPED_CODES))
    def test_dependency_scoped_code_requires_dependency(self, code: str) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(
                **_v2_kwargs(
                    component="infra",
                    status="FAILED",
                    code=_diagnostic_code_v2(code),
                    message="dependency-specific code without dependency must fail",
                )
            )

    @pytest.mark.parametrize("dependency", sorted(DEPENDENCIES))
    def test_dependency_scoped_payload_is_schema_valid(self, dependency: str) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                component="infra",
                phase="readiness",
                dependency=dependency,
                status="PASSED",
                message=f"{dependency} authenticated readiness passed",
            )
        )
        assert event["payload"]["dependency"] == dependency
        validate_event_v2(event)

    def test_dependency_restricts_component(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(
                **_v2_kwargs(
                    component="api-service",
                    phase="readiness",
                    dependency="postgres",
                    message="service components must not carry dependency payloads",
                )
            )

    @pytest.mark.parametrize("component", sorted(DEPENDENCY_COMPONENTS))
    def test_dependency_allowed_components(self, component: str) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                component=component,
                phase="readiness",
                dependency="grafana",
                message=f"{component} dependency payload accepted",
            )
        )
        validate_event_v2(event)

    def test_unknown_dependency_rejected(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(
                **_v2_kwargs(
                    component="infra",
                    phase="readiness",
                    dependency="kafka",
                    message="only the three SF02 dependencies are valid",
                )
            )

    @pytest.mark.parametrize("phase", ["identity", "final", "aggregate", "preflight", "lock"])
    def test_aggregate_identity_and_final_may_omit_dependency(self, phase: str) -> None:
        event = _emit_event_v2(**_v2_kwargs(phase=phase, message=f"{phase} completed"))
        assert "dependency" not in event["payload"]
        validate_event_v2(event)


class TestWaitingState:
    """WAITING expresses bounded in-progress polling and always carries OK."""

    def test_event_log_wait_emits_waiting_with_ok(self) -> None:
        log = _event_log_v2(correlation_id="corr-wait")
        log.wait(
            "dev",
            "infra",
            "readiness",
            dependency="postgres",
            message="postgres probe still starting",
            duration_ms=250,
        )
        event = log.events[-1]
        assert event["payload"]["status"] == "WAITING"
        assert event["payload"]["code"] == "OK"
        assert event["payload"]["duration_ms"] == 250
        validate_event_v2(event)

    def test_waiting_rejects_non_ok_code(self) -> None:
        with pytest.raises(ValueError):
            _emit_event_v2(
                **_v2_kwargs(
                    status="WAITING",
                    code=_diagnostic_code_v2("DEPENDENCY_NOT_READY"),
                    component="infra",
                    phase="readiness",
                    dependency="postgres",
                    message="waiting cannot carry a failure code",
                )
            )

    def test_v2_status_set_extends_v1_with_waiting(self) -> None:
        schema = load_event_schema_v2()
        enum = set(schema["properties"]["payload"]["properties"]["status"]["enum"])
        assert enum == V2_STATUSES
        assert V1_STATUSES < V2_STATUSES


class TestDiagnosticCodes:
    """The v2 diagnostic set is the stable v1 set plus the SF02 additions."""

    def test_stable_codes_v2_exact_contract_set(self) -> None:
        schema = load_event_schema_v2()
        enum = set(schema["properties"]["payload"]["properties"]["code"]["enum"])
        assert _symbol("stable_codes_v2")() == V2_CODES == enum

    def test_v2_codes_preserve_v1_set(self) -> None:
        assert V1_CODES < set(_symbol("stable_codes_v2")())

    def test_v1_stable_codes_unchanged(self) -> None:
        assert getattr(_events_module(), "stable_codes")() == V1_CODES

    @pytest.mark.parametrize("code", sorted(V2_CODES))
    def test_every_v2_code_constructible(self, code: str) -> None:
        assert _diagnostic_code_v2(code).value == code


class TestEmissionOrdering:
    """Events are ordered by emission within one correlation ID."""

    def test_log_preserves_emission_order(self) -> None:
        log = _event_log_v2(correlation_id="corr-order")
        log.start("dev", "repository", "preflight")
        log.finish("dev", "repository", "preflight", status="PASSED")
        log.start("dev", "infra", "readiness", dependency="redis")
        log.wait("dev", "infra", "readiness", dependency="redis", message="redis starting")
        log.finish(
            "dev",
            "infra",
            "readiness",
            dependency="redis",
            status="PASSED",
            message="redis ready",
        )
        statuses = [event["payload"]["status"] for event in log.events]
        assert statuses == ["STARTED", "PASSED", "STARTED", "WAITING", "PASSED"]
        correlation_ids = {event["correlation_id"] for event in log.events}
        assert correlation_ids == {"corr-order"}

    def test_event_ids_unique_within_run(self) -> None:
        log = _event_log_v2(correlation_id="corr-unique")
        for _ in range(5):
            log.wait(
                "dev",
                "infra",
                "liveness",
                dependency="grafana",
                message="grafana starting",
            )
        ids = [event["event_id"] for event in log.events]
        assert len(set(ids)) == len(ids)

    def test_jsonl_lines_preserve_log_order(self) -> None:
        log = _event_log_v2(correlation_id="corr-jsonl")
        log.start("dev-down", "repository", "identity")
        log.finish("dev-down", "repository", "identity", status="PASSED")
        lines = [_to_jsonl(event) for event in log.events]
        parsed = [json.loads(line) for line in lines]
        assert [p["payload"]["status"] for p in parsed] == ["STARTED", "PASSED"]


class TestRedaction:
    """Messages must never carry secret values, user-info URLs, or workspace paths."""

    def test_secret_like_values_redacted(self) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                status="FAILED",
                code=_diagnostic_code_v2("INVALID_CONFIG"),
                message="variable DATABASE_URL contains sk-1234567890abcdef",
            )
        )
        line = _to_jsonl(event)
        assert "sk-1234567890abcdef" not in line
        assert "DATABASE_URL" in line

    def test_local_secret_grammar_redacted(self) -> None:
        secret = "tm_local_" + "a1B2" * 12
        event = _emit_event_v2(
            **_v2_kwargs(
                status="FAILED",
                code=_diagnostic_code_v2("INVALID_CONFIG"),
                message=f"decoded secret {secret} failed validation",
            )
        )
        assert secret not in _to_jsonl(event)

    def test_url_user_info_removed(self) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                status="FAILED",
                code=_diagnostic_code_v2("INVALID_CONFIG"),
                message="reject postgresql://dev:s3cr3t-value@127.0.0.1:5432/tokenmarket",
            )
        )
        message = event["payload"]["message"]
        assert "s3cr3t-value" not in message
        assert "dev:s3cr3t-value@" not in message
        assert "127.0.0.1:5432" in message

    def test_absolute_workspace_path_redacted(self) -> None:
        event = _emit_event_v2(
            **_v2_kwargs(
                status="FAILED",
                code=_diagnostic_code_v2("STEP_FAILED"),
                message="workspace /Users/alice/Projects/TokenMarket is not inspectable",
            )
        )
        message = event["payload"]["message"]
        assert "/Users/alice/Projects/TokenMarket" not in message

    def test_redacted_message_remains_bounded(self) -> None:
        secret = "tm_local_" + "z9" * 40
        event = _emit_event_v2(**_v2_kwargs(message=f"{secret} " + "pad " * 600))
        assert 1 <= len(event["payload"]["message"]) <= 1000
        assert secret not in event["payload"]["message"]


class TestAggregationV2:
    """Aggregate status derives from strict v2 payloads."""

    def _log_with(self, correlation_id: str, statuses: list[str]) -> Any:
        log = _event_log_v2(correlation_id=correlation_id)
        for index, status in enumerate(statuses):
            dependency = ("postgres", "redis", "grafana")[index % 3]
            if status == "WAITING":
                log.wait(
                    "dev",
                    "infra",
                    "readiness",
                    dependency=dependency,
                    message="waiting",
                )
            else:
                log.finish(
                    "dev",
                    "infra",
                    "readiness",
                    dependency=dependency,
                    status=status,
                    message=f"{dependency} {status.lower()}",
                )
        return log

    def test_aggregate_passes_only_when_all_steps_pass(self) -> None:
        log = self._log_with("corr-agg-pass", ["PASSED", "PASSED", "PASSED"])
        result = _symbol("aggregate_status_v2")(log.events)
        assert result["status"] == "PASSED"
        assert result["code"] == "OK"
        assert result["passed"] == 3

    def test_partial_dependency_success_never_aggregates_passed(self) -> None:
        log = self._log_with("corr-agg-partial", ["PASSED", "PASSED", "FAILED"])
        result = _symbol("aggregate_status_v2")(log.events)
        assert result["status"] == "FAILED"
        assert result["code"] != "OK"
        assert result["passed"] == 2
        assert result["failed"] == 1

    def test_unresolved_waiting_prevents_aggregate_pass(self) -> None:
        log = self._log_with("corr-agg-waiting", ["PASSED", "WAITING"])
        result = _symbol("aggregate_status_v2")(log.events)
        assert result["status"] != "PASSED"

    def test_aggregate_reads_v2_payloads(self) -> None:
        log = self._log_with("corr-agg-shape", ["PASSED", "SKIPPED"])
        result = _symbol("aggregate_status_v2")(log.events)
        assert result["skipped"] == 1
        assert result["status"] == "PASSED"


class TestStrictConsumerMigration:
    """Strict v1 and v2 readers reject each other; migration is explicit."""

    def test_strict_v1_reader_rejects_v2_envelope(self) -> None:
        event = _emit_event_v2(**_v2_kwargs())
        assert not strict_v1_reader_accepts(
            event
        ), "a strict v1 reader must reject the v2 envelope instead of misparsing it"

    def test_strict_v2_reader_rejects_v1_event(self) -> None:
        v1_event = getattr(_events_module(), "emit_event")(
            action="lint",
            component="api-service",
            phase="execution",
            status="FAILED",
            code=getattr(_events_module(), "DiagnosticCode")("STEP_FAILED"),
            duration_ms=3,
            message="v1 history event",
            run_id="run-v1",
        )
        with pytest.raises((AssertionError, KeyError, ValueError)):
            validate_event_v2(v1_event)

    def test_v1_emission_preserves_history_shape(self) -> None:
        v1_event = getattr(_events_module(), "emit_event")(
            action="test",
            component="repository",
            phase="execution",
            status="PASSED",
            code=getattr(_events_module(), "DiagnosticCode")("OK"),
            duration_ms=1,
            message="v1 regression event",
            run_id="run-legacy",
        )
        assert v1_event["schema_version"] == "1.0.0"
        assert v1_event["run_id"] == "run-legacy"
        assert "payload" not in v1_event
        assert "event_id" not in v1_event
        assert strict_v1_reader_accepts(v1_event)

    def test_v2_envelope_serializes_as_single_json_object(self) -> None:
        event = _emit_event_v2(**_v2_kwargs())
        line = _to_jsonl(event)
        assert "\n" not in line
        parsed = json.loads(line)
        assert set(parsed.keys()) == ENVELOPE_KEYS
        validate_event_v2(parsed)
