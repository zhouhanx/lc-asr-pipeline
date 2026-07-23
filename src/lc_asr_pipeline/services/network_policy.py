"""Network policy for server-side external model requests."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Collection
from urllib.parse import urlsplit


class UnsafeProviderURL(ValueError):
    pass


def validate_provider_url(url: str, *, allow_private: bool = False) -> tuple[str, int]:
    parsed = urlsplit(url)
    if parsed.username or parsed.password:
        raise UnsafeProviderURL("Provider URL must not contain credentials")
    if not parsed.hostname:
        raise UnsafeProviderURL("Provider URL must include a hostname")
    if allow_private:
        if parsed.scheme not in {"http", "https"}:
            raise UnsafeProviderURL("Local provider URL must use HTTP or HTTPS")
    elif parsed.scheme != "https":
        raise UnsafeProviderURL("External provider URL must use HTTPS")
    hostname = parsed.hostname.casefold().rstrip(".")
    if not allow_private and hostname in {"localhost", "localhost.localdomain"}:
        raise UnsafeProviderURL("External provider URL must not use localhost")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not allow_private and not address.is_global:
            raise UnsafeProviderURL("External provider URL must use a public address")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return hostname, port


async def enforce_provider_network_policy(
    url: str,
    *,
    allow_private: bool = False,
    trusted_hosts: Collection[str] = (),
) -> None:
    hostname, port = validate_provider_url(url, allow_private=allow_private)
    trusted = {item.casefold().rstrip(".") for item in trusted_hosts}
    if allow_private or hostname in trusted:
        return
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    if not records:
        raise UnsafeProviderURL("Provider hostname did not resolve")
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise UnsafeProviderURL("Provider hostname resolves to a non-public address")
