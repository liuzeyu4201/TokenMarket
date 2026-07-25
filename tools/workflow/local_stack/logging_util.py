"""Safe plain-text and JSONL logging for local start/stop."""

from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TextIO

_SECRET_RE = re.compile(r"tm_local_[A-Za-z0-9_-]+")
_USERINFO_RE = re.compile(r"(://[^:/@\s]+):([^@/\s]+)@")


def redact(text: str) -> str:
    """Strip synthetic secrets and URL userinfo from free text."""
    cleaned = _SECRET_RE.sub("[REDACTED]", text)
    return _USERINFO_RE.sub(r"\1:[REDACTED]@", cleaned)


@dataclass
class StartLog:
    """Correlation-scoped logger for one start/stop invocation."""

    action: str
    scope: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plain: bool = True
    stream: TextIO = field(default_factory=lambda: sys.stdout)
    lines: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def emit(self, phase: str, message: str, **fields: Any) -> None:
        safe_msg = redact(message)
        safe_fields = {k: redact(str(v)) if isinstance(v, str) else v for k, v in fields.items()}
        plain_line = f"[{phase}] {safe_msg}"
        if safe_fields:
            detail = " ".join(f"{k}={v}" for k, v in safe_fields.items())
            plain_line = f"{plain_line} {detail}"
        self.lines.append(plain_line)
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": f"local_stack.{self.action}.{phase.lower()}",
            "schema_version": "local-stack-1",
            "timestamp": self._ts(),
            "producer": "workflow.local_stack",
            "correlation_id": self.correlation_id,
            "payload": {
                "action": self.action,
                "scope": self.scope,
                "phase": phase,
                "message": safe_msg,
                **safe_fields,
            },
        }
        self.events.append(envelope)
        if self.plain:
            print(plain_line, file=self.stream, flush=True)
        else:
            print(
                json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )
