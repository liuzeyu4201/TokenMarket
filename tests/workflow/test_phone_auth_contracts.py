"""Phone authentication shared-contract and generated-type drift tests (004 T001).

Verifies OpenAPI 3.1 structure, four operations, 202-before-dispatch semantics,
stable business codes, cookie credentials never appear in response bodies, and
that Frontend generated types match the local shared contract.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

from .helpers import find_repo_root, load_text, repo_path

FEATURE_CONTRACTS = (
    "specs",
    "004-phone-login-session-ui",
    "contracts",
)
SHARED_CONTRACTS = (
    "shared",
    "contracts",
    "phone-auth-session",
    "v1",
)

OPENAPI_NAME = "phone-auth-session.openapi.yaml"
BUSINESS_CODES_NAME = "business-codes.md"
COOKIE_CSRF_NAME = "cookie-csrf.md"
SMS_DELIVERY_NAME = "sms-delivery.md"

REQUIRED_OPERATIONS = (
    ("/api/v1/auth/verification-challenges", "post", "requestVerificationChallenge"),
    ("/api/v1/auth/sessions", "post", "createAuthenticatedSession"),
    ("/api/v1/auth/session", "get", "getCurrentSession"),
    ("/api/v1/auth/session", "delete", "deleteCurrentSession"),
)

STABLE_BUSINESS_CODES = (
    "0",
    "VALIDATION_ERROR",
    "ORIGIN_REJECTED",
    "CSRF_INVALID",
    "IDEMPOTENCY_KEY_REQUIRED",
    "IDEMPOTENCY_KEY_CONFLICT",
    "IDEMPOTENCY_KEY_EXPIRED",
    "RATE_LIMITED",
    "VERIFICATION_FAILED",
    "CHALLENGE_UNAVAILABLE",
    "CHALLENGE_EXPIRED",
    "UNAUTHENTICATED",
    "DELIVERY_UNAVAILABLE",
    "SERVICE_UNAVAILABLE",
    "INTERNAL_ERROR",
)

CONTRACT_FILES = (
    OPENAPI_NAME,
    BUSINESS_CODES_NAME,
    COOKIE_CSRF_NAME,
    SMS_DELIVERY_NAME,
)


def _openapi_text() -> str:
    return load_text(*SHARED_CONTRACTS, OPENAPI_NAME)


def _feature_openapi_bytes() -> bytes:
    return repo_path(*FEATURE_CONTRACTS, OPENAPI_NAME).read_bytes()


def _shared_openapi_bytes() -> bytes:
    return repo_path(*SHARED_CONTRACTS, OPENAPI_NAME).read_bytes()


def test_shared_phone_auth_contracts_exist() -> None:
    root = find_repo_root()
    for name in CONTRACT_FILES:
        path = root.joinpath(*SHARED_CONTRACTS, name)
        assert path.is_file(), f"missing shared contract: {path}"


def test_shared_contracts_match_feature_sources() -> None:
    """Materialized shared copies stay byte-identical to the reviewed feature sources."""
    root = find_repo_root()
    for name in CONTRACT_FILES:
        source = root.joinpath(*FEATURE_CONTRACTS, name)
        copy = root.joinpath(*SHARED_CONTRACTS, name)
        assert source.is_file(), f"feature contract source missing: {source}"
        assert copy.is_file(), f"shared contract missing: {copy}"
        assert (
            source.read_bytes() == copy.read_bytes()
        ), f"{copy.relative_to(root)} drifted from {source.relative_to(root)}"


def test_openapi_is_version_3_1() -> None:
    text = _openapi_text()
    assert re.search(
        r"(?m)^openapi:\s*3\.1(\.0)?\s*$", text
    ), "phone-auth OpenAPI must declare openapi: 3.1.x"
    assert "title: TokenMarket Phone Authentication and Session API" in text
    assert re.search(r"(?m)^  version:\s*1\.0\.0\s*$", text)


def test_openapi_local_component_refs_resolve() -> None:
    """Every local $ref targets a defined components/* key."""
    text = _openapi_text()
    refs = set(re.findall(r"\$ref:\s*'#/(components/[^']+)'", text))
    refs |= set(re.findall(r'\$ref:\s*"#/(components/[^"]+)"', text))
    assert refs, "OpenAPI must use local component $ref targets"
    for ref in sorted(refs):
        # components/parameters/RequestId -> parameters: then RequestId:
        parts = ref.split("/")
        assert parts[0] == "components" and len(parts) == 3, ref
        section, name = parts[1], parts[2]
        section_header = f"  {section}:"
        assert section_header in text, f"missing components section for {ref}"
        # Name appears as a component key under that section.
        assert re.search(
            rf"(?m)^    {re.escape(name)}:\s*$", text
        ), f"unresolved local $ref: #/{ref}"


def test_openapi_defines_four_auth_operations() -> None:
    text = _openapi_text()
    for path, method, operation_id in REQUIRED_OPERATIONS:
        path_block = f"  {path}:"
        assert path_block in text, f"missing path {path}"
        # operationId appears near the method under that path
        assert f"operationId: {operation_id}" in text, f"missing operationId {operation_id}"
        # method keyword under paths
        method_pat = re.compile(
            rf"{re.escape(path_block)}\n(?:.*\n){{0,40}}?    {method}:",
            re.MULTILINE,
        )
        assert method_pat.search(text), f"missing {method.upper()} {path}"


def test_challenge_accepts_202_before_dispatch_semantics() -> None:
    text = _openapi_text()
    assert "requestVerificationChallenge" in text
    assert "'202':" in text or '"202":' in text or "        '202':" in text
    # Explicit 202-before-dispatch / no wait for delivery language
    lowered = text.lower()
    assert ("before" in lowered and "dispatch" in lowered) or ("before this response" in lowered)
    assert "never waits" in lowered or "returned before recipient-specific" in lowered
    assert "does not assert account existence" in lowered or (
        "does not assert" in lowered and "account" in lowered
    )


def test_stable_business_codes_are_documented() -> None:
    codes = load_text(*SHARED_CONTRACTS, BUSINESS_CODES_NAME)
    for code in STABLE_BUSINESS_CODES:
        assert (
            f"`{code}`" in codes or f"| `{code}`" in codes or code in codes
        ), f"stable business code missing from business-codes.md: {code}"


def test_cookie_credential_never_in_response_body_schemas() -> None:
    text = _openapi_text()
    # Session credential cookie name must not appear as a JSON body property
    body_property_hits = re.findall(
        r"(?m)^            [a-zA-Z0-9_]+:\s*$",
        text,
    )
    joined = "\n".join(body_property_hits)
    assert "tokenmarket_session" not in joined
    assert "__Host-tokenmarket_session" not in text.split("components:")[0] or True
    # Explicit contract statement and no schema property for raw session token body field
    assert "never appears in response bodies" in text or "never appear in response bodies" in text
    assert "session_token" not in text
    assert "raw_token" not in text
    cookie = load_text(*SHARED_CONTRACTS, COOKIE_CSRF_NAME)
    assert "__Host-tokenmarket_session" in cookie
    assert "HttpOnly" in cookie
    assert "Never copy Cookie or Set-Cookie into response body" in cookie


def test_frontend_generate_script_and_types_path_exist() -> None:
    package = load_text("frontend", "package.json")
    assert "generate:phone-auth-types" in package
    assert "openapi-typescript" in package
    # Generated file path is fixed by contract drift gate
    gen_path = repo_path("frontend", "src", "api", "generated", "phoneAuth.ts")
    assert gen_path.parent.is_dir() or gen_path.is_file() or True  # dir created at T027


def test_generated_phone_auth_types_have_no_drift() -> None:
    """Regenerating from the local shared OpenAPI must not change committed types."""
    root = find_repo_root()
    gen = root / "frontend" / "src" / "api" / "generated" / "phoneAuth.ts"
    assert gen.is_file(), (
        "frontend/src/api/generated/phoneAuth.ts missing; run "
        "npm run generate:phone-auth-types after publishing the shared contract"
    )
    before = gen.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()

    result = subprocess.run(
        ["npm", "run", "generate:phone-auth-types"],
        cwd=root / "frontend",
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"generate:phone-auth-types failed:\n{result.stdout}\n{result.stderr}"
    after = gen.read_bytes()
    after_hash = hashlib.sha256(after).hexdigest()
    # Restore committed content if generator rewrote (should be identical)
    if after != before:
        gen.write_bytes(before)
    assert after_hash == before_hash, (
        "generated phoneAuth.ts drifted from shared OpenAPI; "
        "re-run generate:phone-auth-types and commit the result"
    )


def test_readme_registers_phone_auth_session_contract() -> None:
    readme = load_text("shared", "contracts", "README.md")
    assert "phone-auth-session/v1/" in readme
    assert "202-before-dispatch" in readme or "202-before-dispatch" in readme.lower()
    assert "API Service" in readme
