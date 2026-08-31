"""Seller validation must not pin the event loop; global concurrency is bounded."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.actors import Actor
from app.domain.sellerkeys.crypto import CredentialEncryptor
from app.domain.sellerkeys.memory_store import MemoryKeyStore
from app.domain.sellerkeys.validator_http import GatewayValidator
from app.domain.sellerkeys.validator_port import ValidationSnapshot
from app.main import app


class SlowValidator:
    def __init__(self, delay: float = 0.4, limit: int = 2) -> None:
        self.delay = delay
        self.limit = limit
        self._lock = threading.Lock()
        self.inflight = 0
        self.max_inflight = 0

    def validate(
        self, *, platform: str, api_key: str, request_id: str
    ) -> ValidationSnapshot:
        with self._lock:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            time.sleep(self.delay)
            return ValidationSnapshot(
                "success", remaining_quota="10", quota_unit="token", validity="valid"
            )
        finally:
            with self._lock:
                self.inflight -= 1


@pytest.mark.asyncio
async def test_health_stays_responsive_and_validation_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELLER_VALIDATION_CONCURRENCY", "2")
    import app.api.v1.seller_keys as seller_keys_mod

    seller_keys_mod._validation_sema = None
    seller_keys_mod._validation_sema_n = 0
    validator = SlowValidator(delay=0.35, limit=2)
    app.state.actor_override = Actor(
        user_id=uuid.uuid4(), role="seller", status="active"
    )
    app.state.seller_key_store = MemoryKeyStore()
    app.state.seller_encryptor = CredentialEncryptor(b"k" * 32, "v1")
    app.state.seller_fp_secret = b"s" * 32
    app.state.seller_validator = validator
    app.state.version = "0.1.0"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def onboard(i: int) -> int:
            res = await client.post(
                "/api/v1/seller-keys",
                json={
                    "platform": "volcano",
                    "api_key": f"sk-synthetic-test-key-not-real-{i}",
                },
                headers={"Idempotency-Key": f"val-{i}"},
            )
            return res.status_code

        start = time.perf_counter()
        health_task = asyncio.create_task(client.get("/health/live"))
        onboard_tasks = [asyncio.create_task(onboard(i)) for i in range(4)]
        health = await asyncio.wait_for(health_task, timeout=0.2)
        elapsed = time.perf_counter() - start
        assert health.status_code == 200
        assert elapsed < 0.25
        codes = await asyncio.gather(*onboard_tasks)
        assert all(code in (200, 503) for code in codes)
        assert validator.max_inflight <= 2


@pytest.mark.asyncio
async def test_resume_validation_leaves_health_responsive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELLER_VALIDATION_CONCURRENCY", "2")
    import app.api.v1.seller_keys as seller_keys_mod

    seller_keys_mod._validation_sema = None
    seller_keys_mod._validation_sema_n = 0
    validator = SlowValidator(delay=0.35, limit=2)
    user = uuid.uuid4()
    enc = CredentialEncryptor(b"k" * 32, "v1")
    store = MemoryKeyStore()
    keys: list[uuid.UUID] = []
    for i in range(4):
        nonce, ct, tag = enc.encrypt(f"sk-synthetic-test-key-not-real-{i}".encode())
        kid = uuid.uuid4()
        store.insert(
            {
                "id": kid,
                "seller_id": user,
                "platform": "volcano",
                "fingerprint": f"fp-resume-{kid}",
                "ciphertext": ct,
                "nonce": nonce,
                "tag": tag,
                "administrative_state": "paused",
                "health_state": "unknown",
                "remaining_quota": "9",
                "soft_deleted": False,
                "version": 1,
            }
        )
        keys.append(kid)
    app.state.actor_override = Actor(user_id=user, role="seller", status="active")
    app.state.seller_key_store = store
    app.state.seller_encryptor = enc
    app.state.seller_fp_secret = b"s" * 32
    app.state.seller_validator = validator
    app.state.version = "0.1.0"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def resume(kid: uuid.UUID) -> int:
            res = await client.post(f"/api/v1/seller-keys/{kid}/resume")
            return res.status_code

        start = time.perf_counter()
        health_task = asyncio.create_task(client.get("/health/live"))
        resume_tasks = [asyncio.create_task(resume(k)) for k in keys]
        health = await asyncio.wait_for(health_task, timeout=0.2)
        elapsed = time.perf_counter() - start
        assert health.status_code == 200
        assert elapsed < 0.25
        codes = await asyncio.gather(*resume_tasks)
        assert all(code in (200, 409, 503) for code in codes)
        assert validator.max_inflight <= 2


def test_gateway_validator_global_concurrency_bound() -> None:
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    inflight = 0
    max_inflight = 0
    lock = threading.Lock()
    release = threading.Event()

    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            nonlocal inflight, max_inflight
            n = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(n)
            with lock:
                inflight += 1
                max_inflight = max(max_inflight, inflight)
            release.wait(timeout=1.0)
            body = json.dumps(
                {"error_category": "success", "remaining_quota": "1"}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            with lock:
                inflight -= 1

        def log_message(self, fmt: str, *args: object) -> None:
            return

    srv = HTTPServer(("127.0.0.1", 0), H)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address
        v = GatewayValidator(
            f"http://{host}:{port}/validate",
            "tok",
            timeout=2.0,
            max_concurrency=2,
        )
        workers = [
            threading.Thread(
                target=lambda: v.validate(
                    platform="volcano", api_key="sk-x", request_id="r"
                )
            )
            for _ in range(6)
        ]
        for w in workers:
            w.start()
        time.sleep(0.2)
        with lock:
            seen = max_inflight
        release.set()
        for w in workers:
            w.join()
        assert seen <= 2
        assert v.max_concurrency == 2
    finally:
        release.set()
        srv.shutdown()
