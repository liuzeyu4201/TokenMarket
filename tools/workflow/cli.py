"""Repository workflow CLI orchestration.

Provides the command-line interface invoked by the root Makefile. It validates
toolchains, loads the component manifest, executes component actions in order,
and emits JSONL/plain-text step events.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from .events import DiagnosticCode, EventLog, aggregate_status, emit_event, to_jsonl
from .images import image_scan, runtime_smoke
from .manifest import ManifestError, action_binding, load_manifest, validate_all
from .mode import ModeError as ModeSelectionError
from .mode import require_production_approval, validate_mode

if TYPE_CHECKING:
    from .local_env.identity import WorkspaceIdentity
    from .local_env.lifecycle import AdapterFactory, ClockFn, ProbeFn, SleepFn
    from .local_env.models import LocalDependencyManifest


class WorkflowError(Exception):
    """Workflow failure carrying a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _repo_root() -> Path:
    """Return the repository root from the script location."""
    return Path(__file__).resolve().parents[2]


def _event_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize v1 flat events and v2 standard envelopes to common fields."""
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    return event


def _event_duration_ms(event: dict[str, Any]) -> int:
    fields = _event_fields(event)
    try:
        return max(0, int(fields.get("duration_ms") or 0))
    except (TypeError, ValueError):
        return 0


def _print_event(event: dict[str, Any], *, plain: bool = False) -> None:
    """Emit an event as JSONL or plain text."""
    if plain or os.environ.get("NO_COLOR"):
        fields = _event_fields(event)
        print(
            f"[{fields['status']}] {fields['component']} {fields['action']}: "
            f"[{fields['code']}] {fields['message']}"
        )
    else:
        print(to_jsonl(event))


TOOLCHAIN_PROFILE_ENV = "TOKENMARKET_TOOLCHAIN_PROFILE"
KNOWN_TOOLCHAIN_PROFILES = frozenset({"local", "github-actions-ubuntu-24.04"})
HOSTED_TOOLCHAIN_PROFILE = "github-actions-ubuntu-24.04"


def _load_toolchain_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "ops" / "workflow" / "toolchains.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _actual_version(tool: str) -> str | None:
    """Return the installed version of a tool, or None if missing."""
    commands = {
        "go": ["go", "version"],
        "python": ["python3", "--version"],
        "uv": ["uv", "--version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "docker": ["docker", "--version"],
        "golangci-lint": ["golangci-lint", "--version"],
    }
    args = commands.get(tool)
    if args is None:
        return None
    exe = shutil.which(args[0])
    if exe is None:
        return None
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    output = result.stdout + result.stderr
    # Extract the first semver-looking token.
    match = __import__("re").search(r"\d+\.\d+(?:\.\d+)?", output)
    return match.group(0) if match else output.strip().split()[-1]


def resolve_toolchain_profile(
    *,
    profile: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve the toolchain execution profile.

    Priority: explicit ``profile`` argument, then
    ``TOKENMARKET_TOOLCHAIN_PROFILE``, then ``local``.

    ``CI`` / ``GITHUB_ACTIONS`` / ``GITHUB_RUN_ID`` never select a profile;
    they only prove hosted authenticity after an explicit hosted profile is
    chosen.
    """
    if profile is not None and str(profile).strip() != "":
        resolved = str(profile).strip()
    else:
        env = environment if environment is not None else os.environ
        raw = env.get(TOOLCHAIN_PROFILE_ENV, "")
        resolved = raw.strip() if raw else "local"
    if resolved not in KNOWN_TOOLCHAIN_PROFILES:
        raise WorkflowError(
            "INVALID_CONFIG",
            f"unknown toolchain profile {resolved!r}; "
            f"allowed: {sorted(KNOWN_TOOLCHAIN_PROFILES)}",
        )
    return resolved


def _assert_hosted_toolchain_environment(environment: Mapping[str, str]) -> None:
    """Fail closed unless the hosted profile is proven by GitHub Actions facts."""
    if environment.get("GITHUB_ACTIONS") != "true":
        raise WorkflowError(
            "INVALID_CONFIG",
            f"toolchain profile {HOSTED_TOOLCHAIN_PROFILE!r} requires "
            "GITHUB_ACTIONS=true",
        )
    if environment.get("RUNNER_OS") != "Linux":
        raise WorkflowError(
            "INVALID_CONFIG",
            f"toolchain profile {HOSTED_TOOLCHAIN_PROFILE!r} requires "
            "RUNNER_OS=Linux",
        )


def _apply_execution_override(
    *,
    tool_name: str,
    actual: str,
    override: Mapping[str, Any],
    profile: str,
) -> None:
    """Validate an execution_overrides entry (exact-list only)."""
    match = override.get("match")
    if match != "exact-list":
        raise WorkflowError(
            "CONTRACT_DRIFT",
            f"tool {tool_name!r} execution_overrides[{profile!r}].match "
            f"must be 'exact-list', got {match!r}",
        )
    allowed = override.get("allowed_versions")
    if not isinstance(allowed, list) or not allowed:
        raise WorkflowError(
            "CONTRACT_DRIFT",
            f"tool {tool_name!r} execution_overrides[{profile!r}]."
            "allowed_versions must be a non-empty list",
        )
    if not all(isinstance(item, str) and item for item in allowed):
        raise WorkflowError(
            "CONTRACT_DRIFT",
            f"tool {tool_name!r} execution_overrides[{profile!r}]."
            "allowed_versions must contain non-empty strings only",
        )
    if actual not in allowed:
        raise WorkflowError(
            "TOOL_VERSION_UNSUPPORTED",
            f"tool {tool_name!r} version {actual!r} is not in allowed_versions "
            f"{allowed!r} for profile {profile!r}",
        )


def toolchain_check(
    manifest_path: Path,
    *,
    repo_root: Path | None = None,
    profile: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> None:
    """Validate declared tools are present and versions match.

    ``environment`` injects process env for tests; when omitted, ``os.environ``
    is used. Profile resolution never auto-selects from ``CI`` or
    ``GITHUB_ACTIONS``.
    """
    env: Mapping[str, str]
    if environment is not None:
        env = environment
    else:
        env = os.environ

    resolved_profile = resolve_toolchain_profile(profile=profile, environment=env)
    if resolved_profile == HOSTED_TOOLCHAIN_PROFILE:
        _assert_hosted_toolchain_environment(env)

    with manifest_path.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    for tool in manifest.get("tools", []):
        name = tool["tool"]
        expected = tool.get("exact_version", "")
        install_policy = tool.get("install_policy", "system-managed")

        if install_policy in {
            "uv-managed",
            "container-image-digest",
            "github-hosted",
            "github-release-sha",
            "go-install",
        }:
            # These tools are resolved per-component, by container images, by the
            # CI host, or by dedicated release installers; only the integrity
            # reference is validated here.
            pass
        else:
            actual = _actual_version(name)
            if actual is None:
                raise WorkflowError("TOOL_MISSING", f"tool {name!r} is not installed")

            override: Mapping[str, Any] | None = None
            if resolved_profile != "local":
                overrides = tool.get("execution_overrides")
                if isinstance(overrides, dict):
                    candidate = overrides.get(resolved_profile)
                    if isinstance(candidate, dict):
                        override = candidate

            if override is not None:
                _apply_execution_override(
                    tool_name=name,
                    actual=actual,
                    override=override,
                    profile=resolved_profile,
                )
            elif not _version_matches(actual, expected):
                raise WorkflowError(
                    "TOOL_VERSION_UNSUPPORTED",
                    f"tool {name!r} version {actual!r} does not match expected {expected!r}",
                )

        integrity = tool.get("integrity_reference", "")
        if integrity and (
            integrity.startswith("services/") or integrity.startswith("ops/")
        ):
            ref_path = repo_root / integrity if repo_root else _repo_root() / integrity
            if not ref_path.is_file():
                raise WorkflowError(
                    "CONTRACT_DRIFT",
                    f"tool {name!r} integrity reference missing: {integrity}",
                )


def _version_matches(actual: str, expected: str) -> bool:
    """Compare versions loosely; exact match for declared exact_version."""
    return actual == expected or actual.startswith(expected.rsplit(".", 1)[0])


def bootstrap(component_path: Path, *, frozen: bool = True) -> None:
    """Prepare locked project dependencies for a component."""
    if (component_path / "uv.lock").is_file():
        cmd = ["uv", "sync", "--locked"]
        result = subprocess.run(cmd, cwd=component_path, check=False)
        if result.returncode != 0:
            raise WorkflowError("STEP_FAILED", f"uv sync failed in {component_path}")
    elif (component_path / "go.mod").is_file():
        result = subprocess.run(
            ["go", "mod", "download"], cwd=component_path, check=False
        )
        if result.returncode != 0:
            raise WorkflowError(
                "STEP_FAILED", f"go mod download failed in {component_path}"
            )
    elif (component_path / "package-lock.json").is_file():
        cmd = ["npm", "ci"]
        result = subprocess.run(cmd, cwd=component_path, check=False)
        if result.returncode != 0:
            raise WorkflowError("STEP_FAILED", f"npm ci failed in {component_path}")


def resolve_fingerprint(component_path: Path) -> str:
    """Return a deterministic fingerprint of resolved dependencies."""
    if (component_path / "uv.lock").is_file():
        content = (component_path / "uv.lock").read_bytes()
        return __import__("hashlib").sha256(content).hexdigest()[:16]
    if (component_path / "go.sum").is_file():
        content = (component_path / "go.sum").read_bytes()
        return __import__("hashlib").sha256(content).hexdigest()[:16]
    if (component_path / "package-lock.json").is_file():
        content = (component_path / "package-lock.json").read_bytes()
        return __import__("hashlib").sha256(content).hexdigest()[:16]
    return "none"


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def dsn_is_production_shaped(url: str) -> bool:
    """True when a DSN host is not a loopback address."""
    text = (url or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except Exception:
        return True
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    return host not in _LOOPBACK_HOSTS


def bind_test_migration_environment(base: Mapping[str, str]) -> dict[str, str]:
    """mode=test: drop ambient DATABASE_URL and refuse production-shaped DSNs."""
    env = dict(base)
    ambient = env.pop("DATABASE_URL", "")
    if ambient and dsn_is_production_shaped(ambient):
        raise WorkflowError(
            "INVALID_TARGET",
            "mode=test refuses a production-shaped ambient DATABASE_URL before Alembic",
        )
    explicit = (env.get("TOKENMARKET_TEST_DATABASE_URL") or "").strip()
    chosen = explicit or ambient
    if chosen and dsn_is_production_shaped(chosen):
        raise WorkflowError(
            "INVALID_TARGET",
            "mode=test refuses a production-shaped database URL before Alembic",
        )
    if chosen:
        env["DATABASE_URL"] = chosen
    return env


def _local_migration_environment(
    repo_root: Path,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the local migration environment from validated ``.env.local``.

    The ignored file remains the sole source for the local database URL.
    Only ``DATABASE_URL`` is forwarded to migration owners; unrelated local
    secrets are never copied into child environments.
    """
    from .local_env.config import parse_local_environment
    from .local_env.models import DependencyId, LocalEnvironmentError

    path = repo_root / ".env.local"
    if not path.is_file():
        raise WorkflowError(
            "INVALID_CONFIG",
            ".env.local is required for local migration; copy .env.example, "
            "set synthetic local secrets, and retry make migrate",
        )
    try:
        configuration = parse_local_environment(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise WorkflowError(
            "INVALID_CONFIG",
            f".env.local could not be read ({type(exc).__name__})",
        ) from exc
    except LocalEnvironmentError as exc:
        raise WorkflowError(exc.code, exc.message) from exc

    postgres = configuration.connection(DependencyId.POSTGRES)
    database_url = (
        f"{postgres.host_scheme}://{postgres.username}:{postgres.secret}@"
        f"{postgres.host_address}:{postgres.host_port}/{postgres.database}"
    )
    environment = dict(base_env if base_env is not None else os.environ)
    environment["DATABASE_URL"] = database_url
    environment.pop("REDIS_URL", None)
    environment.pop("GRAFANA_ADMIN_PASSWORD", None)
    return environment


def _run_component_action(
    component: dict[str, Any],
    action: str,
    repo_root: Path,
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    """Run a single component action via its Makefile adapter."""
    comp_path = repo_root / component["path"]
    make_path = comp_path / "Makefile"
    if not make_path.is_file():
        raise WorkflowError(
            "COMPONENT_NOT_INITIALIZED",
            f"{component['id']}: Makefile missing at {make_path}",
        )

    child_env = dict(env) if env is not None else os.environ.copy()
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    result = subprocess.run(
        ["make", action],
        cwd=comp_path,
        text=True,
        check=False,
        env=child_env,
    )
    return result.returncode


def execute_action(
    action: str,
    *,
    repo_root: Path,
    mode: str | None = None,
    mode_origin: str = "omitted",
    plain: bool = False,
) -> int:
    """Execute an aggregate action across all required components."""
    run_id = str(uuid.uuid4())
    log = EventLog(run_id=run_id)

    def emit(event: dict[str, Any]) -> None:
        _print_event(event, plain=plain)
        log.events.append(event)

    try:
        if action in ("dev", "dev-down"):
            # T074: public SF02 middleware lifecycle is activated. Real
            # compose reconcile replaces the historical SF02_NOT_READY gate.
            if action == "dev":
                return execute_dev_guarded(
                    repo_root=repo_root,
                    mode=mode,
                    mode_origin=mode_origin,
                    plain=plain,
                )
            return execute_dev_down_guarded(
                repo_root=repo_root,
                mode=mode,
                mode_origin=mode_origin,
                plain=plain,
            )

        if action in ("start", "stop"):
            from .local_stack import start_local, stop_local

            start_scope = (
                (os.environ.get("TOKENMARKET_START_SCOPE") or "all").strip().lower()
            )

            # Port overrides arrive via environment (Makefile exports).
            port_keys = (
                "GATEWAY_HOST_PORT",
                "API_HOST_PORT",
                "BILLING_HOST_PORT",
                "ADMIN_HOST_PORT",
                "FRONTEND_HOST_PORT",
            )
            port_overrides = {k: os.environ.get(k) for k in port_keys}
            restart = os.environ.get("RESTART_PROCESS", "").strip() in {
                "1",
                "true",
                "yes",
            }
            # Operator UX: always emit redacted plain lines for start/stop.
            if action == "start":
                return start_local(
                    repo_root,
                    scope=start_scope,
                    mode=mode,
                    mode_origin=mode_origin,
                    plain=True,
                    port_overrides=port_overrides,
                    restart_process=restart,
                )
            return stop_local(
                repo_root,
                scope=start_scope,
                mode=mode,
                mode_origin=mode_origin,
                plain=True,
            )

        if action in ("deploy", "deploy-down"):
            from .deploy_env import deploy_down, deploy_up

            if action == "deploy":
                return deploy_up(
                    repo_root,
                    mode=mode,
                    mode_origin=mode_origin,
                    plain=plain,
                )
            return deploy_down(
                repo_root,
                mode=mode,
                mode_origin=mode_origin,
                plain=plain,
            )

        action_env: Mapping[str, str] | None = None
        if action == "migrate":
            selection = validate_mode(mode, mode_origin)
            if selection.mode == "prod":
                selection = require_production_approval(selection)
            if selection.mode == "local":
                action_env = _local_migration_environment(repo_root)
            elif selection.mode == "test":
                action_env = bind_test_migration_environment(os.environ)

        manifest_path = repo_root / "ops" / "workflow" / "components.json"
        manifest = load_manifest(manifest_path)
        validate_all(manifest, repo_root)

        log.start(action, "repository", "preflight")
        emit(log.events[-1])
        toolchain_path = repo_root / "ops" / "workflow" / "toolchains.json"
        toolchain_check(toolchain_path, repo_root=repo_root)
        log.finish(action, "repository", "preflight", status="PASSED")
        emit(log.events[-1])

        failed = False
        for component in manifest["components"]:
            try:
                binding = action_binding(component, action)
            except ManifestError:
                continue

            if not binding["required"]:
                continue

            if failed:
                log.skip(
                    action, component["id"], "execution", reason="previous step failed"
                )
                emit(log.events[-1])
                continue

            log.start(action, component["id"], "execution")
            emit(log.events[-1])
            start = time.monotonic()
            rc = _run_component_action(
                component,
                action,
                repo_root,
                env=action_env,
            )
            duration = int((time.monotonic() - start) * 1000)

            if rc == 0:
                log.finish(
                    action,
                    component["id"],
                    "execution",
                    status="PASSED",
                    duration_ms=duration,
                )
            else:
                failed = True
                log.finish(
                    action,
                    component["id"],
                    "execution",
                    status="FAILED",
                    code=DiagnosticCode.STEP_FAILED,
                    duration_ms=duration,
                    message=f"{component['id']} {action} exited with {rc}",
                )
            emit(log.events[-1])

        final = aggregate_status(log.events)
        emit(
            emit_event(
                action=action,
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(final["code"]),
                duration_ms=sum(_event_duration_ms(e) for e in log.events),
                message=f"aggregate {action}: {final}",
                run_id=run_id,
            )
        )
        return 0 if final["status"] == "PASSED" else 1

    except ModeSelectionError as exc:
        log.finish(
            action,
            "repository",
            "preflight",
            status="FAILED",
            code=DiagnosticCode(exc.code),
            message=exc.message,
        )
        emit(log.events[-1])
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action=action,
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(exc.code),
                duration_ms=0,
                message=exc.message,
                run_id=run_id,
            )
        )
        return 1

    except WorkflowError as exc:
        log.finish(
            action,
            "repository",
            "preflight",
            status="FAILED",
            code=DiagnosticCode(exc.code),
            message=exc.message,
        )
        emit(log.events[-1])
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action=action,
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(exc.code),
                duration_ms=0,
                message=exc.message,
                run_id=run_id,
            )
        )
        return 1
    except ManifestError as exc:
        log.finish(
            action,
            "repository",
            "preflight",
            status="FAILED",
            code=DiagnosticCode.CONTRACT_DRIFT,
            message=exc.message,
        )
        emit(log.events[-1])
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action=action,
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode.CONTRACT_DRIFT,
                duration_ms=0,
                message=exc.message,
                run_id=run_id,
            )
        )
        return 1


def _emit_lifecycle_outcome(outcome: Any, *, plain: bool) -> int:
    """Print lifecycle evidence and map status to a process exit code."""
    use_plain = plain or bool(os.environ.get("NO_COLOR"))
    for envelope, line in zip(outcome.events, outcome.plain_lines):
        if use_plain:
            print(line)
        else:
            print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
    return 0 if outcome.status == "PASSED" else 1


def execute_dev_guarded(
    *,
    repo_root: Path,
    mode: str | None = None,
    mode_origin: str = "omitted",
    plain: bool = False,
    workspace_root: Path | None = None,
    identity: WorkspaceIdentity | None = None,
    config_reader: Callable[[], str] | None = None,
    manifest_loader: Callable[[], LocalDependencyManifest] | None = None,
    runtime_base: Path | None = None,
    adapter_factory: AdapterFactory | None = None,
    probe_fn: ProbeFn | None = None,
    clock: ClockFn | None = None,
    sleep: SleepFn | None = None,
) -> int:
    """SF02 ``make dev`` dispatch (T032/T074).

    Public ``execute_action("dev")`` and injectable test seams share this path
    after T074 activation. Tests may still inject adapter/probe/config seams.
    Effective-mode validation inside the lifecycle fails closed
    (``INVALID_MODE``) for any non-local or non-command-line mode origin.
    """
    from .local_env import lifecycle as _lifecycle

    outcome = asyncio.run(
        _lifecycle.start_local_environment(
            repo_root=repo_root,
            mode=mode,
            mode_origin=mode_origin,
            workspace_root=workspace_root,
            identity=identity,
            config_reader=config_reader,
            manifest_loader=manifest_loader,
            runtime_base=runtime_base,
            adapter_factory=adapter_factory,
            probe_fn=probe_fn,
            clock=clock,
            sleep=sleep,
        )
    )
    return _emit_lifecycle_outcome(outcome, plain=plain)


def execute_dev_down_guarded(
    *,
    repo_root: Path,
    mode: str | None = None,
    mode_origin: str = "omitted",
    plain: bool = False,
    workspace_root: Path | None = None,
    identity: WorkspaceIdentity | None = None,
    manifest_loader: Callable[[], LocalDependencyManifest] | None = None,
    runtime_base: Path | None = None,
    adapter_factory: AdapterFactory | None = None,
    clock: ClockFn | None = None,
) -> int:
    """SF02 ``make dev-down`` dispatch (T049/T074).

    Mirrors :func:`execute_dev_guarded` for the stop path. Public
    ``execute_action("dev-down")`` uses this path after T074 activation.
    """
    from .local_env import lifecycle as _lifecycle

    outcome = asyncio.run(
        _lifecycle.stop_local_environment(
            repo_root=repo_root,
            mode=mode,
            mode_origin=mode_origin,
            workspace_root=workspace_root,
            identity=identity,
            manifest_loader=manifest_loader,
            runtime_base=runtime_base,
            adapter_factory=adapter_factory,
            clock=clock,
        )
    )
    return _emit_lifecycle_outcome(outcome, plain=plain)


def _release_candidate_main(argv: Sequence[str], *, repo_root: Path) -> int:
    """Handle ``workflow release-candidate capture|verify`` (not a Make target)."""
    from .release_candidate import CaptureConfig, ReleaseCandidateError, capture, verify

    parser = argparse.ArgumentParser(prog="workflow release-candidate")
    sub = parser.add_subparsers(dest="rc_action", required=True)

    capture_p = sub.add_parser("capture", help="Freeze a release candidate manifest")
    capture_p.add_argument(
        "--increment", required=True, choices=["p1", "p2", "P1", "P2"]
    )
    capture_p.add_argument("--output", required=True, help="Manifest JSON output path")
    capture_p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Testing only: allow capture on a dirty worktree",
    )
    capture_p.add_argument("--semantic-version", default=None)
    capture_p.add_argument(
        "--image-digest",
        action="append",
        default=[],
        metavar="NAME=DIGEST",
        help="Optional OCI digest binding (repeatable)",
    )
    capture_p.add_argument("--frontend-digest", default=None)

    verify_p = sub.add_parser("verify", help="Verify a candidate without rebuilding")
    verify_p.add_argument("--manifest", required=True, help="Path to candidate JSON")
    verify_p.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip commit/evidence-only git checks (fixture tests)",
    )
    verify_p.add_argument(
        "--skip-hash-recheck",
        action="store_true",
        help="Skip lock/contract re-hash (fixture-only manifests)",
    )

    args = parser.parse_args(list(argv))

    try:
        if args.rc_action == "capture":
            digests: dict[str, str] = {}
            for item in args.image_digest or []:
                if "=" not in item:
                    raise ReleaseCandidateError(
                        "INVALID_USAGE",
                        f"image-digest must be NAME=DIGEST, got {item!r}",
                    )
                name, digest = item.split("=", 1)
                digests[name.strip()] = digest.strip()
            result = capture(
                CaptureConfig(
                    increment=str(args.increment).lower(),
                    output=Path(args.output),
                    repo_root=repo_root,
                    require_clean=not args.allow_dirty,
                    semantic_version=args.semantic_version,
                    image_digests=digests or None,
                    frontend_digest=args.frontend_digest,
                )
            )
            print(json.dumps({"status": "captured", **result}, sort_keys=True))
            return 0

        report = verify(
            manifest_path=Path(args.manifest),
            repo_root=repo_root,
            check_git=not args.skip_git,
            check_hashes=not args.skip_hash_recheck,
        )
        print(json.dumps({"status": "verified", **report}, sort_keys=True))
        return 0
    except ReleaseCandidateError as exc:
        print(f"FAILED [{exc.code}] {exc.message}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the workflow CLI."""
    raw = list(argv) if argv is not None else sys.argv[1:]

    # Optional subcommand (not a public Make target): release-candidate capture|verify
    if raw and raw[0] == "release-candidate":
        # Optional --repo-root before/after subcommand tokens.
        repo_root = _repo_root()
        rest = raw[1:]
        if "--repo-root" in rest:
            idx = rest.index("--repo-root")
            if idx + 1 < len(rest):
                repo_root = Path(rest[idx + 1])
                rest = rest[:idx] + rest[idx + 2 :]
        return _release_candidate_main(rest, repo_root=repo_root)

    parser = argparse.ArgumentParser(prog="workflow")
    parser.add_argument(
        "action",
        choices=[
            "help",
            "bootstrap",
            "type-check",
            "toolchain-check",
            "fmt",
            "fmt-check",
            "lint",
            "test",
            "build",
            "migrate",
            "dev",
            "dev-down",
            "start",
            "stop",
            "deploy",
            "deploy-down",
            "migrate-check",
            "migrate-integration-check",
            "security-check",
            "runtime-smoke",
            "image-scan",
        ],
    )
    parser.add_argument("--mode", default=None)
    parser.add_argument("--mode-origin", default="omitted")
    parser.add_argument(
        "--scope",
        default=None,
        help="Local start/stop scope: all|apps (default all)",
    )
    parser.add_argument(
        "--toolchain-profile",
        default=None,
        help=(
            "Toolchain execution profile: local | github-actions-ubuntu-24.04 "
            f"(default: ${TOOLCHAIN_PROFILE_ENV} or local)"
        ),
    )
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(raw)

    # Prefer explicit CLI --scope over environment for local start/stop scope.
    if getattr(args, "scope", None):
        os.environ["TOKENMARKET_START_SCOPE"] = str(args.scope)

    repo_root = Path(args.repo_root) if args.repo_root else _repo_root()

    if args.action == "help":
        print(_HELP_TEXT)
        return 0

    if args.action == "toolchain-check":
        try:
            toolchain_check(
                repo_root / "ops" / "workflow" / "toolchains.json",
                repo_root=repo_root,
                profile=args.toolchain_profile,
            )
            return 0
        except WorkflowError as exc:
            print(f"FAILED [{exc.code}] {exc.message}", file=sys.stderr)
            return 1

    if args.action == "bootstrap":
        # Bootstrap all components that have lockfiles.
        manifest = load_manifest(repo_root / "ops" / "workflow" / "components.json")
        for component in manifest["components"]:
            comp_path = repo_root / component["path"]
            if any(
                (comp_path / f).is_file()
                for f in ("uv.lock", "go.sum", "package-lock.json")
            ):
                bootstrap(comp_path)
        return 0

    if args.action == "migrate-check":
        from .migrations import check_migrations

        log = check_migrations(
            repo_root=repo_root,
            mode=args.mode,
            mode_origin=args.mode_origin,
        )
        for event in log.events:
            _print_event(event, plain=args.plain)
        result = aggregate_status(log.events)
        return 0 if result["status"] == "PASSED" else 1

    if args.action == "migrate-integration-check":
        from .migrations import migrate_integration_check

        log = migrate_integration_check(repo_root)
        for event in log.events:
            _print_event(event, plain=args.plain)
        result = aggregate_status(log.events)
        return 0 if result["status"] == "PASSED" else 1

    if args.action == "security-check":
        from .security import run_security_checks

        try:
            run_security_checks(repo_root)
            return 0
        except RuntimeError as exc:
            print(f"FAILED [SECURITY_SCAN] {exc}", file=sys.stderr)
            return 1

    if args.action == "runtime-smoke":
        events = runtime_smoke(repo_root, plain=args.plain)
        final = aggregate_status(events)
        return 0 if final["status"] == "PASSED" else 1

    if args.action == "image-scan":
        events = image_scan(repo_root, plain=args.plain)
        final = aggregate_status(events)
        return 0 if final["status"] == "PASSED" else 1

    return execute_action(
        args.action,
        repo_root=repo_root,
        mode=args.mode,
        mode_origin=args.mode_origin,
        plain=args.plain,
    )


_HELP_TEXT = """TokenMarket repository workflow

Public targets:
  start                 Start the complete local environment
  stop                  Stop the complete local environment; retain data volumes
  dev, dev-down         Canonical SF02 middleware lifecycle (PostgreSQL/Redis/Grafana)
  deploy, deploy-down   Test/prod full stack (requires mode=test|prod; ADR 003)
  fmt                   Apply repository formatters
  lint                  Run static analysis, type checks and boundary checks
  test                  Run all component tests
  build                 Build five service images and three asset bundles
  migrate               Apply reviewed migrations to selected environment

Support targets:
  bootstrap       Prepare locked project dependencies
  type-check      Run the complete type-check set independently
  toolchain-check Verify declared tool versions

Optional tooling (CLI only — not public Make actions):
  release-candidate capture   Freeze candidate JSON + .sha256 companion
  release-candidate verify    Verify candidate without rebuild

Options:
  scope=apps                 Advanced: operate host app processes only
  mode=local|test|prod       Environment selector for migrate/deploy (start only allows local)
  API_HOST_PORT=…            Override an app host port (middleware uses .env.local)
"""


if __name__ == "__main__":
    raise SystemExit(main())
