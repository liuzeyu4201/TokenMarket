"""Shared pytest factories for the SF02 local dependency lifecycle (T018/T035).

Isolation guarantees (research Decision 15):

- Synthetic secrets match the contracted ``tm_local_`` grammar but are random
  per call; they are never real credentials.
- Temporary workspaces live below pytest's own temporary base and can never
  point at the developer's repository checkout.
- Test project identities use the disjoint ``tmtest-`` prefix and the
  ``tmtest`` repository label value, so developer-facing discovery/mutation
  (``tokenmarket`` label value and ``tokenmarket-<hash>`` project names) can
  never select them, and test teardown keyed on these exact labels can never
  address a developer project.

T035 adds the disposable real-Compose layer used by the T025 integration and
performance suites:

- :class:`RealComposeProjectFactory` mints unique ``tmtest-<rand>`` project
  identities with exact test labels, dynamically allocated loopback host
  ports, synthetic ``tm_local_`` credentials, synthetic ``.env.local``
  content, and the derived non-secret ``TOKENMARKET_*`` environment builder.
- :class:`NetworkProbeRunner` executes real PostgreSQL/Redis/Grafana protocol
  probes from a short-lived test-only container attached to the exact project
  network; probe material (secrets) reaches the container over STDIN only and
  never appears in argv, environment, inspect output, or retained evidence.
- :class:`PerformanceHarness` is the shared cross-platform deterministic
  harness: predeclared trial counts, per-trial fresh project-scoped volumes,
  monotonic timing, and aggregate statistics (cold batch of 20 with at least
  19 ready within 60 s excluding image timing; ten healthy repeats ≤ 15 s).
- Fixture-only teardown guards: teardown removes only resources carrying the
  fixture's own exact ``tmtest-`` workspace-id plus full fingerprint labels,
  re-verifies labels before every removal, and hard-fails if any selector
  could address ``tokenmarket``/``tokenmarket-*`` developer resources.

TEST-ONLY uncommitted-asset accommodation: ``infra/docker/compose.local.yml``
is not committed in this session, so the adapter's real ``git show HEAD:``
blob reader fails closed. The fixtures inject the adapter's ``git_show`` seam
to return the WORKTREE bytes (see :func:`worktree_compose_git_show`). Every
other part of blob verification stays real: the regular non-symlink file
checks, the byte-equality comparison against the returned blob, and the
verified-bytes-over-stdin transport are unchanged. Remove the seam once the
asset is committed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import socket
import string
import subprocess
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

import pytest

from workflow.cli import execute_dev_guarded
from workflow.local_env.compose import (
    GRAFANA_HOST_PORT_ENV,
    LABEL_REPOSITORY,
    LABEL_WORKSPACE_FINGERPRINT,
    LABEL_WORKSPACE_ID,
    POSTGRES_DB_ENV,
    POSTGRES_HOST_PORT_ENV,
    POSTGRES_USER_ENV,
    REDIS_HOST_PORT_ENV,
    ComposeAdapter,
)
from workflow.local_env.identity import WorkspaceIdentity
from workflow.local_env.lifecycle import (
    AdapterFactory,
    ClockFn,
    LifecycleRunOutcome,
    ProbeFn,
    SleepFn,
    start_local_environment,
)
from workflow.local_env.models import DependencyId, LocalDependencyManifest, load_manifest

SECRET_PREFIX = "tm_local_"
SECRET_GRAMMAR_ALPHABET = string.ascii_letters + string.digits + "_-"
SECRET_MIN_SUFFIX_LENGTH = 32
SECRET_MAX_SUFFIX_LENGTH = 96

DEVELOPER_REPOSITORY_LABEL = "tokenmarket"
TEST_REPOSITORY_LABEL = "tmtest"
TEST_PROJECT_PREFIX = "tmtest-"


def assert_not_developer_project(project_id: str) -> None:
    """Guard: refuse any identity that could select a developer project."""
    if project_id == DEVELOPER_REPOSITORY_LABEL or project_id.startswith(
        f"{DEVELOPER_REPOSITORY_LABEL}-"
    ):
        raise AssertionError(f"test factory must never address a developer project: {project_id!r}")


class SyntheticSecretFactory:
    """Produce values that satisfy the contracted local synthetic-secret grammar."""

    def new(self, length: int = 48) -> str:
        """Return ``tm_local_`` plus ``length`` random grammar-safe characters."""
        if not SECRET_MIN_SUFFIX_LENGTH <= length <= SECRET_MAX_SUFFIX_LENGTH:
            raise ValueError("synthetic secret suffix must stay within the 32..96 grammar")
        suffix = "".join(secrets.choice(SECRET_GRAMMAR_ALPHABET) for _ in range(length))
        return SECRET_PREFIX + suffix


class TemporaryWorkspaceFactory:
    """Create isolated directories that stand in for a canonical workspace root."""

    def __init__(self, base: Path) -> None:
        if (base / ".git").exists():
            raise AssertionError("workspace factory base must not be a real repository checkout")
        self._base = base
        self._count = 0
        self.created: list[Path] = []

    def new(self, name: str = "workspace") -> Path:
        """Create one numbered workspace directory, spaces/non-ASCII names allowed."""
        self._count += 1
        path = self._base / f"{self._count:02d}-{name}"
        path.mkdir(parents=True)
        self.created.append(path)
        return path


class MonotonicClock:
    """Deterministic monotonic clock for deadline and budget tests."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("a monotonic clock cannot move backwards")
        self.now += seconds
        return self.now


@dataclass(frozen=True)
class FakeSubprocessResponse:
    """One predeclared subprocess result."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class FakeSubprocess:
    """Predeclared-response stand-in for ``subprocess.run``.

    Tests queue every expected response up front; an unexpected call fails the
    test instead of ever spawning a real process.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._responses: deque[FakeSubprocessResponse] = deque()

    def queue(self, *, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        """Declare the next expected call's result."""
        self._responses.append(
            FakeSubprocessResponse(stdout=stdout, stderr=stderr, returncode=returncode)
        )

    @property
    def exhausted(self) -> bool:
        """True when every predeclared response has been consumed."""
        return not self._responses

    def run(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Match the ``subprocess.run`` call shape used by the workflow tool."""
        argv = [str(a) for a in args]
        self.calls.append((argv, dict(kwargs)))
        if not self._responses:
            raise AssertionError(f"fake subprocess received an undeclared call: {argv!r}")
        response = self._responses.popleft()
        if kwargs.get("check", False) and response.returncode != 0:
            raise subprocess.CalledProcessError(
                response.returncode, argv, response.stdout, response.stderr
            )
        return subprocess.CompletedProcess(
            argv, response.returncode, response.stdout, response.stderr
        )


@dataclass(frozen=True)
class TestProjectIdentity:
    """Docker-facing identity for disposable, test-labeled resources only."""

    project_id: str
    workspace_fingerprint: str
    labels: Mapping[str, str]


class TestProjectLabelFactory:
    """Project identities that can never address a developer project.

    Developer projects are named ``tokenmarket-<12 hex>`` and discovered via
    the ``com.tokenmarket.repository=tokenmarket`` label value. Test projects
    use the disjoint ``tmtest-`` prefix and ``tmtest`` label value, so exact
    developer mutation and repository-prefix discovery can never select them,
    and fixture teardown keyed on these exact labels is likewise confined.
    """

    def new(self) -> TestProjectIdentity:
        digest = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        project_id = f"{TEST_PROJECT_PREFIX}{digest[:12]}"
        assert_not_developer_project(project_id)
        labels = {
            "com.tokenmarket.repository": TEST_REPOSITORY_LABEL,
            "com.tokenmarket.workspace-id": project_id,
            "com.tokenmarket.workspace-fingerprint": digest,
        }
        return TestProjectIdentity(
            project_id=project_id,
            workspace_fingerprint=digest,
            labels=labels,
        )


@pytest.fixture
def synthetic_secret_factory() -> SyntheticSecretFactory:
    return SyntheticSecretFactory()


@pytest.fixture
def synthetic_secret(synthetic_secret_factory: SyntheticSecretFactory) -> str:
    return synthetic_secret_factory.new()


@pytest.fixture
def workspace_factory(tmp_path: Path) -> TemporaryWorkspaceFactory:
    return TemporaryWorkspaceFactory(tmp_path)


@pytest.fixture
def tmp_workspace(workspace_factory: TemporaryWorkspaceFactory) -> Path:
    return workspace_factory.new()


@pytest.fixture
def monotonic_clock() -> MonotonicClock:
    return MonotonicClock()


@pytest.fixture
def fake_subprocess() -> FakeSubprocess:
    return FakeSubprocess()


@pytest.fixture
def test_project_label_factory() -> TestProjectLabelFactory:
    return TestProjectLabelFactory()


@pytest.fixture
def test_project_identity(
    test_project_label_factory: TestProjectLabelFactory,
) -> TestProjectIdentity:
    return test_project_label_factory.new()


# ---------------------------------------------------------------------------
# T035: disposable real-Compose fixtures and the shared performance harness
#
# Everything below drives the REAL Docker daemon with disposable, exact
# test-labeled Compose projects. Selection and teardown always use the exact
# ``com.tokenmarket.workspace-id=tmtest-<rand>`` project identity plus the
# full workspace fingerprint; no fixture can address ``tokenmarket`` /
# ``tokenmarket-*`` developer resources (hard-asserted).

COMPOSE_ASSET_RELATIVE_PATH = "infra/docker/compose.local.yml"

# Sentinel canonical path for test identities. It is never emitted and never
# matches a real label value; identity hashing itself is irrelevant here
# because the project ID/fingerprint come from the random label factory.
REAL_TEST_CANONICAL_PATH = "/tmtest-real-compose-workspace"

DOCKER_CLI_TIMEOUT_SECONDS = 60.0
TEARDOWN_CLI_TIMEOUT_SECONDS = 30.0
TEARDOWN_RETRY_SECONDS = 20.0
PROBE_CONTAINER_TIMEOUT_SECONDS = 45.0
PREREQUISITE_PULL_TIMEOUT_SECONDS = 600.0

DECLARED_COLD_TRIALS = 20
DECLARED_HEALTHY_REPEATS = 10
COLD_TRIAL_BUDGET_SECONDS = 60.0
REPEAT_BUDGET_SECONDS = 15.0
REQUIRED_COLD_FRACTION = 0.95

_PROBE_OUTPUT_BOUND = 400


def worktree_compose_git_show(repo_root: Path) -> Callable[[str], bytes]:
    """TEST-ONLY ``git_show`` seam: return the WORKTREE compose asset bytes.

    ``infra/docker/compose.local.yml`` is not committed in this session, so
    the adapter's real ``git show HEAD:<path>`` reader fails closed. This seam
    returns the worktree bytes for exactly that one path; every other part of
    the adapter's verification stays real (regular non-symlink file checks,
    byte-equality comparison, verified-bytes-over-stdin transport). Documented
    accommodation, to be removed once the asset is committed.
    """

    def _show(relative_path: str) -> bytes:
        if relative_path != COMPOSE_ASSET_RELATIVE_PATH:
            raise AssertionError(
                f"test git_show seam only serves {COMPOSE_ASSET_RELATIVE_PATH!r}, "
                f"got {relative_path!r}"
            )
        return (repo_root / relative_path).read_bytes()

    return _show


def allocate_loopback_ports(count: int = 3) -> tuple[int, ...]:
    """Allocate distinct, dynamically assigned loopback host ports.

    Each port is reserved through an ephemeral bind and released immediately,
    so test projects never collide with the developer's fixed 5432/6379/3000
    endpoints. The small race before Compose binds the port is exactly what
    the lifecycle's port preflight and bind-race classification handle.
    """
    allocated: set[int] = set()
    while len(allocated) < count:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", 0))
            allocated.add(int(probe.getsockname()[1]))
        finally:
            probe.close()
    return tuple(sorted(allocated))


def build_env_local_text(
    *,
    ports: Mapping[str, int],
    secrets_map: Mapping[str, str],
    username: str,
    database: str,
    redis_db: int = 0,
) -> str:
    """Render synthetic ``.env.local`` content for one disposable project."""
    return (
        "MODE=local\n"
        f"DATABASE_URL=postgresql://{username}:{secrets_map['postgres']}@"
        f"127.0.0.1:{ports['postgres']}/{database}\n"
        f"REDIS_URL=redis://default:{secrets_map['redis']}@"
        f"127.0.0.1:{ports['redis']}/{redis_db}\n"
        f"GRAFANA_URL=http://127.0.0.1:{ports['grafana']}\n"
        f"GRAFANA_ADMIN_PASSWORD={secrets_map['grafana']}\n"
    )


def build_derived_env(project: RealComposeProject) -> dict[str, str]:
    """Build the non-secret derived ``TOKENMARKET_*`` child variables."""
    return {
        POSTGRES_USER_ENV: project.username,
        POSTGRES_DB_ENV: project.database,
        POSTGRES_HOST_PORT_ENV: str(project.ports["postgres"]),
        REDIS_HOST_PORT_ENV: str(project.ports["redis"]),
        GRAFANA_HOST_PORT_ENV: str(project.ports["grafana"]),
    }


@dataclass(frozen=True)
class RealComposeProject:
    """One disposable, exact test-labeled real Compose project definition."""

    identity: WorkspaceIdentity
    runtime_base: Path
    ports: Mapping[str, int]
    secrets_map: Mapping[str, str]
    username: str
    database: str

    @property
    def project_id(self) -> str:
        return self.identity.project_id

    @property
    def workspace_fingerprint(self) -> str:
        return self.identity.workspace_fingerprint

    @property
    def network_name(self) -> str:
        return f"{self.project_id}_default"

    @property
    def volume_names(self) -> tuple[str, str]:
        return (
            f"{self.project_id}_postgres-data",
            f"{self.project_id}_redis-data",
        )

    @property
    def env_local_text(self) -> str:
        return build_env_local_text(
            ports=self.ports,
            secrets_map=self.secrets_map,
            username=self.username,
            database=self.database,
        )

    def env_local_text_with(
        self,
        *,
        postgres_secret: str | None = None,
        redis_secret: str | None = None,
        grafana_secret: str | None = None,
    ) -> str:
        """Render the same project config with selected secrets replaced."""
        secrets_map = dict(self.secrets_map)
        if postgres_secret is not None:
            secrets_map["postgres"] = postgres_secret
        if redis_secret is not None:
            secrets_map["redis"] = redis_secret
        if grafana_secret is not None:
            secrets_map["grafana"] = grafana_secret
        return build_env_local_text(
            ports=self.ports,
            secrets_map=secrets_map,
            username=self.username,
            database=self.database,
        )

    @property
    def derived_env(self) -> Mapping[str, str]:
        return build_derived_env(self)

    def config_reader(self) -> Callable[[], str]:
        return lambda: self.env_local_text


def _docker_cli(
    args: Sequence[str],
    *,
    timeout: float,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded docker CLI call; raw output stays in the result."""
    argv = ["docker", *[str(arg) for arg in args]]
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            input=input_text,
        )
    except FileNotFoundError as exc:
        raise AssertionError(
            "the docker CLI is required for the real-Compose test fixtures"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"docker CLI call {argv[1]!r} exceeded its {timeout}s bound " "and was terminated"
        ) from exc


def _docker_cli_ok(args: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    result = _docker_cli(args, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(
            f"docker CLI call {args[0]!r} failed with exit {result.returncode} "
            "during fixture bookkeeping"
        )
    return result


@dataclass(frozen=True)
class ProjectResourceSnapshot:
    """Sorted exact-label resource identities of one disposable project."""

    containers: tuple[str, ...]
    networks: tuple[str, ...]
    volumes: tuple[str, ...]


class RealComposeProjectFactory:
    """Mint and dispose exact test-labeled real Compose projects.

    Every project uses a unique ``tmtest-<rand>`` identity, dynamically
    allocated loopback ports, synthetic ``tm_local_`` credentials, and a
    synthetic ``.env.local`` rendering. Teardown removes ONLY resources that
    carry the fixture's own exact workspace-id plus full-fingerprint labels,
    re-verified by inspection immediately before each removal.
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        runtime_root: Path,
        secret_factory: SyntheticSecretFactory,
        label_factory: TestProjectLabelFactory,
    ) -> None:
        self._repo_root = repo_root
        self._secret_factory = secret_factory
        self._label_factory = label_factory
        runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(runtime_root, 0o700)
        self._runtime_root = runtime_root
        self._projects: list[RealComposeProject] = []
        self._manifest: LocalDependencyManifest | None = None

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def projects(self) -> tuple[RealComposeProject, ...]:
        return tuple(self._projects)

    def manifest(self) -> LocalDependencyManifest:
        if self._manifest is None:
            self._manifest = load_manifest(
                self._repo_root / "ops" / "workflow" / "local-dependencies.json"
            )
        return self._manifest

    def new(
        self, *, username: str = "tmtestuser", database: str = "tmtestdb"
    ) -> RealComposeProject:
        """Mint one unique disposable project definition (no Docker access)."""
        label_identity = self._label_factory.new()
        identity = WorkspaceIdentity(
            workspace_hash=label_identity.project_id.removeprefix(TEST_PROJECT_PREFIX),
            workspace_fingerprint=label_identity.workspace_fingerprint,
            project_id=label_identity.project_id,
            canonical_path=REAL_TEST_CANONICAL_PATH,
        )
        postgres_port, redis_port, grafana_port = allocate_loopback_ports()
        project = RealComposeProject(
            identity=identity,
            runtime_base=self._runtime_root,
            ports={
                "postgres": postgres_port,
                "redis": redis_port,
                "grafana": grafana_port,
            },
            secrets_map={
                dependency: self._secret_factory.new()
                for dependency in ("postgres", "redis", "grafana")
            },
            username=username,
            database=database,
        )
        self._projects.append(project)
        return project

    def adapter_factory(self, **adapter_overrides: Any) -> AdapterFactory:
        """Real ComposeAdapter factory with the documented git_show seam.

        ``adapter_overrides`` may inject the remaining adapter seams
        (``environ``, ``bind_check``, ``pull_timeout_seconds`` ...) for
        fault-injection tests; the worktree ``git_show`` seam is always
        installed (see :func:`worktree_compose_git_show`).
        """
        repo_root = self._repo_root

        def _factory(
            manifest: LocalDependencyManifest,
            identity: WorkspaceIdentity,
            project_dir: Path,
            _root: Path,
        ) -> ComposeAdapter:
            overrides = dict(adapter_overrides)
            overrides["git_show"] = worktree_compose_git_show(repo_root)
            return ComposeAdapter(
                manifest=manifest,
                identity=identity,
                project_dir=project_dir,
                repo_root=repo_root,
                **overrides,
            )

        return _factory

    async def start(
        self,
        project: RealComposeProject,
        *,
        config_text: str | None = None,
        adapter_factory: AdapterFactory | None = None,
        probe_fn: ProbeFn | None = None,
        clock: ClockFn | None = None,
        sleep: SleepFn | None = None,
    ) -> LifecycleRunOutcome:
        """Drive the real start orchestration for one disposable project."""
        reader: Callable[[], str] = (
            project.config_reader() if config_text is None else (lambda: config_text)
        )
        return await start_local_environment(
            repo_root=self._repo_root,
            identity=project.identity,
            config_reader=reader,
            runtime_base=project.runtime_base,
            adapter_factory=adapter_factory or self.adapter_factory(),
            probe_fn=probe_fn,
            clock=clock,
            sleep=sleep,
        )

    def run_guarded(self, project: RealComposeProject, *, plain: bool = False) -> int:
        """Drive the internal guarded dev dispatch (T032) synchronously."""
        return execute_dev_guarded(
            repo_root=self._repo_root,
            plain=plain,
            identity=project.identity,
            config_reader=project.config_reader(),
            runtime_base=project.runtime_base,
            adapter_factory=self.adapter_factory(),
        )

    # -- exact-label resource accounting and guarded teardown ----------------

    def _owned_ids(self, kind: str, project: RealComposeProject) -> list[str]:
        """List IDs by exact project label, then re-verify every label set."""
        assert_not_developer_project(project.project_id)
        if not project.project_id.startswith(TEST_PROJECT_PREFIX):
            raise AssertionError(
                f"teardown selector must stay {TEST_PROJECT_PREFIX} scoped: "
                f"{project.project_id!r}"
            )
        list_args = {
            "container": [
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                f"label={LABEL_WORKSPACE_ID}={project.project_id}",
            ],
            "network": [
                "network",
                "ls",
                "--no-trunc",
                "-q",
                "--filter",
                f"label={LABEL_WORKSPACE_ID}={project.project_id}",
            ],
            "volume": [
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label={LABEL_WORKSPACE_ID}={project.project_id}",
            ],
        }[kind]
        result = _docker_cli_ok(list_args, timeout=TEARDOWN_CLI_TIMEOUT_SECONDS)
        ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not ids:
            return []
        self._verify_exact_labels(kind, project, ids)
        return ids

    def _verify_exact_labels(
        self, kind: str, project: RealComposeProject, ids: Sequence[str]
    ) -> None:
        inspect_args = {
            "container": ["inspect"],
            "network": ["network", "inspect"],
            "volume": ["volume", "inspect"],
        }[kind]
        result = _docker_cli_ok([*inspect_args, *ids], timeout=TEARDOWN_CLI_TIMEOUT_SECONDS)
        documents: Any = json.loads(result.stdout)
        if not isinstance(documents, list):
            raise AssertionError(f"docker {kind} inspect returned an unexpected shape")
        for document in documents:
            if not isinstance(document, dict):
                raise AssertionError(f"docker {kind} inspect entry is not an object")
            raw_labels: Any = (
                document.get("Config", {}).get("Labels")
                if kind == "container"
                else document.get("Labels")
            )
            if not isinstance(raw_labels, dict):
                raise AssertionError(f"{kind} resource lacks labels; refusing fixture removal")
            if (
                raw_labels.get(LABEL_WORKSPACE_ID) != project.project_id
                or raw_labels.get(LABEL_WORKSPACE_FINGERPRINT) != project.workspace_fingerprint
            ):
                raise AssertionError(
                    f"{kind} resource labels do not match the exact fixture "
                    "identity; refusing removal"
                )

    def snapshot(self, project: RealComposeProject) -> ProjectResourceSnapshot:
        """Capture the sorted exact-label resource identities of one project."""
        return ProjectResourceSnapshot(
            containers=tuple(sorted(self._owned_ids("container", project))),
            networks=tuple(sorted(self._owned_ids("network", project))),
            volumes=tuple(sorted(self._owned_ids("volume", project))),
        )

    def teardown_project(self, project: RealComposeProject) -> None:
        """Remove ONLY resources carrying this project's exact test labels.

        Docker Desktop deregisters containers/networks/ports asynchronously,
        so the removal pass retries briefly; the hard label re-verification
        before every removal never relaxes.
        """
        deadline = time.monotonic() + TEARDOWN_RETRY_SECONDS
        last_error: AssertionError | None = None
        while True:
            try:
                for container_id in self._owned_ids("container", project):
                    _docker_cli_ok(["rm", "-f", container_id], timeout=TEARDOWN_CLI_TIMEOUT_SECONDS)
                for network_id in self._owned_ids("network", project):
                    _docker_cli_ok(
                        ["network", "rm", network_id], timeout=TEARDOWN_CLI_TIMEOUT_SECONDS
                    )
                for volume_name in self._owned_ids("volume", project):
                    _docker_cli_ok(
                        ["volume", "rm", volume_name], timeout=TEARDOWN_CLI_TIMEOUT_SECONDS
                    )
                last_error = None
            except AssertionError as exc:
                last_error = exc
            leftovers = self.snapshot(project)
            if not (leftovers.containers or leftovers.networks or leftovers.volumes):
                if project in self._projects:
                    self._projects.remove(project)
                return
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"fixture teardown left resources behind for "
                    f"{project.project_id}: {leftovers!r} (last error: {last_error})"
                )
            time.sleep(0.5)

    def teardown_all(self) -> None:
        for project in list(self._projects):
            self.teardown_project(project)


def find_tmtest_resources() -> Mapping[str, list[str]]:
    """Read-only sweep for tmtest-named or tmtest-labeled Docker resources.

    This is a proof scan only: it matches the disjoint ``tmtest`` test
    namespace and can never select ``tokenmarket``/``tokenmarket-*``
    developer resources.
    """
    container_names = _docker_cli_ok(
        ["ps", "-a", "--format", "{{.Names}}"], timeout=DOCKER_CLI_TIMEOUT_SECONDS
    ).stdout.split()
    labeled_containers = _docker_cli_ok(
        ["ps", "-aq", "--filter", f"label={LABEL_REPOSITORY}={TEST_REPOSITORY_LABEL}"],
        timeout=DOCKER_CLI_TIMEOUT_SECONDS,
    ).stdout.split()
    network_names = _docker_cli_ok(
        ["network", "ls", "--format", "{{.Name}}"], timeout=DOCKER_CLI_TIMEOUT_SECONDS
    ).stdout.split()
    volume_names = _docker_cli_ok(
        ["volume", "ls", "--format", "{{.Name}}"], timeout=DOCKER_CLI_TIMEOUT_SECONDS
    ).stdout.split()
    return {
        "containers": sorted(
            {name for name in container_names if name.startswith(TEST_PROJECT_PREFIX)}
            | set(labeled_containers)
        ),
        "networks": sorted(name for name in network_names if name.startswith(TEST_PROJECT_PREFIX)),
        "volumes": sorted(name for name in volume_names if name.startswith(TEST_PROJECT_PREFIX)),
    }


def assert_no_tmtest_leftovers() -> None:
    """Hard proof that no tmtest-named/labeled resource survives a suite."""
    leftovers = find_tmtest_resources()
    if any(leftovers.values()):
        raise AssertionError(f"tmtest resources leaked: {leftovers!r}")


@dataclass(frozen=True)
class NetworkProbeEvidence:
    """Bounded, secret-free evidence of one project-network probe."""

    dependency: str
    exit_code: int
    matched: bool
    stdout: str
    stderr: str


class NetworkProbeRunner:
    """Run short-lived test-only probe containers on the exact project network.

    Probe material (credentials) reaches the container process over STDIN
    only: the probe ``argv`` carries no secret, no secret-bearing environment
    variable is set, and ``docker inspect`` of the short-lived container
    therefore exposes nothing. Captured output is asserted secret-free,
    bounded, and never retained beyond the returned evidence record.
    """

    def __init__(self, factory: RealComposeProjectFactory) -> None:
        self._factory = factory

    def _run_script(
        self,
        project: RealComposeProject,
        *,
        dependency: DependencyId,
        script: str,
        secret: str,
        matcher: Callable[[str], bool],
        timeout: float = PROBE_CONTAINER_TIMEOUT_SECONDS,
    ) -> NetworkProbeEvidence:
        assert_not_developer_project(project.project_id)
        image_ref = self._factory.manifest().dependency(dependency).image_ref
        # --entrypoint sh: the postgres/redis entrypoint scripts would also
        # exec a trailing `sh`, but grafana's run script would start a full
        # server instead; an explicit entrypoint keeps all three uniform.
        argv = [
            "run",
            "--rm",
            "-i",
            "--entrypoint",
            "sh",
            "--network",
            project.network_name,
            "--label",
            f"{LABEL_REPOSITORY}={TEST_REPOSITORY_LABEL}",
            "--label",
            f"{LABEL_WORKSPACE_ID}={project.project_id}",
            "--label",
            f"{LABEL_WORKSPACE_FINGERPRINT}={project.workspace_fingerprint}",
            image_ref,
        ]
        if any(secret in arg for arg in argv):
            raise AssertionError("probe secret must never enter container argv")
        result = _docker_cli(argv, timeout=timeout, input_text=script)
        stdout = result.stdout
        stderr = result.stderr
        if secret in stdout or secret in stderr:
            raise AssertionError("probe container output leaked secret material")
        return NetworkProbeEvidence(
            dependency=dependency.value,
            exit_code=result.returncode,
            matched=result.returncode == 0 and matcher(stdout),
            stdout=stdout[-_PROBE_OUTPUT_BOUND:],
            stderr=stderr[-_PROBE_OUTPUT_BOUND:],
        )

    def probe_postgres(
        self, project: RealComposeProject, *, secret: str | None = None
    ) -> NetworkProbeEvidence:
        """Real authenticated ``SELECT 1`` against ``postgres:5432``."""
        password = project.secrets_map["postgres"] if secret is None else secret
        script = (
            f"PGPASSWORD='{password}' psql -h postgres -p 5432 "
            f"-U {project.username} -d {project.database} -tAc 'SELECT 1'\n"
        )
        return self._run_script(
            project,
            dependency=DependencyId.POSTGRES,
            script=script,
            secret=password,
            matcher=lambda out: out.strip() == "1",
        )

    def probe_redis(
        self, project: RealComposeProject, *, secret: str | None = None
    ) -> NetworkProbeEvidence:
        """Real authenticated RESP ``PING`` against ``redis:6379``."""
        password = project.secrets_map["redis"] if secret is None else secret
        script = f"REDISCLI_AUTH='{password}' redis-cli -h redis -p 6379 -n 0 PING\n"
        return self._run_script(
            project,
            dependency=DependencyId.REDIS,
            script=script,
            secret=password,
            matcher=lambda out: "PONG" in out,
        )

    def probe_grafana(
        self, project: RealComposeProject, *, secret: str | None = None
    ) -> NetworkProbeEvidence:
        """Real Grafana health plus administrator-identity HTTP requests."""
        password = project.secrets_map["grafana"] if secret is None else secret
        # busybox base64 wraps at 76 columns; the wrapped newline would make
        # the Authorization header malformed (grafana answers 400), so the
        # script strips it before use.
        script = (
            "set -e\n"
            "wget -q -O /tmp/tmtest-health.json http://grafana:3000/api/health\n"
            f"AUTH=$(printf 'admin:%s' '{password}' | base64 | tr -d '\\n')\n"
            'wget -q -O /tmp/tmtest-user.json --header "Authorization: Basic $AUTH" '
            "http://grafana:3000/api/user\n"
            "cat /tmp/tmtest-health.json\n"
            "cat /tmp/tmtest-user.json\n"
        )

        def _match(out: str) -> bool:
            compact = "".join(out.split())
            return '"database":"ok"' in compact and '"isGrafanaAdmin":true' in compact

        return self._run_script(
            project,
            dependency=DependencyId.GRAFANA,
            script=script,
            secret=password,
            matcher=_match,
        )


def _event_timestamp(event: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))


def readiness_window_seconds(outcome: LifecycleRunOutcome) -> float:
    """Measure the contracted readiness window of one run.

    The lifecycle starts its single 60-second readiness deadline immediately
    after image verification, so the delta between the last ``image-verify``
    event timestamp and the ``final`` event timestamp measures exactly the
    contracted window (reconcile + probes) with image timing excluded.
    """
    verify = [
        _event_timestamp(event)
        for event in outcome.events
        if event["payload"]["phase"] == "image-verify"
    ]
    finals = [
        _event_timestamp(event) for event in outcome.events if event["payload"]["phase"] == "final"
    ]
    if not verify or not finals:
        return outcome.duration_ms / 1000.0
    return max(0.0, (finals[-1] - max(verify)).total_seconds())


@dataclass(frozen=True)
class ColdTrialRecord:
    """One predeclared cold-start trial's accounting record."""

    trial: int
    project_id: str
    status: str
    readiness_seconds: float
    wall_seconds: float
    within_budget: bool
    correlation_id: str


@dataclass(frozen=True)
class ColdBatchReport:
    """Aggregate statistics of one predeclared cold-start trial batch."""

    declared_trials: int
    budget_seconds: float
    records: tuple[ColdTrialRecord, ...]

    @property
    def valid_trials(self) -> int:
        return len(self.records)

    @property
    def within_budget_count(self) -> int:
        return sum(1 for record in self.records if record.within_budget)

    @property
    def required_within_budget(self) -> int:
        return math.ceil(self.declared_trials * REQUIRED_COLD_FRACTION)

    @property
    def accepted(self) -> bool:
        return (
            self.valid_trials == self.declared_trials
            and self.within_budget_count >= self.required_within_budget
        )

    @property
    def slowest_readiness_seconds(self) -> float:
        return max((record.readiness_seconds for record in self.records), default=0.0)

    def summary(self) -> str:
        return (
            f"cold batch: {self.within_budget_count}/{self.valid_trials} trials "
            f"passed within {self.budget_seconds:.0f}s "
            f"(required >= {self.required_within_budget}/{self.declared_trials}; "
            f"slowest readiness window {self.slowest_readiness_seconds:.2f}s)"
        )


@dataclass(frozen=True)
class HealthyRepeatRecord:
    """One healthy repeat-start confirmation record."""

    repeat: int
    wall_seconds: float
    status: str
    pulled: bool
    within_budget: bool


@dataclass(frozen=True)
class HealthyRepeatReport:
    """Aggregate statistics of the ten healthy repeat confirmations."""

    declared_repeats: int
    budget_seconds: float
    snapshot_before: ProjectResourceSnapshot
    snapshot_after: ProjectResourceSnapshot
    records: tuple[HealthyRepeatRecord, ...]

    @property
    def within_budget_count(self) -> int:
        return sum(1 for record in self.records if record.within_budget)

    @property
    def accepted(self) -> bool:
        return (
            len(self.records) == self.declared_repeats
            and self.within_budget_count == self.declared_repeats
            and self.snapshot_before == self.snapshot_after
        )

    @property
    def slowest_wall_seconds(self) -> float:
        return max((record.wall_seconds for record in self.records), default=0.0)

    def summary(self) -> str:
        return (
            f"healthy repeats: {self.within_budget_count}/{len(self.records)} "
            f"within {self.budget_seconds:.0f}s, no pulls, stable resource "
            f"identities (slowest {self.slowest_wall_seconds:.2f}s)"
        )


class PerformanceHarness:
    """Shared deterministic cross-platform performance harness (T035).

    Trial counts are predeclared; every valid trial is counted; each cold
    trial runs in a fresh disposable project (fresh isolated test-owned
    volumes) and is torn down immediately after its measurement. Timing is
    monotonic wall time plus the event-derived readiness window (image
    timing excluded by construction).
    """

    def __init__(self, factory: RealComposeProjectFactory) -> None:
        self._factory = factory

    def ensure_images_present(self) -> None:
        """Prerequisite gate: every reviewed image identity must be local.

        A genuinely missing image is pulled once here, BEFORE any trial
        timing; a prerequisite failure invalidates the batch loudly instead
        of dropping individual slow results.
        """
        for definition in self._factory.manifest().dependencies:
            present = _docker_cli(
                ["image", "inspect", definition.image_ref, "--format", "{{.Id}}"],
                timeout=DOCKER_CLI_TIMEOUT_SECONDS,
            )
            if present.returncode == 0:
                continue
            pulled = _docker_cli(
                ["pull", definition.image_ref],
                timeout=PREREQUISITE_PULL_TIMEOUT_SECONDS,
            )
            if pulled.returncode != 0:
                raise AssertionError(
                    f"prerequisite image unavailable for {definition.id.value}; "
                    "the cold batch is invalid and must be rerun completely"
                )

    async def run_cold_batch(
        self,
        *,
        trials: int = DECLARED_COLD_TRIALS,
        budget_seconds: float = COLD_TRIAL_BUDGET_SECONDS,
    ) -> ColdBatchReport:
        """Run one predeclared cold-trial batch (fresh volumes per trial)."""
        self.ensure_images_present()
        records: list[ColdTrialRecord] = []
        for trial in range(trials):
            project = self._factory.new()
            started = time.monotonic()
            outcome = await self._factory.start(project)
            wall_seconds = time.monotonic() - started
            readiness_seconds = readiness_window_seconds(outcome)
            passed = outcome.status == "PASSED"
            records.append(
                ColdTrialRecord(
                    trial=trial,
                    project_id=project.project_id,
                    status=outcome.status,
                    readiness_seconds=readiness_seconds,
                    wall_seconds=wall_seconds,
                    within_budget=passed and readiness_seconds <= budget_seconds,
                    correlation_id=outcome.correlation_id,
                )
            )
            self._factory.teardown_project(project)
        return ColdBatchReport(
            declared_trials=trials,
            budget_seconds=budget_seconds,
            records=tuple(records),
        )

    async def run_healthy_repeats(
        self,
        project: RealComposeProject,
        *,
        repeats: int = DECLARED_HEALTHY_REPEATS,
        budget_seconds: float = REPEAT_BUDGET_SECONDS,
    ) -> HealthyRepeatReport:
        """Run the predeclared healthy repeat confirmations on one project."""
        before = self._factory.snapshot(project)
        records: list[HealthyRepeatRecord] = []
        for repeat in range(repeats):
            started = time.monotonic()
            outcome = await self._factory.start(project)
            wall_seconds = time.monotonic() - started
            pulled = any(
                "pulled the reviewed pinned image digest" in str(event["payload"]["message"])
                for event in outcome.events
            )
            records.append(
                HealthyRepeatRecord(
                    repeat=repeat,
                    wall_seconds=wall_seconds,
                    status=outcome.status,
                    pulled=pulled,
                    within_budget=(
                        outcome.status == "PASSED" and wall_seconds <= budget_seconds and not pulled
                    ),
                )
            )
        after = self._factory.snapshot(project)
        return HealthyRepeatReport(
            declared_repeats=repeats,
            budget_seconds=budget_seconds,
            snapshot_before=before,
            snapshot_after=after,
            records=tuple(records),
        )


@pytest.fixture
def real_compose_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def real_compose_project_factory(
    real_compose_repo_root: Path,
    tmp_path: Path,
    synthetic_secret_factory: SyntheticSecretFactory,
    test_project_label_factory: TestProjectLabelFactory,
) -> Iterator[RealComposeProjectFactory]:
    """Yield the disposable-project factory; tear down EVERY project after.

    The finalizer removes all resources carrying the fixture's exact test
    labels (even on failure) and then proves the host has zero tmtest
    leftovers.
    """
    factory = RealComposeProjectFactory(
        repo_root=real_compose_repo_root,
        runtime_root=tmp_path / "tmtest-runtime",
        secret_factory=synthetic_secret_factory,
        label_factory=test_project_label_factory,
    )
    yield factory
    factory.teardown_all()
    assert_no_tmtest_leftovers()


@pytest.fixture
def network_probe_runner(
    real_compose_project_factory: RealComposeProjectFactory,
) -> NetworkProbeRunner:
    return NetworkProbeRunner(real_compose_project_factory)


@pytest.fixture
def performance_harness(
    real_compose_project_factory: RealComposeProjectFactory,
) -> PerformanceHarness:
    return PerformanceHarness(real_compose_project_factory)
