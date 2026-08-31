"""Runtime smoke and image scanning for container deliverables.

Implements the contract from
``shared/contracts/repository-workflow/v1/image-scan.md``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .events import DiagnosticCode, EventLog, aggregate_status, emit_event
from .manifest import load_manifest

IMAGE_DELIVERABLES = {"container-image", "static-site-image"}

HEALTH_ENDPOINTS = {
    "proxy-gateway": "/health/live",
    "api-service": "/health/live",
    "billing-service": "/health/live",
    "admin-service": "/health/live",
    "frontend": "/",
}

EXPOSED_PORTS = {
    "proxy-gateway": 8080,
    "api-service": 8000,
    "billing-service": 8001,
    "admin-service": 8002,
    "frontend": 3000,
}

# Host publish ports for smoke. Keep off the local SF02 Grafana :3000 and
# other operator loopback bindings so docker run -p does not collide.
SMOKE_HOST_PORTS = {
    "proxy-gateway": 18080,
    "api-service": 18000,
    "billing-service": 18001,
    "admin-service": 18002,
    "frontend": 13000,
}

_SMOKE_GATEWAY_PEPPER = "dev-only-proxy-pepper-not-for-prod"
_SMOKE_SELLER_MATERIAL = "11" * 32
_SMOKE_FINGERPRINT_SECRET = "22" * 32

_SMOKE_TOKEN_RE = re.compile(r"^[a-z0-9]{8,16}$")
_SMOKE_NETWORK_RE = re.compile(r"^tm-smoke-[a-z0-9]{8,16}$")
_SMOKE_CONTAINER_RE = re.compile(r"^tm-smoke-[a-z0-9]{8,16}-[a-z0-9_]+$")


class ImageWorkflowError(Exception):
    """Failure in image smoke or scan with a stable diagnostic code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _image_components(repo_root: Path) -> list[dict[str, Any]]:
    manifest = load_manifest(repo_root / "ops" / "workflow" / "components.json")
    return [
        c
        for c in manifest["components"]
        if IMAGE_DELIVERABLES.intersection(c.get("deliverables", []))
    ]


def _default_image_tag(component_id: str) -> str:
    return f"tokenmarket/{component_id}:0.1.0"


def _smoke_run_flags(repo_root: Path, component_id: str) -> list[str]:
    """Minimum env/mounts so a smoke container can bind and answer liveness."""
    flags: list[str] = []
    if component_id == "proxy-gateway":
        flags.extend(["-e", f"PROXY_AUTH_PEPPER={_SMOKE_GATEWAY_PEPPER}"])
    if component_id in {"api-service", "billing-service", "admin-service"}:
        catalog = repo_root / "shared" / "contracts" / "endpoint-catalog" / "v1" / "catalog.json"
        if catalog.is_file():
            flags.extend(
                [
                    "-e",
                    "TOKENMARKET_ENDPOINT_CATALOG=/catalog.json",
                    "-v",
                    f"{catalog}:/catalog.json:ro",
                ]
            )
    if component_id == "api-service":
        flags.extend(
            [
                "-e",
                f"SELLER_KEY_MATERIAL={_SMOKE_SELLER_MATERIAL}",
                "-e",
                f"SELLER_KEY_FINGERPRINT_SECRET={_SMOKE_FINGERPRINT_SECRET}",
                "-e",
                f"PROXY_AUTH_PEPPER={_SMOKE_GATEWAY_PEPPER}",
                "-e",
                "SELLER_KEY_VERSION=v1",
            ]
        )
    return flags


def _run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def _trivy_finding_summary(payload: str) -> str:
    """Compact HIGH/CRITICAL finding list for workflow events."""
    if not payload:
        return "see trivy output"
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return " ".join(payload.split())[:240]
    findings: list[str] = []
    for result in data.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            vid = str(vuln.get("VulnerabilityID") or "").strip()
            pkg = str(vuln.get("PkgName") or "").strip()
            installed = str(vuln.get("InstalledVersion") or "").strip()
            fixed = str(vuln.get("FixedVersion") or "").strip()
            if not vid:
                continue
            findings.append(f"{vid}:{pkg}@{installed}->{fixed}")
            if len(findings) >= 12:
                break
        if len(findings) >= 12:
            break
    if findings:
        return "; ".join(findings)
    return " ".join(payload.split())[:240]


def new_smoke_run_token() -> str:
    """Return a short unique token for one runtime-smoke run."""
    return uuid.uuid4().hex[:12]


def smoke_network_name(run_token: str) -> str:
    """Build a unique user-defined Docker network name for one smoke run."""
    token = re.sub(r"[^a-z0-9]", "", (run_token or "").lower())
    if not _SMOKE_TOKEN_RE.fullmatch(token):
        raise ImageWorkflowError(
            "STEP_FAILED",
            "smoke run token must be 8–16 lowercase alphanumeric characters",
        )
    name = f"tm-smoke-{token}"
    if not _SMOKE_NETWORK_RE.fullmatch(name):
        raise ImageWorkflowError("STEP_FAILED", f"invalid smoke network name: {name!r}")
    return name


def smoke_container_name(run_token: str, component_id: str) -> str:
    """Build a unique container name scoped to one smoke run and component."""
    token = re.sub(r"[^a-z0-9]", "", (run_token or "").lower())
    if not _SMOKE_TOKEN_RE.fullmatch(token):
        raise ImageWorkflowError(
            "STEP_FAILED",
            "smoke run token must be 8–16 lowercase alphanumeric characters",
        )
    slug = re.sub(r"[^a-z0-9]+", "_", (component_id or "").lower()).strip("_")
    if not slug:
        raise ImageWorkflowError(
            "STEP_FAILED",
            f"component id {component_id!r} cannot form a container name",
        )
    name = f"tm-smoke-{token}-{slug}"
    if not _SMOKE_CONTAINER_RE.fullmatch(name):
        raise ImageWorkflowError("STEP_FAILED", f"invalid smoke container name: {name!r}")
    return name


def _event_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize v2 envelope events (payload) and flat events for plain printing."""
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    return event


def _emit_workflow_event(
    event: dict[str, Any],
    *,
    events: list[dict[str, Any]],
    plain: bool,
) -> None:
    events.append(event)
    if plain:
        fields = _event_fields(event)
        print(
            f"[{fields['status']}] {fields['component']} {fields['action']}: "
            f"[{fields['code']}] {fields['message']}"
        )
    else:
        print(json.dumps(event, sort_keys=True))


def _cleanup_smoke_resources(
    *,
    container_names: list[str],
    network_name: str | None,
    network_created: bool,
) -> None:
    """Best-effort cleanup of this run's containers and network only."""
    for name in container_names:
        if not _SMOKE_CONTAINER_RE.fullmatch(name):
            continue
        _run(["docker", "stop", "--time", "5", name])
        _run(["docker", "rm", "--force", name])
    if network_created and network_name and _SMOKE_NETWORK_RE.fullmatch(network_name):
        _run(["docker", "network", "rm", network_name])


def runtime_smoke(repo_root: Path, *, plain: bool = False) -> list[dict[str, Any]]:
    """Start built images on a shared ephemeral network and probe health.

    All image components share one user-defined Docker network so service DNS
    names (for example frontend → ``api-service``) resolve. Containers stay up
    until every component has been checked; cleanup always runs in ``finally``.
    """
    run_token = new_smoke_run_token()
    run_id = f"runtime-smoke-{run_token}"
    log = EventLog(run_id=run_id)
    events: list[dict[str, Any]] = []
    network_name = smoke_network_name(run_token)
    network_created = False
    started_containers: list[str] = []

    def emit(event: dict[str, Any]) -> None:
        _emit_workflow_event(event, events=events, plain=plain)

    failed = False
    try:
        create_net = _run(["docker", "network", "create", network_name])
        if create_net.returncode != 0:
            detail = (create_net.stderr or create_net.stdout or "").strip()
            raise ImageWorkflowError(
                "STEP_FAILED",
                f"failed to create smoke network {network_name}: {detail[:300]}",
            )
        network_created = True

        for component in _image_components(repo_root):
            comp_id = component["id"]
            image_tag = _default_image_tag(comp_id)
            container_name = smoke_container_name(run_token, comp_id)
            container_port = EXPOSED_PORTS[comp_id]
            host_port = SMOKE_HOST_PORTS[comp_id]
            health_path = HEALTH_ENDPOINTS[comp_id]

            log.start("runtime-smoke", comp_id, "execution")
            try:
                if failed:
                    log.skip(
                        "runtime-smoke",
                        comp_id,
                        "execution",
                        reason="previous smoke failed",
                    )
                    emit(log.events[-1])
                    continue

                # Ensure the image exists; build it if necessary.
                inspect = _run(["docker", "inspect", "--format", "{{.Id}}", image_tag])
                if inspect.returncode != 0:
                    build = _run(
                        ["make", "build", f"IMAGE_TAG={image_tag}"],
                        cwd=repo_root / component["path"],
                    )
                    if build.returncode != 0:
                        raise ImageWorkflowError(
                            "STEP_FAILED",
                            f"{comp_id}: image build failed before smoke",
                        )

                run_cmd = [
                    "docker",
                    "run",
                    "--rm",
                    "-d",
                    "--name",
                    container_name,
                    "--network",
                    network_name,
                    "--network-alias",
                    comp_id,
                    "-p",
                    f"127.0.0.1:{host_port}:{container_port}",
                ]
                run_cmd.extend(_smoke_run_flags(repo_root, comp_id))
                run_cmd.append(image_tag)
                run_result = _run(run_cmd)
                if run_result.returncode != 0:
                    raise ImageWorkflowError(
                        "STEP_FAILED",
                        f"{comp_id}: docker run failed: {run_result.stderr.strip()}",
                    )
                started_containers.append(container_name)

                deadline = time.time() + 30
                last_error = ""
                while time.time() < deadline:
                    probe = _run(
                        [
                            "curl",
                            "--noproxy",
                            "*",
                            "-fsS",
                            f"http://127.0.0.1:{host_port}{health_path}",
                        ]
                    )
                    if probe.returncode == 0:
                        break
                    last_error = probe.stderr.strip()
                    time.sleep(0.5)
                else:
                    logs = _run(["docker", "logs", "--tail", "30", container_name])
                    log_text = ((logs.stderr or "") + (logs.stdout or "")).strip()
                    detail = last_error
                    if log_text:
                        detail = f"{last_error}; container logs: {log_text[-800:]}"
                    raise ImageWorkflowError(
                        "STEP_FAILED",
                        f"{comp_id}: health endpoint did not respond: {detail}",
                    )

                inspect = _run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.Config.User}}",
                        container_name,
                    ]
                )
                if inspect.returncode != 0:
                    raise ImageWorkflowError(
                        "STEP_FAILED",
                        f"{comp_id}: docker inspect failed: {inspect.stderr.strip()}",
                    )
                user = inspect.stdout.strip()
                if not user or user in ("root", "0"):
                    raise ImageWorkflowError(
                        "STEP_FAILED",
                        f"{comp_id}: container runs as root user {user!r}",
                    )

                log.finish(
                    "runtime-smoke",
                    comp_id,
                    "execution",
                    status="PASSED",
                    message=f"{comp_id} healthy at {image_tag}",
                )
                emit(log.events[-1])
            except ImageWorkflowError as exc:
                failed = True
                log.finish(
                    "runtime-smoke",
                    comp_id,
                    "execution",
                    status="FAILED",
                    code=DiagnosticCode(exc.code),
                    message=exc.message,
                )
                emit(log.events[-1])

        # Aggregate uses the full log (including STARTED); emit only terminal
        # component events above, then the repository aggregate.
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action="runtime-smoke",
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(final["code"]),
                duration_ms=sum(int(_event_fields(e).get("duration_ms") or 0) for e in log.events),
                message=f"runtime-smoke aggregate: {final}",
                run_id=run_id,
            )
        )
    except ImageWorkflowError as exc:
        # Network create (or other pre-loop) failure: emit a repository FAILED.
        log.finish(
            "runtime-smoke",
            "repository",
            "execution",
            status="FAILED",
            code=DiagnosticCode(exc.code),
            message=exc.message,
        )
        emit(log.events[-1])
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action="runtime-smoke",
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(final["code"]),
                duration_ms=0,
                message=f"runtime-smoke aggregate: {final}",
                run_id=run_id,
            )
        )
    finally:
        # Never let cleanup errors mask the smoke outcome already recorded.
        try:
            _cleanup_smoke_resources(
                container_names=list(started_containers),
                network_name=network_name,
                network_created=network_created,
            )
        except Exception:  # noqa: BLE001 — cleanup must not override smoke failure
            pass

    return events


def image_scan(repo_root: Path, *, plain: bool = False) -> list[dict[str, Any]]:
    """Scan container images with Trivy; fail on HIGH/CRITICAL vulnerabilities."""
    run_id = f"image-scan-{int(time.time())}"
    log = EventLog(run_id=run_id)
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        _emit_workflow_event(event, events=events, plain=plain)

    trivy = shutil.which("trivy")
    if trivy is None:
        log.finish(
            "image-scan",
            "repository",
            "preflight",
            status="FAILED",
            code=DiagnosticCode.TOOL_MISSING,
            message="trivy is not installed; image scan cannot run",
        )
        emit(log.events[-1])
        final = aggregate_status(log.events)
        emit(
            emit_event(
                action="image-scan",
                component="repository",
                phase="aggregate",
                status=final["status"],
                code=DiagnosticCode(final["code"]),
                duration_ms=0,
                message="trivy is not installed; image scan cannot run",
                run_id=run_id,
            )
        )
        return events

    failed = False
    for component in _image_components(repo_root):
        comp_id = component["id"]
        image_tag = _default_image_tag(comp_id)
        log.start("image-scan", comp_id, "execution")
        emit(log.events[-1])
        if failed:
            log.skip(
                "image-scan",
                comp_id,
                "execution",
                reason="previous scan failed",
            )
            emit(log.events[-1])
            continue

        # Fail only on HIGH/CRITICAL findings that have a published fix. Base-image
        # packages with no available fix remain visible via local trivy runs but
        # do not block the SF01/SF02 scaffold gate (fail-closed still applies to
        # fixable application and OS packages).
        scan = _run(
            [
                trivy,
                "image",
                "--severity",
                "HIGH,CRITICAL",
                "--exit-code",
                "1",
                "--scanners",
                "vuln",
                "--ignore-unfixed",
                "--skip-db-update",
                "--timeout",
                "5m",
                "--format",
                "json",
                image_tag,
            ]
        )
        if scan.returncode == 0:
            log.finish(
                "image-scan",
                comp_id,
                "execution",
                status="PASSED",
                message=f"{comp_id} no HIGH/CRITICAL vulnerabilities",
            )
            emit(log.events[-1])
        else:
            failed = True
            detail = (scan.stdout or scan.stderr or "").strip()
            snippet = _trivy_finding_summary(detail)
            log.finish(
                "image-scan",
                comp_id,
                "execution",
                status="FAILED",
                code=DiagnosticCode.STEP_FAILED,
                message=(
                    f"{comp_id} image scan found HIGH/CRITICAL issues for "
                    f"{image_tag}: {snippet}"
                ),
            )
            emit(log.events[-1])

    final = aggregate_status(log.events)
    emit(
        emit_event(
            action="image-scan",
            component="repository",
            phase="aggregate",
            status=final["status"],
            code=DiagnosticCode(final["code"]),
            duration_ms=sum(int(_event_fields(e).get("duration_ms") or 0) for e in log.events),
            message=f"image-scan aggregate: {final}",
            run_id=run_id,
        )
    )
    return events
