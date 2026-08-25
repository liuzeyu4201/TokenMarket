"""Image build and runtime health smoke contract tests.

T029: verify the five deliverable images (proxy-gateway, api-service,
billing-service, admin-service, frontend) have independent build contexts,
multi-stage Dockerfiles, non-root runtime users, health checks, immutable
tags, and that a runtime smoke test confirms each image starts healthy.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest

from .helpers import find_repo_root, load_json, repo_path, run

IMAGE_DELIVERABLES = {"container-image", "static-site-image"}
HEALTH_ENDPOINTS = {
    "proxy-gateway": "/health/live",
    "api-service": "/health/live",
    "billing-service": "/health/live",
    "admin-service": "/health/live",
    "frontend": "/",
}


def image_delivering_components() -> list[dict]:
    """Return components that declare an image deliverable."""
    manifest = load_json("ops", "workflow", "components.json")
    return [
        component
        for component in manifest["components"]
        if IMAGE_DELIVERABLES.intersection(component.get("deliverables", []))
    ]


def component_path(component: dict) -> Path:
    """Return absolute path to a component directory."""
    return repo_path(component["path"])


def dockerfile_path(component: dict) -> Path:
    """Return absolute path to a component Dockerfile."""
    return component_path(component) / "Dockerfile"


def dockerignore_path(component: dict) -> Path:
    """Return absolute path to a component .dockerignore."""
    return component_path(component) / ".dockerignore"


def read_dockerfile(component: dict) -> str:
    """Read the component Dockerfile; fails clearly if missing."""
    path = dockerfile_path(component)
    assert path.is_file(), f"{component['id']}: Dockerfile missing at {path}"
    return path.read_text(encoding="utf-8")


def test_five_image_components_are_declared() -> None:
    """Exactly five components must deliver container or static-site images."""
    components = image_delivering_components()
    ids = {c["id"] for c in components}
    expected = {
        "proxy-gateway",
        "api-service",
        "billing-service",
        "admin-service",
        "frontend",
    }
    assert ids == expected, f"expected image components {expected}, got {ids}"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_exists(component: dict) -> None:
    """Each image component must have a Dockerfile."""
    assert dockerfile_path(component).is_file()


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerignore_exists(component: dict) -> None:
    """Each image component must exclude unintended files from the build context."""
    assert dockerignore_path(component).is_file()


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_is_multi_stage(component: dict) -> None:
    """Each image must use a multi-stage build (at least two FROM lines)."""
    text = read_dockerfile(component)
    from_lines = [
        line for line in text.splitlines() if re.match(r"^\s*FROM\s+", line, re.IGNORECASE)
    ]
    assert len(from_lines) >= 2, f"{component['id']}: expected multi-stage Dockerfile"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_uses_pinned_base_image(component: dict) -> None:
    """Base images must be pinned by digest or explicit version, never mutable tags."""
    text = read_dockerfile(component)
    from_lines = [
        line for line in text.splitlines() if re.match(r"^\s*FROM\s+", line, re.IGNORECASE)
    ]
    assert from_lines, f"{component['id']}: Dockerfile has no FROM line"
    for line in from_lines:
        image = re.sub(r"^\s*FROM\s+", "", line, flags=re.IGNORECASE).split()[0]
        assert "@sha256:" in image or re.search(
            r":\d+(\.\d+)*(-[a-z0-9]+)?$", image
        ), f"{component['id']}: base image {image!r} is not pinned by digest or explicit version"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_has_non_root_user(component: dict) -> None:
    """Runtime stage must switch to a non-root user."""
    text = read_dockerfile(component)
    user_lines = [
        line for line in text.splitlines() if re.match(r"^\s*USER\s+", line, re.IGNORECASE)
    ]
    assert user_lines, f"{component['id']}: Dockerfile missing USER directive"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_has_health_check(component: dict) -> None:
    """Runtime stage must expose a Docker HEALTHCHECK."""
    text = read_dockerfile(component)
    health_lines = [
        line for line in text.splitlines() if re.match(r"^\s*HEALTHCHECK\s+", line, re.IGNORECASE)
    ]
    assert health_lines, f"{component['id']}: Dockerfile missing HEALTHCHECK directive"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_dockerfile_build_context_is_independent(component: dict) -> None:
    """Dockerfile must not copy files from outside its component directory."""
    text = read_dockerfile(component)
    copy_lines = [
        line for line in text.splitlines() if re.match(r"^\s*COPY\s+", line, re.IGNORECASE)
    ]
    for line in copy_lines:
        # Reject any COPY source that walks up from the build context.
        assert (
            "../" not in line
        ), f"{component['id']}: Dockerfile copies from outside build context: {line.strip()}"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_image_tag_is_immutable(component: dict) -> None:
    """Image tag must include commit SHA or semantic version, never 'latest'."""
    text = read_dockerfile(component)
    assert (
        "latest" not in text.lower()
    ), f"{component['id']}: Dockerfile references mutable 'latest' tag"
    # Also check that the component Makefile does not tag as latest.
    make_path = component_path(component) / "Makefile"
    if make_path.is_file():
        make_text = make_path.read_text(encoding="utf-8")
        assert ":latest" not in make_text, f"{component['id']}: Makefile tags image as latest"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_make_build_produces_image(component: dict) -> None:
    """Component Makefile build target must produce a tagged local image."""
    comp_path = component_path(component)
    make_path = comp_path / "Makefile"
    assert make_path.is_file(), f"{component['id']}: Makefile missing at {make_path}"

    result = run(
        ["make", "build"],
        cwd=comp_path,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"{component['id']}: make build failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"


@pytest.mark.parametrize("component", image_delivering_components(), ids=lambda c: c["id"])
def test_runtime_health_smoke(component: dict) -> None:
    """Built image must start and respond to its health endpoint as a non-root user."""
    comp_path = component_path(component)
    image_tag = f"tokenmarket/{component['id']}:smoke-{int(time.time())}"

    # Build the component image via its Makefile.
    build = run(
        ["make", "build", f"IMAGE_TAG={image_tag}"],
        cwd=comp_path,
        check=False,
    )
    assert build.returncode == 0, (
        f"{component['id']}: make build failed for smoke test\n"
        f"stdout:\n{build.stdout}\nstderr:\n{build.stderr}"
    )

    container_name = f"tm-smoke-{component['id'].replace('-', '_')}"
    port = {
        "proxy-gateway": 8080,
        "api-service": 8000,
        "billing-service": 8001,
        "admin-service": 8002,
        "frontend": 3000,
    }[component["id"]]

    try:
        run_container = run(
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
            ],
            check=False,
        )
        assert run_container.returncode == 0, (
            f"{component['id']}: docker run failed\nstdout:\n{run_container.stdout}\n"
            f"stderr:\n{run_container.stderr}"
        )

        # Wait briefly for the container to start its HTTP listener.
        deadline = time.time() + 30
        health_path = HEALTH_ENDPOINTS[component["id"]]
        last_error = ""
        while time.time() < deadline:
            probe = run(
                ["curl", "-fsS", f"http://127.0.0.1:{port}{health_path}"],
                check=False,
            )
            if probe.returncode == 0:
                break
            last_error = probe.stderr
            time.sleep(0.5)
        else:
            pytest.fail(f"{component['id']}: health endpoint did not respond: {last_error}")

        # Runtime user must be non-root.
        inspect = run(
            ["docker", "inspect", "--format", "{{.Config.User}}", container_name],
            check=False,
        )
        assert inspect.returncode == 0, f"{component['id']}: docker inspect failed"
        runtime_user = inspect.stdout.strip()
        assert (
            runtime_user and runtime_user != "root" and runtime_user != "0"
        ), f"{component['id']}: container runs as root user {runtime_user!r}"
    finally:
        # Best-effort cleanup; do not fail the test if cleanup errors occur.
        subprocess.run(
            ["docker", "stop", "--time", "5", container_name],
            capture_output=True,
        )
        subprocess.run(
            ["docker", "rmi", "-f", image_tag],
            capture_output=True,
        )


# ---------------------------------------------------------------------------
# runtime_smoke orchestration (shared network + deferred cleanup + events)
# ---------------------------------------------------------------------------


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=stderr)


def _fail(stderr: str = "error") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


def test_smoke_network_and_container_names_are_unique_and_safe() -> None:
    from workflow.images import (
        new_smoke_run_token,
        smoke_container_name,
        smoke_network_name,
    )

    a = new_smoke_run_token()
    b = new_smoke_run_token()
    assert a != b
    na, nb = smoke_network_name(a), smoke_network_name(b)
    assert na.startswith("tm-smoke-")
    assert na != nb
    assert re.fullmatch(r"tm-smoke-[a-z0-9]{8,16}", na)
    ca = smoke_container_name(a, "api-service")
    cb = smoke_container_name(a, "frontend")
    assert ca != cb
    assert ca.startswith(f"tm-smoke-{a}-")
    assert "api_service" in ca
    assert re.fullmatch(r"tm-smoke-[a-z0-9]{8,16}-[a-z0-9_]+", ca)


def test_runtime_smoke_uses_shared_network_and_defers_cleanup(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """All docker run share one network; api stays until frontend finishes."""
    from workflow import images as images_mod

    calls: list[list[str]] = []
    components = [
        {"id": "proxy-gateway", "path": "services/proxy-gateway", "deliverables": ["container-image"]},
        {"id": "api-service", "path": "services/api-service", "deliverables": ["container-image"]},
        {"id": "billing-service", "path": "services/billing-service", "deliverables": ["container-image"]},
        {"id": "admin-service", "path": "services/admin-service", "deliverables": ["container-image"]},
        {"id": "frontend", "path": "frontend", "deliverables": ["static-site-image"]},
    ]

    def fake_components(_root: Path) -> list[dict]:
        return components

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        cmd = args
        if cmd[:3] == ["docker", "network", "create"]:
            return _ok(stdout=cmd[3] + "\n")
        if cmd[:2] == ["docker", "inspect"] and "{{.Id}}" in cmd:
            return _ok(stdout="sha256:deadbeef\n")
        if cmd[:2] == ["docker", "run"]:
            return _ok(stdout="cid\n")
        if cmd[0] == "curl":
            return _ok(stdout="ok\n")
        if cmd[:2] == ["docker", "inspect"] and "{{.Config.User}}" in cmd:
            return _ok(stdout="appuser\n")
        if cmd[:2] == ["docker", "stop"] or cmd[:2] == ["docker", "rm"]:
            return _ok()
        if cmd[:3] == ["docker", "network", "rm"]:
            return _ok()
        return _ok()

    monkeypatch.setattr(images_mod, "_image_components", fake_components)
    monkeypatch.setattr(images_mod, "_run", fake_run)
    monkeypatch.setattr(images_mod, "new_smoke_run_token", lambda: "aabbccddeeff")

    events = images_mod.runtime_smoke(find_repo_root(), plain=True)
    out = capsys.readouterr().out

    # Network created once with unique name.
    net_creates = [c for c in calls if c[:3] == ["docker", "network", "create"]]
    assert len(net_creates) == 1
    network = net_creates[0][3]
    assert network == "tm-smoke-aabbccddeeff"

    # All five docker run use the same network and component-id alias.
    runs = [c for c in calls if c[:2] == ["docker", "run"]]
    assert len(runs) == 5
    for run_cmd, comp in zip(runs, components, strict=True):
        assert "--network" in run_cmd
        assert run_cmd[run_cmd.index("--network") + 1] == network
        assert "--network-alias" in run_cmd
        assert run_cmd[run_cmd.index("--network-alias") + 1] == comp["id"]
        assert f"127.0.0.1:{images_mod.EXPOSED_PORTS[comp['id']]}" in " ".join(run_cmd)

    # api-service container must still be running when frontend is started:
    # no stop/rm for api before the last docker run.
    api_name = "tm-smoke-aabbccddeeff-api_service"
    frontend_run_idx = next(
        i for i, c in enumerate(calls) if c[:2] == ["docker", "run"] and "frontend" in " ".join(c)
    )
    early = calls[:frontend_run_idx]
    assert not any(
        c[:2] == ["docker", "stop"] and api_name in c for c in early
    ), "api-service must not be stopped before frontend starts"
    assert not any(c[:2] == ["docker", "rm"] and api_name in c for c in early)

    # Cleanup after all checks: stop/rm each started container + network rm.
    stops = [c for c in calls if c[:2] == ["docker", "stop"]]
    rms = [c for c in calls if c[:2] == ["docker", "rm"]]
    net_rms = [c for c in calls if c[:3] == ["docker", "network", "rm"]]
    assert len(stops) == 5
    assert len(rms) == 5
    assert net_rms == [["docker", "network", "rm", network]]
    # Cleanup only after the last run (index of last run < first stop).
    last_run_idx = max(i for i, c in enumerate(calls) if c[:2] == ["docker", "run"])
    first_stop_idx = min(i for i, c in enumerate(calls) if c[:2] == ["docker", "stop"])
    assert last_run_idx < first_stop_idx

    # curl uses --noproxy '*'
    curls = [c for c in calls if c and c[0] == "curl"]
    assert curls
    for c in curls:
        assert "--noproxy" in c
        assert c[c.index("--noproxy") + 1] == "*"

    # Component terminal events printed in plain mode (no KeyError).
    for comp_id in (c["id"] for c in components):
        assert f"] {comp_id} runtime-smoke:" in out or f"] {comp_id} " in out
        assert "PASSED" in out
    assert "repository" in out
    assert "aggregate" in out.lower() or "runtime-smoke aggregate" in out

    # Aggregate event present and successful.
    statuses = []
    for ev in events:
        payload = ev.get("payload", ev)
        if payload.get("phase") == "aggregate":
            assert payload["status"] == "PASSED"
        if payload.get("status") in ("PASSED", "FAILED", "SKIPPED") and payload.get(
            "component"
        ) != "repository":
            statuses.append(payload["status"])
    assert statuses.count("PASSED") == 5
    assert statuses.count("FAILED") == 0


def test_runtime_smoke_failure_still_cleans_network_and_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflow import images as images_mod

    calls: list[list[str]] = []
    components = [
        {"id": "proxy-gateway", "path": "services/proxy-gateway", "deliverables": ["container-image"]},
        {"id": "api-service", "path": "services/api-service", "deliverables": ["container-image"]},
        {"id": "frontend", "path": "frontend", "deliverables": ["static-site-image"]},
    ]
    run_count = {"n": 0}

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        if args[:3] == ["docker", "network", "create"]:
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Id}}" in args:
            return _ok(stdout="sha256:x\n")
        if args[:2] == ["docker", "run"]:
            run_count["n"] += 1
            # Fail the second container start after first succeeded.
            if run_count["n"] == 2:
                return _fail("boom")
            return _ok(stdout="cid\n")
        if args[0] == "curl":
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Config.User}}" in args:
            return _ok(stdout="appuser\n")
        if args[:2] in (["docker", "stop"], ["docker", "rm"]) or args[:3] == [
            "docker",
            "network",
            "rm",
        ]:
            return _ok()
        return _ok()

    monkeypatch.setattr(images_mod, "_image_components", lambda _r: components)
    monkeypatch.setattr(images_mod, "_run", fake_run)
    monkeypatch.setattr(images_mod, "new_smoke_run_token", lambda: "deadbeefcafe")

    events = images_mod.runtime_smoke(find_repo_root(), plain=False)
    # First passed, second failed, third skipped.
    terminal = [
        e.get("payload", e)
        for e in events
        if e.get("payload", e).get("status") in ("PASSED", "FAILED", "SKIPPED")
        and e.get("payload", e).get("component") != "repository"
    ]
    assert [t["component"] for t in terminal] == [
        "proxy-gateway",
        "api-service",
        "frontend",
    ]
    assert terminal[0]["status"] == "PASSED"
    assert terminal[1]["status"] == "FAILED"
    assert terminal[2]["status"] == "SKIPPED"

    # Cleanup still ran for started containers + network.
    assert any(c[:3] == ["docker", "network", "rm"] for c in calls)
    assert any(c[:2] == ["docker", "stop"] for c in calls)
    # Only resources from this token.
    for c in calls:
        if c[:2] == ["docker", "stop"] or (len(c) >= 3 and c[0:2] == ["docker", "rm"]):
            name = c[-1]
            assert name.startswith("tm-smoke-deadbeefcafe-")
        if c[:3] == ["docker", "network", "rm"]:
            assert c[3] == "tm-smoke-deadbeefcafe"


def test_runtime_smoke_plain_mode_reads_payload_without_keyerror(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from workflow import images as images_mod

    components = [
        {"id": "proxy-gateway", "path": "services/proxy-gateway", "deliverables": ["container-image"]},
    ]

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["docker", "network", "create"]:
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Id}}" in args:
            return _ok(stdout="id\n")
        if args[:2] == ["docker", "run"]:
            return _ok(stdout="cid\n")
        if args[0] == "curl":
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Config.User}}" in args:
            return _ok(stdout="nonroot\n")
        return _ok()

    monkeypatch.setattr(images_mod, "_image_components", lambda _r: components)
    monkeypatch.setattr(images_mod, "_run", fake_run)
    monkeypatch.setattr(images_mod, "new_smoke_run_token", lambda: "plainmode0001")

    images_mod.runtime_smoke(find_repo_root(), plain=True)
    out = capsys.readouterr().out
    assert "KeyError" not in out
    assert "[PASSED] proxy-gateway runtime-smoke:" in out
    assert "[PASSED] repository runtime-smoke:" in out or "[PASSED] repository " in out


def test_image_scan_plain_mode_reads_payload_without_keyerror(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from workflow import images as images_mod

    monkeypatch.setattr(images_mod.shutil, "which", lambda _n: None)
    images_mod.image_scan(find_repo_root(), plain=True)
    out = capsys.readouterr().out
    assert "KeyError" not in out
    assert "FAILED" in out
    assert "repository" in out
    assert "trivy" in out.lower()


def test_trivy_finding_summary_extracts_cve_and_fix_versions() -> None:
    import json

    from workflow.images import _trivy_finding_summary

    payload = json.dumps(
        {
            "Results": [
                {
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2026-1",
                            "PkgName": "openssl",
                            "InstalledVersion": "1.0",
                            "FixedVersion": "1.1",
                        }
                    ]
                }
            ]
        }
    )
    assert _trivy_finding_summary(payload) == "CVE-2026-1:openssl@1.0->1.1"
    assert "not json" in _trivy_finding_summary("this is not json")


def test_runtime_smoke_rejects_root_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from workflow import images as images_mod

    components = [
        {"id": "proxy-gateway", "path": "services/proxy-gateway", "deliverables": ["container-image"]},
    ]

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["docker", "network", "create"]:
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Id}}" in args:
            return _ok(stdout="id\n")
        if args[:2] == ["docker", "run"]:
            return _ok(stdout="cid\n")
        if args[0] == "curl":
            return _ok()
        if args[:2] == ["docker", "inspect"] and "{{.Config.User}}" in args:
            return _ok(stdout="root\n")
        return _ok()

    monkeypatch.setattr(images_mod, "_image_components", lambda _r: components)
    monkeypatch.setattr(images_mod, "_run", fake_run)
    monkeypatch.setattr(images_mod, "new_smoke_run_token", lambda: "rootcheck0001")

    events = images_mod.runtime_smoke(find_repo_root(), plain=False)
    failed = [
        e.get("payload", e)
        for e in events
        if e.get("payload", e).get("status") == "FAILED"
        and e.get("payload", e).get("component") == "proxy-gateway"
    ]
    assert failed
    assert "root" in failed[0]["message"].lower()
