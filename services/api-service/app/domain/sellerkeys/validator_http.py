"""SF06 HTTP adapter: call gateway internal validate."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.domain.sellerkeys.validator_port import ValidationSnapshot


class GatewayValidator:
    def __init__(self, url: str, token: str, timeout: float = 3.5) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        payload = json.dumps(
            {"platform": platform, "api_key": api_key, "request_id": request_id}
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": self._token,
                "X-Request-ID": request_id,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return ValidationSnapshot("temporary_unavailable")
        cat = str(body.get("error_category") or "temporary_unavailable")
        quota = body.get("remaining_quota")
        unit = body.get("quota_unit")
        return ValidationSnapshot(
            error_category=cat,
            remaining_quota=str(quota) if quota is not None else None,
            quota_unit=str(unit) if unit is not None else None,
            validity=str(body.get("validity") or "unknown"),
        )


class FailClosedValidator:
    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        return ValidationSnapshot("temporary_unavailable")
