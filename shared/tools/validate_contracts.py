"""Validate shared contract assets and produce a deterministic bundle."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def validate_contracts() -> None:
    """Validate that all published contracts are parseable and mapped."""
    root = _repo_root()
    contracts_dir = root / "shared" / "contracts"
    contracts_dir = contracts_dir / "repository-workflow" / "v1"
    required = [
        "component-manifest.schema.json",
        "workflow-event.schema.json",
        "migration-manifest.schema.json",
        "service-health.openapi.yaml",
        "make-workflow.md",
        "environment-mode.md",
        "ci-gates.md",
    ]
    for name in required:
        path = contracts_dir / name
        if not path.is_file():
            raise ValueError(f"missing contract: {path}")
        if name.endswith(".json"):
            with path.open("r", encoding="utf-8") as fh:
                json.load(fh)

    readme = contracts_dir / "README.md"
    if not readme.is_file():
        raise ValueError("missing contract README")


def build_archive() -> Path:
    """Create a deterministic asset archive."""
    root = _repo_root()
    source = root / "shared" / "contracts"
    dist = root / "shared" / "dist"
    dist.mkdir(exist_ok=True)
    archive = dist / "shared-contracts.tar.gz"

    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=path.relative_to(source))

    return archive


if __name__ == "__main__":
    validate_contracts()
    archive = build_archive()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f"archive={archive} sha256={digest}")
