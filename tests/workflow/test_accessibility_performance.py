"""T087 accessibility and performance contract tests.

Verify that `make help` completes within two seconds, preflight checks complete
within five seconds, NO_COLOR disables color, and status is readable without a
TTY.

The SF02 section below (T024) extends the same guarantees to the new guarded
local-dependency lifecycle output: plain-text and JSONL forms must stay
NO_COLOR-safe, screen-reader understandable (no color-only semantics, no
icons/animation), non-interactive, and the process exit status must match the
aggregate outcome. All SF02 cases use scripted seams (no real Docker access).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pytest

from workflow.cli import execute_dev_guarded
from workflow.local_env.compose import ImagePullRecord, RuntimeFacts, ServiceState
from workflow.local_env.identity import WorkspaceIdentity
from workflow.local_env.models import (
    DependencyHealthResult,
    DependencyId,
    LivenessState,
    ProbeKind,
    ReadinessState,
    load_manifest,
)

from .conftest import TestProjectIdentity
from .helpers import find_repo_root, read_events_v2_jsonl


def test_help_completes_within_two_seconds() -> None:
    root = find_repo_root()
    start = time.monotonic()
    result = subprocess.run(
        ["make", "help"], cwd=str(root), capture_output=True, text=True, check=False
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 2.0


def test_toolchain_check_completes_within_five_seconds() -> None:
    root = find_repo_root()
    start = time.monotonic()
    result = subprocess.run(
        ["make", "toolchain-check"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 5.0


def test_no_color_disables_color_output() -> None:
    root = find_repo_root()
    env = {"NO_COLOR": "1", "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        ["make", "help"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "\033[" not in result.stdout


# ---------------------------------------------------------------------------
# SF02 (T024): guarded lifecycle output accessibility

_SF02_PORTS = {"postgres": 25432, "redis": 26379, "grafana": 23000}
_SF02_PLAIN_LINE = re.compile(
    r"^\[(PASSED|FAILED|STARTED|WAITING|SKIPPED)\] "
    r"(repository|infra) dev/[a-z-]+( (postgres|redis|grafana))?: "
    r"\[[A-Z0-9_]+\] .+ "
    r"\(duration_ms=\d+, correlation_id=[0-9a-f-]{36}\)$"
)


def _sf02_config_text() -> str:
    secret = "tm_local_" + "a" * 40
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://devuser:{secret}@127.0.0.1:{_SF02_PORTS['postgres']}/appdb\n"
        f"REDIS_URL=redis://default:{secret}@127.0.0.1:{_SF02_PORTS['redis']}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{_SF02_PORTS['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secret}\n"
    )


class _Sf02FakeAdapter:
    """Minimal scripted ComposeAdapter protocol fake (no Docker access)."""

    def __init__(self, manifest: Any) -> None:
        self._manifest = manifest

    def verify_runtime(self) -> RuntimeFacts:
        return RuntimeFacts(
            host_platform="darwin/arm64",
            container_platform="linux/arm64",
            docker_version="29.5.3",
            compose_version="5.1.4",
            daemon_arch="arm64",
        )

    def verified_compose_bytes(self) -> bytes:
        return b"# verified committed compose bytes\n"

    def project_state(self) -> tuple[ServiceState, ...]:
        return ()

    def assert_exact_ownership(self, state: Sequence[ServiceState]) -> None:
        return None

    def assert_no_workspace_path_in_labels(self, state: Sequence[ServiceState]) -> None:
        return None

    def assert_loopback_publishers(self, state: Sequence[ServiceState]) -> None:
        return None

    def preflight_ports(
        self,
        state: Sequence[ServiceState],
        desired_ports: Mapping[DependencyId, int],
    ) -> None:
        return None

    def ensure_images(self, runtime: RuntimeFacts) -> tuple[ImagePullRecord, ...]:
        return tuple(
            ImagePullRecord(dependency=definition.id, pulled=False)
            for definition in self._manifest.dependencies
        )

    def reconcile_up(
        self,
        secrets: Any,
        *,
        timeout_seconds: float,
        derived_env: Mapping[str, str] | None = None,
    ) -> None:
        return None


def _sf02_probe(ready: bool) -> Any:
    first_kind = {
        DependencyId.POSTGRES: ProbeKind.POSTGRES_QUERY,
        DependencyId.REDIS: ProbeKind.REDIS_AUTH_PING,
        DependencyId.GRAFANA: ProbeKind.GRAFANA_HEALTH,
    }

    async def _probe(target: Any, deadline: float) -> DependencyHealthResult:
        return DependencyHealthResult(
            dependency=target.dependency,
            liveness=LivenessState.ALIVE,
            readiness=ReadinessState.READY if ready else ReadinessState.NOT_READY,
            probe=first_kind[target.dependency],
            checked_at=datetime.now(timezone.utc),
            duration_ms=5,
            code="OK" if ready else "DEPENDENCY_NOT_READY",
            safe_reason=(
                ""
                if ready
                else f"{target.dependency.value} rejected the configured credentials; "
                "fix the URL and retry"
            ),
        )

    return _probe


@pytest.fixture
def sf02_identity(test_project_identity: TestProjectIdentity) -> WorkspaceIdentity:
    return WorkspaceIdentity(
        workspace_hash=test_project_identity.project_id.removeprefix("tmtest-"),
        workspace_fingerprint=test_project_identity.workspace_fingerprint,
        project_id=test_project_identity.project_id,
        canonical_path="/sf02-a11y-sentinel-workspace",
    )


@pytest.fixture
def sf02_runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


def _run_sf02_guarded(
    *,
    ready: bool,
    identity: WorkspaceIdentity,
    runtime_base: Path,
    plain: bool = False,
) -> int:
    def _adapter_factory(manifest: Any, _identity: Any, _dir: Any, _root: Any) -> Any:
        return _Sf02FakeAdapter(manifest)

    manifest_path = find_repo_root() / "ops" / "workflow" / "local-dependencies.json"
    return execute_dev_guarded(
        repo_root=find_repo_root(),
        plain=plain,
        identity=identity,
        config_reader=_sf02_config_text,
        manifest_loader=lambda: load_manifest(manifest_path),
        runtime_base=runtime_base,
        adapter_factory=_adapter_factory,
        probe_fn=_sf02_probe(ready),
    )


def test_sf02_plain_output_is_no_color_screen_reader_and_icon_safe(
    sf02_identity: WorkspaceIdentity,
    sf02_runtime_base: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    exit_code = _run_sf02_guarded(
        ready=False, identity=sf02_identity, runtime_base=sf02_runtime_base
    )
    assert exit_code == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "expected plain-text lifecycle output"
    for line in lines:
        assert "\x1b[" not in line, "NO_COLOR output must contain no ANSI escapes"
        assert line.isascii(), "plain output must stay icon-free ASCII text"
        assert _SF02_PLAIN_LINE.match(line), f"line must be self-describing text: {line!r}"
    statuses = set()
    for line in lines:
        match = _SF02_PLAIN_LINE.match(line)
        assert match is not None
        statuses.add(match.group(1))
    assert "FAILED" in statuses, "failure must be expressed in words, not color"
    correlation_ids = {line.rsplit("correlation_id=", 1)[1] for line in lines}
    assert len(correlation_ids) == 1, "one lifecycle run must share one correlation id"
    assert "[FAILED]" in lines[-1], "the final line must state the outcome in text"

    monkeypatch.setenv("NO_COLOR", "1")
    passing_exit = _run_sf02_guarded(
        ready=True, identity=sf02_identity, runtime_base=sf02_runtime_base
    )
    assert passing_exit == 0
    passing_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert passing_lines[-1].startswith("[PASSED]")


def test_sf02_jsonl_output_validates_v2_and_exit_status_matches_outcome(
    sf02_identity: WorkspaceIdentity,
    sf02_runtime_base: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    failing_exit = _run_sf02_guarded(
        ready=False, identity=sf02_identity, runtime_base=sf02_runtime_base
    )
    assert failing_exit == 1
    failing_events = read_events_v2_jsonl(capsys.readouterr().out)
    assert failing_events, "expected v2 JSONL envelopes on stdout"
    assert failing_events[-1]["payload"]["status"] == "FAILED"
    dependencies = {
        event["payload"].get("dependency")
        for event in failing_events
        if event["payload"]["phase"] == "readiness"
    }
    assert dependencies == {"postgres", "redis", "grafana"}

    passing_exit = _run_sf02_guarded(
        ready=True, identity=sf02_identity, runtime_base=sf02_runtime_base
    )
    assert passing_exit == 0
    passing_events = read_events_v2_jsonl(capsys.readouterr().out)
    assert passing_events[-1]["payload"]["status"] == "PASSED"


def test_sf02_output_needs_no_interactive_terminal(
    sf02_identity: WorkspaceIdentity,
    sf02_runtime_base: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoStdin:
        def read(self, *args: Any) -> Any:
            raise AssertionError("lifecycle output must never read stdin")

        def readline(self, *args: Any) -> Any:
            raise AssertionError("lifecycle output must never read stdin")

        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", _NoStdin())
    monkeypatch.setenv("NO_COLOR", "1")
    exit_code = _run_sf02_guarded(
        ready=False, identity=sf02_identity, runtime_base=sf02_runtime_base
    )
    assert exit_code == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "non-interactive output must still communicate the outcome"
    assert "[FAILED]" in lines[-1]
