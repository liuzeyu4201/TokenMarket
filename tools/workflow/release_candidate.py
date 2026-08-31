"""Immutable release-candidate capture/verify (feature 004).

Public CLI surface (not a Make target):

    workflow release-candidate capture --increment p1 --output path.json
    workflow release-candidate verify --manifest path.json

Capture records git commit SHA, clean-tree status, lockfile hashes, and
contract hashes into a JSON manifest plus a sibling ``.sha256`` companion.
Verify re-reads the manifest and companion without rebuilding images or
running ``make build`` / ``make ci``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class ReleaseCandidateError(Exception):
    """Fail-closed capture/verify error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_DEFAULT_LOCK_GLOBS: tuple[str, ...] = (
    "services/api-service/uv.lock",
    "services/billing-service/uv.lock",
    "services/admin-service/uv.lock",
    "tools/workflow/uv.lock",
    "frontend/package-lock.json",
    "services/proxy-gateway/go.sum",
)

_DEFAULT_CONTRACT_ROOTS: tuple[str, ...] = (
    "shared/contracts/phone-auth-session/v1",
    "shared/contracts/user-registration/v1",
    "shared/contracts/repository-workflow/v2",
)

_EVIDENCE_ALLOWLIST_PREFIX = "specs/004-phone-login-session-ui/evidence/"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseCandidateError(
            "GIT_ERROR",
            f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}",
        )
    return result.stdout.strip()


def git_commit_sha(repo_root: Path) -> str:
    return _run_git(repo_root, "rev-parse", "HEAD")


def git_tree_clean(repo_root: Path) -> bool:
    status = _run_git(repo_root, "status", "--porcelain")
    return status == ""


def hash_paths(repo_root: Path, relative_paths: Iterable[str]) -> dict[str, str]:
    """Return sorted map of repo-relative path → sha256 for existing files."""
    out: dict[str, str] = {}
    for rel in relative_paths:
        path = repo_root / rel
        if path.is_file():
            out[rel.replace("\\", "/")] = _sha256_file(path)
    return dict(sorted(out.items()))


def hash_contract_tree(repo_root: Path, roots: Sequence[str]) -> dict[str, str]:
    files: list[str] = []
    for root in roots:
        base = repo_root / root
        if not base.exists():
            continue
        if base.is_file():
            files.append(root)
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                files.append(path.relative_to(repo_root).as_posix())
    return hash_paths(repo_root, files)


def companion_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(manifest_path.suffix + ".sha256")


def write_manifest(manifest_path: Path, payload: Mapping[str, Any]) -> str:
    """Write canonical JSON + sibling .sha256; return hex digest of JSON bytes."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    data = body.encode("utf-8")
    digest = _sha256_bytes(data)
    manifest_path.write_bytes(data)
    companion_path(manifest_path).write_text(f"{digest}  {manifest_path.name}\n", encoding="utf-8")
    return digest


def read_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise ReleaseCandidateError("MANIFEST_MISSING", f"manifest not found: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseCandidateError("MANIFEST_INVALID", f"manifest is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseCandidateError("MANIFEST_INVALID", "manifest root must be an object")
    return payload


def verify_companion(manifest_path: Path) -> str:
    companion = companion_path(manifest_path)
    if not companion.is_file():
        raise ReleaseCandidateError(
            "COMPANION_MISSING",
            f"sha256 companion missing: {companion}",
        )
    recorded = companion.read_text(encoding="utf-8").strip().split()[0]
    actual = _sha256_file(manifest_path)
    if recorded != actual:
        raise ReleaseCandidateError(
            "HASH_MISMATCH",
            "manifest sha256 does not match companion",
        )
    return actual


@dataclass(frozen=True)
class CaptureConfig:
    increment: str
    output: Path
    repo_root: Path
    require_clean: bool = True
    semantic_version: str | None = None
    lock_paths: Sequence[str] = _DEFAULT_LOCK_GLOBS
    contract_roots: Sequence[str] = _DEFAULT_CONTRACT_ROOTS
    image_digests: Mapping[str, str] | None = None
    frontend_digest: str | None = None


def capture(config: CaptureConfig) -> dict[str, Any]:
    """Build and write a release candidate manifest.

    Fails closed on a dirty worktree when ``require_clean`` is true.
    Never runs build or CI.
    """
    increment = config.increment.strip().lower()
    if increment not in {"p1", "p2"}:
        raise ReleaseCandidateError(
            "INVALID_INCREMENT",
            f"increment must be p1 or p2, got {config.increment!r}",
        )

    if config.require_clean and not git_tree_clean(config.repo_root):
        raise ReleaseCandidateError(
            "DIRTY_TREE",
            "worktree is dirty; capture requires a clean source tree",
        )

    commit = git_commit_sha(config.repo_root)
    lock_hashes = hash_paths(config.repo_root, config.lock_paths)
    contract_hashes = hash_contract_tree(config.repo_root, config.contract_roots)

    semantic = config.semantic_version
    if semantic is None:
        # Prefer api-service package version as the auth MVP coordinate.
        pyproject = config.repo_root / "services" / "api-service" / "pyproject.toml"
        semantic = "0.0.0"
        if pyproject.is_file():
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version"):
                    # version = "x.y.z"
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        semantic = parts[1].strip().strip("\"'")
                    break

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": "tokenmarket.release_candidate",
        "increment": increment,
        "commit_sha": commit,
        "semantic_version": semantic,
        "source_tree_clean": True if config.require_clean else git_tree_clean(config.repo_root),
        "lock_hashes": lock_hashes,
        "contract_hashes": contract_hashes,
        "image_digests": dict(config.image_digests or {}),
        "frontend_digest": config.frontend_digest,
        "evidence_allowlist_prefix": _EVIDENCE_ALLOWLIST_PREFIX,
        "notes": {
            "verify_rebuilds": False,
            "capture_rebuilds": False,
        },
    }
    digest = write_manifest(config.output, payload)
    payload_with_digest = dict(payload)
    payload_with_digest["manifest_sha256"] = digest
    return payload_with_digest


def verify(
    *,
    manifest_path: Path,
    repo_root: Path,
    check_git: bool = True,
    check_hashes: bool = True,
) -> dict[str, Any]:
    """Verify an existing candidate without rebuilding.

    Checks companion digest, required fields, optional lock/contract re-hash,
    and that HEAD relative to the recorded commit only differs under the
    evidence allowlist (when git is available).
    """
    payload = read_manifest(manifest_path)
    digest = verify_companion(manifest_path)

    required = (
        "schema_version",
        "kind",
        "increment",
        "commit_sha",
        "lock_hashes",
        "contract_hashes",
    )
    for key in required:
        if key not in payload:
            raise ReleaseCandidateError("MANIFEST_INVALID", f"missing field {key!r}")

    if payload.get("kind") != "tokenmarket.release_candidate":
        raise ReleaseCandidateError("MANIFEST_INVALID", "unexpected kind")

    if check_hashes:
        expected_locks = payload.get("lock_hashes") or {}
        if not isinstance(expected_locks, dict):
            raise ReleaseCandidateError("MANIFEST_INVALID", "lock_hashes must be an object")
        actual_locks = hash_paths(repo_root, expected_locks.keys())
        if actual_locks != expected_locks:
            raise ReleaseCandidateError(
                "LOCK_HASH_MISMATCH",
                "lockfile hashes do not match manifest",
            )
        expected_contracts = payload.get("contract_hashes") or {}
        if not isinstance(expected_contracts, dict):
            raise ReleaseCandidateError("MANIFEST_INVALID", "contract_hashes must be an object")
        actual_contracts = hash_paths(repo_root, expected_contracts.keys())
        if actual_contracts != expected_contracts:
            raise ReleaseCandidateError(
                "CONTRACT_HASH_MISMATCH",
                "contract hashes do not match manifest",
            )

    evidence_only = None
    if check_git:
        recorded = str(payload["commit_sha"])
        head = git_commit_sha(repo_root)
        if head != recorded:
            diff = _run_git(
                repo_root,
                "diff",
                "--name-only",
                f"{recorded}..HEAD",
            )
            changed = [line for line in diff.splitlines() if line.strip()]
            disallowed = [
                p
                for p in changed
                if not p.replace("\\", "/").startswith(_EVIDENCE_ALLOWLIST_PREFIX)
            ]
            if disallowed:
                raise ReleaseCandidateError(
                    "EVIDENCE_ONLY_VIOLATION",
                    "source commit..HEAD has non-evidence changes: " + ", ".join(disallowed[:10]),
                )
            evidence_only = True
        else:
            evidence_only = True

    return {
        "ok": True,
        "manifest_sha256": digest,
        "commit_sha": payload["commit_sha"],
        "increment": payload["increment"],
        "evidence_only_diff": evidence_only,
        "rebuild_performed": False,
    }
