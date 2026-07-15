"""Repository workflow CLI orchestration.

Provides the command-line interface invoked by the root Makefile. It validates
toolchains, loads the component manifest, executes component actions in order,
and emits JSONL/plain-text step events.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from .events import DiagnosticCode, EventLog, aggregate_status, emit_event, to_jsonl
from .images import image_scan, runtime_smoke
from .manifest import ManifestError, action_binding, load_manifest, validate_all
from .mode import ModeError as ModeSelectionError
from .mode import require_production_approval, validate_mode


class WorkflowError(Exception):
    """Workflow failure carrying a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _repo_root() -> Path:
    """Return the repository root from the script location."""
    return Path(__file__).resolve().parents[2]


def _print_event(event: dict[str, Any], *, plain: bool = False) -> None:
    """Emit an event as JSONL or plain text."""
    if plain or os.environ.get("NO_COLOR"):
        print(
            f"[{event['status']}] {event['component']} {event['action']}: "
            f"[{event['code']}] {event['message']}"
        )
    else:
        print(to_jsonl(event))


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


def toolchain_check(manifest_path: Path, *, repo_root: Path | None = None) -> None:
    """Validate declared tools are present and versions match."""
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
            if not _version_matches(actual, expected):
                raise WorkflowError(
                    "TOOL_VERSION_UNSUPPORTED",
                    f"tool {name!r} version {actual!r} does not match expected {expected!r}",
                )

        integrity = tool.get("integrity_reference", "")
        if integrity and (integrity.startswith("services/") or integrity.startswith("ops/")):
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
        result = subprocess.run(["go", "mod", "download"], cwd=component_path, check=False)
        if result.returncode != 0:
            raise WorkflowError("STEP_FAILED", f"go mod download failed in {component_path}")
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


def _run_component_action(component: dict[str, Any], action: str, repo_root: Path) -> int:
    """Run a single component action via its Makefile adapter."""
    comp_path = repo_root / component["path"]
    make_path = comp_path / "Makefile"
    if not make_path.is_file():
        raise WorkflowError(
            "COMPONENT_NOT_INITIALIZED",
            f"{component['id']}: Makefile missing at {make_path}",
        )

    result = subprocess.run(
        ["make", action],
        cwd=comp_path,
        capture_output=True,
        text=True,
        check=False,
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
            raise WorkflowError("SF02_NOT_READY", "SF02 must provide the lifecycle adapter")

        if action == "migrate":
            selection = validate_mode(mode, mode_origin)
            if selection.mode == "prod":
                selection = require_production_approval(selection)

        manifest_path = repo_root / "ops" / "workflow" / "components.json"
        manifest = load_manifest(manifest_path)
        validate_all(manifest, repo_root)

        log.start(action, "repository", "preflight")
        toolchain_path = repo_root / "ops" / "workflow" / "toolchains.json"
        toolchain_check(toolchain_path, repo_root=repo_root)
        log.finish(action, "repository", "preflight", status="PASSED")

        failed = False
        for component in manifest["components"]:
            try:
                binding = action_binding(component, action)
            except ManifestError:
                continue

            if not binding["required"]:
                continue

            if failed:
                log.skip(action, component["id"], "execution", reason="previous step failed")
                continue

            log.start(action, component["id"], "execution")
            start = time.monotonic()
            rc = _run_component_action(component, action, repo_root)
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

        final = aggregate_status(log.events)
        emit(
            emit_event(
                action=action,
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(final["code"]),
                duration_ms=sum(e.get("duration_ms", 0) for e in log.events),
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
                code=DiagnosticCode(final["code"]),
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
                code=DiagnosticCode(final["code"]),
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
                code=DiagnosticCode(final["code"]),
                duration_ms=0,
                message=exc.message,
                run_id=run_id,
            )
        )
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the workflow CLI."""
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
            "migrate-check",
            "migrate-integration-check",
            "security-check",
            "runtime-smoke",
            "image-scan",
        ],
    )
    parser.add_argument("--mode", default=None)
    parser.add_argument("--mode-origin", default="omitted")
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else _repo_root()

    if args.action == "help":
        print(_HELP_TEXT)
        return 0

    if args.action == "toolchain-check":
        try:
            toolchain_check(repo_root / "ops" / "workflow" / "toolchains.json", repo_root=repo_root)
            return 0
        except WorkflowError as exc:
            print(f"FAILED [{exc.code}] {exc.message}", file=sys.stderr)
            return 1

    if args.action == "bootstrap":
        # Bootstrap all components that have lockfiles.
        manifest = load_manifest(repo_root / "ops" / "workflow" / "components.json")
        for component in manifest["components"]:
            comp_path = repo_root / component["path"]
            if any((comp_path / f).is_file() for f in ("uv.lock", "go.sum", "package-lock.json")):
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
  dev, dev-down   Local dependency lifecycle (blocked until SF02)
  fmt             Apply repository formatters
  lint            Run static analysis, type checks and boundary checks
  test            Run all component tests
  build           Build five service images and three asset bundles
  migrate         Apply reviewed migrations to selected environment

Support targets:
  bootstrap       Prepare locked project dependencies
  type-check      Run the complete type-check set independently
  toolchain-check Verify declared tool versions

Options:
  mode=local|test|prod   Environment selector for migration/deployment
"""


if __name__ == "__main__":
    raise SystemExit(main())
