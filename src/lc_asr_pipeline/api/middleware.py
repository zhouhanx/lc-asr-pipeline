"""Application-wide operation identity and HTTP security response headers."""

from __future__ import annotations

import logging
from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.operation_identity import (
    OPERATION_ID_HEADER,
    operation_reference,
)

# Uvicorn owns the application process logging configuration in this project.
# Reuse its error logger so operation events are emitted to logs/backend.log.
logger = logging.getLogger("uvicorn.error")


class OperationIdMiddleware:
    """Assign and safely log a unique server-generated ID for every HTTP operation."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        operation_id = operation_reference()
        state = scope.setdefault("state", {})
        state["operation_id"] = operation_id
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        started_at = perf_counter()
        status_code = 500
        response_started = False

        logger.info(
            "event=operation_started operation_id=%s method=%s path=%s",
            operation_id,
            method,
            path,
        )

        async def send_with_operation_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_started = True
                headers = MutableHeaders(scope=message)
                headers[OPERATION_ID_HEADER] = operation_id
            await send(message)

        try:
            await self._app(scope, receive, send_with_operation_id)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.exception(
                "event=operation_failed operation_id=%s method=%s path=%s "
                "status=500 duration_ms=%s",
                operation_id,
                method,
                path,
                duration_ms,
            )
            if response_started:
                raise
            body = b'{"detail":"Internal server error"}'
            await send_with_operation_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send_with_operation_id({"type": "http.response.body", "body": body})
        else:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            logger.info(
                "event=operation_completed operation_id=%s method=%s path=%s "
                "status=%s duration_ms=%s",
                operation_id,
                method,
                path,
                status_code,
                duration_ms,
            )


class SecurityHeadersMiddleware:
    """Apply conservative browser security and private-cache defaults."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self._app = app
        self._production = settings.app_env.casefold() == "production"
        self._hsts_seconds = settings.security_hsts_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Content-Security-Policy"] = (
                    "frame-ancestors 'none'; base-uri 'none'; object-src 'none'"
                )
                headers["Cross-Origin-Resource-Policy"] = "same-site"
                headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
                )
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["X-XSS-Protection"] = "0"
                if self._production and self._hsts_seconds > 0:
                    headers["Strict-Transport-Security"] = (
                        f"max-age={self._hsts_seconds}; includeSubDomains"
                    )
            await send(message)

        await self._app(scope, receive, send_with_headers)
