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
