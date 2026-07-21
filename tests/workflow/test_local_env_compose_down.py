"""Fake Docker CLI tests for the SF02 Compose down path (T037, US2).

Covers the ``make dev-down`` adapter rules of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 2, 7 and 11 without a real Docker daemon:

- config-free exact-project down: no ``.env.local`` is required, parsed, or
  validated; the dedicated child environment carries only safe ``tm_local_``
  parse-only placeholder values plus the workspace identity variables;
- exact project ID plus full-64-hex-fingerprint authorization before any
  mutation; a matching 12-hex ID with a different fingerprint fails closed;
- discovery of the already-stopped volume-only state, stopped containers, and
  orphan networks through exact-label read-only listings;
- ``down --remove-orphans`` from the verified committed bytes over stdin with
  a fixed argument order and NO ``--volumes``/``--rmi``/prune/``--timeout``
  flags, so Compose applies the declared 60/30/30 stop grace periods while
  the workflow's outer 75-second bound is caller-supplied;
- exact-label container/network fallback when Compose cannot parse the model:
  graceful ``stop --time`` with the declared per-service grace, then removal;
  never volumes, images, prune, or prefix-matched resources; a stop timeout
  or forced termination is failure evidence, never silent success;
- stable redacted errors that never leak stderr/stdout/argv/env/secrets/paths.

Every identity uses the disjoint ``tmtest-`` test prefix so the fake CLI can
never address a developer project. These tests fail until T043 implements the
down surface in ``tools/workflow/local_env/compose.py``.
"""

from __future__ import annotations

import importlib
import inspect
import json
import subprocess
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
STOP_OPERATION_BUDGET_SECONDS = 75.0

_ADAPTER_DOWN_METHODS = (
    "reconcile_down",
    "project_resources",
    "repository_resources",
    "assert_exact_resource_ownership",
    "remove_exact_resources",
)
_MODULE_DOWN_TYPES = ("ProjectResource", "ResourceKind")

_PARSE_ERROR_STDERR = (
    "error while interpolating services.postgres.ports.0.published: required "
    "variable TOKENMARKET_POSTGRES_HOST_PORT is missing a value"
)


def _compose() -> Any:
    compose = importlib.import_module("workflow.local_env.compose")
    missing = [name for name in _ADAPTER_DOWN_METHODS if not hasattr(compose.ComposeAdapter, name)]
    missing += [name for name in _MODULE_DOWN_TYPES if not hasattr(compose, name)]
    if missing:
        pytest.fail(
            "workflow.local_env.compose down support is not implemented yet "
            f"(T043): missing {', '.join(missing)}"
        )
    return compose


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
    )
    return adapter, git


def _argvs(fake: FakeSubprocess) -> list[list[str]]:
    return [argv for argv, _ in fake.calls]


def _owned_labels(identity: Any, service: str | None = None) -> dict[str, str]:
    """Full ownership label set for the exact test project."""
    compose = _compose()
    labels = {
        compose.LABEL_REPOSITORY: TEST_REPOSITORY_LABEL,
        compose.LABEL_WORKSPACE_ID: identity.project_id,
        compose.LABEL_WORKSPACE_FINGERPRINT: identity.workspace_fingerprint,
    }
    if service is not None:
        labels["com.docker.compose.service"] = service
    return labels


def _container_inspect_json(identity: Any, containers: Sequence[tuple[str, str]]) -> str:
    documents = [
        {
            "Id": container_id,
            "Name": f"/{identity.project_id}-{service}-1",
            "Config": {"Labels": _owned_labels(identity, service)},
        }
        for container_id, service in containers
    ]
    return json.dumps(documents)


def _network_inspect_json(identity: Any, networks: Sequence[str]) -> str:
    documents = [
        {
            "Id": network_id,
            "Name": f"{identity.project_id}_default",
            "Labels": _owned_labels(identity),
        }
        for network_id in networks
    ]
    return json.dumps(documents)


def _volume_inspect_json(identity: Any, volumes: Sequence[str]) -> str:
    documents = [{"Name": name, "Labels": _owned_labels(identity)} for name in volumes]
    return json.dumps(documents)


def _queue_project_listing(
    fake: FakeSubprocess,
    identity: Any,
    *,
    containers: Sequence[tuple[str, str]] = (),
    networks: Sequence[str] = (),
    volumes: Sequence[str] = (),
) -> None:
    """Queue the exact-label ls/inspect sequence of one discovery pass."""
    fake.queue(stdout="".join(f"{container_id}\n" for container_id, _ in containers))
    if containers:
        fake.queue(stdout=_container_inspect_json(identity, containers))
    fake.queue(stdout="".join(f"{network_id}\n" for network_id in networks))
    if networks:
        fake.queue(stdout=_network_inspect_json(identity, networks))
    fake.queue(stdout="".join(f"{name}\n" for name in volumes))
    if volumes:
        fake.queue(stdout=_volume_inspect_json(identity, volumes))


def _listing_argvs(
    identity: Any,
    *,
    containers: Sequence[tuple[str, str]] = (),
    networks: Sequence[str] = (),
    volumes: Sequence[str] = (),
    repository_scan: bool = False,
) -> list[list[str]]:
    if repository_scan:
        filter_value = "label=com.tokenmarket.repository=tokenmarket"
    else:
        filter_value = f"label=com.docker.compose.project={identity.project_id}"
    argvs = [["docker", "ps", "-aq", "--no-trunc", "--filter", filter_value]]
    if containers:
        argvs.append(["docker", "inspect", *[cid for cid, _ in containers]])
    argvs.append(["docker", "network", "ls", "--no-trunc", "-q", "--filter", filter_value])
    if networks:
        argvs.append(["docker", "network", "inspect", *networks])
    argvs.append(["docker", "volume", "ls", "-q", "--filter", filter_value])
    if volumes:
        argvs.append(["docker", "volume", "inspect", *volumes])
    return argvs


def _placeholders(manifest: Any, identity: Any) -> Any:
    return _compose().build_teardown_placeholders(manifest, identity)


def _resource(
    compose: Any, kind: Any, resource_id: str, name: str, labels: Mapping[str, str]
) -> Any:
    return compose.ProjectResource(
        kind=kind, resource_id=resource_id, name=name, labels=dict(labels)
    )


def _exact_project_resources(identity: Any) -> list[Any]:
    compose = _compose()
    containers = [
        _resource(
            compose,
            compose.ResourceKind.CONTAINER,
            f"{service}-id-0001",
            f"{identity.project_id}-{service}-1",
            _owned_labels(identity, service),
        )
        for service in ("postgres", "redis", "grafana")
    ]
    network = _resource(
        compose,
        compose.ResourceKind.NETWORK,
        "network-id-0001",
        f"{identity.project_id}_default",
        _owned_labels(identity),
    )
    return [*containers, network]


def _assert_no_destructive_spawns(fake: FakeSubprocess) -> None:
    """No volume/image removal, prune, or forced removal may ever be spawned."""
    for argv in _argvs(fake):
        lowered = [token.lower() for token in argv]
        assert "prune" not in lowered, f"prune is forbidden: {argv!r}"
        assert "--volumes" not in lowered and "--rmi" not in lowered
        assert lowered[:2] != ["docker", "image"], f"image mutation: {argv!r}"
        assert lowered[:2] != ["docker", "system"], f"system mutation: {argv!r}"
        if lowered[:2] == ["docker", "volume"]:
            raise AssertionError(f"volume mutation is forbidden: {argv!r}")
        if "rm" in lowered:
            position = lowered.index("rm")
            assert (
                "-f" not in lowered[position:] and "--force" not in lowered[position:]
            ), f"forced removal is failure evidence, not a command: {argv!r}"


# ---------------------------------------------------------------------------
# The down command surface
# ---------------------------------------------------------------------------


class TestDownCommandSurface:
    def test_down_argv_exact_order_stdin_and_verified_bytes(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, git = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="")

        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )

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
            "down",
            "--remove-orphans",
        ]
        assert kwargs["timeout"] == STOP_OPERATION_BUDGET_SECONDS
        assert kwargs["input"].encode("utf-8") == SYNTHETIC_COMPOSE
        assert git.calls == [compose.COMPOSE_FILE_RELATIVE_PATH]

    def test_down_child_env_is_parse_only_placeholders(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="")

        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )

        _, kwargs = fake_subprocess.calls[0]
        env = kwargs["env"]
        assert set(env) == {
            compose.POSTGRES_PASSWORD_ENV,
            compose.REDIS_CONFIG_ENV,
            compose.GRAFANA_ADMIN_PASSWORD_ENV,
            compose.WORKSPACE_ID_ENV,
            compose.WORKSPACE_FINGERPRINT_ENV,
            compose.POSTGRES_USER_ENV,
            compose.POSTGRES_DB_ENV,
            compose.POSTGRES_HOST_PORT_ENV,
            compose.REDIS_HOST_PORT_ENV,
            compose.GRAFANA_HOST_PORT_ENV,
        }, "the down child mapping must contain only parse-only adapter values"
        assert env[compose.POSTGRES_PASSWORD_ENV] == compose.TEARDOWN_PLACEHOLDER_SECRET
        assert (
            env[compose.REDIS_CONFIG_ENV] == f"requirepass {compose.TEARDOWN_PLACEHOLDER_SECRET}\n"
        )
        assert env[compose.GRAFANA_ADMIN_PASSWORD_ENV] == compose.TEARDOWN_PLACEHOLDER_SECRET
        assert env[compose.WORKSPACE_ID_ENV] == identity.project_id
        assert env[compose.WORKSPACE_FINGERPRINT_ENV] == identity.workspace_fingerprint
        for key in (
            compose.POSTGRES_USER_ENV,
            compose.POSTGRES_DB_ENV,
            compose.POSTGRES_HOST_PORT_ENV,
            compose.REDIS_HOST_PORT_ENV,
            compose.GRAFANA_HOST_PORT_ENV,
        ):
            assert env[key], "non-secret parse values must let the model parse"

    def test_down_surface_accepts_no_configuration_input(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        signature = inspect.signature(compose.ComposeAdapter.reconcile_down)
        assert not any(
            "config" in name.lower() for name in signature.parameters
        ), "the down surface must not require, parse, or validate .env.local"
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="")
        # The whole down path needs only manifest, identity, and placeholders.
        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )
        assert len(fake_subprocess.calls) == 1

    def test_down_forbids_volume_image_prune_and_timeout_flags(
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

        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )

        argv, _ = fake_subprocess.calls[0]
        assert argv[-2:] == [
            "down",
            "--remove-orphans",
        ], "down carries no trailing flags beyond --remove-orphans"
        for forbidden in ("--volumes", "-v", "--rmi", "--timeout", "--force", "prune"):
            assert forbidden not in argv, f"forbidden flag {forbidden!r} in {argv!r}"
        _assert_no_destructive_spawns(fake_subprocess)

    def test_down_outer_bound_is_caller_supplied_without_cli_timeout(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        _compose()
        assert manifest.timeouts.stop_operation_seconds == 75
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        fake_subprocess.queue(stdout="")

        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )

        argv, kwargs = fake_subprocess.calls[0]
        assert kwargs["timeout"] == STOP_OPERATION_BUDGET_SECONDS
        assert "--timeout" not in argv, (
            "Compose applies the declared 60/30/30 stop_grace_period values; "
            "the CLI timeout override is forbidden"
        )

    def test_down_nonzero_exit_is_redacted_step_failed(
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
            returncode=1,
            stderr=(
                "Error response from daemon: tm_local_realsecretvalue000000000000 "
                f"under {SENTINEL_WORKSPACE_PATH} and /Users/developer/checkout"
            ),
        )

        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.reconcile_down(
                _placeholders(manifest, identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )

        assert excinfo.value.code == "STEP_FAILED"
        message = str(excinfo.value)
        assert "tm_local_" not in message
        assert SENTINEL_WORKSPACE_PATH not in message
        assert "/Users" not in message

    def test_down_timeout_maps_to_bounded_redacted_failure(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()

        def interruptible(args: Sequence[str], **kwargs: Any) -> Any:
            if list(args[-2:]) == ["down", "--remove-orphans"]:
                raise subprocess.TimeoutExpired(
                    cmd=[str(arg) for arg in args], timeout=STOP_OPERATION_BUDGET_SECONDS
                )
            return fake_subprocess.run(args, **kwargs)

        adapter, _ = _adapter(
            manifest, identity, project_dir, repo_root, fake_subprocess, run=interruptible
        )
        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.reconcile_down(
                _placeholders(manifest, identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )
        assert excinfo.value.code == "STEP_FAILED"
        assert "terminated" in str(excinfo.value).lower()

    def test_down_dirty_asset_fails_closed_before_any_spawn(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        (repo_root / "infra" / "docker" / "compose.local.yml").write_bytes(
            b"services:\n  postgres:\n    image: tampered\n"
        )
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)

        with pytest.raises(compose.ComposeAssetError):
            adapter.reconcile_down(
                _placeholders(manifest, identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )
        assert fake_subprocess.calls == [], "asset drift fails before Compose access"

    def test_down_parse_failure_triggers_exact_label_fallback(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        containers = [
            ("postgres-id-0001", "postgres"),
            ("redis-id-0001", "redis"),
            ("grafana-id-0001", "grafana"),
        ]
        fake_subprocess.queue(returncode=1, stderr=_PARSE_ERROR_STDERR)
        _queue_project_listing(
            fake_subprocess, identity, containers=containers, networks=["network-id-0001"]
        )
        for _ in range(7):  # stop/rm per container, then network rm
            fake_subprocess.queue(stdout="")

        adapter.reconcile_down(
            _placeholders(manifest, identity), timeout_seconds=STOP_OPERATION_BUDGET_SECONDS
        )

        argvs = _argvs(fake_subprocess)
        down_argv, _ = fake_subprocess.calls[0]
        assert down_argv[-2:] == ["down", "--remove-orphans"]
        assert argvs[1:3] == [
            [
                "docker",
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={identity.project_id}",
            ],
            ["docker", "inspect", "postgres-id-0001", "redis-id-0001", "grafana-id-0001"],
        ]
        assert argvs[3:5] == [
            [
                "docker",
                "network",
                "ls",
                "--no-trunc",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={identity.project_id}",
            ],
            ["docker", "network", "inspect", "network-id-0001"],
        ]
        assert argvs[5:] == [
            ["docker", "stop", "--time", "60", "postgres-id-0001"],
            ["docker", "rm", "postgres-id-0001"],
            ["docker", "stop", "--time", "30", "redis-id-0001"],
            ["docker", "rm", "redis-id-0001"],
            ["docker", "stop", "--time", "30", "grafana-id-0001"],
            ["docker", "rm", "grafana-id-0001"],
            ["docker", "network", "rm", "network-id-0001"],
        ], f"fallback must stop/remove only exact-label containers/networks: {argvs!r}"
        assert not any(
            "volume" in [token.lower() for token in argv] for argv in argvs
        ), "the fallback never lists or touches volumes"
        _assert_no_destructive_spawns(fake_subprocess)

    def test_down_genuine_failure_does_not_fallback(
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
            returncode=1,
            stderr="Error response from daemon: driver failed programming connectivity",
        )

        with pytest.raises(compose.ComposeCommandError):
            adapter.reconcile_down(
                _placeholders(manifest, identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )
        assert (
            len(fake_subprocess.calls) == 1
        ), "only a parse failure may trigger the exact-label fallback"


# ---------------------------------------------------------------------------
# Exact-label read-only discovery
# ---------------------------------------------------------------------------


class TestProjectResourceDiscovery:
    def test_already_stopped_volume_only_state(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        volumes = [
            f"{identity.project_id}_postgres-data",
            f"{identity.project_id}_redis-data",
        ]
        _queue_project_listing(fake_subprocess, identity, volumes=volumes)

        resources = adapter.project_resources()

        assert {resource.kind for resource in resources} == {compose.ResourceKind.VOLUME}
        assert {resource.name for resource in resources} == set(volumes)
        assert _argvs(fake_subprocess) == _listing_argvs(identity, volumes=volumes)

    def test_stopped_containers_are_listed_for_reconciliation(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        containers = [("postgres-id-0001", "postgres"), ("redis-id-0001", "redis")]
        _queue_project_listing(fake_subprocess, identity, containers=containers)

        resources = adapter.project_resources()

        by_id = {resource.resource_id: resource for resource in resources}
        assert set(by_id) == {"postgres-id-0001", "redis-id-0001"}
        assert all(
            resource.kind == compose.ResourceKind.CONTAINER for resource in resources
        ), "docker ps -a lists stopped containers so down still removes them"
        assert by_id["postgres-id-0001"].name == f"{identity.project_id}-postgres-1"
        assert (
            by_id["postgres-id-0001"].labels[compose.LABEL_WORKSPACE_FINGERPRINT]
            == identity.workspace_fingerprint
        )

    def test_orphan_network_is_listed(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_project_listing(fake_subprocess, identity, networks=["network-id-0001"])

        resources = adapter.project_resources()

        assert len(resources) == 1
        assert resources[0].kind == compose.ResourceKind.NETWORK
        assert resources[0].resource_id == "network-id-0001"
        assert resources[0].name == f"{identity.project_id}_default"

    def test_discovery_uses_exact_filters_and_never_reads_the_asset(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        _compose()
        adapter, git = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        _queue_project_listing(fake_subprocess, identity)

        resources = adapter.project_resources()

        assert resources == ()
        assert _argvs(fake_subprocess) == _listing_argvs(identity)
        assert git.calls == [], "read-only discovery does not need the Compose asset"

    def test_repository_scan_reports_foreign_workspace_resources(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        adapter, git = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        foreign_id = "tokenmarket-eeee5555ffff"
        foreign_labels = {
            compose.LABEL_REPOSITORY: "tokenmarket",
            compose.LABEL_WORKSPACE_ID: foreign_id,
            compose.LABEL_WORKSPACE_FINGERPRINT: "e" * 64,
        }
        fake_subprocess.queue(stdout="foreign-container-id\n")
        fake_subprocess.queue(
            stdout=json.dumps(
                [
                    {
                        "Id": "foreign-container-id",
                        "Name": f"/{foreign_id}-postgres-1",
                        "Config": {"Labels": foreign_labels},
                    }
                ]
            )
        )
        fake_subprocess.queue(stdout="")
        fake_subprocess.queue(stdout="")

        resources = adapter.repository_resources()

        assert _argvs(fake_subprocess) == _listing_argvs(identity, repository_scan=True)
        assert len(resources) == 1
        assert resources[0].labels[compose.LABEL_WORKSPACE_ID] == foreign_id
        assert git.calls == [], "repository scan is read-only discovery"
        # A scan only reports; it must never mutate. No further spawns exist.
        assert len(fake_subprocess.calls) == 4


# ---------------------------------------------------------------------------
# Exact project/fingerprint authorization before mutation
# ---------------------------------------------------------------------------


class TestDownOwnershipAuthorization:
    def test_exact_resources_pass_authorization(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        adapter.assert_exact_resource_ownership(_exact_project_resources(identity))

    def test_foreign_workspace_fails_before_mutation(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        models = _models()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        foreign = _resource(
            compose,
            compose.ResourceKind.CONTAINER,
            "foreign-id",
            "tokenmarket-eeee5555ffff-postgres-1",
            {
                compose.LABEL_REPOSITORY: "tokenmarket",
                compose.LABEL_WORKSPACE_ID: "tokenmarket-eeee5555ffff",
                compose.LABEL_WORKSPACE_FINGERPRINT: "e" * 64,
            },
        )

        with pytest.raises(models.OwnershipConflictError) as excinfo:
            adapter.assert_exact_resource_ownership([foreign])
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert SENTINEL_WORKSPACE_PATH not in str(excinfo.value)

    def test_full_fingerprint_collision_fails_before_mutation(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        models = _models()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        flipped = identity.workspace_fingerprint[:-1] + (
            "0" if identity.workspace_fingerprint[-1] != "0" else "1"
        )
        colliding = _resource(
            compose,
            compose.ResourceKind.CONTAINER,
            "colliding-id",
            f"{identity.project_id}-postgres-1",
            {
                compose.LABEL_REPOSITORY: TEST_REPOSITORY_LABEL,
                compose.LABEL_WORKSPACE_ID: identity.project_id,
                compose.LABEL_WORKSPACE_FINGERPRINT: flipped,
            },
        )

        with pytest.raises(models.OwnershipConflictError) as excinfo:
            adapter.assert_exact_resource_ownership([colliding])
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert "fingerprint" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Exact-label container/network fallback removal
# ---------------------------------------------------------------------------


class TestExactLabelFallbackRemoval:
    def test_removes_containers_with_declared_grace_then_networks(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        _compose()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        for _ in range(7):
            fake_subprocess.queue(stdout="")

        adapter.remove_exact_resources(
            _exact_project_resources(identity),
            timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
        )

        assert _argvs(fake_subprocess) == [
            ["docker", "stop", "--time", "60", "postgres-id-0001"],
            ["docker", "rm", "postgres-id-0001"],
            ["docker", "stop", "--time", "30", "redis-id-0001"],
            ["docker", "rm", "redis-id-0001"],
            ["docker", "stop", "--time", "30", "grafana-id-0001"],
            ["docker", "rm", "grafana-id-0001"],
            ["docker", "network", "rm", "network-id-0001"],
        ]
        for _, kwargs in fake_subprocess.calls:
            assert 0 < kwargs["timeout"] <= STOP_OPERATION_BUDGET_SECONDS
        _assert_no_destructive_spawns(fake_subprocess)

    def test_refuses_volumes_and_foreign_resources_without_side_effects(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()
        models = _models()
        adapter, _ = _adapter(manifest, identity, project_dir, repo_root, fake_subprocess)
        volume = _resource(
            compose,
            compose.ResourceKind.VOLUME,
            f"{identity.project_id}_postgres-data",
            f"{identity.project_id}_postgres-data",
            _owned_labels(identity),
        )
        foreign = _resource(
            compose,
            compose.ResourceKind.CONTAINER,
            "foreign-id",
            "tokenmarket-eeee5555ffff-postgres-1",
            {
                compose.LABEL_REPOSITORY: "tokenmarket",
                compose.LABEL_WORKSPACE_ID: "tokenmarket-eeee5555ffff",
                compose.LABEL_WORKSPACE_FINGERPRINT: "e" * 64,
            },
        )

        with pytest.raises(models.OwnershipConflictError) as volume_error:
            adapter.remove_exact_resources([volume], timeout_seconds=STOP_OPERATION_BUDGET_SECONDS)
        assert "volume" in str(volume_error.value).lower()
        with pytest.raises(models.OwnershipConflictError):
            adapter.remove_exact_resources([foreign], timeout_seconds=STOP_OPERATION_BUDGET_SECONDS)
        assert (
            fake_subprocess.calls == []
        ), "volume or foreign removal attempts fail closed before any spawn"

    def test_stop_failure_is_failure_evidence_not_silent_success(
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
            returncode=1,
            stderr="Error response from daemon: tm_local_leakedsecret00000000000000",
        )

        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.remove_exact_resources(
                _exact_project_resources(identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )

        assert excinfo.value.code == "STEP_FAILED"
        assert "tm_local_" not in str(excinfo.value)
        assert _argvs(fake_subprocess) == [
            ["docker", "stop", "--time", "60", "postgres-id-0001"]
        ], "a failed graceful stop must not escalate to forced removal"

    def test_stop_timeout_is_bounded_failure_evidence(
        self,
        manifest: Any,
        identity: Any,
        project_dir: Path,
        repo_root: Path,
        fake_subprocess: FakeSubprocess,
    ) -> None:
        compose = _compose()

        def interruptible(args: Sequence[str], **kwargs: Any) -> Any:
            if list(args[:2]) == ["docker", "stop"]:
                raise subprocess.TimeoutExpired(cmd=[str(arg) for arg in args], timeout=60.0)
            return fake_subprocess.run(args, **kwargs)

        adapter, _ = _adapter(
            manifest, identity, project_dir, repo_root, fake_subprocess, run=interruptible
        )
        with pytest.raises(compose.ComposeCommandError) as excinfo:
            adapter.remove_exact_resources(
                _exact_project_resources(identity),
                timeout_seconds=STOP_OPERATION_BUDGET_SECONDS,
            )
        assert excinfo.value.code == "STEP_FAILED"
        assert "terminated" in str(excinfo.value).lower()
        assert _argvs(fake_subprocess) == [["docker", "stop", "--time", "60", "postgres-id-0001"]]
