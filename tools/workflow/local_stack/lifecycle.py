"""Orchestrate complete or apps-only local start/stop."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Mapping

from ..local_env.config import parse_local_environment
from ..local_env.identity import ensure_project_runtime_dir, secure_runtime_base, workspace_identity
from ..local_env.lifecycle import start_local_environment, stop_local_environment
from ..local_env.models import DependencyId, LocalEnvironmentError
from .logging_util import StartLog
from .ports import resolve_ports
from .processes import parse_dotenv_text, start_processes, stop_processes
from .scope import LocalScopeError, parse_local_scope


class LocalStackError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_env_mode(mode: str | None, mode_origin: str) -> None:
    """start/stop are local-only; reject test/prod escalation."""
    if mode is None or str(mode).strip() == "":
        return
    normalized = str(mode).strip().lower()
    if normalized != "local":
        raise LocalStackError(
            "INVALID_MODE",
            "make start/stop only allow omitted mode or mode=local "
            f"(got mode={mode!r}); use make deploy mode=test|prod for shared hosts",
        )
    origin = (mode_origin or "omitted").lower().replace("_", " ")
    if origin not in {"command line", "command", "override"}:
        raise LocalStackError(
            "INVALID_MODE",
            "mode=local must come from the Make command line when set",
        )


def _runtime_dir(repo_root: Path) -> Path:
    identity = workspace_identity(repo_root)
    base = secure_runtime_base()
    return ensure_project_runtime_dir(base, identity.project_id)


def _load_local_start_configuration(
    repo_root: Path,
) -> tuple[dict[str, int], dict[str, str]]:
    """Read and validate one immutable ``.env.local`` snapshot per start."""
    path = repo_root / ".env.local"
    if not path.is_file():
        raise LocalStackError(
            "INVALID_CONFIG",
            ".env.local is required; copy .env.example, set synthetic local "
            "secrets, and retry make start",
        )
    try:
        text = path.read_text(encoding="utf-8")
        configuration = parse_local_environment(text)
    except (OSError, UnicodeError) as exc:
        raise LocalStackError(
            "INVALID_CONFIG",
            f".env.local could not be read ({type(exc).__name__})",
        ) from exc
    except LocalEnvironmentError as exc:
        raise LocalStackError(exc.code, exc.message) from exc
    ports = {
        "postgres": configuration.connection(DependencyId.POSTGRES).host_port,
        "redis": configuration.connection(DependencyId.REDIS).host_port,
        "grafana": configuration.connection(DependencyId.GRAFANA).host_port,
    }
    return ports, parse_dotenv_text(text)


def _emit_stack_outcome(outcome: Any, log: StartLog) -> tuple[int, str]:
    """Forward SF02 plain lines / summarize reuse. Returns (rc, diagnostic_code)."""
    reused = False
    code = "DEPENDENCY_NOT_READY"
    for line in getattr(outcome, "plain_lines", []) or []:
        text = str(line)
        lower = text.lower()
        if "already" in lower or "healthy" in lower or "reuse" in lower:
            reused = True
        for token in (
            "INVALID_CONFIG",
            "INVALID_MODE",
            "PORT_CONFLICT",
            "TOOL_MISSING",
            "IMAGE_UNAVAILABLE",
            "OPERATION_IN_PROGRESS",
            "DEPENDENCY_NOT_READY",
        ):
            if token in text:
                code = token
        # Avoid double-printing secrets; lifecycle lines are already redacted.
        log.emit("STACK", text)
    status = getattr(outcome, "status", "FAILED")
    log.emit(
        "STACK",
        "phase=done",
        result=status,
        reused=reused,
    )
    if status == "PASSED":
        return 0, "OK"
    return 1, code


def start_local(
    repo_root: Path,
    *,
    scope: str | None = None,
    mode: str | None = None,
    mode_origin: str = "omitted",
    plain: bool = True,
    port_overrides: Mapping[str, str | int | None] | None = None,
    restart_process: bool = False,
) -> int:
    """Public start orchestration for the complete or apps-only scope."""
    try:
        resolved_scope = parse_local_scope(scope)
        _validate_env_mode(mode, mode_origin)
        middleware_ports, env_local = _load_local_start_configuration(repo_root)
        ports = resolve_ports(
            port_overrides,
            middleware_ports=middleware_ports,
        )
    except LocalScopeError as exc:
        log = StartLog(action="start", scope=str(scope or ""), plain=plain)
        log.emit("FAILED", exc.message, code=exc.code)
        return 1
    except LocalStackError as exc:
        log = StartLog(action="start", scope=str(scope or "all"), plain=plain)
        log.emit("FAILED", exc.message, code=exc.code)
        return 1
    except ValueError as exc:
        log = StartLog(action="start", scope=str(scope or "all"), plain=plain)
        log.emit("FAILED", str(exc), code="INVALID_CONFIG")
        return 1

    log = StartLog(action="start", scope=resolved_scope.value, plain=plain)
    log.emit(
        "STARTED",
        f"start scope={resolved_scope.value}",
        correlation_id=log.correlation_id,
    )
    log.emit(
        "PORTS",
        "resolved host ports",
        postgres=ports.postgres,
        redis=ports.redis,
        grafana=ports.grafana,
        gateway=ports.gateway,
        api=ports.api,
        billing=ports.billing,
        admin=ports.admin,
        frontend=ports.frontend,
    )

    # Environment mode for SF02 lifecycle: omitted or command-line local.
    stack_mode = mode if mode else None
    stack_origin = mode_origin if mode else "omitted"

    if resolved_scope.wants_stack:
        log.emit(
            "STACK",
            "phase=preflight",
            note="SF02 middleware reconcile (reuse if healthy)",
        )
        outcome = asyncio.run(
            start_local_environment(
                repo_root=repo_root,
                mode=stack_mode,
                mode_origin=stack_origin,
            )
        )
        rc, diag = _emit_stack_outcome(outcome, log)
        if rc != 0:
            recovery = (
                "copy .env.example to .env.local and set tm_local_ secrets"
                if diag == "INVALID_CONFIG"
                else "fix Docker / port / auth diagnostics and rerun make start"
            )
            log.emit(
                "FAILED",
                "middleware stack did not become ready",
                code=diag,
                recovery=recovery,
            )
            return rc

    if resolved_scope.wants_process:
        try:
            runtime_dir = _runtime_dir(repo_root)
        except Exception as exc:  # identity/runtime failures
            log.emit("FAILED", f"runtime directory unavailable: {exc}", code="STEP_FAILED")
            return 1
        rc = start_processes(
            repo_root,
            runtime_dir,
            ports,
            log,
            env_local=env_local,
            restart=restart_process,
        )
        if rc != 0:
            return rc

    log.emit(
        "PASSED",
        f"start scope={resolved_scope.value} complete",
        gateway=f"127.0.0.1:{ports.gateway}",
        api=f"127.0.0.1:{ports.api}",
        frontend=f"127.0.0.1:{ports.frontend}",
    )
    return 0


def stop_local(
    repo_root: Path,
    *,
    scope: str | None = None,
    mode: str | None = None,
    mode_origin: str = "omitted",
    plain: bool = True,
) -> int:
    """Public stop orchestration; apps stop before middleware."""
    try:
        resolved_scope = parse_local_scope(scope)
        _validate_env_mode(mode, mode_origin)
    except LocalScopeError as exc:
        log = StartLog(action="stop", scope=str(scope or ""), plain=plain)
        log.emit("FAILED", exc.message, code=exc.code)
        return 1
    except LocalStackError as exc:
        log = StartLog(action="stop", scope=str(scope or "all"), plain=plain)
        log.emit("FAILED", exc.message, code=exc.code)
        return 1

    log = StartLog(action="stop", scope=resolved_scope.value, plain=plain)
    log.emit(
        "STARTED",
        f"stop scope={resolved_scope.value}",
        correlation_id=log.correlation_id,
    )

    stack_mode = mode if mode else None
    stack_origin = mode_origin if mode else "omitted"
    failed = False

    if resolved_scope.wants_process:
        try:
            runtime_dir = _runtime_dir(repo_root)
        except Exception as exc:
            log.emit("FAILED", f"runtime directory unavailable: {exc}", code="STEP_FAILED")
            return 1
        if stop_processes(runtime_dir, log) != 0:
            failed = True

    if resolved_scope.wants_stack:
        log.emit("STACK", "phase=stop", note="SF02 middleware down (volumes retained)")
        outcome = asyncio.run(
            stop_local_environment(
                repo_root=repo_root,
                mode=stack_mode,
                mode_origin=stack_origin,
            )
        )
        rc, _diag = _emit_stack_outcome(outcome, log)
        if rc != 0:
            failed = True

    if failed:
        log.emit(
            "FAILED",
            f"stop scope={resolved_scope.value} completed with errors",
        )
        return 1
    log.emit("PASSED", f"stop scope={resolved_scope.value} complete")
    return 0
