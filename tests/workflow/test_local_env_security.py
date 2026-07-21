"""Security boundary tests for the SF02 local environment lifecycle (T024).

Proves, without touching a real Docker daemon (scripted seams only):

- Rejection ordering: effective-mode and ``.env.local`` rejection precede ANY
  coordination metadata (runtime directories, lock files) and ANY Docker
  access; the reviewed deviation ordering is effective-mode → pure
  ``.env.local`` parse → pure identity/manifest → first Docker CLI call, with
  every read-only preflight still before lock creation.
- Redaction: secrets, absolute workspace paths, URLs with user-info, and raw
  subprocess/probe output never appear in JSONL events, plain-text lines,
  error messages, or leak out of the dedicated child-process secret mapping.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pytest

from workflow.cli import execute_dev_guarded
from workflow.events import DiagnosticCodeV2, emit_event_v2
from workflow.local_env.compose import (
    GRAFANA_ADMIN_PASSWORD_ENV,
    POSTGRES_PASSWORD_ENV,
    REDIS_CONFIG_ENV,
    ComposeAdapter,
    ComposeCommandError,
    ComposeStateParseError,
    ImagePullRecord,
    ImageUnavailableError,
    InvalidSecretMaterialError,
    PortConflictError,
    RuntimeFacts,
    ServiceState,
    UnsupportedRuntimeError,
    build_secret_material,
)
from workflow.local_env.config import parse_local_environment
from workflow.local_env.identity import WorkspaceIdentity
from workflow.local_env.lifecycle import start_local_environment
from workflow.local_env.models import (
    DependencyHealthResult,
    DependencyId,
    LivenessState,
    ProbeKind,
    ReadinessState,
    load_manifest,
)
from workflow.local_env.probes import ProbeOutcome, ProbeTarget, safe_reason

from .conftest import FakeSubprocess, TestProjectIdentity, worktree_compose_git_show
from .helpers import find_repo_root, read_events_v2_jsonl

SENTINEL_PATH = "/Users/tmtest-security/sentinel workspace"
CONFIG_PORTS = {"postgres": 25432, "redis": 26379, "grafana": 23000}
MARKER_SECRETS = {
    "postgres": "tm_local_PgMarkerSecret0000000000000000000000000000aaaa",
    "redis": "tm_local_RedisMarkerSecret00000000000000000000000000bbbb",
    "grafana": "tm_local_GrafanaMarkerSecret00000000000000000000cccc",
}

_FIRST_PROBE_KIND = {
    DependencyId.POSTGRES: ProbeKind.POSTGRES_QUERY,
    DependencyId.REDIS: ProbeKind.REDIS_AUTH_PING,
    DependencyId.GRAFANA: ProbeKind.GRAFANA_HEALTH,
}


def _config_text(
    secrets_map: Mapping[str, str] = MARKER_SECRETS,
    ports: Mapping[str, int] = CONFIG_PORTS,
) -> str:
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://devuser:{secrets_map['postgres']}@"
        f"127.0.0.1:{ports['postgres']}/appdb\n"
        f"REDIS_URL=redis://default:{secrets_map['redis']}@127.0.0.1:{ports['redis']}/0\n"
        f"GRAFANA_URL=http://127.0.0.1:{ports['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets_map['grafana']}\n"
    )


@pytest.fixture
def identity(test_project_identity: TestProjectIdentity) -> WorkspaceIdentity:
    return WorkspaceIdentity(
        workspace_hash=test_project_identity.project_id.removeprefix("tmtest-"),
        workspace_fingerprint=test_project_identity.workspace_fingerprint,
        project_id=test_project_identity.project_id,
        canonical_path=SENTINEL_PATH,
    )


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "secure-runtime"
    base.mkdir()
    os.chmod(base, 0o700)
    return base


@pytest.fixture
def real_manifest_loader() -> Callable[[], Any]:
    manifest_path = find_repo_root() / "ops" / "workflow" / "local-dependencies.json"
    return lambda: load_manifest(manifest_path)


class CountingConfigReader:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self._text


class SpyDockerWorld:
    """Shared call log and failure scripting for the spy adapter."""

    def __init__(self, fail_at: str = "") -> None:
        self.fail_at = fail_at
        self.calls: list[str] = []
        self.factory_calls = 0

    def log(self, name: str) -> None:
        self.calls.append(name)

    def factory(
        self,
        manifest: Any,
        identity: WorkspaceIdentity,
        project_dir: Path,
        repo_root: Path,
    ) -> "SpyComposeAdapter":
        self.factory_calls += 1
        return SpyComposeAdapter(self, manifest)


class SpyComposeAdapter:
    """Records every Docker-facing call; optionally fails at one named call."""

    def __init__(self, world: SpyDockerWorld, manifest: Any) -> None:
        self._world = world
        self._manifest = manifest

    def verify_runtime(self) -> RuntimeFacts:
        self._world.log("verify_runtime")
        if self._world.fail_at == "verify_runtime":
            raise UnsupportedRuntimeError(
                "the docker daemon is unreachable; start the local runtime and retry"
            )
        return RuntimeFacts(
            host_platform="darwin/arm64",
            container_platform="linux/arm64",
            docker_version="29.5.3",
            compose_version="5.1.4",
            daemon_arch="arm64",
        )

    def verified_compose_bytes(self) -> bytes:
        self._world.log("verified_compose_bytes")
        return b"# verified committed compose bytes\n"

    def project_state(self) -> tuple[ServiceState, ...]:
        self._world.log("project_state")
        return ()

    def assert_exact_ownership(self, state: Sequence[ServiceState]) -> None:
        self._world.log("assert_exact_ownership")

    def assert_no_workspace_path_in_labels(self, state: Sequence[ServiceState]) -> None:
        self._world.log("assert_no_workspace_path_in_labels")

    def assert_loopback_publishers(self, state: Sequence[ServiceState]) -> None:
        self._world.log("assert_loopback_publishers")

    def preflight_ports(
        self,
        state: Sequence[ServiceState],
        desired_ports: Mapping[DependencyId, int],
    ) -> None:
        for definition in self._manifest.dependencies:
            self._world.log(f"preflight_ports:{definition.id.value}")
            if self._world.fail_at == "preflight_ports" and definition.id is (
                DependencyId.POSTGRES
            ):
                raise PortConflictError(
                    "postgres desired loopback port 25432 is unavailable; "
                    "free the port or change its URL and retry"
                )

    def ensure_images(self, runtime: RuntimeFacts) -> tuple[ImagePullRecord, ...]:
        for definition in self._manifest.dependencies:
            self._world.log(f"ensure_images:{definition.id.value}")
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
        self._world.log("reconcile_up")


def _probe_result(target: ProbeTarget, *, ready: bool) -> DependencyHealthResult:
    return DependencyHealthResult(
        dependency=target.dependency,
        liveness=LivenessState.ALIVE,
        readiness=ReadinessState.READY if ready else ReadinessState.NOT_READY,
        probe=_FIRST_PROBE_KIND[target.dependency],
        checked_at=datetime.now(timezone.utc),
        duration_ms=5,
        code="OK" if ready else "DEPENDENCY_NOT_READY",
        safe_reason=("" if ready else safe_reason(target.dependency, ProbeOutcome.AUTH_FAILED)),
    )


def _ready_probe(target: ProbeTarget, deadline: float) -> Any:
    async def _probe(_target: ProbeTarget, _deadline: float) -> DependencyHealthResult:
        return _probe_result(_target, ready=True)

    return _probe(target, deadline)


def _failing_probe(target: ProbeTarget, deadline: float) -> Any:
    async def _probe(_target: ProbeTarget, _deadline: float) -> DependencyHealthResult:
        return _probe_result(_target, ready=False)

    return _probe(target, deadline)


def _outcome_kwargs(
    identity: WorkspaceIdentity,
    runtime_base: Path,
    world: SpyDockerWorld,
    reader: CountingConfigReader,
    real_manifest_loader: Callable[[], Any],
) -> dict[str, Any]:
    return {
        "repo_root": find_repo_root(),
        "identity": identity,
        "config_reader": reader,
        "manifest_loader": real_manifest_loader,
        "runtime_base": runtime_base,
        "adapter_factory": world.factory,
    }


# ---------------------------------------------------------------------------
# Rejection ordering: mode/config rejection precedes coordination and Docker


class TestRejectionOrdering:
    async def test_invalid_mode_value_rejected_before_config_docker_and_lock(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **{
                **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader),
                "mode": "test",
                "mode_origin": "command",
            }
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "INVALID_MODE"
        assert reader.calls == 0, "mode validation must precede .env.local reads"
        assert world.factory_calls == 0, "mode rejection must precede any Docker access"
        assert list(runtime_base.iterdir()) == [], "no coordination metadata may be created"

    async def test_shell_mode_origin_cannot_select_or_elevate_mode(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **{
                **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader),
                "mode": "local",
                "mode_origin": "environment",
            }
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "INVALID_MODE"
        assert reader.calls == 0
        assert world.factory_calls == 0
        assert list(runtime_base.iterdir()) == []

    async def test_file_mode_must_be_local_before_any_other_field_validation(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(
            "MODE=prod\n" "DATABASE_URL=not-even-a-url\n" "REDIS_URL=also-broken\n" "GRAFANA_URL=\n"
        )
        outcome = await start_local_environment(
            **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader)
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "INVALID_MODE"
        assert reader.calls == 1
        assert world.factory_calls == 0
        assert list(runtime_base.iterdir()) == []

    async def test_missing_env_local_rejected_before_docker_and_lock(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
        tmp_workspace: Path,
    ) -> None:
        world = SpyDockerWorld()
        outcome = await start_local_environment(
            repo_root=tmp_workspace,
            identity=identity,
            manifest_loader=real_manifest_loader,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "INVALID_CONFIG"
        assert ".env.local" in outcome.message
        assert world.factory_calls == 0
        assert list(runtime_base.iterdir()) == []

    @pytest.mark.parametrize(
        "config_text,field,poison",
        [
            (
                "MODE=local\n"
                "REDIS_URL=redis://default:tm_local_" + "a" * 40 + "@127.0.0.1:26379/0\n"
                "GRAFANA_URL=http://127.0.0.1:23000\n"
                "GRAFANA_ADMIN_PASSWORD=tm_local_" + "b" * 40 + "\n",
                "DATABASE_URL",
                "",
            ),
            (
                _config_text(
                    {
                        "postgres": "replace-me-with-a-generated-tm-local-secret",
                        "redis": MARKER_SECRETS["redis"],
                        "grafana": MARKER_SECRETS["grafana"],
                    }
                ),
                "DATABASE_URL",
                "replace-me-with-a-generated-tm-local-secret",
            ),
            (
                _config_text().replace("127.0.0.1:25432", "192.168.1.5:25432"),
                "DATABASE_URL",
                "192.168.1.5",
            ),
            (
                _config_text().replace("127.0.0.1:25432", "localhost:25432"),
                "DATABASE_URL",
                "localhost",
            ),
            (
                _config_text().replace("127.0.0.1:26379", "127.0.0.1:25432"),
                "DATABASE_URL and REDIS_URL",
                "",
            ),
            (
                _config_text().replace(MARKER_SECRETS["grafana"], "tm_local_short"),
                "GRAFANA_ADMIN_PASSWORD",
                "tm_local_short",
            ),
            (
                _config_text().replace(
                    "GRAFANA_URL=http://127.0.0.1:23000",
                    "GRAFANA_URL=http://admin:tm_local_" + "c" * 40 + "@127.0.0.1:23000",
                ),
                "GRAFANA_URL",
                "tm_local_" + "c" * 40,
            ),
            (
                _config_text().replace("127.0.0.1:23000", "127.0.0.1:0"),
                "GRAFANA_URL",
                "",
            ),
        ],
        ids=[
            "missing-database-url",
            "placeholder-secret",
            "lan-address",
            "hostname-not-loopback-literal",
            "duplicate-ports",
            "secret-grammar",
            "grafana-userinfo",
            "port-out-of-range",
        ],
    )
    async def test_invalid_config_rejected_before_docker_and_lock(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
        config_text: str,
        field: str,
        poison: str,
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(config_text)
        outcome = await start_local_environment(
            **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader)
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "INVALID_CONFIG"
        assert field in outcome.message, "the diagnostic must name the field"
        assert reader.calls == 1
        assert world.factory_calls == 0, "config rejection must precede any Docker access"
        assert list(runtime_base.iterdir()) == [], "no lock file may be created"
        if poison:
            assert poison not in outcome.message, "field values must never be echoed"
            serialized = json.dumps(outcome.events) + "\n".join(outcome.plain_lines)
            assert poison not in serialized

    async def test_readonly_runtime_preflight_precedes_lock_and_mutation(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld(fail_at="verify_runtime")
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader)
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "TOOL_VERSION_UNSUPPORTED"
        assert world.calls == [
            "verify_runtime"
        ], "the first Docker-facing call fails the run before any other access"
        assert "reconcile_up" not in world.calls
        assert not any(call.startswith("ensure_images") for call in world.calls)
        assert list(runtime_base.iterdir()) == [], "no lock or project dir may be created"

    async def test_port_preflight_precedes_lock_and_names_the_dependency(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld(fail_at="preflight_ports")
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader)
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "PORT_CONFLICT"
        conflicts = [
            event["payload"]
            for event in outcome.events
            if event["payload"]["code"] == "PORT_CONFLICT"
        ]
        assert conflicts
        assert conflicts[0]["dependency"] == "postgres"
        assert "25432" in str(conflicts[0]["message"])
        assert "reconcile_up" not in world.calls
        assert not any(call.startswith("ensure_images") for call in world.calls)
        assert list(runtime_base.iterdir()) == []

    async def test_readonly_preflight_order_and_in_lock_revalidation(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **{
                **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader),
                "probe_fn": _failing_probe,
            }
        )
        assert outcome.status == "FAILED"
        assert outcome.diagnostic_code == "DEPENDENCY_NOT_READY"

        # Pure config/identity/manifest validation precedes the FIRST
        # Docker-facing call; the read-only preflight precedes the lock; the
        # lock precedes every mutation (pull, reconcile).
        calls = world.calls
        assert calls[0] == "verify_runtime"
        first_verify = calls.index("verify_runtime")
        first_state = calls.index("project_state")
        assert first_verify < first_state
        in_lock_verify = calls.index("verify_runtime", first_verify + 1)
        assert "verified_compose_bytes" in calls[first_state:in_lock_verify]
        first_pull = calls.index("ensure_images:postgres")
        assert in_lock_verify < first_pull
        assert calls.index("reconcile_up") > first_pull
        preflight_calls = [
            index for index, name in enumerate(calls) if name.startswith("preflight_ports")
        ]
        assert preflight_calls and max(preflight_calls) < first_pull

        # Configuration is re-read inside the lock (initial read plus
        # in-lock revalidation).
        assert reader.calls == 2

        phases = [event["payload"]["phase"] for event in outcome.events]
        assert phases.index("identity") < phases.index("preflight") < phases.index("lock")
        assert phases.index("lock") < phases.index("image-pull")

        # A failed run leaves the released lock file behind only after the
        # preflight passed; no coordination metadata exists before that.
        assert (runtime_base / identity.project_id / "lifecycle.lock").is_file()


# ---------------------------------------------------------------------------
# Redaction boundaries


class TestRedactionBoundaries:
    async def test_secrets_paths_and_userinfo_never_enter_any_output_surface(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **{
                **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader),
                "probe_fn": _failing_probe,
            }
        )
        assert outcome.status == "FAILED"
        serialized = json.dumps(outcome.events, ensure_ascii=False)
        serialized += "\n" + "\n".join(outcome.plain_lines) + outcome.message
        for secret in MARKER_SECRETS.values():
            assert secret not in serialized
        assert "tm_local_" not in serialized
        assert SENTINEL_PATH not in serialized
        assert "devuser" not in serialized
        assert "://" not in serialized or ":@" not in serialized
        for event in outcome.events:
            message = str(event["payload"]["message"])
            assert "://" not in message or "@" not in message.split("://", 1)[1].split("/", 1)[0]

    async def test_success_output_shows_endpoints_without_userinfo_or_secrets(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        outcome = await start_local_environment(
            **{
                **_outcome_kwargs(identity, runtime_base, world, reader, real_manifest_loader),
                "probe_fn": _ready_probe,
            }
        )
        assert outcome.status == "PASSED"
        final = outcome.events[-1]["payload"]
        message = str(final["message"])
        assert "127.0.0.1:25432" in message
        assert "devuser" not in message
        assert "@" not in message
        serialized = json.dumps(outcome.events) + "\n".join(outcome.plain_lines)
        for secret in MARKER_SECRETS.values():
            assert secret not in serialized
        assert SENTINEL_PATH not in serialized

    def test_child_secret_mapping_is_confined_to_the_compose_invocation(
        self,
        identity: WorkspaceIdentity,
        real_manifest_loader: Callable[[], Any],
    ) -> None:
        manifest = real_manifest_loader()
        secrets = build_secret_material(
            manifest,
            identity,
            postgres_password=MARKER_SECRETS["postgres"],
            redis_password=MARKER_SECRETS["redis"],
            grafana_admin_password=MARKER_SECRETS["grafana"],
        )
        # repr/str/equality never expose secret bytes.
        assert MARKER_SECRETS["postgres"] not in repr(secrets)
        assert MARKER_SECRETS["redis"] not in repr(secrets)
        assert MARKER_SECRETS["grafana"] not in repr(secrets)

        # The dedicated child mapping is the ONLY surface carrying secrets.
        mapping = secrets.child_mapping()
        assert mapping[POSTGRES_PASSWORD_ENV] == MARKER_SECRETS["postgres"]
        assert mapping[GRAFANA_ADMIN_PASSWORD_ENV] == MARKER_SECRETS["grafana"]
        assert mapping[REDIS_CONFIG_ENV] == f"requirepass {MARKER_SECRETS['redis']}\n"

        # The mapping is never merged into the parent environment.
        for name in (POSTGRES_PASSWORD_ENV, REDIS_CONFIG_ENV, GRAFANA_ADMIN_PASSWORD_ENV):
            assert name not in os.environ
        for secret in MARKER_SECRETS.values():
            assert secret not in os.environ.values()

        # Released mappings drop every secret byte and refuse further use.
        released = secrets.release()
        with pytest.raises(InvalidSecretMaterialError):
            released.child_mapping()
        for secret in MARKER_SECRETS.values():
            assert secret not in repr(released)

    def test_derived_connection_repr_hides_credentials(self) -> None:
        config = parse_local_environment(_config_text())
        for connection in config.connections:
            rendered = repr(connection)
            for secret in MARKER_SECRETS.values():
                assert secret not in rendered
            assert "devuser" not in rendered
            assert "container_url" not in rendered
            endpoint = connection.displayed_endpoint
            assert "@" not in endpoint
            assert endpoint.startswith(f"{connection.host_scheme}://127.0.0.1:")

    def test_event_v2_redacts_secrets_userinfo_and_absolute_paths(self) -> None:
        poison = MARKER_SECRETS["postgres"]
        event = emit_event_v2(
            action="dev",
            component="repository",
            phase="final",
            status="FAILED",
            code=DiagnosticCodeV2.STEP_FAILED,
            duration_ms=0,
            message=(
                f"probe failed for postgresql://devuser:{poison}@127.0.0.1:25432/appdb "
                f"under /Users/tmtest-security/workspace and /tmp/tmtest-lock with {poison}"
            ),
            correlation_id="tmtest-correlation",
        )
        message = str(event["payload"]["message"])
        assert poison not in message
        assert "tm_local_" not in message
        assert "devuser" not in message
        assert "/Users/tmtest-security/workspace" not in message
        assert "/tmp/tmtest-lock" not in message

    def test_compose_failure_never_leaks_raw_subprocess_output(
        self,
        identity: WorkspaceIdentity,
        real_manifest_loader: Callable[[], Any],
        fake_subprocess: FakeSubprocess,
        tmp_path: Path,
    ) -> None:
        poison = (
            f"boom {MARKER_SECRETS['postgres']} /Users/tmtest-security/workspace "
            "postgresql://devuser:tm_local_x@127.0.0.1:25432/appdb"
        )
        repo_root = find_repo_root()
        adapter = ComposeAdapter(
            manifest=real_manifest_loader(),
            identity=identity,
            project_dir=tmp_path,
            repo_root=repo_root,
            run=fake_subprocess.run,
            git_show=worktree_compose_git_show(repo_root),
            environ={},
        )
        manifest = real_manifest_loader()
        secrets = build_secret_material(
            manifest,
            identity,
            postgres_password=MARKER_SECRETS["postgres"],
            redis_password=MARKER_SECRETS["redis"],
            grafana_admin_password=MARKER_SECRETS["grafana"],
        )
        fake_subprocess.queue(returncode=1, stderr=poison)
        with pytest.raises(ComposeCommandError) as captured:
            adapter.reconcile_up(secrets, timeout_seconds=5.0)
        assert poison not in str(captured.value)
        for secret in MARKER_SECRETS.values():
            assert secret not in str(captured.value)
        assert "/Users/tmtest-security" not in str(captured.value)

        # Secrets travel only in the dedicated child environment of that one
        # call, and the compose bytes travel over stdin, never in argv.
        argv, kwargs = fake_subprocess.calls[0]
        assert argv[argv.index("-f") + 1] == "-"
        joined_argv = " ".join(argv)
        for secret in MARKER_SECRETS.values():
            assert secret not in joined_argv
        child_env = kwargs.get("env") or {}
        assert child_env[POSTGRES_PASSWORD_ENV] == MARKER_SECRETS["postgres"]
        assert kwargs.get("input") is not None
        for name in (POSTGRES_PASSWORD_ENV, REDIS_CONFIG_ENV, GRAFANA_ADMIN_PASSWORD_ENV):
            assert name not in os.environ

    def test_compose_state_parse_error_never_leaks_raw_output(
        self,
        identity: WorkspaceIdentity,
        real_manifest_loader: Callable[[], Any],
        fake_subprocess: FakeSubprocess,
        tmp_path: Path,
    ) -> None:
        poison = f"not-json {MARKER_SECRETS['redis']}"
        repo_root = find_repo_root()
        adapter = ComposeAdapter(
            manifest=real_manifest_loader(),
            identity=identity,
            project_dir=tmp_path,
            repo_root=repo_root,
            run=fake_subprocess.run,
            git_show=worktree_compose_git_show(repo_root),
            environ={},
        )
        fake_subprocess.queue(stdout=poison, returncode=0)
        with pytest.raises(ComposeStateParseError) as captured:
            adapter.project_state()
        assert MARKER_SECRETS["redis"] not in str(captured.value)

    def test_image_pull_failure_never_leaks_raw_output(
        self,
        identity: WorkspaceIdentity,
        real_manifest_loader: Callable[[], Any],
        fake_subprocess: FakeSubprocess,
        tmp_path: Path,
    ) -> None:
        poison = f"registry said no: {MARKER_SECRETS['grafana']}"
        repo_root = find_repo_root()
        adapter = ComposeAdapter(
            manifest=real_manifest_loader(),
            identity=identity,
            project_dir=tmp_path,
            repo_root=repo_root,
            run=fake_subprocess.run,
            git_show=worktree_compose_git_show(repo_root),
            environ={},
        )
        runtime = RuntimeFacts(
            host_platform="darwin/arm64",
            container_platform="linux/arm64",
            docker_version="29.5.3",
            compose_version="5.1.4",
            daemon_arch="arm64",
        )
        # First dependency (postgres): inspect misses, pull fails with a
        # poisoned stderr; the diagnostic stays static and safe.
        fake_subprocess.queue(returncode=1, stderr="Error: No such image")
        fake_subprocess.queue(returncode=1, stderr=poison)
        with pytest.raises(ImageUnavailableError) as captured:
            adapter.ensure_images(runtime)
        assert MARKER_SECRETS["grafana"] not in str(captured.value)


# ---------------------------------------------------------------------------
# Guarded dispatch exit status and zero-side-effect rejections


class TestGuardedDispatchSecurity:
    def test_guarded_dispatch_rejects_invalid_mode_with_zero_side_effects(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        exit_code = execute_dev_guarded(
            repo_root=find_repo_root(),
            mode="prod",
            mode_origin="command",
            identity=identity,
            config_reader=reader,
            manifest_loader=real_manifest_loader,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
        )
        assert exit_code == 1
        assert reader.calls == 0
        assert world.factory_calls == 0
        assert list(runtime_base.iterdir()) == []
        events = read_events_v2_jsonl(capsys.readouterr().out)
        assert any(event["payload"]["code"] == "INVALID_MODE" for event in events)
        assert events[-1]["payload"]["status"] == "FAILED"

    def test_guarded_dispatch_exit_status_matches_aggregate_outcome(
        self,
        identity: WorkspaceIdentity,
        runtime_base: Path,
        real_manifest_loader: Callable[[], Any],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        world = SpyDockerWorld()
        reader = CountingConfigReader(_config_text())
        exit_code = execute_dev_guarded(
            repo_root=find_repo_root(),
            identity=identity,
            config_reader=reader,
            manifest_loader=real_manifest_loader,
            runtime_base=runtime_base,
            adapter_factory=world.factory,
            probe_fn=_failing_probe,
        )
        assert exit_code == 1
        events = read_events_v2_jsonl(capsys.readouterr().out)
        assert events[-1]["payload"]["status"] == "FAILED"
        assert events[-1]["payload"]["code"] == "STEP_FAILED"
        serialized = capsys.readouterr().out + json.dumps(events)
        for secret in MARKER_SECRETS.values():
            assert secret not in serialized
