"""Release candidate capture/verify (T092 / T098 partial)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from workflow.release_candidate import (
    CaptureConfig,
    ReleaseCandidateError,
    capture,
    companion_path,
    verify,
    write_manifest,
)


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "rc-test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "RC Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    # Minimal tree for hashes
    (root / "services" / "api-service").mkdir(parents=True)
    (root / "services" / "api-service" / "uv.lock").write_text("lock-a\n", encoding="utf-8")
    (root / "services" / "api-service" / "pyproject.toml").write_text(
        '[project]\nname = "api-service"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "shared" / "contracts" / "phone-auth-session" / "v1").mkdir(parents=True)
    (
        root / "shared" / "contracts" / "phone-auth-session" / "v1" / "business-codes.md"
    ).write_text("# codes\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_capture_rejects_dirty_tree(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ReleaseCandidateError) as exc:
        capture(
            CaptureConfig(
                increment="p1",
                output=tmp_path / "out" / "candidate.json",
                repo_root=tmp_path,
                require_clean=True,
            )
        )
    assert exc.value.code == "DIRTY_TREE"


def test_capture_writes_json_and_sha256(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = tmp_path / "evidence" / "candidate-p1.json"
    result = capture(
        CaptureConfig(
            increment="p1",
            output=out,
            repo_root=tmp_path,
            require_clean=True,
            image_digests={"api-service": "sha256:deadbeef"},
            frontend_digest="sha256:cafebabe",
        )
    )
    assert out.is_file()
    assert companion_path(out).is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["increment"] == "p1"
    assert payload["commit_sha"]
    assert payload["source_tree_clean"] is True
    assert "services/api-service/uv.lock" in payload["lock_hashes"]
    assert any("phone-auth-session" in k for k in payload["contract_hashes"])
    assert payload["image_digests"]["api-service"] == "sha256:deadbeef"
    assert payload["frontend_digest"] == "sha256:cafebabe"
    assert result["manifest_sha256"] == companion_path(out).read_text(encoding="utf-8").split()[0]


def test_capture_p2_increment(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = tmp_path / "candidate-p2.json"
    result = capture(
        CaptureConfig(increment="p2", output=out, repo_root=tmp_path, require_clean=True)
    )
    assert result["increment"] == "p2"


def test_verify_succeeds_without_rebuild(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = tmp_path / "candidate.json"
    capture(
        CaptureConfig(
            increment="p1",
            output=out,
            repo_root=tmp_path,
            require_clean=True,
        )
    )
    report = verify(manifest_path=out, repo_root=tmp_path)
    assert report["ok"] is True
    assert report["rebuild_performed"] is False


def test_verify_detects_tampered_manifest(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = tmp_path / "candidate.json"
    capture(
        CaptureConfig(increment="p1", output=out, repo_root=tmp_path, require_clean=True)
    )
    # Tamper JSON without updating companion
    data = json.loads(out.read_text(encoding="utf-8"))
    data["commit_sha"] = "0" * 40
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ReleaseCandidateError) as exc:
        verify(manifest_path=out, repo_root=tmp_path, check_hashes=False)
    assert exc.value.code == "HASH_MISMATCH"


def test_verify_detects_lock_hash_mismatch(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    out = tmp_path / "candidate.json"
    capture(
        CaptureConfig(increment="p1", output=out, repo_root=tmp_path, require_clean=True)
    )
    # Change lock content and amend would change commit; instead rewrite lock only
    # and skip git check — hash recheck must still fail.
    (tmp_path / "services" / "api-service" / "uv.lock").write_text(
        "lock-changed\n", encoding="utf-8"
    )
    with pytest.raises(ReleaseCandidateError) as exc:
        verify(
            manifest_path=out,
            repo_root=tmp_path,
            check_git=False,
            check_hashes=True,
        )
    assert exc.value.code == "LOCK_HASH_MISMATCH"


def test_cli_release_candidate_capture_and_verify(tmp_path: Path) -> None:
    from workflow.cli import main

    _init_git_repo(tmp_path)
    out = tmp_path / "cand.json"
    code = main(
        [
            "release-candidate",
            "capture",
            "--increment",
            "p1",
            "--output",
            str(out),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert out.is_file()
    code = main(
        [
            "release-candidate",
            "verify",
            "--manifest",
            str(out),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert code == 0


def test_write_manifest_companion_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    digest = write_manifest(path, {"hello": "world"})
    assert companion_path(path).read_text(encoding="utf-8").startswith(digest)
