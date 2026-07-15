"""Validate infra assets and produce a deterministic bundle."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def validate_assets() -> None:
    root = _repo_root()
    for name in ("docker", "nginx", "grafana", "kafka"):
        readme = root / "infra" / name / "README.md"
        if not readme.is_file():
            raise ValueError(f"missing infra README: {readme}")


def build_archive() -> Path:
    root = _repo_root()
    dist = root / "infra" / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / "infra-assets.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        for name in ("docker", "nginx", "grafana", "kafka"):
            path = root / "infra" / name / "README.md"
            tar.add(path, arcname=f"{name}/README.md")

    return archive


if __name__ == "__main__":
    validate_assets()
    archive = build_archive()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"archive={archive} sha256={digest}")
