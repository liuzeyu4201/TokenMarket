"""SSRF allowlist for Provider Connection base URLs."""

from __future__ import annotations

import pytest

from app.domain.connections.ssrf import (
    SsrfError,
    guarded_fetch,
    reject_redirect,
    validate_base_url,
)


def _public(_host: str, _port: int) -> list[str]:
    return ["1.1.1.1"]


def _private(_host: str, _port: int) -> list[str]:
    return ["10.0.0.8"]


def _link_local(_host: str, _port: int) -> list[str]:
    return ["169.254.169.254"]


def _loopback(_host: str, _port: int) -> list[str]:
    return ["127.0.0.1"]


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com",
        "https://user:pass@api.openai.com",
        "https://localhost/v1",
        "https://localhost.localdomain/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://192.168.1.8/v1",
        "https://172.16.0.8/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/",
        "https://metadata/",
        "https://[::1]/",
        "https://0.0.0.0/",
    ],
)
def test_literal_and_scheme_rejected(url: str) -> None:
    with pytest.raises(SsrfError) as exc:
        validate_base_url(url, resolver=_public)
    assert exc.value.code == "SSRF_REJECTED"


def test_official_skip_resolve_does_not_dns() -> None:
    def boom(_host: str, _port: int) -> list[str]:
        raise AssertionError("must not resolve official defaults")

    out = validate_base_url("https://api.openai.com", resolver=boom, skip_resolve=True)
    assert out.startswith("https://")


def test_resolved_private_rejected() -> None:
    with pytest.raises(SsrfError, match="内网或元数据"):
        validate_base_url("https://evil.example", resolver=_private)


def test_resolved_metadata_rejected() -> None:
    with pytest.raises(SsrfError):
        validate_base_url("https://evil.example", resolver=_link_local)


def test_resolved_loopback_rejected() -> None:
    with pytest.raises(SsrfError):
        validate_base_url("https://evil.example", resolver=_loopback)


def test_resolver_oserror() -> None:
    def fail(_host: str, _port: int) -> list[str]:
        raise OSError("nxdomain")

    with pytest.raises(SsrfError, match="无法解析"):
        validate_base_url("https://missing.example", resolver=fail)


def test_resolver_empty() -> None:
    def empty(_host: str, _port: int) -> list[str]:
        return []

    with pytest.raises(SsrfError, match="无法解析"):
        validate_base_url("https://empty.example", resolver=empty)


def test_public_https_allowed() -> None:
    assert validate_base_url("https://api.example.com/v1", resolver=_public)


def test_empty_redirect_rejected() -> None:
    with pytest.raises(SsrfError, match="重定向"):
        reject_redirect("", resolver=_public)


def test_redirects_never_followed() -> None:
    with pytest.raises(SsrfError, match="重定向"):
        reject_redirect("https://api.example.com", resolver=_public)
    with pytest.raises(SsrfError, match="重定向"):
        reject_redirect("/internal", resolver=_public)
    with pytest.raises(SsrfError):
        reject_redirect("https://127.0.0.1/", resolver=_public)


def test_guarded_fetch_rejects_redirect_status() -> None:
    def fetch(_url: str) -> tuple[int, dict[str, str], bytes]:
        return 302, {"Location": "https://1.1.1.1/steal"}, b""

    with pytest.raises(SsrfError, match="重定向"):
        guarded_fetch("https://api.example.com", fetch, resolver=_public)


def test_guarded_fetch_rejects_location_on_200() -> None:
    def fetch(_url: str) -> tuple[int, dict[str, str], bytes]:
        return 200, {"location": "https://10.0.0.1/"}, b"ok"

    with pytest.raises(SsrfError):
        guarded_fetch("https://api.example.com", fetch, resolver=_public)


def test_guarded_fetch_ok_without_redirect() -> None:
    def fetch(_url: str) -> tuple[int, dict[str, str], bytes]:
        return 200, {"content-type": "text/plain"}, b"ok"

    status, headers, body = guarded_fetch(
        "https://api.example.com", fetch, resolver=_public
    )
    assert status == 200
    assert body == b"ok"
    assert "content-type" in headers
