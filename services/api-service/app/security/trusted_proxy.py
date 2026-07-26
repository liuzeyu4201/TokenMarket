"""Trusted reverse-proxy client IP resolution (X-Forwarded-For).

Only when the socket peer is inside an explicit trusted CIDR allowlist is
``X-Forwarded-For`` consulted. The chain is stripped right-to-left of trusted
proxies; the first non-trusted hop is the client. Untrusted peers ignore XFF
entirely so clients cannot forge rate-limit identity.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Iterable


def _parse_networks(trusted_cidrs: Iterable[str]) -> list[object]:
    networks: list[object] = []
    for raw in trusted_cidrs:
        text = (raw or "").strip()
        if not text:
            continue
        try:
            networks.append(ip_network(text, strict=False))
        except ValueError:
            # Invalid CIDR entries are ignored at resolve time; config load
            # should have already rejected them for operator feedback.
            continue
    return networks


def _is_trusted(address: str, networks: list[object]) -> bool:
    try:
        ip = ip_address(address.strip())
    except ValueError:
        return False
    for net in networks:
        if ip in net:  # type: ignore[operator]
            return True
    return False


def _normalize_ip(value: str) -> str | None:
    text = value.strip()
    if not text or text.lower() in {"unknown", "null", "-"}:
        return None
    # Strip surrounding brackets used for IPv6 literals in some proxies.
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    # Drop optional :port on IPv4 (never on bare IPv6 without brackets).
    if text.count(":") == 1 and "." in text:
        host, _port = text.rsplit(":", 1)
        text = host
    try:
        return str(ip_address(text))
    except ValueError:
        return None


def resolve_client_ip(
    peer: str | None,
    xff: str | None,
    trusted_cidrs: Iterable[str],
) -> str:
    """Return the effective client IP for rate limiting and audit.

    Parameters
    ----------
    peer:
        Socket peer address (``request.client.host``).
    xff:
        Raw ``X-Forwarded-For`` header value, or None.
    trusted_cidrs:
        Explicit CIDR allowlist of reverse proxies.
    """
    networks = _parse_networks(trusted_cidrs)
    peer_ip = _normalize_ip(peer) if peer else None

    if peer_ip is None:
        # No verifiable peer — refuse to invent an identity from XFF.
        return "unknown"

    if not networks or not _is_trusted(peer_ip, networks):
        # Untrusted (or empty allowlist): ignore client-supplied XFF.
        return peer_ip

    if not xff or not str(xff).strip():
        return peer_ip

    # XFF is client, proxy1, ..., nearest-proxy. Strip trusted hops from the
    # right; first non-trusted address is the originating client.
    parts = [p.strip() for p in str(xff).split(",")]
    chosen = peer_ip
    for part in reversed(parts):
        hop = _normalize_ip(part)
        if hop is None:
            # Malformed hop aborts further leftward trust; keep last good.
            break
        if _is_trusted(hop, networks):
            chosen = hop
            continue
        return hop

    return chosen
