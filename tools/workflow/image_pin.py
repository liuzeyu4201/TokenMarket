"""Production image references must be digest-pinned repo@sha256:... values."""

from __future__ import annotations

import re
import subprocess
from typing import Callable, Iterable

InspectFn = Callable[[str], str]


def is_digest_pinned(ref: str) -> bool:
    text = (ref or "").strip()
    if not text or ":latest" in text.split("@", 1)[0]:
        return False
    if "@sha256:" not in text:
        return False
    name, digest = text.rsplit("@", 1)
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        return False
    if re.fullmatch(r"[0-9a-f]{64}", digest[7:]) is None:
        return False
    # Tag-only (no digest) already rejected. Name may include a tag before @.
    return bool(name) and "://" not in name


def require_digest_pinned_image(ref: str, *, name: str = "image") -> str:
    from .deploy_env.lifecycle import DeployError

    text = (ref or "").strip()
    if not is_digest_pinned(text):
        raise DeployError(
            "INVALID_CONFIG",
            f"tag-only or mutable production image reference rejected for {name}: {text}",
        )
    return text


def digest_from_ref(ref: str) -> str:
    pinned = require_digest_pinned_image(ref)
    return pinned.rsplit("@", 1)[1]


def inspect_image_digest(ref: str) -> str:
    from .deploy_env.lifecycle import DeployError

    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeployError("IMAGE_UNAVAILABLE", f"cannot inspect image {ref}")
    ident = result.stdout.strip()
    if ident.startswith("sha256:"):
        return ident
    raise DeployError("DIGEST_MISMATCH", f"inspected identifier is not a digest: {ident}")


def tagged_name(ref: str) -> str:
    return require_digest_pinned_image(ref).rsplit("@", 1)[0]


def verify_approved_digests(
    refs: Iterable[str],
    *,
    inspect: InspectFn | None = None,
) -> None:
    from .deploy_env.lifecycle import DeployError

    inspect_fn = inspect if inspect is not None else inspect_image_digest
    for ref in refs:
        expected = digest_from_ref(ref)
        expected_hex = expected.split(":", 1)[-1]
        inspected = inspect_fn(tagged_name(ref))
        inspected_hex = inspected.split(":", 1)[-1]
        if inspected_hex != expected_hex:
            raise DeployError(
                "DIGEST_MISMATCH",
                "image content changed after approval; refusing deploy",
            )
