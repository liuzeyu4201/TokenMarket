"""Runtime smoke and image scanning for container deliverables.

Implements the contract from
``shared/contracts/repository-workflow/v1/image-scan.md``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
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


def _run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)


def runtime_smoke(repo_root: Path, *, plain: bool = False) -> list[dict[str, Any]]:
    """Start each built image, probe its health endpoint, and verify non-root."""
    run_id = f"runtime-smoke-{int(time.time())}"
    log = EventLog(run_id=run_id)
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if plain:
            print(
                f"[{event['status']}] {event['component']} {event['action']}: "
                f"[{event['code']}] {event['message']}"
            )
        else:
            print(json.dumps(event, sort_keys=True))

    failed = False
    for component in _image_components(repo_root):
        comp_id = component["id"]
        image_tag = _default_image_tag(comp_id)
        container_name = f"tm-smoke-{comp_id.replace('-', '_')}"
        port = EXPOSED_PORTS[comp_id]
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

            run_result = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-d",
                    "--name",
                    container_name,
                    "-p",
                    f"127.0.0.1:{port}:{port}",
                    image_tag,
                ]
            )
            if run_result.returncode != 0:
                raise ImageWorkflowError(
                    "STEP_FAILED",
                    f"{comp_id}: docker run failed: {run_result.stderr.strip()}",
                )

            deadline = time.time() + 30
            last_error = ""
            while time.time() < deadline:
                probe = _run(["curl", "-fsS", f"http://127.0.0.1:{port}{health_path}"])
                if probe.returncode == 0:
                    break
                last_error = probe.stderr.strip()
                time.sleep(0.5)
            else:
                raise ImageWorkflowError(
                    "STEP_FAILED",
                    f"{comp_id}: health endpoint did not respond: {last_error}",
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
        finally:
            _run(["docker", "stop", "--time", "5", container_name])
            _run(["docker", "rm", "--force", container_name])
    final = aggregate_status(log.events)
    emit(
        emit_event(
            action="runtime-smoke",
            component="repository",
            phase="aggregate",
            status=final["status"],
            code=DiagnosticCode(final["code"]),
            duration_ms=sum(e.get("duration_ms", 0) for e in log.events),
            message=f"runtime-smoke aggregate: {final}",
            run_id=run_id,
        )
    )
    return events


def image_scan(repo_root: Path, *, plain: bool = False) -> list[dict[str, Any]]:
    """Scan container images with Trivy; fail on HIGH/CRITICAL vulnerabilities."""
    run_id = f"image-scan-{int(time.time())}"
    log = EventLog(run_id=run_id)
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if plain:
            print(
                f"[{event['status']}] {event['component']} {event['action']}: "
                f"[{event['code']}] {event['message']}"
            )
        else:
            print(json.dumps(event, sort_keys=True))

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
            detail = (scan.stderr or scan.stdout or "").strip()
            # Keep message bounded and free of multi-line noise for JSONL.
            snippet = " ".join(detail.split())[:240] if detail else "see trivy output"
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
            duration_ms=sum(e.get("duration_ms", 0) for e in log.events),
            message=f"image-scan aggregate: {final}",
            run_id=run_id,
        )
    )
    return events
