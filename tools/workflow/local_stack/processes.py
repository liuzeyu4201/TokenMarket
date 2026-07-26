"""Host-process supervisor for local application services (not Compose)."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .logging_util import StartLog
from .ports import PortMap

PROCESS_STATE_NAME = "main-processes.json"
LogFn = Callable[[str, str], None]


@dataclass(frozen=True)
class ServiceSpec:
    """One supervised main process."""

    id: str
    cwd_relative: str
    port: int
    health_path: str | None
    argv: list[str]
    env: dict[str, str] = field(repr=False, compare=False)
    managed_env: dict[str, str] = field(repr=False, compare=False)


def _service_fingerprint(spec: ServiceSpec) -> str:
    """Hash managed process inputs so changed configuration forces a restart."""
    payload = {
        "id": spec.id,
        "cwd": spec.cwd_relative,
        "port": spec.port,
        "health_path": spec.health_path,
        "argv": spec.argv,
        "managed_env": spec.managed_env,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return __import__("hashlib").sha256(encoded).hexdigest()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_live(url: str, timeout: float = 1.5) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def parse_dotenv_text(text: str) -> dict[str, str]:
    """Parse already-validated dotenv text without another filesystem read."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def build_service_specs(
    repo_root: Path,
    ports: PortMap,
    *,
    env_local: Mapping[str, str] | None = None,
) -> list[ServiceSpec]:
    """Return startup specs for the five application processes."""
    env_local = dict(env_local or {})
    database_url = env_local.get("DATABASE_URL", "")
    redis_url = env_local.get("REDIS_URL", "")

    def py_managed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
        managed = dict(extra or {})
        if database_url:
            managed["DATABASE_URL"] = database_url
        if redis_url:
            managed["REDIS_URL"] = redis_url
        return managed

    gateway_managed = {"PORT": str(ports.gateway)}
    api_managed = py_managed_env({"PORT": str(ports.api)})
    cors_origins = env_local.get("CORS_ALLOW_ORIGINS") or os.environ.get("CORS_ALLOW_ORIGINS")
    if cors_origins:
        api_managed["CORS_ALLOW_ORIGINS"] = cors_origins
    billing_managed = py_managed_env({"PORT": str(ports.billing)})
    admin_managed = {"PORT": str(ports.admin)}
    # Same-origin relative `/api` via Vite HTTPS proxy (FR-012a). Never inject a
    # direct API host into VITE_API_BASE_URL — Secure cookies require same origin.
    frontend_managed = {
        "VITE_API_BASE_URL": "",
        "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{ports.api}",
    }

    return [
        ServiceSpec(
            id="proxy-gateway",
            cwd_relative="services/proxy-gateway",
            port=ports.gateway,
            health_path="/health/live",
            argv=["go", "run", "./cmd/gateway"],
            env={**os.environ, **gateway_managed},
            managed_env=gateway_managed,
        ),
        ServiceSpec(
            id="api-service",
            cwd_relative="services/api-service",
            port=ports.api,
            health_path="/health/live",
            argv=[
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports.api),
            ],
            env={**os.environ, **api_managed},
            managed_env=api_managed,
        ),
        ServiceSpec(
            id="billing-service",
            cwd_relative="services/billing-service",
            port=ports.billing,
            health_path="/health/live",
            argv=[
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports.billing),
            ],
            env={**os.environ, **billing_managed},
            managed_env=billing_managed,
        ),
        ServiceSpec(
            id="admin-service",
            cwd_relative="services/admin-service",
            port=ports.admin,
            health_path="/health/live",
            argv=[
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports.admin),
            ],
            env={**os.environ, **admin_managed},
            managed_env=admin_managed,
        ),
        ServiceSpec(
            id="frontend",
            cwd_relative="frontend",
            port=ports.frontend,
            health_path=None,
            argv=[
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports.frontend),
            ],
            env={**os.environ, **frontend_managed},
            managed_env=frontend_managed,
        ),
    ]


def _state_path(runtime_dir: Path) -> Path:
    return runtime_dir / PROCESS_STATE_NAME


def read_state(runtime_dir: Path) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return {"services": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"services": {}}
    if not isinstance(data, dict):
        return {"services": {}}
    services = data.get("services")
    if not isinstance(services, dict):
        data["services"] = {}
    return data


def write_state(runtime_dir: Path, state: dict[str, Any]) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(runtime_dir)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _service_healthy(spec: ServiceSpec) -> bool:
    if not _port_open("127.0.0.1", spec.port):
        return False
    if spec.health_path:
        return _http_live(f"http://127.0.0.1:{spec.port}{spec.health_path}")
    return True


def start_processes(
    repo_root: Path,
    runtime_dir: Path,
    ports: PortMap,
    log: StartLog,
    *,
    env_local: Mapping[str, str] | None = None,
    restart: bool = False,
    ready_timeout_s: float = 45.0,
) -> int:
    """Start or reuse host application processes. Returns 0 on success."""
    specs = build_service_specs(repo_root, ports, env_local=env_local)
    state = read_state(runtime_dir)
    services_state: dict[str, Any] = dict(state.get("services") or {})
    log.emit(
        "PROCESS",
        "phase=plan",
        services=",".join(s.id for s in specs),
        restart=restart,
    )

    failures: list[str] = []
    for spec in specs:
        cwd = repo_root / spec.cwd_relative
        if not cwd.is_dir():
            failures.append(spec.id)
            log.emit("PROCESS", f"service={spec.id} missing cwd", status="FAILED")
            continue

        prev = services_state.get(spec.id) or {}
        prev_pid = int(prev.get("pid") or 0)
        fingerprint = _service_fingerprint(spec)
        previous_fingerprint = str(prev.get("config_fingerprint") or "")
        previous_alive = bool(prev_pid and _pid_alive(prev_pid))
        if (
            not restart
            and previous_alive
            and previous_fingerprint == fingerprint
            and _service_healthy(spec)
        ):
            log.emit(
                "PROCESS",
                f"service={spec.id} action=reuse",
                pid=prev_pid,
                port=spec.port,
                liveness="pass",
            )
            continue

        if previous_alive:
            reason = (
                "forced"
                if restart
                else ("config_changed" if previous_fingerprint != fingerprint else "unhealthy")
            )
            log.emit(
                "PROCESS",
                f"service={spec.id} action=restart",
                pid=prev_pid,
                reason=reason,
            )
            _terminate_pid(prev_pid, log, spec.id)

        if _port_open("127.0.0.1", spec.port):
            # Port held by foreign process — fail closed for this service.
            failures.append(spec.id)
            log.emit(
                "PROCESS",
                f"service={spec.id} action=start",
                status="PORT_CONFLICT",
                port=spec.port,
            )
            continue

        log_dir = runtime_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / f"{spec.id}.stdout.log"
        stderr_path = log_dir / f"{spec.id}.stderr.log"
        stdout_f = open(stdout_path, "ab")  # noqa: SIM115
        stderr_f = open(stderr_path, "ab")  # noqa: SIM115
        try:
            proc = subprocess.Popen(
                spec.argv,
                cwd=str(cwd),
                env=spec.env,
                stdout=stdout_f,
                stderr=stderr_f,
                start_new_session=True,
            )
        except OSError as exc:
            stdout_f.close()
            stderr_f.close()
            failures.append(spec.id)
            log.emit(
                "PROCESS",
                f"service={spec.id} action=start",
                status="FAILED",
                error=type(exc).__name__,
            )
            continue
        finally:
            # Parent keeps files open only via child inheritance; close our fds.
            stdout_f.close()
            stderr_f.close()

        services_state[spec.id] = {
            "pid": proc.pid,
            "port": spec.port,
            "cwd": spec.cwd_relative,
            "config_fingerprint": fingerprint,
        }
        write_state(runtime_dir, {"services": services_state})
        log.emit(
            "PROCESS",
            f"service={spec.id} action=start",
            pid=proc.pid,
            port=spec.port,
            status="spawned",
        )

        deadline = time.monotonic() + ready_timeout_s
        healthy = False
        while time.monotonic() < deadline:
            if not _pid_alive(proc.pid):
                break
            if _service_healthy(spec):
                healthy = True
                break
            time.sleep(0.4)

        if healthy:
            log.emit(
                "PROCESS",
                f"service={spec.id} liveness=pass",
                pid=proc.pid,
                port=spec.port,
                url=(
                    f"http://127.0.0.1:{spec.port}{spec.health_path}"
                    if spec.health_path
                    else f"tcp://127.0.0.1:{spec.port}"
                ),
            )
        else:
            failures.append(spec.id)
            log.emit(
                "PROCESS",
                f"service={spec.id} liveness=fail",
                pid=proc.pid,
                port=spec.port,
                status="APP_NOT_READY",
            )

    write_state(runtime_dir, {"services": services_state})
    if failures:
        log.emit(
            "FAILED",
            "one or more main processes failed",
            failed=",".join(failures),
            code="APP_NOT_READY",
        )
        return 1
    log.emit("PROCESS", "phase=done", result="PASSED")
    return 0


def _terminate_pid(pid: int, log: StartLog, service_id: str) -> None:
    log.emit("PROCESS", f"service={service_id} action=stop", pid=pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def stop_processes(runtime_dir: Path, log: StartLog) -> int:
    """Stop supervised main processes recorded in state. Idempotent."""
    state = read_state(runtime_dir)
    services_state: dict[str, Any] = dict(state.get("services") or {})
    if not services_state:
        log.emit("PROCESS", "phase=done", result="already_stopped")
        return 0

    for service_id, meta in list(services_state.items()):
        pid = int((meta or {}).get("pid") or 0)
        if pid and _pid_alive(pid):
            _terminate_pid(pid, log, service_id)
        else:
            log.emit("PROCESS", f"service={service_id} action=skip", reason="not_running")
        services_state.pop(service_id, None)
        write_state(runtime_dir, {"services": services_state})

    write_state(runtime_dir, {"services": {}})
    log.emit("PROCESS", "phase=done", result="STOPPED")
    return 0
