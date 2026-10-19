import socket
from types import SimpleNamespace

import pytest

from cygnusx.infrastructure.cache import redis_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_redis_fails_fast_when_host_resolution_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    redis_client._redis = None
    redis_client._redis_loop = None
    redis_client._redis_dns_disabled_until = 0.0
    redis_client._redis_dns_key = None
    monkeypatch.setattr(
        redis_client,
        "get_settings",
        lambda: SimpleNamespace(redis_host="missing-cache", redis_port=6379),
    )

    def fail_resolution(*_args: object, **_kwargs: object) -> list[object]:
        raise OSError("name resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)

    try:
        with pytest.raises(ConnectionError, match="Redis host is unavailable"):
            redis_client.get_redis()

        assert redis_client._redis is None
    finally:
        redis_client._redis = None
        redis_client._redis_loop = None
        redis_client._redis_dns_disabled_until = 0.0
        redis_client._redis_dns_key = None
