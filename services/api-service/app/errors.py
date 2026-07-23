"""Domain/transport errors that map to the unified business envelope."""

from __future__ import annotations


class DependencyUnavailableError(Exception):
    """A required dependency is missing or down; respond with envelope 503."""

    def __init__(
        self,
        code: str = "SERVICE_UNAVAILABLE",
        message: str = "服务暂时不可用，请稍后重试",
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
