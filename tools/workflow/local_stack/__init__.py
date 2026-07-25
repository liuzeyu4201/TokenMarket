"""Local full-stack start/stop (middleware + host application processes).

``make start`` / ``make stop`` operate the complete environment. The optional
``scope=apps`` path operates only host processes. Middleware-only operations
remain owned by ``make dev`` / ``make dev-down``.
"""

from .lifecycle import start_local, stop_local

__all__ = ["start_local", "stop_local"]
