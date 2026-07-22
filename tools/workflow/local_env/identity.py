"""Canonical workspace identity and per-project POSIX advisory locking (SF02).

Implements the identity and lock rules of
``specs/002-local-dependency-lifecycle/contracts/local-environment-lifecycle.md``
(research Decisions 5 and 8):

- Identity is the SHA-256 of the physical, NFC-normalized UTF-8 canonical
  workspace path: 12 lowercase hex characters form the project suffix and the
  full 64 characters form the collision/ownership fingerprint. The canonical
  path never enters resource names, labels, events, logs, or repr output.
- Mutation is authorized by exact ``project_id`` plus the full fingerprint; a
  matching 12-hex project ID with a different fingerprint is a detected
  collision and fails closed.
- The per-user runtime base is the macOS per-user temporary directory, a valid
  owned ``/run/user/<euid>`` on Linux, or an owned ``0700`` child below a
  root-owned sticky ``/tmp``. Every managed component is checked with no
  symlink following; ownership, mode, or type drift fails closed.
- One non-blocking exclusive ``fcntl`` lock per project serializes lifecycle
  operations; contention fails fast with ``OPERATION_IN_PROGRESS`` and the
  kernel releases the lock on normal or abnormal holder exit.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import re
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Callable, Mapping, Sequence

from .models import LockSafetyError, OperationInProgressError, OwnershipConflictError

PROJECT_PREFIX = "tokenmarket"
WORKSPACE_HASH_LENGTH = 12
WORKSPACE_FINGERPRINT_LENGTH = 64
LOCK_FILE_NAME = "lifecycle.lock"
COMPOSE_PROJECT_DIR_NAME = "compose-project"

# Path-free ownership labels carried on Compose resources (T042). The raw and
# canonical workspace paths are deliberately absent from both keys and values.
LABEL_REPOSITORY = "com.tokenmarket.repository"
LABEL_WORKSPACE_ID = "com.tokenmarket.workspace-id"
LABEL_WORKSPACE_FINGERPRINT = "com.tokenmarket.workspace-fingerprint"
REPOSITORY_LABEL_VALUE = "tokenmarket"

_PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

# Signature seam for filesystem metadata checks; tests inject wrapped stat
# results to exercise owner/mode drift without privileged operations.
StatFn = Callable[[Path], os.stat_result]
FStatFn = Callable[[int], os.stat_result]


@dataclass(frozen=True)
class WorkspaceIdentity:
    """Canonical workspace identity derived from the physical repository root.

    ``canonical_path`` is held only to document derivation; it is excluded
    from repr/str so it can never leak into events, logs, or diagnostics.
    """

    workspace_hash: str
    workspace_fingerprint: str
    project_id: str
    canonical_path: str = field(repr=False)


def canonical_workspace_path(path: Path | str) -> str:
    """Return the physical canonical path: symlinks resolved, NFC normalized.

    Resolution is physical (``.``, ``..`` and symlinks are resolved), the
    trailing separator is removed, case is preserved, and the result is
    Unicode NFC normalized for the UTF-8 hash input.
    """
    resolved = os.path.realpath(os.fspath(path))
    if resolved != os.sep:
        resolved = resolved.rstrip(os.sep)
    return unicodedata.normalize("NFC", resolved)


def workspace_identity(path: Path | str) -> WorkspaceIdentity:
    """Compute the hash, fingerprint, and project ID for a workspace root."""
    canonical = canonical_workspace_path(path)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    workspace_hash = digest[:WORKSPACE_HASH_LENGTH]
    return WorkspaceIdentity(
        workspace_hash=workspace_hash,
        workspace_fingerprint=digest,
        project_id=f"{PROJECT_PREFIX}-{workspace_hash}",
        canonical_path=canonical,
    )


def verify_fingerprint_ownership(
    identity: WorkspaceIdentity,
    *,
    observed_project_id: str,
    observed_fingerprint: str,
) -> None:
    """Authorize mutation by exact project ID plus the full fingerprint.

    A matching 12-hex project ID with a different 64-hex fingerprint is a
    detected short-hash collision and fails closed before any mutation.
    """
    if observed_project_id != identity.project_id:
        raise OwnershipConflictError(
            f"resources for {observed_project_id!r} are not owned by project "
            f"{identity.project_id}; refusing to adopt, stop, or mutate them"
        )
    if observed_fingerprint != identity.workspace_fingerprint:
        raise OwnershipConflictError(
            f"workspace hash collision detected for {identity.project_id}: the full "
            "fingerprint does not match this workspace; failing closed before mutation"
        )


def ownership_labels(identity: WorkspaceIdentity) -> dict[str, str]:
    """Return the path-free ownership label set for exact-project resources.

    Labels carry only the repository constant, the short project id, and the
    full 64-hex fingerprint. Raw and canonical workspace paths never appear
    in keys or values (T042).
    """
    return {
        LABEL_REPOSITORY: REPOSITORY_LABEL_VALUE,
        LABEL_WORKSPACE_ID: identity.project_id,
        LABEL_WORKSPACE_FINGERPRINT: identity.workspace_fingerprint,
    }


def authorize_label_mutation(
    identity: WorkspaceIdentity, labels: Mapping[str, str]
) -> None:
    """Authorize mutation from a resource's ownership labels.

    Requires exact ``workspace-id`` plus full ``workspace-fingerprint`` match.
    Missing labels, foreign workspaces, and short-hash collisions fail closed
    with :class:`OwnershipConflictError` before any mutation (T042).
    """
    observed_project_id = labels.get(LABEL_WORKSPACE_ID, "")
    observed_fingerprint = labels.get(LABEL_WORKSPACE_FINGERPRINT, "")
    if not observed_project_id or not observed_fingerprint:
        raise OwnershipConflictError(
            "resource is missing required ownership labels; refusing to adopt, "
            "stop, or mutate it"
        )
    verify_fingerprint_ownership(
        identity,
        observed_project_id=observed_project_id,
        observed_fingerprint=observed_fingerprint,
    )


@dataclass(frozen=True)
class ResourceObservation:
    """Read-only view of one Docker resource discovered by label filter."""

    kind: str
    name: str
    labels: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class MovedWorkspaceFinding:
    """Report-only finding for a resource owned by a different workspace.

    Findings must never be adopted, stopped, removed, renamed, or attached.
    ``guidance`` is safe to emit: it may name the old project id but never the
    workspace path.
    """

    workspace_id: str
    observation: ResourceObservation
    guidance: str


@dataclass(frozen=True)
class RepositoryResourceClassification:
    """Split of repository-labeled resources into owned vs moved findings."""

    owned: tuple[ResourceObservation, ...]
    moved: tuple[MovedWorkspaceFinding, ...]


def _moved_workspace_guidance(workspace_id: str) -> str:
    return (
        f"resources for moved or prior workspace {workspace_id} were found; "
        "they are report-only and were not stopped or removed. Recover from "
        "the original workspace path or stop them with that workspace's "
        "project identity, then retry."
    )


def classify_repository_resources(
    identity: WorkspaceIdentity,
    observations: Sequence[ResourceObservation],
) -> RepositoryResourceClassification:
    """Classify repository-labeled resources as owned or report-only moved.

    Exact project+fingerprint ownership is required for the owned set. A
    matching short project id with a different fingerprint is a collision and
    fails closed. Other workspace ids become mandatory report-only findings
    with safe recovery guidance (T042).
    """
    owned: list[ResourceObservation] = []
    moved: list[MovedWorkspaceFinding] = []
    for observation in observations:
        labels = dict(observation.labels)
        observed_project_id = labels.get(LABEL_WORKSPACE_ID, "")
        observed_fingerprint = labels.get(LABEL_WORKSPACE_FINGERPRINT, "")
        if not observed_project_id or not observed_fingerprint:
            # ADR 003 deploy stack reuses the repository label with
            # ``com.tokenmarket.stack=deploy`` and environment labels only
            # (no workspace identity). Those resources are out of SF02 scope
            # and must not block local lifecycle discovery/stop (T083).
            if labels.get("com.tokenmarket.stack") == "deploy":
                continue
            raise OwnershipConflictError(
                "resource is missing required ownership labels; refusing to "
                "classify or mutate it"
            )
        if observed_project_id == identity.project_id:
            # Exact match authorizes; fingerprint mismatch is a collision.
            authorize_label_mutation(identity, labels)
            owned.append(observation)
            continue
        moved.append(
            MovedWorkspaceFinding(
                workspace_id=observed_project_id,
                observation=observation,
                guidance=_moved_workspace_guidance(observed_project_id),
            )
        )
    return RepositoryResourceClassification(
        owned=tuple(owned), moved=tuple(moved)
    )


def _require_secure_directory(
    path: Path, *, euid: int, lstat: StatFn, what: str
) -> None:
    """Verify a directory is real (no symlink), owned by euid, owner-only."""
    try:
        st = lstat(path)
    except FileNotFoundError:
        raise LockSafetyError(f"{what} does not exist") from None
    if not stat.S_ISDIR(st.st_mode):
        raise LockSafetyError(f"{what} must be a real directory, not a symlink or file")
    if st.st_uid != euid:
        raise LockSafetyError(f"{what} owner drift detected; failing closed")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise LockSafetyError(f"{what} must not be accessible by group or other users")


def _is_valid_per_user_dir(path: Path, *, euid: int, lstat: StatFn) -> bool:
    try:
        _require_secure_directory(
            path, euid=euid, lstat=lstat, what="per-user runtime base"
        )
    except LockSafetyError:
        return False
    return True


def _ensure_owned_child(path: Path, *, euid: int, lstat: StatFn, what: str) -> Path:
    """Create ``path`` as a 0700 current-user directory or verify an existing one."""
    try:
        st = lstat(path)
    except FileNotFoundError:
        os.mkdir(path, 0o700)
        return path
    if not stat.S_ISDIR(st.st_mode):
        raise LockSafetyError(f"{what} must be a real directory, not a symlink or file")
    if st.st_uid != euid:
        raise LockSafetyError(f"{what} owner drift detected; failing closed")
    if stat.S_IMODE(st.st_mode) != 0o700:
        raise LockSafetyError(f"{what} mode drift detected; expected exactly 0700")
    return path


def secure_runtime_base(
    *,
    platform: str | None = None,
    euid: int | None = None,
    environ: Mapping[str, str] | None = None,
    lstat: StatFn = os.lstat,
    darwin_user_temp: Path | None = None,
    run_user_dir: Path | None = None,
    tmp_dir: Path | None = None,
) -> Path:
    """Return the verified secure per-user runtime base.

    macOS uses the OS-provided per-user temporary directory. Linux uses an
    owned ``/run/user/<euid>`` when valid, otherwise an owned ``0700`` child
    below a root-owned sticky ``/tmp`` (created when missing). Anything else
    fails closed; no secret or workspace path is ever stored below it.
    """
    effective_platform = sys.platform if platform is None else platform
    effective_euid = os.geteuid() if euid is None else euid
    effective_environ = os.environ if environ is None else environ

    if effective_platform == "darwin":
        if darwin_user_temp is not None:
            candidate = darwin_user_temp
        else:
            candidate = Path(effective_environ.get("TMPDIR") or tempfile.gettempdir())
        _require_secure_directory(
            candidate,
            euid=effective_euid,
            lstat=lstat,
            what="per-user temporary directory",
        )
        return candidate

    if effective_platform.startswith("linux"):
        run_user = (
            Path("/run/user") / str(effective_euid)
            if run_user_dir is None
            else run_user_dir
        )
        if _is_valid_per_user_dir(run_user, euid=effective_euid, lstat=lstat):
            return run_user
        tmp = Path("/tmp") if tmp_dir is None else tmp_dir
        try:
            tmp_stat = lstat(tmp)
        except FileNotFoundError:
            raise LockSafetyError(
                "no secure runtime base: /tmp is unavailable"
            ) from None
        if not stat.S_ISDIR(tmp_stat.st_mode):
            raise LockSafetyError(
                "no secure runtime base: /tmp must be a real directory"
            )
        if tmp_stat.st_uid != 0 or not tmp_stat.st_mode & stat.S_ISVTX:
            raise LockSafetyError(
                "no secure runtime base: /tmp must be root-owned with the sticky bit set"
            )
        return _ensure_owned_child(
            tmp / f"tokenmarket-runtime-{effective_euid}",
            euid=effective_euid,
            lstat=lstat,
            what="per-user runtime fallback directory",
        )

    raise LockSafetyError(
        f"unsupported platform {effective_platform!r}; SF02 supports macOS arm64 and "
        "Linux x86_64 only"
    )


def ensure_project_runtime_dir(
    base: Path,
    project_id: str,
    *,
    euid: int | None = None,
    lstat: StatFn = os.lstat,
) -> Path:
    """Create/verify the 0700 project directory and empty Compose project dir.

    The project directory is named only from ``project_id`` directly below the
    verified per-user ``base``; every component is checked without following
    symlinks and any ownership, mode, or type drift fails closed.
    """
    effective_euid = os.geteuid() if euid is None else euid
    if not _PROJECT_ID_PATTERN.fullmatch(project_id):
        raise LockSafetyError("project_id is not a safe runtime path component")
    _require_secure_directory(
        base, euid=effective_euid, lstat=lstat, what="runtime base"
    )
    project_dir = _ensure_owned_child(
        base / project_id,
        euid=effective_euid,
        lstat=lstat,
        what="project runtime directory",
    )
    _ensure_owned_child(
        project_dir / COMPOSE_PROJECT_DIR_NAME,
        euid=effective_euid,
        lstat=lstat,
        what="Compose project directory",
    )
    return project_dir


class ProjectLock:
    """A held non-blocking exclusive advisory lock for one project.

    The empty lock file may remain after release; kernel lock state is
    authoritative and the kernel releases the lock on normal or abnormal
    process exit, so no PID-based stale recovery is needed.
    """

    def __init__(self, *, fd: int, path: Path) -> None:
        self._fd = fd
        self._path = path
        self._held = True

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._held

    def release(self) -> None:
        """Release the kernel lock and close the file descriptor (idempotent)."""
        if not self._held:
            return
        self._held = False
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)

    def __enter__(self) -> ProjectLock:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def acquire_project_lock(
    project_dir: Path,
    *,
    project_id: str = "",
    euid: int | None = None,
    lstat: StatFn = os.lstat,
    fstat: FStatFn = os.fstat,
) -> ProjectLock:
    """Acquire the per-project non-blocking exclusive lock.

    The lock file is a regular, current-user-owned ``0600`` file opened with
    ``O_NOFOLLOW|O_CREAT``; type/owner/mode drift fails closed. Contention
    raises :class:`OperationInProgressError` immediately with a stable
    diagnostic; the loser creates, starts, stops, probes, or deletes nothing.
    """
    effective_euid = os.geteuid() if euid is None else euid
    _require_secure_directory(
        project_dir, euid=effective_euid, lstat=lstat, what="project runtime directory"
    )
    lock_path = project_dir / LOCK_FILE_NAME
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LockSafetyError(
                "lock path must be a regular file, not a symlink; failing closed"
            ) from exc
        raise
    try:
        st = fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LockSafetyError("lock path must be a regular file; failing closed")
        if st.st_uid != effective_euid:
            raise LockSafetyError("lock file owner drift detected; failing closed")
        if stat.S_IMODE(st.st_mode) != 0o600:
            raise LockSafetyError(
                "lock file mode drift detected; expected exactly 0600"
            )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                label = project_id or "this project"
                raise OperationInProgressError(
                    f"another lifecycle operation holds the lock for {label}; "
                    "retry after the active operation finishes"
                ) from exc
            raise
    except BaseException:
        os.close(fd)
        raise
    return ProjectLock(fd=fd, path=lock_path)
