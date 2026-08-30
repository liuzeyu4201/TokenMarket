"""SSRF guards for Provider Connection base URLs."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

Resolver = Callable[[str, int], list[str]]
Fetcher = Callable[[str], tuple[int, dict[str, str], bytes]]


class SsrfError(ValueError):
    def __init__(self, message: str = "目标地址不被允许") -> None:
        super().__init__(message)
        self.code = "SSRF_REJECTED"
        self.message = message


_METADATA = frozenset(
    {
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
    }
)

OFFICIAL_BASE = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "vertex": "https://aiplatform.googleapis.com",
}


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(item[4][0]) for item in infos]


def validate_base_url(
    url: str,
    *,
    resolver: Resolver = default_resolver,
    skip_resolve: bool = False,
) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise SsrfError("仅允许 HTTPS")
    if parsed.username or parsed.password:
        raise SsrfError("URL 不得包含用户信息")
    host = (parsed.hostname or "").lower()
    if not host or host in _METADATA:
        raise SsrfError("主机不被允许")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _blocked_ip(literal):
        raise SsrfError("地址不被允许")
    if skip_resolve:
        return url
    try:
        addrs = resolver(host, parsed.port or 443)
    except OSError as exc:
        raise SsrfError("无法解析主机") from exc
    if not addrs:
        raise SsrfError("无法解析主机")
    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if _blocked_ip(ip):
            raise SsrfError("解析结果指向内网或元数据地址")
    return url


def reject_redirect(location: str, *, resolver: Resolver = default_resolver) -> None:
    """Never follow redirects; Location must still pass SSRF."""
    if not location:
        raise SsrfError("重定向不被允许")
    target = location
    if location.startswith("/"):
        raise SsrfError("重定向不被允许")
    validate_base_url(target, resolver=resolver)
    raise SsrfError("重定向不被允许")


def guarded_fetch(
    url: str,
    fetch: Fetcher,
    *,
    resolver: Resolver = default_resolver,
) -> tuple[int, dict[str, str], bytes]:
    """Call fetch(url) with redirects forbidden.

    fetch returns (status, headers, body).
    """
    validate_base_url(url, resolver=resolver)
    status, headers, body = fetch(url)
    loc = ""
    for key, val in headers.items():
        if key.lower() == "location":
            loc = val
            break
    if 300 <= int(status) < 400 or loc:
        joined = urljoin(url, loc) if loc else url
        reject_redirect(joined, resolver=resolver)
    return int(status), headers, body
