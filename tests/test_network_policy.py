import asyncio

import httpx
import pytest

from lc_asr_pipeline.api.routes.jobs import _subtitle_time
from lc_asr_pipeline.services.network_policy import (
    UnsafeProviderURL,
    enforce_provider_network_policy,
    validate_provider_url,
)
from lc_asr_pipeline.worker import _is_transient


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://user:secret@api.example.com/v1",
    ],
)
def test_external_provider_policy_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(UnsafeProviderURL):
        validate_provider_url(url)


def test_local_provider_policy_allows_loopback_http() -> None:
    assert validate_provider_url("http://127.0.0.1:8765", allow_private=True) == (
        "127.0.0.1",
        8765,
    )


@pytest.mark.asyncio
async def test_explicit_trusted_host_skips_synthetic_proxy_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_lookup(*args: object, **kwargs: object) -> list[object]:
        raise AssertionError("trusted host must not be resolved by the SSRF guard")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", forbidden_lookup)
    await enforce_provider_network_policy(
        "https://api.stepfun.com/v1",
        trusted_hosts={"api.stepfun.com"},
    )


def test_worker_retries_only_transient_provider_errors() -> None:
    request = httpx.Request("POST", "https://api.example.com")
    temporary = httpx.HTTPStatusError(
        "temporary",
        request=request,
        response=httpx.Response(503, request=request),
    )
    rejected = httpx.HTTPStatusError(
        "rejected",
        request=request,
        response=httpx.Response(400, request=request),
    )
    assert _is_transient(temporary)
    assert not _is_transient(rejected)


def test_subtitle_time_formats_srt_and_vtt() -> None:
    assert _subtitle_time(3661.234, vtt=False) == "01:01:01,234"
    assert _subtitle_time(3661.234, vtt=True) == "01:01:01.234"
