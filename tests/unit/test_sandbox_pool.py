"""Docker 沙盒预热池的容量与生命周期测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from omichub.infrastructure.sandbox.pool import SandboxPool, SandboxUnavailableError


class _FakeContainer:
    def __init__(self, container_id: str, labels: dict[str, str] | None = None) -> None:
        self.id = container_id
        self.labels = labels or {"omicshub.sandbox": "warm"}

class _FakeContainers:
    def __init__(self) -> None:
        self.created: list[_FakeContainer] = []

    def run(self, **kwargs: object) -> _FakeContainer:
        container = _FakeContainer(f"sandbox-{len(self.created) + 1}", kwargs["labels"])
        self.created.append(container)
        return container

    def get(self, container_id: str) -> _FakeContainer:
        return next(container for container in self.created if container.id == container_id)


class _FakeClient:
    def __init__(self) -> None:
        self.containers = _FakeContainers()


def _settings(*, warm_size: int = 2, max_size: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        sandbox_warm_pool_size=warm_size,
        sandbox_max_pool_size=max_size,
        sandbox_default_memory="1g",
        sandbox_default_cpu=1.0,
        sandbox_network_isolated=True,
        sandbox_docker_network="omichub_default",
        sandbox_image="omichub/sandbox-base:latest",
    )


@pytest.mark.unit
async def test_initialize_is_idempotent_and_respects_pool_limit() -> None:
    pool = SandboxPool()
    client = _FakeClient()
    pool._settings = _settings(warm_size=4, max_size=2)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True

    await pool.initialize()
    await pool.initialize()

    assert pool._warm_pool.qsize() == 2
    assert [container.id for container in client.containers.created] == ["sandbox-1", "sandbox-2"]


@pytest.mark.unit
async def test_get_or_create_rejects_requests_beyond_pool_limit() -> None:
    pool = SandboxPool()
    client = _FakeClient()
    pool._settings = _settings(warm_size=2, max_size=2)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True
    await pool.initialize()

    assert await pool.get_or_create_container() == "sandbox-1"
    assert await pool.get_or_create_container() == "sandbox-2"
    with pytest.raises(SandboxUnavailableError, match="最大容量"):
        await pool.get_or_create_container()
