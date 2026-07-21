"""Fake Docker CLI tests for the SF02 Compose adapter (T021).

Covers the adapter rules of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 2, 3, 4, 7, 9 and 12 without a real Docker daemon:

- fixed Compose argument order (``-p`` identity, safe 0700 runtime project
  directory, verified bytes over ``-f -`` stdin, ``--ansi never``);
- committed-blob verification of ``infra/docker/compose.local.yml`` with
  fail-closed dirty/replaced/symlink handling before any Compose access;
- read-only local runtime preflight: supported host platform, local Unix
  endpoint (remote ``DOCKER_HOST``/contexts rejected), maintained Docker
  29.5.3 / Compose 5.1.4 versions, Linux daemon architecture and Compose
  capability checks, all before any state-changing call;
- captured ``ps --format json`` state parsing (JSONL/array forms, unknown
  fields tolerated, malformed/partial input rejected), exact project +
  full-64-hex-fingerprint ownership inspection, loopback-only publisher
  inspection, and bind-only port preflight/race mapping;
- missing-only image pull with current-platform digest verification and
  ``up --detach --pull never`` reconcile sequencing;
- bounded subprocess termination (timeout/interruption mapping) and stable
  redacted errors that never leak stderr/stdout/argv/env/secrets/paths;
- T030 dedicated child-only secret mappings (PostgreSQL/Grafana password
  files, single-directive injection-safe Redis config, manifest UID/GID and
  0400 metadata) and parse-only teardown placeholders.

Every identity uses the disjoint ``tmtest-`` test prefix so the fake CLI can
never address a developer project. These tests fail until T028/T030 implement
``tools/workflow/local_env/compose.py``.
"""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import pytest

from .conftest import TEST_REPOSITORY_LABEL, FakeSubprocess, assert_not_developer_project
from .helpers import load_json

if TYPE_CHECKING:
    from .conftest import TestProjectIdentity

SYNTHETIC_COMPOSE = (
    b"services:\n"
    b"  postgres:\n"
    b"    image: docker.io/library/postgres:15.18-bookworm@sha256:pinned\n"
)
SENTINEL_WORKSPACE_PATH = "/sf02-test-workspace-canonical-path"
COMPOSE_PROJECT_DIR_NAME = "compose-project"


def _compose() -> Any:
    try:
        return importlib.import_module("workflow.local_env.compose")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.compose is not implemented yet (T028/T030): {exc}")


def _models() -> Any:
    return importlib.import_module("workflow.local_env.models")


@pytest.fixture(scope="module")
def manifest() -> Any:
    return _models().parse_manifest(load_json("ops", "workflow", "local-dependencies.json"))


@pytest.fixture
def identity(test_project_identity: TestProjectIdentity) -> Any:
    identity_module = importlib.import_module("workflow.local_env.identity")
    assert_not_developer_project(test_project_identity.project_id)
    return identity_module.WorkspaceIdentity(
        workspace_hash=test_project_identity.project_id.removeprefix("tmtest-"),
        workspace_fingerprint=test_project_identity.workspace_fingerprint,
        project_id=test_project_identity.project_id,
        canonical_path=SENTINEL_WORKSPACE_PATH,
    )


@pytest.fixture
def project_dir(tmp_path: Path, identity: Any) -> Path:
    compose_dir = tmp_path / "runtime" / str(identity.project_id) / COMPOSE_PROJECT_DIR_NAME
    compose_dir.mkdir(parents=True)
    return compose_dir.parent


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    compose_path = root / "infra" / "docker" / "compose.local.yml"
    compose_path.parent.mkdir(parents=True)
    compose_path.write_bytes(SYNTHETIC_COMPOSE)
    return root


@pytest.fixture
def secret_values(synthetic_secret_factory: Any) -> dict[str, str]:
    return {
        "postgres": synthetic_secret_factory.new(),
        "redis": synthetic_secret_factory.new(),
        "grafana": synthetic_secret_factory.new(),
    }


class FakeGitShow:
    """Predeclared committed-blob stand-in for the read-only git seam."""

    def __init__(self, blobs: Mapping[str, bytes]) -> None:
        self._blobs = dict(blobs)
        self.calls: list[str] = []

    def __call__(self, relative_path: str) -> bytes:
        self.calls.append(relative_path)
        if relative_path not in self._blobs:
            raise _compose().ComposeAssetError(f"no committed blob for {relative_path}")
        return self._blobs[relative_path]


def _adapter(
    manifest: Any,
    identity: Any,
    project_dir: Path,
    repo_root: Path,
    fake: FakeSubprocess,
    *,
    git_blobs: Mapping[str, bytes] | None = None,
    environ: Mapping[str, str] | None = None,
    host_platform: str | None = "darwin/arm64",
    bind_check: Any = None,
    run: Any = None,
) -> tuple[Any, FakeGitShow]:
    compose = _compose()
    git = FakeGitShow(
        dict(git_blobs)
        if git_blobs is not None
        else {compose.COMPOSE_FILE_RELATIVE_PATH: SYNTHETIC_COMPOSE}
    )
    adapter = compose.ComposeAdapter(
        manifest=manifest,
        identity=identity,
        project_dir=project_dir,
        repo_root=repo_root,
        run=run if run is not None else fake.run,
        git_show=git,
        environ={} if environ is None else environ,
        host_platform=host_platform,
        bind_check=bind_check,
    )
    return adapter, git


def _argvs(fake: FakeSubprocess) -> list[list[str]]:
    return [argv for argv, _ in fake.calls]


def _queue_runtime_preflight(
    fake: FakeSubprocess,
    *,
    docker_version: str = "29.5.3",
    compose_version: str = "5.1.4",
    context_host: str = "unix:///var/run/docker.sock",
    os_type: str = "linux",
    architecture: str = "aarch64",
    up_help: str = "Usage: docker compose up --detach --pull <policy>",
    ps_help: str = "Usage: docker compose ps --format json",
) -> None:
    fake.queue(stdout=f"Docker version {docker_version}, build d1c06ef\n")
    fake.queue(stdout=f"Docker Compose version v{compose_version}\n")
    fake.queue(
        stdout=json.dumps(
            [{"Name": "desktop-linux", "Endpoints": {"docker": {"Host": context_host}}}]
        )
    )
    fake.queue(
        stdout=json.dumps(
            {
                "OSType": os_type,
                "Architecture": architecture,
                "ServerVersion": docker_version,
            }
        )
    )
    fake.queue(stdout=up_help)
    fake.queue(stdout=ps_help)


_PREFLIGHT_ARGVS = [
    ["docker", "--version"],
    ["docker", "compose", "version"],
    ["docker", "context", "inspect", "--format", "json"],
    ["docker", "info", "--format", "json"],
    ["docker", "compose", "up", "--help"],
    ["docker", "compose", "ps", "--help"],
]


def _owned_labels(identity: Any) -> dict[str, str]:
    """Full ownership label set for the exact test project."""
    compose = _compose()
    return {
        compose.LABEL_REPOSITORY: TEST_REPOSITORY_LABEL,
        compose.LABEL_WORKSPACE_ID: identity.project_id,
        compose.LABEL_WORKSPACE_FINGERPRINT: identity.workspace_fingerprint,
    }


def _ps_record(
    identity: Any,
    service: str,
    *,
    state: str = "running",
    health: str = "healthy",
    publishers: Sequence[Mapping[str, Any]] = (),
    labels: Mapping[str, str] | None = None,
    project: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record_labels = _owned_labels(identity) if labels is None else dict(labels)
    record: dict[str, Any] = {
        "ID": "0123456789ab",
        "Name": f"{identity.project_id}-{service}-1",
        "Project": identity.project_id if project is None else project,
        "Service": service,
        "State": state,
        "Health": health,
        "Labels": ",".join(f"{key}={value}" for key, value in record_labels.items()),
        "Publishers": [dict(publisher) for publisher in publishers],
    }
    if extra:
        record.update(extra)
    return record


def _publisher(host_ip: str, target_port: int, published_port: int) -> dict[str, Any]:
    return {
        "URL": host_ip,
        "TargetPort": target_port,
        "PublishedPort": published_port,
        "Protocol": "tcp",
    }


def _ps_jsonl(*records: Mapping[str, Any]) -> str:
    return "".join(json.dumps(record) + "\n" for record in records)


def _image_stdout(dependency: Any, *, arch: str = "arm64", digests: Sequence[str] = ()) -> str:
    repo_digests = [f"{dependency.repository}@{digest}" for digest in digests]
    return json.dumps(
        [
            {
                "Id": "sha256:" + "ab" * 32,
                "Os": "linux",
                "Architecture": arch,
                "RepoDigests": repo_digests,
            }
        ]
    )


def _runtime_facts(compose: Any) -> Any:
    return compose.RuntimeFacts(
        host_platform="darwin/arm64",
        container_platform="linux/arm64",
        docker_version="29.5.3",
        compose_version="5.1.4",
        daemon_arch="arm64",
    )


def _child_digest(dependency: Any, container_platform: str = "linux/arm64") -> str:
    if container_platform == "linux/amd64":
        return str(dependency.platform_digests.linux_amd64)
    return str(dependency.platform_digests.linux_arm64)


# ---------------------------------------------------------------------------
# Fixed argument order and safe transport
# ---------------------------------------------------------------------------


class TestFixedArgumentOrder:
    def test_up_argv_uses_fixed_order_safe_dir_and_stdin(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, git = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        fake_subprocess.queue(stdout="")

        adapter.reconcile_up(secrets, timeout_seconds=42.0)

        assert len(fake_subprocess.calls) == 1
        argv, kwargs = fake_subprocess.calls[0]
        expected_dir = str(project_dir / COMPOSE_PROJECT_DIR_NAME)
        assert argv == [
            "docker",
            "compose",
            "--project-name",
            identity.project_id,
            "--project-directory",
            expected_dir,
            "-f",
            "-",
            "--ansi",
            "never",
            "up",
            "--detach",
            "--pull",
            "never",
        ]
        assert kwargs["timeout"] == 42.0
        assert kwargs["input"].encode("utf-8") == SYNTHETIC_COMPOSE
        assert git.calls == [compose.COMPOSE_FILE_RELATIVE_PATH]

    def test_ps_argv_uses_fixed_order_without_stdin(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="")

        state = adapter.project_state()

        assert state == ()
        argv, kwargs = fake_subprocess.calls[0]
        expected_dir = str(project_dir / COMPOSE_PROJECT_DIR_NAME)
        assert argv == [
            "docker",
            "compose",
            "--project-name",
            identity.project_id,
            "--project-directory",
            expected_dir,
            "--ansi",
            "never",
            "ps",
            "--all",
            "--format",
            "json",
        ]
        assert kwargs["timeout"] is not None and kwargs["timeout"] > 0
        assert kwargs.get("input") is None

    def test_argv_never_contains_workspace_path_or_secrets(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        _queue_runtime_preflight(fake_subprocess)
        for dependency in manifest.dependencies:
            fake_subprocess.queue(
                stdout=_image_stdout(dependency, digests=(dependency.index_digest,))
            )
        fake_subprocess.queue(stdout="")

        runtime = adapter.verify_runtime()
        adapter.ensure_images(runtime)
        adapter.reconcile_up(secrets, timeout_seconds=30.0)

        forbidden = [
            SENTINEL_WORKSPACE_PATH,
            str(repo_root),
            secret_values["postgres"],
            secret_values["redis"],
            secret_values["grafana"],
        ]
        for argv in _argvs(fake_subprocess):
            for token in forbidden:
                assert not any(token in arg for arg in argv), f"argv leaked {token!r}: {argv!r}"


# ---------------------------------------------------------------------------
# Committed-blob verification
# ---------------------------------------------------------------------------


class TestCommittedBlobVerification:
    def test_verified_bytes_equal_committed_blob(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        assert adapter.verified_compose_bytes() == SYNTHETIC_COMPOSE
        assert fake_subprocess.calls == []

    def test_dirty_asset_fails_closed_before_any_compose_access(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        (repo_root / "infra" / "docker" / "compose.local.yml").write_bytes(
            b"services:\n  postgres:\n    image: tampered\n"
        )
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )

        with pytest.raises(compose.ComposeAssetError) as excinfo:
            adapter.reconcile_up(secrets, timeout_seconds=30.0)

        assert excinfo.value.code == "CONTRACT_DRIFT"
        assert fake_subprocess.calls == []

    def test_symlink_asset_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        asset = repo_root / "infra" / "docker" / "compose.local.yml"
        target = repo_root / "infra" / "docker" / "real.yml"
        asset.rename(target)
        asset.symlink_to(target)
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)

        with pytest.raises(compose.ComposeAssetError):
            adapter.verified_compose_bytes()
        assert fake_subprocess.calls == []

    def test_missing_committed_blob_fails_closed(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(
            manifest, identity, project_dir, repo_root, fake_subprocess, git_blobs={}
        )
        with pytest.raises(compose.ComposeAssetError):
            adapter.verified_compose_bytes()
        assert fake_subprocess.calls == []

    def test_project_state_verifies_asset_before_running(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(
            manifest, identity, project_dir, repo_root, fake_subprocess, git_blobs={}
        )
        with pytest.raises(compose.ComposeAssetError):
            adapter.project_state()
        assert fake_subprocess.calls == []


# ---------------------------------------------------------------------------
# Runtime preflight (read-only, before any state change)
# ---------------------------------------------------------------------------


class TestRuntimePreflight:
    def test_preflight_happy_path_returns_facts_and_fixed_calls(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess)

        facts = adapter.verify_runtime()

        assert facts.host_platform == "darwin/arm64"
        assert facts.container_platform == "linux/arm64"
        assert facts.docker_version == "29.5.3"
        assert facts.compose_version == "5.1.4"
        assert facts.daemon_arch == "arm64"
        assert _argvs(fake_subprocess) == _PREFLIGHT_ARGVS
        assert fake_subprocess.exhausted

    def test_preflight_linux_amd64_host(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            host_platform="linux/amd64",
        )
        _queue_runtime_preflight(fake_subprocess, architecture="x86_64")

        facts = adapter.verify_runtime()

        assert facts.host_platform == "linux/amd64"
        assert facts.container_platform == "linux/amd64"
        assert facts.daemon_arch == "amd64"

    @pytest.mark.parametrize(
        "docker_host",
        [
            "tcp://192.0.2.10:2375",
            "ssh://builder@example.internal",
            "npipe:////./pipe/docker_engine",
        ],
    )
    def test_remote_docker_host_rejected_before_any_subprocess(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        docker_host: str,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            environ={"DOCKER_HOST": docker_host},
        )

        with pytest.raises(compose.UnsupportedRuntimeError) as excinfo:
            adapter.verify_runtime()

        assert excinfo.value.code == "TOOL_VERSION_UNSUPPORTED"
        assert fake_subprocess.calls == []

    def test_unix_docker_host_accepted(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            environ={"DOCKER_HOST": "unix:///custom/docker.sock"},
        )
        _queue_runtime_preflight(fake_subprocess)
        facts = adapter.verify_runtime()
        assert facts.docker_version == "29.5.3"

    @pytest.mark.parametrize("platform_id", ["windows/amd64", "darwin/amd64", "linux/arm64"])
    def test_unsupported_host_platform_rejected_before_any_subprocess(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        platform_id: str,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            host_platform=platform_id,
        )
        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert fake_subprocess.calls == []

    def test_docker_cli_missing(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()

        def missing_docker(args: Sequence[str], **kwargs: Any) -> Any:
            raise FileNotFoundError("docker")

        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            run=missing_docker,
        )
        with pytest.raises(compose.ToolMissingError) as excinfo:
            adapter.verify_runtime()
        assert excinfo.value.code == "TOOL_MISSING"

    def test_compose_plugin_missing(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="Docker version 29.5.3, build d1c06ef\n")
        fake_subprocess.queue(returncode=1, stderr="docker: 'compose' is not a docker command")

        with pytest.raises(compose.ToolMissingError):
            adapter.verify_runtime()

    def test_wrong_docker_version_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, docker_version="28.2.0")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert _argvs(fake_subprocess) == [["docker", "--version"]]

    def test_wrong_compose_version_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, compose_version="2.29.0")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert _argvs(fake_subprocess) == _PREFLIGHT_ARGVS[:2]

    def test_remote_context_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, context_host="tcp://203.0.113.5:2376")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert _argvs(fake_subprocess) == _PREFLIGHT_ARGVS[:3]

    def test_daemon_unreachable_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="Docker version 29.5.3, build d1c06ef\n")
        fake_subprocess.queue(stdout="Docker Compose version v5.1.4\n")
        fake_subprocess.queue(
            stdout=json.dumps(
                [
                    {
                        "Name": "desktop-linux",
                        "Endpoints": {"docker": {"Host": "unix:///var/run/docker.sock"}},
                    }
                ]
            )
        )
        fake_subprocess.queue(returncode=1, stderr="Cannot connect to the Docker daemon")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert _argvs(fake_subprocess) == _PREFLIGHT_ARGVS[:4]

    def test_non_linux_daemon_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, os_type="windows")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()

    def test_emulated_architecture_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, architecture="x86_64")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()

    def test_missing_compose_capability_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess, up_help="Usage: docker compose up")

        with pytest.raises(compose.UnsupportedRuntimeError):
            adapter.verify_runtime()
        assert _argvs(fake_subprocess) == _PREFLIGHT_ARGVS[:5]

    def test_preflight_is_read_only(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess)
        adapter.verify_runtime()
        for argv in _argvs(fake_subprocess):
            assert argv in _PREFLIGHT_ARGVS
        assert not any(argv[1:2] == ["pull"] for argv in _argvs(fake_subprocess))


# ---------------------------------------------------------------------------
# Captured JSON state parsing
# ---------------------------------------------------------------------------


class TestProjectStateParsing:
    def test_jsonl_records_parse(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(
            stdout=_ps_jsonl(
                _ps_record(identity, "postgres"),
                _ps_record(identity, "redis", state="exited", health=""),
            )
        )

        state = adapter.project_state()

        assert [record.service for record in state] == ["postgres", "redis"]
        assert state[0].project == identity.project_id
        assert state[0].state == "running"
        assert state[0].health == "healthy"
        assert state[1].state == "exited"

    def test_json_array_form_accepted(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout=json.dumps([_ps_record(identity, "grafana")]))

        state = adapter.project_state()
        assert [record.service for record in state] == ["grafana"]

    def test_unknown_fields_tolerated(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(
            stdout=_ps_jsonl(_ps_record(identity, "postgres", extra={"FutureField": {"x": 1}}))
        )
        state = adapter.project_state()
        assert len(state) == 1

    def test_malformed_json_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="this is not json\n")

        with pytest.raises(compose.ComposeStateParseError) as excinfo:
            adapter.project_state()
        assert excinfo.value.code == "STEP_FAILED"

    def test_partial_trailing_line_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout=_ps_jsonl(_ps_record(identity, "postgres")) + '{"Project": "')

        with pytest.raises(compose.ComposeStateParseError):
            adapter.project_state()

    def test_missing_required_field_rejected(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        record = _ps_record(identity, "postgres")
        del record["Service"]
        fake_subprocess.queue(stdout=_ps_jsonl(record))

        with pytest.raises(compose.ComposeStateParseError):
            adapter.project_state()

    def test_ps_failure_is_safe_error(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(
            returncode=1, stderr=f"daemon exploded near {SENTINEL_WORKSPACE_PATH}"
        )

        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.project_state()
        assert excinfo.value.code == "STEP_FAILED"
        assert SENTINEL_WORKSPACE_PATH not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Ownership and publisher inspection
# ---------------------------------------------------------------------------


class TestOwnershipInspection:
    def test_exact_project_and_fingerprint_accepted(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        state = compose.parse_ps_json(
            _ps_jsonl(*(_ps_record(identity, svc) for svc in ("postgres", "redis", "grafana")))
        )
        adapter.assert_exact_ownership(state)
        adapter.assert_no_workspace_path_in_labels(state)

    def test_foreign_project_refused(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        state = compose.parse_ps_json(
            _ps_jsonl(_ps_record(identity, "postgres", project="tokenmarket-ffffffffffff"))
        )
        with pytest.raises(compose.OwnershipConflictError) as excinfo:
            adapter.assert_exact_ownership(state)
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"

    def test_fingerprint_mismatch_is_detected_collision(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        collision_labels = _owned_labels(identity)
        collision_labels[compose.LABEL_WORKSPACE_FINGERPRINT] = "f" * 64
        state = compose.parse_ps_json(
            _ps_jsonl(_ps_record(identity, "postgres", labels=collision_labels))
        )
        with pytest.raises(compose.OwnershipConflictError):
            adapter.assert_exact_ownership(state)

    def test_missing_workspace_labels_refused(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        state = compose.parse_ps_json(_ps_jsonl(_ps_record(identity, "postgres", labels={})))
        with pytest.raises(compose.OwnershipConflictError):
            adapter.assert_exact_ownership(state)

    def test_workspace_path_in_labels_refused(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        leaking_labels = _owned_labels(identity)
        leaking_labels["com.docker.compose.project.working_dir"] = SENTINEL_WORKSPACE_PATH
        state = compose.parse_ps_json(
            _ps_jsonl(_ps_record(identity, "postgres", labels=leaking_labels))
        )
        with pytest.raises(compose.OwnershipConflictError):
            adapter.assert_no_workspace_path_in_labels(state)


class TestPublisherInspection:
    def test_loopback_publishers_accepted(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        state = compose.parse_ps_json(
            _ps_jsonl(
                _ps_record(
                    identity,
                    "postgres",
                    publishers=(_publisher("127.0.0.1", 5432, 5432),),
                )
            )
        )
        adapter.assert_loopback_publishers(state)

    @pytest.mark.parametrize("host_ip", ["0.0.0.0", "::", "192.168.1.20"])
    def test_non_loopback_publisher_refused(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        host_ip: str,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
        state = compose.parse_ps_json(
            _ps_jsonl(_ps_record(identity, "redis", publishers=(_publisher(host_ip, 6379, 6379),)))
        )
        with pytest.raises(compose.OwnershipConflictError) as excinfo:
            adapter.assert_loopback_publishers(state)
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert host_ip not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Port preflight and race mapping
# ---------------------------------------------------------------------------


class TestPortPreflight:
    def _desired(self, manifest: Any) -> dict[Any, int]:
        models = _models()
        return {
            models.DependencyId.POSTGRES: 15432,
            models.DependencyId.REDIS: 16379,
            models.DependencyId.GRAFANA: 13000,
        }

    def test_clean_state_binds_each_desired_port(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        bound: list[tuple[str, int]] = []

        def recording_bind(host: str, port: int) -> None:
            bound.append((host, port))

        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            FakeSubprocess(),
            bind_check=recording_bind,
        )
        adapter.preflight_ports((), self._desired(manifest))

        assert sorted(bound) == [
            ("127.0.0.1", 13000),
            ("127.0.0.1", 15432),
            ("127.0.0.1", 16379),
        ]

    def test_bind_race_lost_maps_to_port_conflict(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()

        def losing_bind(host: str, port: int) -> None:
            raise compose.PortConflictError(f"{host}:{port} unavailable")

        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            FakeSubprocess(),
            bind_check=losing_bind,
        )
        with pytest.raises(compose.PortConflictError) as excinfo:
            adapter.preflight_ports((), self._desired(manifest))
        assert excinfo.value.code == "PORT_CONFLICT"
        assert "postgres" in str(excinfo.value)
        assert "15432" in str(excinfo.value)

    def test_exact_owned_publisher_accepted_without_bind(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        bound: list[tuple[str, int]] = []
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            FakeSubprocess(),
            bind_check=lambda host, port: bound.append((host, port)),
        )
        state = compose.parse_ps_json(
            _ps_jsonl(
                _ps_record(
                    identity,
                    "postgres",
                    publishers=(_publisher("127.0.0.1", 5432, 15432),),
                )
            )
        )

        adapter.preflight_ports(state, self._desired(manifest))

        assert sorted(bound) == [("127.0.0.1", 13000), ("127.0.0.1", 16379)]

    def test_owned_publisher_on_other_port_is_rechecked(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        bound: list[tuple[str, int]] = []
        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            FakeSubprocess(),
            bind_check=lambda host, port: bound.append((host, port)),
        )
        state = compose.parse_ps_json(
            _ps_jsonl(
                _ps_record(
                    identity,
                    "postgres",
                    publishers=(_publisher("127.0.0.1", 5432, 25432),),
                )
            )
        )

        adapter.preflight_ports(state, self._desired(manifest))
        assert ("127.0.0.1", 15432) in bound

    def test_default_bind_check_detects_occupied_port(
        self, manifest: Any, identity: Any, project_dir: Path, repo_root: Path
    ) -> None:
        compose = _compose()
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied_port = blocker.getsockname()[1]
        try:
            adapter, _ = _adapter(manifest, identity, project_dir, repo_root, FakeSubprocess())
            models = _models()
            with pytest.raises(compose.PortConflictError):
                adapter.preflight_ports(
                    (),
                    {
                        models.DependencyId.POSTGRES: occupied_port,
                        models.DependencyId.REDIS: 0,
                        models.DependencyId.GRAFANA: 0,
                    },
                )
        finally:
            blocker.close()

    def test_up_publish_race_maps_to_port_conflict(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        fake_subprocess.queue(
            returncode=1,
            stderr=(
                "Error response from daemon: driver failed programming external "
                "connectivity: Bind for 127.0.0.1:15432 failed: port is already allocated"
            ),
        )

        with pytest.raises(compose.PortConflictError):
            adapter.reconcile_up(secrets, timeout_seconds=30.0)


# ---------------------------------------------------------------------------
# Image pull sequencing and digest verification
# ---------------------------------------------------------------------------


class TestImagePullSequencing:
    def test_all_images_present_never_pulls(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        for dependency in manifest.dependencies:
            fake_subprocess.queue(
                stdout=_image_stdout(dependency, digests=(dependency.index_digest,))
            )
        fake_subprocess.queue(stdout="")  # reconcile up

        records = adapter.ensure_images(_runtime_facts(compose))
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        adapter.reconcile_up(secrets, timeout_seconds=30.0)

        assert [record.pulled for record in records] == [False, False, False]
        assert [record.dependency for record in records] == [
            dependency.id for dependency in manifest.dependencies
        ]
        argvs = _argvs(fake_subprocess)
        assert not any(argv[1:2] == ["pull"] for argv in argvs)
        up_argv = argvs[-1]
        assert up_argv[-3:] == ["--detach", "--pull", "never"]

    def test_only_missing_image_is_pulled_then_reverified(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        postgres, redis_dep, grafana = manifest.dependencies
        fake_subprocess.queue(returncode=1, stderr=f"Error: No such image: {postgres.image_ref}")
        fake_subprocess.queue(stdout="")  # docker pull postgres
        fake_subprocess.queue(stdout=_image_stdout(postgres, digests=(postgres.index_digest,)))
        fake_subprocess.queue(stdout=_image_stdout(redis_dep, digests=(redis_dep.index_digest,)))
        fake_subprocess.queue(stdout=_image_stdout(grafana, digests=(grafana.index_digest,)))

        records = adapter.ensure_images(_runtime_facts(compose))

        assert [record.pulled for record in records] == [True, False, False]
        argvs = _argvs(fake_subprocess)
        pull_argvs = [argv for argv in argvs if argv[1:2] == ["pull"]]
        assert pull_argvs == [["docker", "pull", postgres.image_ref]]
        assert argvs[0] == [
            "docker",
            "image",
            "inspect",
            postgres.image_ref,
            "--format",
            "json",
        ]
        assert argvs[1] == ["docker", "pull", postgres.image_ref]
        assert argvs[2][0:2] == ["docker", "image"]

    def test_empty_inspect_array_counts_as_missing(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        postgres, redis_dep, grafana = manifest.dependencies
        fake_subprocess.queue(stdout="[]")
        fake_subprocess.queue(stdout="")
        fake_subprocess.queue(stdout=_image_stdout(postgres, digests=(postgres.index_digest,)))
        fake_subprocess.queue(stdout=_image_stdout(redis_dep, digests=(redis_dep.index_digest,)))
        fake_subprocess.queue(stdout=_image_stdout(grafana, digests=(grafana.index_digest,)))

        records = adapter.ensure_images(_runtime_facts(compose))
        assert [record.pulled for record in records] == [True, False, False]

    def test_present_image_with_unverified_digest_fails(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        postgres = manifest.dependencies[0]
        fake_subprocess.queue(stdout=_image_stdout(postgres, digests=("sha256:" + "0" * 64,)))

        with pytest.raises(compose.ImageUnavailableError) as excinfo:
            adapter.ensure_images(_runtime_facts(compose))
        assert excinfo.value.code == "IMAGE_UNAVAILABLE"
        assert not any(argv[1:2] == ["pull"] for argv in _argvs(fake_subprocess))

    def test_wrong_platform_image_fails(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        postgres = manifest.dependencies[0]
        fake_subprocess.queue(
            stdout=_image_stdout(postgres, arch="amd64", digests=(postgres.index_digest,))
        )

        with pytest.raises(compose.ImageUnavailableError):
            adapter.ensure_images(_runtime_facts(compose))

    def test_platform_child_digest_accepted(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        for dependency in manifest.dependencies:
            fake_subprocess.queue(
                stdout=_image_stdout(dependency, digests=(_child_digest(dependency),))
            )

        records = adapter.ensure_images(_runtime_facts(compose))
        assert [record.pulled for record in records] == [False, False, False]

    def test_pull_failure_is_safe_image_unavailable(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        synthetic_secret: str,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(returncode=1, stderr="Error: No such image")
        fake_subprocess.queue(
            returncode=1,
            stderr=f"registry denied {synthetic_secret} at {SENTINEL_WORKSPACE_PATH}",
        )

        with pytest.raises(compose.ImageUnavailableError) as excinfo:
            adapter.ensure_images(_runtime_facts(compose))
        message = str(excinfo.value)
        assert synthetic_secret not in message
        assert SENTINEL_WORKSPACE_PATH not in message
        assert "registry denied" not in message


# ---------------------------------------------------------------------------
# Bounded termination and interruption
# ---------------------------------------------------------------------------


class TestBoundedTermination:
    def test_every_subprocess_call_carries_a_timeout(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_runtime_preflight(fake_subprocess)
        fake_subprocess.queue(stdout="")  # ps
        for dependency in manifest.dependencies:
            fake_subprocess.queue(
                stdout=_image_stdout(dependency, digests=(dependency.index_digest,))
            )
        fake_subprocess.queue(stdout="")  # up

        runtime = adapter.verify_runtime()
        adapter.project_state()
        adapter.ensure_images(runtime)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        adapter.reconcile_up(secrets, timeout_seconds=30.0)

        assert fake_subprocess.calls
        for _, kwargs in fake_subprocess.calls:
            assert kwargs["timeout"] is not None
            assert kwargs["timeout"] > 0

    def test_timeout_maps_to_stable_redacted_diagnostic(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()

        def interruptible(args: Sequence[str], **kwargs: Any) -> Any:
            if args[-3:] == ["--detach", "--pull", "never"]:
                raise subprocess.TimeoutExpired(cmd=list(args), timeout=30.0)
            return fake_subprocess.run(args, **kwargs)

        adapter, _ = _adapter(
            manifest,
            identity,
            project_dir,
            repo_root,
            fake_subprocess,
            run=interruptible,
        )
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )

        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.reconcile_up(secrets, timeout_seconds=30.0)

        message = str(excinfo.value)
        assert excinfo.value.code == "STEP_FAILED"
        assert "terminat" in message.lower() or "exceed" in message.lower()
        assert secret_values["postgres"] not in message
        assert identity.project_id not in message

    def test_keyboard_interrupt_propagates(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()

        def sigint(args: Sequence[str], **kwargs: Any) -> Any:
            raise KeyboardInterrupt

        adapter, _ = _adapter(
            manifest, identity, project_dir, repo_root, fake_subprocess, run=sigint
        )
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )

        with pytest.raises(KeyboardInterrupt):
            adapter.reconcile_up(secrets, timeout_seconds=30.0)

    def test_default_run_terminates_bounded_process_group(self) -> None:
        compose = _compose()
        started = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            compose.default_run(["sleep", "30"], timeout=0.2)
        assert time.monotonic() - started < 10

    def test_default_run_captures_output(self) -> None:
        compose = _compose()
        result = compose.default_run(["echo", "hello"], timeout=5)
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"


# ---------------------------------------------------------------------------
# Error redaction
# ---------------------------------------------------------------------------


class TestErrorRedaction:
    def test_up_failure_never_leaks_stderr_secrets_or_paths(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        fake_subprocess.queue(
            returncode=1,
            stderr=(
                f"compose failed: {secret_values['postgres']} "
                f"at {SENTINEL_WORKSPACE_PATH} on {repo_root}"
            ),
            stdout=f"partial output {secret_values['redis']}",
        )

        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.reconcile_up(secrets, timeout_seconds=30.0)

        message = str(excinfo.value)
        for forbidden in (
            secret_values["postgres"],
            secret_values["redis"],
            secret_values["grafana"],
            SENTINEL_WORKSPACE_PATH,
            str(repo_root),
            "compose failed:",
            "partial output",
        ):
            assert forbidden not in message

    def test_state_parse_error_never_echoes_raw_output(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        synthetic_secret: str,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout=f'{{"Service": "{synthetic_secret}"\n')

        with pytest.raises(compose.ComposeStateParseError) as excinfo:
            adapter.project_state()
        assert synthetic_secret not in str(excinfo.value)


# ---------------------------------------------------------------------------
# T030: dedicated child-only secret mappings
# ---------------------------------------------------------------------------


class TestSecretMaterial:
    def test_child_mapping_contents_and_single_directive_redis(
        self,
        manifest: Any,
        identity: Any,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )

        mapping = secrets.child_mapping()

        assert mapping == {
            compose.POSTGRES_PASSWORD_ENV: secret_values["postgres"],
            compose.REDIS_CONFIG_ENV: f"requirepass {secret_values['redis']}\n",
            compose.GRAFANA_ADMIN_PASSWORD_ENV: secret_values["grafana"],
        }
        redis_lines = mapping[compose.REDIS_CONFIG_ENV].splitlines()
        assert redis_lines == [f"requirepass {secret_values['redis']}"]

    def test_material_metadata_matches_manifest_ownership_and_mode(
        self,
        manifest: Any,
        identity: Any,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        models = _models()
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        postgres = manifest.dependency(models.DependencyId.POSTGRES)
        redis_dep = manifest.dependency(models.DependencyId.REDIS)
        grafana = manifest.dependency(models.DependencyId.GRAFANA)

        expectations = (
            (
                secrets.postgres_password,
                models.SecretPurpose.POSTGRES_PASSWORD,
                "DATABASE_URL",
                postgres,
            ),
            (
                secrets.redis_config,
                models.SecretPurpose.REDIS_CONFIG,
                "REDIS_URL",
                redis_dep,
            ),
            (
                secrets.grafana_admin_password,
                models.SecretPurpose.GRAFANA_ADMIN_PASSWORD,
                "GRAFANA_ADMIN_PASSWORD",
                grafana,
            ),
        )
        for material, purpose, source_field, definition in expectations:
            assert material.project_id == identity.project_id
            assert material.purpose == purpose
            assert material.source_field == source_field
            assert material.container_owner_uid == definition.runtime_uid
            assert material.container_owner_gid == definition.runtime_gid
            assert material.container_file_mode == "0400"
            assert material.cleanup_state == models.SecretCleanupState.IN_MEMORY

        assert (postgres.runtime_uid, postgres.runtime_gid) == (999, 999)
        assert (redis_dep.runtime_uid, redis_dep.runtime_gid) == (999, 999)
        assert (grafana.runtime_uid, grafana.runtime_gid) == (472, 472)

    @pytest.mark.parametrize(
        "bad_value",
        [
            "tm_local_short",
            "not_local_" + "a" * 40,
            "tm_local_" + "a" * 31 + "\nrequirepass hacked",
            "tm_local_" + "a" * 31 + "\r\nbind 0.0.0.0",
            "tm_local_with space" + "a" * 30,
            "tm_local_with'quote" + "a" * 30,
            'tm_local_with"dquote' + "a" * 30,
            "tm_local_with\\backslash" + "a" * 28,
            "tm_local_with;semicolon" + "a" * 28,
        ],
    )
    def test_config_injection_passwords_rejected_with_field_name_only(
        self,
        manifest: Any,
        identity: Any,
        secret_values: dict[str, str],
        bad_value: str,
    ) -> None:
        compose = _compose()
        with pytest.raises(compose.InvalidSecretMaterialError) as excinfo:
            compose.build_secret_material(
                manifest,
                identity,
                postgres_password=secret_values["postgres"],
                redis_password=bad_value,
                grafana_admin_password=secret_values["grafana"],
            )
        message = str(excinfo.value)
        assert excinfo.value.code == "INVALID_CONFIG"
        assert "REDIS_URL" in message
        assert bad_value not in message

    def test_release_drops_bytes_and_mapping_fails_closed(
        self,
        manifest: Any,
        identity: Any,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        models = _models()
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )

        released = secrets.release()

        for material in (
            released.postgres_password,
            released.redis_config,
            released.grafana_admin_password,
        ):
            assert material.cleanup_state == models.SecretCleanupState.RELEASED
        with pytest.raises(compose.InvalidSecretMaterialError):
            released.child_mapping()
        # The original set remains usable; release is immutable.
        assert secrets.child_mapping()

    def test_secret_values_stay_out_of_repr_and_parent_environ(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        for material in (
            secrets.postgres_password,
            secrets.redis_config,
            secrets.grafana_admin_password,
        ):
            assert secret_values["postgres"] not in repr(material)
            assert secret_values["redis"] not in repr(material)
            assert secret_values["grafana"] not in repr(material)

        fake_subprocess.queue(stdout="")
        adapter.reconcile_up(secrets, timeout_seconds=30.0)

        env = fake_subprocess.calls[0][1]["env"]
        assert env[compose.POSTGRES_PASSWORD_ENV] == secret_values["postgres"]
        assert env[compose.REDIS_CONFIG_ENV] == f"requirepass {secret_values['redis']}\n"
        assert env[compose.GRAFANA_ADMIN_PASSWORD_ENV] == secret_values["grafana"]
        assert env[compose.WORKSPACE_ID_ENV] == identity.project_id
        assert env[compose.WORKSPACE_FINGERPRINT_ENV] == identity.workspace_fingerprint
        for variable in (
            compose.POSTGRES_PASSWORD_ENV,
            compose.REDIS_CONFIG_ENV,
            compose.GRAFANA_ADMIN_PASSWORD_ENV,
        ):
            assert variable not in os.environ
        for value in secret_values.values():
            assert value not in os.environ.values()
            assert SENTINEL_WORKSPACE_PATH not in env.values()


# ---------------------------------------------------------------------------
# T030: parse-only teardown placeholders
# ---------------------------------------------------------------------------


class TestTeardownPlaceholders:
    def test_placeholders_match_grammar_and_single_directive(
        self, manifest: Any, identity: Any
    ) -> None:
        compose = _compose()
        models = _models()
        placeholders = compose.build_teardown_placeholders(manifest, identity)

        mapping = placeholders.child_mapping()
        grammar = compose.LOCAL_SECRET_GRAMMAR
        assert grammar.fullmatch(mapping[compose.POSTGRES_PASSWORD_ENV])
        assert grammar.fullmatch(mapping[compose.GRAFANA_ADMIN_PASSWORD_ENV])
        redis_lines = mapping[compose.REDIS_CONFIG_ENV].splitlines()
        assert len(redis_lines) == 1
        directive, _, value = redis_lines[0].partition(" ")
        assert directive == "requirepass"
        assert grammar.fullmatch(value)

        for material in (
            placeholders.postgres_password,
            placeholders.redis_config,
            placeholders.grafana_admin_password,
        ):
            assert material.purpose == models.SecretPurpose.TEARDOWN_PLACEHOLDER
            assert material.container_file_mode == "0400"
            assert material.cleanup_state == models.SecretCleanupState.IN_MEMORY

    def test_placeholders_are_not_real_values(
        self,
        manifest: Any,
        identity: Any,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        placeholders = compose.build_teardown_placeholders(manifest, identity)
        mapping = placeholders.child_mapping()
        assert mapping[compose.POSTGRES_PASSWORD_ENV] != secret_values["postgres"]
        assert mapping[compose.GRAFANA_ADMIN_PASSWORD_ENV] != secret_values["grafana"]
        assert secret_values["redis"] not in mapping[compose.REDIS_CONFIG_ENV]

    def test_placeholder_ownership_matches_manifest(self, manifest: Any, identity: Any) -> None:
        compose = _compose()
        models = _models()
        placeholders = compose.build_teardown_placeholders(manifest, identity)
        postgres = manifest.dependency(models.DependencyId.POSTGRES)
        redis_dep = manifest.dependency(models.DependencyId.REDIS)
        grafana = manifest.dependency(models.DependencyId.GRAFANA)
        assert (
            placeholders.postgres_password.container_owner_uid,
            placeholders.postgres_password.container_owner_gid,
        ) == (postgres.runtime_uid, postgres.runtime_gid)
        assert (
            placeholders.redis_config.container_owner_uid,
            placeholders.redis_config.container_owner_gid,
        ) == (redis_dep.runtime_uid, redis_dep.runtime_gid)
        assert (
            placeholders.grafana_admin_password.container_owner_uid,
            placeholders.grafana_admin_password.container_owner_gid,
        ) == (grafana.runtime_uid, grafana.runtime_gid)


# ---------------------------------------------------------------------------
# Derived non-secret child variables (wired by the lifecycle orchestrator)
# ---------------------------------------------------------------------------


class TestDerivedChildEnvironment:
    def _derived(self, compose: Any) -> dict[str, str]:
        return {
            compose.POSTGRES_USER_ENV: "devuser",
            compose.POSTGRES_DB_ENV: "tokenmarket",
            compose.POSTGRES_HOST_PORT_ENV: "15432",
            compose.REDIS_HOST_PORT_ENV: "16379",
            compose.GRAFANA_HOST_PORT_ENV: "13000",
        }

    def test_derived_env_is_merged_into_the_child_environment(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        fake_subprocess.queue(stdout="")

        adapter.reconcile_up(secrets, timeout_seconds=30.0, derived_env=self._derived(compose))

        env = fake_subprocess.calls[0][1]["env"]
        for key, value in self._derived(compose).items():
            assert env[key] == value
        assert env[compose.POSTGRES_PASSWORD_ENV] == secret_values["postgres"]
        assert env[compose.WORKSPACE_ID_ENV] == identity.project_id

    def test_derived_env_cannot_override_adapter_owned_variables(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
        secret_values: dict[str, str],
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        secrets = compose.build_secret_material(
            manifest,
            identity,
            postgres_password=secret_values["postgres"],
            redis_password=secret_values["redis"],
            grafana_admin_password=secret_values["grafana"],
        )
        derived = self._derived(compose)
        derived[compose.POSTGRES_PASSWORD_ENV] = "override-attempt"

        with pytest.raises(ValueError):
            adapter.reconcile_up(secrets, timeout_seconds=30.0, derived_env=derived)
        assert fake_subprocess.calls == []
