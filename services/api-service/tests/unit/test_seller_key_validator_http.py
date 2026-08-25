"""SF06 HTTP validator adapter."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from app.domain.sellerkeys.validator_http import FailClosedValidator, GatewayValidator


def test_fail_closed() -> None:
    snap = FailClosedValidator().validate(
        platform="volcano", api_key="sk-x", request_id="r"
    )
    assert snap.error_category == "temporary_unavailable"


def test_gateway_validator_maps_body() -> None:
    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            n = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(n)
            body = json.dumps(
                {
                    "error_category": "success",
                    "remaining_quota": "12",
                    "quota_unit": "token",
                    "validity": "valid",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    srv = HTTPServer(("127.0.0.1", 0), H)
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address
        url = f"http://{host}:{port}/internal/v1/provider-credentials/validate"
        v = GatewayValidator(url, "tok")
        snap = v.validate(platform="volcano", api_key="sk-synthetic", request_id="r")
        assert snap.error_category == "success"
        assert snap.remaining_quota == "12"
    finally:
        srv.shutdown()


def test_gateway_validator_unreachable() -> None:
    v = GatewayValidator("http://127.0.0.1:1/validate", "tok", timeout=0.05)
    snap = v.validate(platform="volcano", api_key="sk-x", request_id="r")
    assert snap.error_category == "temporary_unavailable"
