"""Platform-wide HTTP operation identity tests."""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr
from starlette.types import Message, Receive, Scope, Send

from lc_asr_pipeline.api.middleware import OperationIdMiddleware
from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.operation_identity import OPERATION_ID_HEADER
from lc_asr_pipeline.main import create_app


async def _call_middleware(
    middleware: OperationIdMiddleware,
) -> tuple[str, Scope]:
    messages: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "server": ("test", 80),
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "method": "DELETE",
        "root_path": "",
        "path": "/api/v1/resume-writer/documents/example",
        "raw_path": b"/api/v1/resume-writer/documents/example",
        "query_string": b"",
        "headers": [
            (
                OPERATION_ID_HEADER.lower().encode(),
                b"OP-00000000-0000-4000-8000-000000000000",
            )
        ],
        "state": {},
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await middleware(scope, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = {
        key.decode("latin-1").casefold(): value.decode("latin-1") for key, value in start["headers"]
    }
    return headers[OPERATION_ID_HEADER.casefold()], scope


@pytest.mark.asyncio
async def test_every_http_operation_gets_a_unique_logged_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = OperationIdMiddleware(app)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    first_id, first_scope = await _call_middleware(middleware)
    second_id, second_scope = await _call_middleware(middleware)

    assert first_id.startswith("OP-")
    assert second_id.startswith("OP-")
    UUID(first_id.removeprefix("OP-"))
    UUID(second_id.removeprefix("OP-"))
    assert first_id != second_id
    assert first_scope["state"]["operation_id"] == first_id
    assert second_scope["state"]["operation_id"] == second_id
    assert f"event=operation_started operation_id={first_id}" in caplog.text
    assert f"event=operation_completed operation_id={first_id}" in caplog.text


@pytest.mark.asyncio
async def test_application_exposes_operation_id_on_success_and_failure() -> None:
    app = create_app(
        Settings(
            postgres_user="test",
            postgres_password=SecretStr("test"),
            postgres_database="test",
            auth_secret_key=SecretStr("test-operation-secret-that-is-long-enough"),
            app_debug=True,
        )
    )

    @app.get("/unexpected-test-failure")
    async def unexpected_test_failure() -> None:
        raise RuntimeError("test failure")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        success = await client.get(
            "/api/v1/health/live",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        failure = await client.get(
            "/unexpected-test-failure",
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    success_id = success.headers[OPERATION_ID_HEADER]
    failure_id = failure.headers[OPERATION_ID_HEADER]
    UUID(success_id.removeprefix("OP-"))
    UUID(failure_id.removeprefix("OP-"))
    assert success_id != failure_id
    assert success.headers["access-control-expose-headers"] == OPERATION_ID_HEADER
    assert failure.status_code == 500
    assert failure.json() == {"detail": "Internal server error"}
    assert failure.headers["access-control-expose-headers"] == OPERATION_ID_HEADER
    assert failure.headers["x-content-type-options"] == "nosniff"
