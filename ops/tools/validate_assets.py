"""Validate ops assets and produce a deterministic bundle."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def validate_assets() -> None:
    root = _repo_root()
    for name in ("migrations", "monitoring", "backup", "runbooks"):
        readme = root / "ops" / name / "README.md"
        if not readme.is_file():
            raise ValueError(f"missing ops README: {readme}")

    owners = root / "ops" / "migrations" / "owners.json"
    if not owners.is_file():
        raise ValueError("missing migration owner manifest")

    for name in ("workflow.md", "migrations.md"):
        runbook = root / "ops" / "runbooks" / name
        if not runbook.is_file():
            raise ValueError(f"missing runbook: {runbook}")


def build_archive() -> Path:
    root = _repo_root()
    dist = root / "ops" / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / "ops-assets.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        for name in ("migrations", "monitoring", "backup", "runbooks"):
            path = root / "ops" / name / "README.md"
            tar.add(path, arcname=f"{name}/README.md")
        owners = root / "ops" / "migrations" / "owners.json"
        tar.add(owners, arcname="migrations/owners.json")
        for name in ("workflow.md", "migrations.md"):
            runbook = root / "ops" / "runbooks" / name
            tar.add(runbook, arcname=f"runbooks/{name}")

    return archive


if __name__ == "__main__":
    validate_assets()
    archive = build_archive()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"archive={archive} sha256={digest}")
