"""Unit tests for trusted-proxy client IP resolution (T011)."""

from __future__ import annotations

from app.security.trusted_proxy import resolve_client_ip

TRUSTED_V4 = ["10.0.0.0/8", "127.0.0.1/32"]
TRUSTED_V6 = ["fd00::/8", "::1/128"]


def test_untrusted_peer_ignores_xff() -> None:
    ip = resolve_client_ip(
        peer="203.0.113.9",
        xff="1.2.3.4, 10.0.0.1",
        trusted_cidrs=TRUSTED_V4,
    )
    assert ip == "203.0.113.9"


def test_trusted_peer_strips_right_to_left() -> None:
    # XFF: original client, intermediate trusted proxy; peer is nearest proxy.
    ip = resolve_client_ip(
        peer="10.0.0.5",
        xff="198.51.100.7, 10.0.0.2",
        trusted_cidrs=TRUSTED_V4,
    )
    assert ip == "198.51.100.7"


def test_all_xff_hops_trusted_falls_back_to_leftmost_or_peer() -> None:
    ip = resolve_client_ip(
        peer="10.0.0.5",
        xff="10.0.0.9, 10.0.0.8",
        trusted_cidrs=TRUSTED_V4,
    )
    # After stripping all trusted hops, last chosen trusted hop remains.
    assert ip in {"10.0.0.9", "10.0.0.8", "10.0.0.5"}


def test_empty_trusted_list_ignores_xff() -> None:
    ip = resolve_client_ip(
        peer="203.0.113.1",
        xff="8.8.8.8",
        trusted_cidrs=[],
    )
    assert ip == "203.0.113.1"


def test_missing_xff_uses_peer() -> None:
    ip = resolve_client_ip(peer="10.0.0.1", xff=None, trusted_cidrs=TRUSTED_V4)
    assert ip == "10.0.0.1"


def test_ipv6_trusted_chain() -> None:
    ip = resolve_client_ip(
        peer="::1",
        xff="2001:db8::1, fd00::2",
        trusted_cidrs=TRUSTED_V6,
    )
    assert ip == "2001:db8::1"


def test_ipv4_mapped_and_loopback_cidrs() -> None:
    ip = resolve_client_ip(
        peer="127.0.0.1",
        xff="203.0.113.50",
        trusted_cidrs=["127.0.0.1/32"],
    )
    assert ip == "203.0.113.50"


def test_malformed_xff_hop_stops_leftward_parse() -> None:
    ip = resolve_client_ip(
        peer="10.0.0.1",
        xff="not-an-ip, 10.0.0.2",
        trusted_cidrs=TRUSTED_V4,
    )
    # Rightmost hop trusted then malformed left hop aborts → keep last good.
    assert ip in {"10.0.0.2", "10.0.0.1"}


def test_null_unknown_xff_tokens_ignored() -> None:
    ip = resolve_client_ip(
        peer="10.0.0.1",
        xff="unknown, null, -",
        trusted_cidrs=TRUSTED_V4,
    )
    assert ip == "10.0.0.1"


def test_missing_peer_returns_unknown() -> None:
    ip = resolve_client_ip(
        peer=None,
        xff="1.2.3.4",
        trusted_cidrs=TRUSTED_V4,
    )
    assert ip == "unknown"


def test_empty_peer_returns_unknown() -> None:
    ip = resolve_client_ip(peer="", xff="1.2.3.4", trusted_cidrs=TRUSTED_V4)
    assert ip == "unknown"


def test_multi_proxy_chain_selects_first_untrusted_from_right() -> None:
    ip = resolve_client_ip(
        peer="10.0.0.3",
        xff="203.0.113.1, 198.51.100.2, 10.0.0.2",
        trusted_cidrs=TRUSTED_V4,
    )
    # From right: 10.0.0.2 trusted, 198.51.100.2 not → client.
    assert ip == "198.51.100.2"


def test_whitespace_in_xff_tolerated() -> None:
    ip = resolve_client_ip(
        peer="10.0.0.1",
        xff="  203.0.113.9  ,  10.0.0.9  ",
        trusted_cidrs=TRUSTED_V4,
    )
    assert ip == "203.0.113.9"
