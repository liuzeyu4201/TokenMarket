"""Canonical identity, secure runtime directory, and lock tests (T012).

Covers the identity/lock rules of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
and research Decisions 5 and 8: canonical physical-path hashing with NFC/UTF-8
normalization (spaces, non-ASCII, symlink resolution, no case folding),
short-hash collision fail-closed ownership, the secure per-user runtime base
on macOS and Linux, 0700 project/Compose directories, no-symlink 0600 lock
files, non-blocking ``fcntl`` contention behavior, and kernel-level recovery
after an abnormal holder exit. Everything runs without Docker and never
addresses a developer project.

These tests fail until T017 implements ``tools/workflow/local_env/identity.py``.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import stat
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import pytest

PROJECT_ID = "tokenmarket-0123456789ab"

_HOLDER_SCRIPT = """\
import os
import sys
from pathlib import Path

from workflow.local_env.identity import acquire_project_lock, ensure_project_runtime_dir

project_dir = ensure_project_runtime_dir(Path(sys.argv[1]), sys.argv[2])
acquire_project_lock(project_dir, project_id=sys.argv[2])
os._exit(3)
"""


def _identity() -> Any:
    try:
        return importlib.import_module("workflow.local_env.identity")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.identity is not implemented yet (T017): {exc}")


def _models() -> Any:
    try:
        return importlib.import_module("workflow.local_env.models")
    except ImportError as exc:
        pytest.fail(f"workflow.local_env.models is not implemented yet (T014): {exc}")


def _expected_fingerprint(path: Path) -> str:
    canonical = unicodedata.normalize("NFC", os.path.realpath(str(path)))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fake_stat(st: os.stat_result, *, uid: int, mode: int | None = None) -> os.stat_result:
    return os.stat_result(
        (
            mode if mode is not None else st.st_mode,
            st.st_ino,
            st.st_dev,
            st.st_nlink,
            uid,
            st.st_gid,
            st.st_size,
            st.st_atime,
            st.st_mtime,
            st.st_ctime,
        )
    )


def _root_owned_sticky(path: Path) -> Any:
    """lstat wrapper reporting ``path`` as a root-owned sticky directory."""

    def fake_lstat(p: Any) -> os.stat_result:
        candidate = Path(p)
        real = os.lstat(candidate)
        if candidate == path:
            return _fake_stat(real, uid=0, mode=stat.S_IFDIR | 0o1777)
        return real

    return fake_lstat


@pytest.fixture
def runtime_base(tmp_path: Path) -> Path:
    base = tmp_path / "runtime-base"
    base.mkdir(mode=0o700)
    return base


class TestCanonicalPathIdentity:
    def test_symlink_path_resolves_to_same_identity(self, tmp_path: Path) -> None:
        identity = _identity()
        real = tmp_path / "real-workspace"
        real.mkdir()
        link = tmp_path / "linked-workspace"
        link.symlink_to(real, target_is_directory=True)
        assert identity.workspace_identity(link) == identity.workspace_identity(real)
        assert identity.canonical_workspace_path(link) == identity.canonical_workspace_path(real)

    def test_identity_is_deterministic(self, tmp_workspace: Path) -> None:
        identity = _identity()
        first = identity.workspace_identity(tmp_workspace)
        second = identity.workspace_identity(tmp_workspace)
        assert first == second

    def test_nfc_utf8_hash(self, tmp_path: Path) -> None:
        identity = _identity()
        workspace = tmp_path / "café 工作区"
        workspace.mkdir()
        expected = _expected_fingerprint(workspace)
        result = identity.workspace_identity(workspace)
        assert result.workspace_fingerprint == expected
        assert result.workspace_hash == expected[:12]
        assert result.project_id == f"tokenmarket-{expected[:12]}"

    def test_nfd_input_yields_same_identity(self, tmp_path: Path) -> None:
        identity = _identity()
        name = "café-測試"
        (tmp_path / name).mkdir()
        nfc = identity.workspace_identity(tmp_path / name)
        nfd = identity.workspace_identity(tmp_path / unicodedata.normalize("NFD", name))
        assert nfd == nfc

    def test_spaces_in_path(self, tmp_path: Path) -> None:
        identity = _identity()
        workspace = tmp_path / "my work space"
        workspace.mkdir()
        assert identity.workspace_identity(workspace).workspace_fingerprint == (
            _expected_fingerprint(workspace)
        )

    def test_case_is_not_folded(self, tmp_path: Path) -> None:
        identity = _identity()
        upper = identity.workspace_identity(tmp_path / "Workspace")
        lower = identity.workspace_identity(tmp_path / "workspace")
        assert upper.workspace_fingerprint != lower.workspace_fingerprint

    def test_trailing_separator_ignored(self, tmp_workspace: Path) -> None:
        identity = _identity()
        plain = identity.canonical_workspace_path(tmp_workspace)
        with_separator = identity.canonical_workspace_path(f"{tmp_workspace}{os.sep}")
        assert with_separator == plain
        assert not plain.endswith(os.sep)

    def test_identity_repr_hides_workspace_path(self, tmp_workspace: Path) -> None:
        identity = _identity()
        result = identity.workspace_identity(tmp_workspace)
        rendered = repr(result)
        assert os.path.realpath(str(tmp_workspace)) not in rendered
        assert result.project_id in rendered


class TestOwnershipFingerprint:
    def test_full_fingerprint_match_passes(self, tmp_workspace: Path) -> None:
        identity = _identity()
        owned = identity.workspace_identity(tmp_workspace)
        identity.verify_fingerprint_ownership(
            owned,
            observed_project_id=owned.project_id,
            observed_fingerprint=owned.workspace_fingerprint,
        )

    def test_short_hash_collision_fails_closed(self, tmp_workspace: Path) -> None:
        identity = _identity()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        flipped = owned.workspace_fingerprint[:-1] + (
            "0" if owned.workspace_fingerprint[-1] != "0" else "1"
        )
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            identity.verify_fingerprint_ownership(
                owned,
                observed_project_id=owned.project_id,
                observed_fingerprint=flipped,
            )
        message = str(excinfo.value)
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert "collision" in message.lower()
        assert owned.project_id in message
        assert os.path.realpath(str(tmp_workspace)) not in message

    def test_foreign_project_fails_closed(self, tmp_workspace: Path) -> None:
        identity = _identity()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        with pytest.raises(models.OwnershipConflictError):
            identity.verify_fingerprint_ownership(
                owned,
                observed_project_id="tokenmarket-ffffffffffff",
                observed_fingerprint="f" * 64,
            )


class TestSecureRuntimeBase:
    def test_linux_run_user_accepted(self, tmp_path: Path) -> None:
        identity = _identity()
        run_user = tmp_path / "run-user"
        run_user.mkdir(mode=0o700)
        result = identity.secure_runtime_base(
            platform="linux",
            euid=os.geteuid(),
            run_user_dir=run_user,
            tmp_dir=tmp_path / "unused-tmp",
        )
        assert result == run_user

    def test_linux_run_user_missing_falls_back_to_tmp_child(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()
        result = identity.secure_runtime_base(
            platform="linux",
            euid=euid,
            run_user_dir=tmp_path / "missing-run-user",
            tmp_dir=fake_tmp,
            lstat=_root_owned_sticky(fake_tmp),
        )
        assert result == fake_tmp / f"tokenmarket-runtime-{euid}"
        assert stat.S_IMODE(os.lstat(result).st_mode) == 0o700

    def test_linux_run_user_wrong_owner_falls_back(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        run_user = tmp_path / "run-user"
        run_user.mkdir(mode=0o700)
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()
        sticky = _root_owned_sticky(fake_tmp)

        def fake_lstat(p: Any) -> os.stat_result:
            real: os.stat_result = sticky(p)
            if Path(p) == run_user:
                return _fake_stat(real, uid=euid + 1)
            return real

        result = identity.secure_runtime_base(
            platform="linux",
            euid=euid,
            run_user_dir=run_user,
            tmp_dir=fake_tmp,
            lstat=fake_lstat,
        )
        assert result == fake_tmp / f"tokenmarket-runtime-{euid}"

    def test_linux_run_user_group_accessible_falls_back(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        run_user = tmp_path / "run-user"
        run_user.mkdir(mode=0o750)
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()
        result = identity.secure_runtime_base(
            platform="linux",
            euid=euid,
            run_user_dir=run_user,
            tmp_dir=fake_tmp,
            lstat=_root_owned_sticky(fake_tmp),
        )
        assert result == fake_tmp / f"tokenmarket-runtime-{euid}"

    def test_tmp_without_sticky_bit_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()

        def fake_lstat(p: Any) -> os.stat_result:
            real = os.lstat(p)
            if Path(p) == fake_tmp:
                return _fake_stat(real, uid=0, mode=stat.S_IFDIR | 0o0777)
            return real

        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="linux",
                euid=os.geteuid(),
                run_user_dir=tmp_path / "missing",
                tmp_dir=fake_tmp,
                lstat=fake_lstat,
            )

    def test_tmp_not_root_owned_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()

        def fake_lstat(p: Any) -> os.stat_result:
            real = os.lstat(p)
            if Path(p) == fake_tmp:
                return _fake_stat(real, uid=euid, mode=stat.S_IFDIR | 0o1777)
            return real

        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="linux",
                euid=euid,
                run_user_dir=tmp_path / "missing",
                tmp_dir=fake_tmp,
                lstat=fake_lstat,
            )

    def test_tmp_child_mode_drift_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()
        child = fake_tmp / f"tokenmarket-runtime-{euid}"
        child.mkdir(mode=0o755)
        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="linux",
                euid=euid,
                run_user_dir=tmp_path / "missing",
                tmp_dir=fake_tmp,
                lstat=_root_owned_sticky(fake_tmp),
            )

    def test_tmp_child_symlink_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        euid = os.geteuid()
        fake_tmp = tmp_path / "fake-tmp"
        fake_tmp.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        (fake_tmp / f"tokenmarket-runtime-{euid}").symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="linux",
                euid=euid,
                run_user_dir=tmp_path / "missing",
                tmp_dir=fake_tmp,
                lstat=_root_owned_sticky(fake_tmp),
            )

    def test_darwin_user_temp_accepted(self, tmp_path: Path) -> None:
        identity = _identity()
        darwin_temp = tmp_path / "darwin-user-temp"
        darwin_temp.mkdir(mode=0o700)
        result = identity.secure_runtime_base(
            platform="darwin",
            euid=os.geteuid(),
            darwin_user_temp=darwin_temp,
        )
        assert result == darwin_temp

    def test_darwin_temp_wrong_owner_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        darwin_temp = tmp_path / "darwin-user-temp"
        darwin_temp.mkdir(mode=0o700)

        def fake_lstat(p: Any) -> os.stat_result:
            return _fake_stat(os.lstat(p), uid=os.geteuid() + 1)

        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="darwin",
                euid=os.geteuid(),
                darwin_user_temp=darwin_temp,
                lstat=fake_lstat,
            )

    def test_darwin_temp_group_accessible_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        darwin_temp = tmp_path / "darwin-user-temp"
        darwin_temp.mkdir(mode=0o750)
        with pytest.raises(_models().LockSafetyError):
            identity.secure_runtime_base(
                platform="darwin",
                euid=os.geteuid(),
                darwin_user_temp=darwin_temp,
            )

    def test_unsupported_platform_fails_closed(self) -> None:
        with pytest.raises(_models().LockSafetyError):
            _identity().secure_runtime_base(platform="win32", euid=os.geteuid())


class TestProjectRuntimeDir:
    def test_project_dir_created_0700_with_compose_dir(self, runtime_base: Path) -> None:
        identity = _identity()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        assert project_dir == runtime_base / PROJECT_ID
        assert stat.S_IMODE(os.lstat(project_dir).st_mode) == 0o700
        compose_dir = project_dir / "compose-project"
        assert compose_dir.is_dir()
        assert stat.S_IMODE(os.lstat(compose_dir).st_mode) == 0o700
        assert list(compose_dir.iterdir()) == []

    def test_project_dir_creation_is_idempotent(self, runtime_base: Path) -> None:
        identity = _identity()
        first = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        second = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        assert first == second

    def test_project_dir_mode_drift_fails_closed(self, runtime_base: Path) -> None:
        identity = _identity()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        project_dir.chmod(0o755)
        with pytest.raises(_models().LockSafetyError):
            identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)

    def test_project_dir_symlink_fails_closed(self, runtime_base: Path) -> None:
        identity = _identity()
        elsewhere = runtime_base.parent / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        (runtime_base / PROJECT_ID).symlink_to(elsewhere, target_is_directory=True)
        with pytest.raises(_models().LockSafetyError):
            identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)

    def test_base_symlink_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        real_base = tmp_path / "real-base"
        real_base.mkdir(mode=0o700)
        link_base = tmp_path / "link-base"
        link_base.symlink_to(real_base, target_is_directory=True)
        with pytest.raises(_models().LockSafetyError):
            identity.ensure_project_runtime_dir(link_base, PROJECT_ID)

    def test_path_unsafe_project_ids_rejected(self, runtime_base: Path) -> None:
        identity = _identity()
        for bad in ("../evil", "Has Upper", "has space", "has/slash", ""):
            with pytest.raises(_models().LockSafetyError):
                identity.ensure_project_runtime_dir(runtime_base, bad)


class TestProjectLock:
    def test_lock_file_is_regular_0600_and_current_user(self, runtime_base: Path) -> None:
        identity = _identity()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        lock = identity.acquire_project_lock(project_dir, project_id=PROJECT_ID)
        try:
            st = os.lstat(project_dir / "lifecycle.lock")
            assert stat.S_ISREG(st.st_mode)
            assert stat.S_IMODE(st.st_mode) == 0o600
            assert st.st_uid == os.geteuid()
        finally:
            lock.release()

    def test_lock_reacquires_after_release(self, runtime_base: Path) -> None:
        identity = _identity()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        identity.acquire_project_lock(project_dir, project_id=PROJECT_ID).release()
        with identity.acquire_project_lock(project_dir, project_id=PROJECT_ID) as held:
            assert held.held

    def test_contention_fails_fast_with_stable_diagnostic(self, runtime_base: Path) -> None:
        identity = _identity()
        models = _models()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        first = identity.acquire_project_lock(project_dir, project_id=PROJECT_ID)
        try:
            started = time.monotonic()
            with pytest.raises(models.OperationInProgressError) as excinfo:
                identity.acquire_project_lock(project_dir, project_id=PROJECT_ID)
            assert time.monotonic() - started < 5
            assert excinfo.value.code == "OPERATION_IN_PROGRESS"
            assert PROJECT_ID in str(excinfo.value)
            assert str(project_dir) not in str(excinfo.value)
        finally:
            first.release()
        with identity.acquire_project_lock(project_dir, project_id=PROJECT_ID):
            pass

    def test_lock_symlink_is_never_followed(self, runtime_base: Path, tmp_path: Path) -> None:
        identity = _identity()
        models = _models()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        target = tmp_path / "must-stay-untouched"
        target.write_text("original", encoding="utf-8")
        (project_dir / "lifecycle.lock").symlink_to(target)
        with pytest.raises(models.LockSafetyError):
            identity.acquire_project_lock(project_dir, project_id=PROJECT_ID)
        assert target.read_text(encoding="utf-8") == "original"

    def test_lock_mode_drift_fails_closed(self, runtime_base: Path) -> None:
        identity = _identity()
        models = _models()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)
        lock_path = project_dir / "lifecycle.lock"
        lock_path.touch()
        lock_path.chmod(0o644)
        with pytest.raises(models.LockSafetyError):
            identity.acquire_project_lock(project_dir, project_id=PROJECT_ID)

    def test_lock_owner_drift_fails_closed(self, runtime_base: Path) -> None:
        identity = _identity()
        models = _models()
        project_dir = identity.ensure_project_runtime_dir(runtime_base, PROJECT_ID)

        def fake_fstat(fd: int) -> os.stat_result:
            return _fake_stat(os.fstat(fd), uid=os.geteuid() + 1)

        with pytest.raises(models.LockSafetyError):
            identity.acquire_project_lock(project_dir, project_id=PROJECT_ID, fstat=fake_fstat)

    def test_abnormal_holder_exit_leaves_lock_recoverable(self, tmp_path: Path) -> None:
        identity = _identity()
        base = tmp_path / "runtime-base"
        base.mkdir(mode=0o700)
        result = subprocess.run(
            [sys.executable, "-c", _HOLDER_SCRIPT, str(base), PROJECT_ID],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmp_path,
        )
        assert result.returncode == 3, result.stderr
        project_dir = identity.ensure_project_runtime_dir(base, PROJECT_ID)
        with identity.acquire_project_lock(project_dir, project_id=PROJECT_ID) as lock:
            assert lock.held
        # The empty lock file may remain; kernel lock state is authoritative.
        assert (project_dir / "lifecycle.lock").is_file()


# ---------------------------------------------------------------------------
# T036 (US2): ownership and workspace-preservation extensions for dev-down
#
# Covers the workspace-identity rules of the ``make dev-down`` contract:
# the same canonical path keeps one stable project identity across branch
# switches and content changes; different clones/worktrees are isolated;
# moving the workspace produces a new identity; resources of a previous
# workspace are mandatory report-only findings (never adopted, stopped,
# removed, renamed, or attached); a full-64-hex fingerprint mismatch with a
# matching 12-hex project ID fails closed before mutation; and ownership
# labels never carry the raw or canonical workspace path.
#
# The label/discovery API under test is implemented by T042 in
# ``tools/workflow/local_env/identity.py``; those tests fail with an explicit
# not-implemented guard until then.
# ---------------------------------------------------------------------------

OLD_WORKSPACE_PROJECT_ID = "tokenmarket-aaaa1111bbbb"
OLD_WORKSPACE_FINGERPRINT = "f" * 64


def _identity_t042() -> Any:
    module = _identity()
    required = (
        "ownership_labels",
        "authorize_label_mutation",
        "classify_repository_resources",
        "ResourceObservation",
        "MovedWorkspaceFinding",
    )
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        pytest.fail(
            "workflow.local_env.identity ownership/discovery extensions are not "
            f"implemented yet (T042): missing {', '.join(missing)}"
        )
    return module


def _flipped_fingerprint(fingerprint: str) -> str:
    return fingerprint[:-1] + ("0" if fingerprint[-1] != "0" else "1")


def _old_workspace_labels() -> dict[str, str]:
    return {
        "com.tokenmarket.repository": "tokenmarket",
        "com.tokenmarket.workspace-id": OLD_WORKSPACE_PROJECT_ID,
        "com.tokenmarket.workspace-fingerprint": OLD_WORKSPACE_FINGERPRINT,
    }


class TestSamePathStability:
    def test_identity_stable_across_branch_changes(self, tmp_path: Path) -> None:
        identity = _identity()
        workspace = tmp_path / "checkout"
        (workspace / ".git").mkdir(parents=True)
        (workspace / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        first = identity.workspace_identity(workspace)
        (workspace / ".git" / "HEAD").write_text(
            "ref: refs/heads/feature/other\n", encoding="utf-8"
        )
        second = identity.workspace_identity(workspace)
        assert first == second, "the branch name is never an identity input"

    def test_identity_stable_across_worktree_content_changes(self, tmp_path: Path) -> None:
        identity = _identity()
        workspace = tmp_path / "checkout"
        workspace.mkdir()
        tracked = workspace / "tracked.txt"
        tracked.write_text("committed content\n", encoding="utf-8")
        first = identity.workspace_identity(workspace)
        tracked.write_text("locally modified content\n", encoding="utf-8")
        (workspace / "untracked.log").write_text("scratch\n", encoding="utf-8")
        second = identity.workspace_identity(workspace)
        assert first == second, "worktree content is never an identity input"

    def test_dot_segments_resolve_to_same_identity(self, tmp_path: Path) -> None:
        identity = _identity()
        workspace = tmp_path / "checkout"
        workspace.mkdir()
        direct = identity.workspace_identity(workspace)
        via_segments = identity.workspace_identity(tmp_path / "subdir" / ".." / "checkout")
        assert via_segments == direct


class TestWorkspaceIsolationAndMoveDetection:
    def test_different_clones_are_isolated(self, tmp_path: Path) -> None:
        identity = _identity()
        clone_one = tmp_path / "clone-one"
        clone_two = tmp_path / "clone-two"
        clone_one.mkdir()
        clone_two.mkdir()
        first = identity.workspace_identity(clone_one)
        second = identity.workspace_identity(clone_two)
        assert first.project_id != second.project_id
        assert first.workspace_fingerprint != second.workspace_fingerprint
        assert first.project_id.startswith("tokenmarket-")
        assert second.project_id.startswith("tokenmarket-")

    def test_cross_workspace_authorization_fails_closed(self, tmp_path: Path) -> None:
        identity = _identity()
        models = _models()
        clone_one = tmp_path / "clone-one"
        clone_two = tmp_path / "clone-two"
        clone_one.mkdir()
        clone_two.mkdir()
        first = identity.workspace_identity(clone_one)
        second = identity.workspace_identity(clone_two)
        with pytest.raises(models.OwnershipConflictError):
            identity.verify_fingerprint_ownership(
                first,
                observed_project_id=second.project_id,
                observed_fingerprint=second.workspace_fingerprint,
            )

    def test_moved_workspace_gets_new_identity(self, tmp_path: Path) -> None:
        identity = _identity()
        old_location = tmp_path / "old-location"
        old_location.mkdir()
        old_identity = identity.workspace_identity(old_location)
        new_location = tmp_path / "new-location"
        os.rename(old_location, new_location)
        new_identity = identity.workspace_identity(new_location)
        assert new_identity.project_id != old_identity.project_id
        assert new_identity.workspace_fingerprint != old_identity.workspace_fingerprint

    def test_old_workspace_not_authorized_after_move(self, tmp_path: Path) -> None:
        identity = _identity()
        models = _models()
        old_location = tmp_path / "old-location"
        old_location.mkdir()
        old_identity = identity.workspace_identity(old_location)
        new_location = tmp_path / "new-location"
        os.rename(old_location, new_location)
        new_identity = identity.workspace_identity(new_location)
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            identity.verify_fingerprint_ownership(
                new_identity,
                observed_project_id=old_identity.project_id,
                observed_fingerprint=old_identity.workspace_fingerprint,
            )
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert os.path.realpath(str(new_location)) not in str(excinfo.value)


class TestOwnershipLabels:
    """T042: the path-free ownership label set carried by exact resources."""

    def test_ownership_labels_exact_and_path_free(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        owned = identity.workspace_identity(tmp_workspace)
        labels = identity.ownership_labels(owned)
        assert dict(labels) == {
            "com.tokenmarket.repository": "tokenmarket",
            "com.tokenmarket.workspace-id": owned.project_id,
            "com.tokenmarket.workspace-fingerprint": owned.workspace_fingerprint,
        }
        canonical = os.path.realpath(str(tmp_workspace))
        for key, value in labels.items():
            assert canonical not in key
            assert canonical not in value

    def test_labels_path_free_with_spaces_and_unicode(self, tmp_path: Path) -> None:
        identity = _identity_t042()
        workspace = tmp_path / "meine entwicklungs umgebung 工作区"
        workspace.mkdir()
        owned = identity.workspace_identity(workspace)
        labels = identity.ownership_labels(owned)
        raw = str(workspace)
        canonical = os.path.realpath(raw)
        for key, value in labels.items():
            assert raw not in key and raw not in value
            assert canonical not in key and canonical not in value
            assert " " not in value, "label values carry hashes, never raw paths"


class TestLabelMutationAuthorization:
    """T042: exact project/full-fingerprint label authorization before mutation."""

    def test_exact_labels_authorize_mutation(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        owned = identity.workspace_identity(tmp_workspace)
        identity.authorize_label_mutation(owned, identity.ownership_labels(owned))

    def test_foreign_workspace_labels_fail_closed(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            identity.authorize_label_mutation(owned, _old_workspace_labels())
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"

    def test_full_fingerprint_collision_fails_closed(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        labels = {
            "com.tokenmarket.repository": "tokenmarket",
            "com.tokenmarket.workspace-id": owned.project_id,
            "com.tokenmarket.workspace-fingerprint": _flipped_fingerprint(
                owned.workspace_fingerprint
            ),
        }
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            identity.authorize_label_mutation(owned, labels)
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        message = str(excinfo.value)
        assert "collision" in message.lower() or "fingerprint" in message.lower()
        assert os.path.realpath(str(tmp_workspace)) not in message

    def test_missing_ownership_labels_fail_closed(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        with pytest.raises(models.OwnershipConflictError):
            identity.authorize_label_mutation(owned, {"com.tokenmarket.repository": "tokenmarket"})


class TestMovedWorkspaceReportOnly:
    """T042: different old workspace IDs are mandatory report-only findings."""

    def test_classification_splits_owned_and_moved(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        owned = identity.workspace_identity(tmp_workspace)
        observations = [
            identity.ResourceObservation(
                kind="container",
                name="mine-postgres-1",
                labels=identity.ownership_labels(owned),
            ),
            identity.ResourceObservation(
                kind="container",
                name="old-postgres-1",
                labels=_old_workspace_labels(),
            ),
            identity.ResourceObservation(
                kind="volume",
                name="old_postgres-data",
                labels=_old_workspace_labels(),
            ),
        ]
        result = identity.classify_repository_resources(owned, observations)
        assert [resource.name for resource in result.owned] == ["mine-postgres-1"]
        assert {finding.workspace_id for finding in result.moved} == {OLD_WORKSPACE_PROJECT_ID}
        assert {finding.observation.name for finding in result.moved} == {
            "old-postgres-1",
            "old_postgres-data",
        }

    def test_moved_findings_are_report_only_with_safe_guidance(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        owned = identity.workspace_identity(tmp_workspace)
        observations = [
            identity.ResourceObservation(
                kind="network",
                name="old_default",
                labels=_old_workspace_labels(),
            )
        ]
        result = identity.classify_repository_resources(owned, observations)
        assert len(result.moved) == 1
        finding = result.moved[0]
        assert finding.workspace_id == OLD_WORKSPACE_PROJECT_ID
        guidance = finding.guidance
        assert guidance, "a moved-workspace finding must carry recovery direction"
        assert OLD_WORKSPACE_PROJECT_ID in guidance
        assert "moved" in guidance.lower() or "recover" in guidance.lower()
        canonical = os.path.realpath(str(tmp_workspace))
        assert canonical not in guidance, "guidance never exposes workspace paths"
        # Report-only classification never mutates its input observations.
        assert [observation.name for observation in observations] == ["old_default"]

    def test_collision_during_classification_fails_closed(self, tmp_workspace: Path) -> None:
        identity = _identity_t042()
        models = _models()
        owned = identity.workspace_identity(tmp_workspace)
        colliding = {
            "com.tokenmarket.repository": "tokenmarket",
            "com.tokenmarket.workspace-id": owned.project_id,
            "com.tokenmarket.workspace-fingerprint": _flipped_fingerprint(
                owned.workspace_fingerprint
            ),
        }
        observations = [
            identity.ResourceObservation(kind="container", name="colliding-1", labels=colliding)
        ]
        with pytest.raises(models.OwnershipConflictError) as excinfo:
            identity.classify_repository_resources(owned, observations)
        assert excinfo.value.code == "RESOURCE_OWNERSHIP_CONFLICT"
        assert "collision" in str(excinfo.value).lower()
