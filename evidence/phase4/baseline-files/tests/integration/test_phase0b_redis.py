"""Optional real, isolated Redis and two independent consumer processes."""

import asyncio
import shutil
import socket
import sys

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from cygnusx.application.services.tool_confirmation_service import (
    ToolConfirmationService,
    _RedisStore,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_isolated_redis_two_processes_one_consumer(tmp_path):
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("BLOCKED: redis-server unavailable; configured Redis must not be used")
    try:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.bind(str(tmp_path / "probe.sock"))
    except PermissionError:
        pytest.skip("BLOCKED: sandbox prohibits local sockets")
    path = str(tmp_path / "redis.sock")
    server = await asyncio.create_subprocess_exec(
        executable, "--port", "0", "--unixsocket", path,
        "--save", "", "--appendonly", "no", "--dir", str(tmp_path),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    client = Redis(unix_socket_path=path, decode_responses=True)
    children = []
    try:
        for _ in range(100):
            try:
                if await client.ping():
                    break
            except (OSError, RedisError):
                pass
            await asyncio.sleep(0.05)
        else:
            pytest.fail("isolated Redis startup timed out")
        service = ToolConfirmationService(_RedisStore(client))
        record = await service.create_for_tool("isolated-owner", "isolated-write", {"value": 1})
        await service.approve_by_human(user_id="isolated-owner", confirmation_id=record.confirmation_id)
        assert await client.ttl(_RedisStore._KEY_PREFIX + record.confirmation_id) > 0
        worker = """
import asyncio, sys
from redis.asyncio import Redis
from cygnusx.application.services.tool_confirmation_service import ToolConfirmationService, _RedisStore, ConfirmationError
async def run():
    client = Redis(unix_socket_path=sys.argv[1], decode_responses=True)
    try:
        await ToolConfirmationService(_RedisStore(client)).consume_tool_confirmation(
            'isolated-owner', sys.argv[2], 'isolated-write', {'value': 1})
        print('CONSUMED')
    except ConfirmationError:
        print('REJECTED')
    finally:
        await client.aclose()
asyncio.run(run())
"""
        for _ in range(2):
            children.append(await asyncio.create_subprocess_exec(
                sys.executable, "-c", worker, path, record.confirmation_id,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ))
        results = await asyncio.wait_for(
            asyncio.gather(*(child.communicate() for child in children)), timeout=15,
        )
        assert all(child.returncode == 0 for child in children), results
        assert sorted(stdout.decode().strip() for stdout, _ in results) == ["CONSUMED", "REJECTED"]
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
            await asyncio.wait_for(child.wait(), timeout=5)
        await client.aclose()
        if server.returncode is None:
            server.terminate()
        await asyncio.wait_for(server.wait(), timeout=5)
