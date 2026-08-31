"""Independent production approval proofs bound to action, target, commit, and run."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableSet

from .mode import ModeError


def _canonical(payload: Mapping[str, Any]) -> bytes:
    body = {
        "action": payload["action"],
        "environment": payload["environment"],
        "target": payload["target"],
        "commit_sha": payload["commit_sha"],
        "run_id": payload.get("run_id") or "",
        "manifest_digest": payload.get("manifest_digest") or "",
        "image_digests": list(payload.get("image_digests") or ()),
        "nonce": payload["nonce"],
        "expires_at": payload["expires_at"],
        "issuer": payload["issuer"],
        "subject": payload["subject"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def approval_hmac_key(raw: str | None = None) -> bytes:
    text = (raw if raw is not None else os.environ.get("PROD_APPROVAL_HMAC_KEY", "")).strip()
    if len(text) < 32:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "PROD_APPROVAL_HMAC_KEY must be at least 32 characters",
        )
    return text.encode("utf-8")


_HMAC_MINT_ENV = (
    "PROD_APPROVAL_ISSUE_KEY",
    "PROD_APPROVAL_VERIFY_KEY",
    "PROD_APPROVAL_HMAC_KEY",
    "PROD_APPROVAL_ISSUE_PRIVATE_KEY",
)


def refuse_hmac_mint_authority(*, hmac_key: bytes | None = None) -> None:
    """HMAC in the verifying process is mint capability, not independent authority."""
    if hmac_key is not None:
        raise ModeError(
            "SELF_ISSUED_APPROVAL",
            "caller-selected HMAC key cannot authorize production",
        )
    held = [name for name in _HMAC_MINT_ENV if os.environ.get(name, "").strip()]
    if held:
        raise ModeError(
            "SELF_ISSUED_APPROVAL",
            "verifying process holds HMAC or issue material and can mint this proof",
        )


def production_verify_pubkey() -> bytes:
    """Load the host Ed25519 public key. The private key must not be in-process."""
    raw = (os.environ.get("PROD_APPROVAL_VERIFY_PUBKEY") or "").strip()
    if not raw:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "PROD_APPROVAL_VERIFY_PUBKEY is required; HMAC cannot authorize production",
        )
    if "BEGIN" in raw:
        return raw.replace("\\n", "\n").encode("utf-8")
    path = Path(raw)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "PROD_APPROVAL_VERIFY_PUBKEY could not be read",
        ) from exc


def production_verify_key(*, hmac_key: bytes | None = None) -> bytes:
    """Production entry: HMAC material is mint authority and is refused."""
    refuse_hmac_mint_authority(hmac_key=hmac_key)
    production_verify_pubkey()
    return b""


def generate_approval_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem) for tests and isolated issuers."""
    with tempfile.TemporaryDirectory() as tmp:
        priv_path = Path(tmp) / "priv.pem"
        pub_path = Path(tmp) / "pub.pem"
        gen = subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(priv_path)],
            capture_output=True,
            check=False,
        )
        if gen.returncode != 0:
            raise ModeError("PROD_APPROVAL_REQUIRED", "openssl Ed25519 keygen failed")
        pub = subprocess.run(
            ["openssl", "pkey", "-in", str(priv_path), "-pubout", "-out", str(pub_path)],
            capture_output=True,
            check=False,
        )
        if pub.returncode != 0:
            raise ModeError("PROD_APPROVAL_REQUIRED", "openssl Ed25519 pubout failed")
        return priv_path.read_bytes(), pub_path.read_bytes()


def _ed25519_sign(canonical: bytes, private_pem: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        priv_path = Path(tmp) / "priv.pem"
        msg_path = Path(tmp) / "msg"
        sig_path = Path(tmp) / "sig"
        priv_path.write_bytes(private_pem)
        os.chmod(priv_path, 0o600)
        msg_path.write_bytes(canonical)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(priv_path),
                "-rawin",
                "-in",
                str(msg_path),
                "-out",
                str(sig_path),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not sig_path.is_file():
            raise ModeError("PROD_APPROVAL_REQUIRED", "openssl Ed25519 sign failed")
        return sig_path.read_bytes()


def _ed25519_verify(canonical: bytes, signature: bytes, public_pem: bytes) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        pub_path = Path(tmp) / "pub.pem"
        msg_path = Path(tmp) / "msg"
        sig_path = Path(tmp) / "sig"
        pub_path.write_bytes(public_pem)
        msg_path.write_bytes(canonical)
        sig_path.write_bytes(signature)
        result = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(pub_path),
                "-rawin",
                "-in",
                str(msg_path),
                "-sigfile",
                str(sig_path),
            ],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0


def sign_approval_ed25519(payload: Mapping[str, Any], private_pem: bytes) -> str:
    return "ed25519:" + _ed25519_sign(_canonical(payload), private_pem).hex()


def issuer_allowlist() -> frozenset[str]:
    raw = (os.environ.get("PROD_APPROVAL_ISSUER_ALLOWLIST") or "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def sign_approval(payload: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def issue_approval(
    *,
    issuer: str,
    subject: str,
    action: str,
    environment: str,
    target: str,
    commit_sha: str,
    image_digests: Iterable[str],
    nonce: str,
    expires_at: str,
    key: bytes,
    run_id: str = "",
    manifest_digest: str = "",
) -> dict[str, Any]:
    if issuer.strip() == "" or subject.strip() == "":
        raise ModeError("PROD_APPROVAL_REQUIRED", "issuer and subject are required")
    if issuer == subject:
        raise ModeError(
            "SELF_APPROVAL_FORBIDDEN",
            "an operator cannot approve their own production action",
        )
    payload: dict[str, Any] = {
        "action": action,
        "environment": environment,
        "target": target,
        "commit_sha": commit_sha,
        "run_id": run_id,
        "manifest_digest": manifest_digest,
        "image_digests": list(image_digests),
        "nonce": nonce,
        "expires_at": expires_at,
        "issuer": issuer,
        "subject": subject,
    }
    payload["signature"] = sign_approval(payload, key)
    return payload


def issue_asymmetric_approval(
    *,
    issuer: str,
    subject: str,
    action: str,
    environment: str,
    target: str,
    commit_sha: str,
    image_digests: Iterable[str],
    nonce: str,
    expires_at: str,
    private_pem: bytes,
    run_id: str = "",
    manifest_digest: str = "",
) -> dict[str, Any]:
    if issuer.strip() == "" or subject.strip() == "":
        raise ModeError("PROD_APPROVAL_REQUIRED", "issuer and subject are required")
    if issuer == subject:
        raise ModeError(
            "SELF_APPROVAL_FORBIDDEN",
            "an operator cannot approve their own production action",
        )
    payload: dict[str, Any] = {
        "action": action,
        "environment": environment,
        "target": target,
        "commit_sha": commit_sha,
        "run_id": run_id,
        "manifest_digest": manifest_digest,
        "image_digests": list(image_digests),
        "nonce": nonce,
        "expires_at": expires_at,
        "issuer": issuer,
        "subject": subject,
    }
    payload["signature"] = sign_approval_ed25519(payload, private_pem)
    return payload


def _parse_expires(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def nonce_store_path() -> Path:
    raw = (os.environ.get("PROD_APPROVAL_NONCE_DIR") or "").strip()
    if not raw:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            "PROD_APPROVAL_NONCE_DIR is required for durable replay protection",
        )
    return Path(raw)


def consume_nonce_durable(nonce: str, directory: Path | None = None) -> None:
    """Atomically consume *nonce* in a shared directory (O_EXCL)."""
    if not nonce or not nonce.strip():
        raise ModeError("PROD_APPROVAL_INVALID", "approval nonce is missing")
    root = directory if directory is not None else nonce_store_path()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            f"approval nonce directory is not writable: {type(exc).__name__}",
        ) from exc
    digest = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    path = root / digest
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ModeError("PROD_APPROVAL_INVALID", "approval proof was replayed") from exc
    except OSError as exc:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            f"approval nonce could not be consumed: {type(exc).__name__}",
        ) from exc
    try:
        os.write(fd, nonce.encode("utf-8"))
    finally:
        os.close(fd)


def verify_approval(
    proof: Mapping[str, Any],
    *,
    operator: str,
    action: str,
    environment: str,
    target: str,
    image_digests: Iterable[str],
    key: bytes,
    now: datetime | None = None,
    seen_nonces: MutableSet[str] | None = None,
    expected_commit_sha: str | None = None,
    expected_run_id: str | None = None,
    expected_manifest_digest: str | None = None,
    dirty_worktree: bool = False,
    durable_nonce_dir: Path | None = None,
    enforce_issuer_allowlist: bool = False,
    require_asymmetric: bool = False,
    public_key_pem: bytes | None = None,
) -> None:
    required = {
        "action",
        "environment",
        "target",
        "commit_sha",
        "image_digests",
        "nonce",
        "expires_at",
        "issuer",
        "subject",
        "signature",
    }
    missing = required - proof.keys()
    if missing:
        raise ModeError(
            "PROD_APPROVAL_REQUIRED",
            f"production approval proof missing fields: {sorted(missing)}",
        )
    issuer = str(proof["issuer"])
    subject = str(proof["subject"])
    if issuer == subject or subject != operator:
        raise ModeError(
            "SELF_APPROVAL_FORBIDDEN",
            "an operator cannot approve their own production action",
        )
    if enforce_issuer_allowlist:
        allowed = issuer_allowlist()
        if not allowed or issuer not in allowed:
            raise ModeError(
                "SELF_ISSUED_APPROVAL",
                "approval issuer is not on the host allowlist",
            )
    presented = str(proof["signature"])
    if require_asymmetric:
        if not presented.startswith("ed25519:"):
            raise ModeError(
                "SELF_ISSUED_APPROVAL",
                "production approval requires a signature the verifying process cannot mint",
            )
        pub = public_key_pem if public_key_pem is not None else production_verify_pubkey()
        try:
            raw_sig = bytes.fromhex(presented.split(":", 1)[1])
        except ValueError as exc:
            raise ModeError("PROD_APPROVAL_INVALID", "approval signature is malformed") from exc
        if not _ed25519_verify(_canonical(proof), raw_sig, pub):
            raise ModeError("PROD_APPROVAL_INVALID", "forged or corrupted approval proof")
    else:
        expected_sig = sign_approval(proof, key)
        if not hmac.compare_digest(expected_sig, presented):
            raise ModeError("PROD_APPROVAL_INVALID", "forged or corrupted approval proof")
    if str(proof["action"]) != action or str(proof["environment"]) != environment:
        raise ModeError("PROD_APPROVAL_INVALID", "approval is bound to a different action")
    if str(proof["target"]) != target:
        raise ModeError("PROD_APPROVAL_INVALID", "approval is bound to a different target")
    presented_digests = [str(x) for x in (proof.get("image_digests") or ())]
    expected_digests = [str(x) for x in image_digests]
    if presented_digests != expected_digests:
        raise ModeError("PROD_APPROVAL_INVALID", "approval digest binding mismatch")
    if expected_commit_sha is not None and str(proof["commit_sha"]) != expected_commit_sha:
        raise ModeError(
            "PROD_APPROVAL_INVALID",
            "approval is bound to a different commit",
        )
    if expected_run_id is not None and str(proof.get("run_id") or "") != expected_run_id:
        raise ModeError(
            "PROD_APPROVAL_INVALID",
            "approval is bound to a different run",
        )
    if (
        expected_manifest_digest is not None
        and str(proof.get("manifest_digest") or "") != expected_manifest_digest
    ):
        raise ModeError(
            "PROD_APPROVAL_INVALID",
            "approval is bound to a different deploy manifest",
        )
    if dirty_worktree:
        raise ModeError(
            "PROD_APPROVAL_INVALID",
            "production deploy refuses a dirty worktree",
        )
    when = now if now is not None else datetime.now(timezone.utc)
    try:
        expires = _parse_expires(str(proof["expires_at"]))
    except ValueError as exc:
        raise ModeError("PROD_APPROVAL_INVALID", "approval expiry is malformed") from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= when:
        raise ModeError("PROD_APPROVAL_INVALID", "approval proof has expired")
    nonce = str(proof["nonce"])
    if seen_nonces is not None:
        if nonce in seen_nonces:
            raise ModeError("PROD_APPROVAL_INVALID", "approval proof was replayed")
        seen_nonces.add(nonce)
        return
    consume_nonce_durable(nonce, durable_nonce_dir)


def unix_expires_in(seconds: int) -> str:
    return datetime.fromtimestamp(time.time() + seconds, tz=timezone.utc).isoformat()
