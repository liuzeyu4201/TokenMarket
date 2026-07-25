"""Default host ports and CLI/Make overrides for local start."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PortMap:
    """Loopback publish / listen ports for middleware facts and app processes."""

    postgres: int = 5432
    redis: int = 6379
    grafana: int = 3000
    gateway: int = 8080
    api: int = 8000
    billing: int = 8001
    admin: int = 8002
    frontend: int = 5173

    def pairwise_conflicts(self) -> list[str]:
        """Return human-safe messages if two roles share a port."""
        roles = {
            "postgres": self.postgres,
            "redis": self.redis,
            "grafana": self.grafana,
            "gateway": self.gateway,
            "api": self.api,
            "billing": self.billing,
            "admin": self.admin,
            "frontend": self.frontend,
        }
        by_port: dict[int, list[str]] = {}
        for name, port in roles.items():
            by_port.setdefault(port, []).append(name)
        return [
            f"port {port} assigned to {', '.join(names)}"
            for port, names in sorted(by_port.items())
            if len(names) > 1
        ]


_APP_KEY_TO_FIELD = {
    "GATEWAY_HOST_PORT": "gateway",
    "API_HOST_PORT": "api",
    "BILLING_HOST_PORT": "billing",
    "ADMIN_HOST_PORT": "admin",
    "FRONTEND_HOST_PORT": "frontend",
}


def _parse_port(raw: str, key: str) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer port") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{key} must be in 1..65535")
    return value


def resolve_ports(
    overrides: Mapping[str, str | int | None] | None = None,
    *,
    middleware_ports: Mapping[str, int] | None = None,
) -> PortMap:
    """Resolve app overrides and validated middleware configuration ports.

    PostgreSQL, Redis, and Grafana ports have one source of truth:
    ``.env.local``. Callers pass those already-validated values through
    ``middleware_ports``; similarly named shell variables are deliberately
    ignored.
    """
    data = {
        "postgres": 5432,
        "redis": 6379,
        "grafana": 3000,
        "gateway": 8080,
        "api": 8000,
        "billing": 8001,
        "admin": 8002,
        "frontend": 5173,
    }
    if middleware_ports:
        for field in ("postgres", "redis", "grafana"):
            middleware_raw = middleware_ports.get(field)
            if middleware_raw is not None:
                data[field] = _parse_port(
                    str(middleware_raw),
                    f"{field} port from .env.local",
                )
    if overrides:
        for key, field in _APP_KEY_TO_FIELD.items():
            app_raw = overrides.get(key)
            if app_raw is None or str(app_raw).strip() == "":
                continue
            data[field] = _parse_port(str(app_raw), key)
    ports = PortMap(**data)
    conflicts = ports.pairwise_conflicts()
    if conflicts:
        raise ValueError("port collision: " + "; ".join(conflicts))
    return ports
