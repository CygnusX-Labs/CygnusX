"""沙盒容器池管理 - Docker 预热容器池 + 代码执行

设计（轻量版，符合 1 人运维 / 单机部署原则）：
- warm pool 维护若干常驻容器（base image，sleep 保持存活）
- 会话亲和性：会话绑定一个 container_id，复用直至超时回收
- 代码执行：`docker exec -i <container> python -` 经 stdin 投递，stdout/stderr 流式回传
- 图表协议：脚本输出 `%%ECHARTS%%<json>` / `%%IMAGE%%<base64>` 标记行，由池解析为结构化输出
- Docker 不可用时优雅降级：is_available() 返回 False，调用方给出友好错误
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from loguru import logger

from omichub.core.config import get_settings

_ECHARTS_PREFIX = "%%ECHARTS%%"
_IMAGE_PREFIX = "%%IMAGE%%"
_SENTINEL = object()


class SandboxUnavailableError(Exception):
    """沙盒不可用（Docker 未就绪或镜像缺失）"""


class SandboxPool:
    """Docker 沙盒容器池"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: Any = None
        self._warm_pool: asyncio.Queue[str] = asyncio.Queue(
            maxsize=self._warm_pool_target()
        )
        self._managed_container_ids: set[str] = set()
        self._available: bool | None = None
        self._init_lock = asyncio.Lock()
        self._container_lock = asyncio.Lock()

    def _max_pool_size(self) -> int:
        return max(self._settings.sandbox_max_pool_size, 0)

    def _warm_pool_target(self) -> int:
        return min(max(self._settings.sandbox_warm_pool_size, 0), self._max_pool_size())

    # ------------------------------------------------------------------
    # Docker 客户端 & 可用性
    # ------------------------------------------------------------------
    def _get_client(self) -> Any:
        if self._client is None:
            import docker  # 延迟导入

            self._client = docker.from_env()
        return self._client

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            client = self._get_client()
            await asyncio.to_thread(client.ping)
            self._available = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"沙盒 Docker 不可用: {e}")
            self._available = False
        return self._available

    async def initialize(self) -> None:
        """预热容器池"""
        if not await self.is_available():
            logger.info("沙盒 Docker 不可用，跳过预热")
            return
        async with self._init_lock:
            while self._warm_pool.qsize() < self._warm_pool_target():
                try:
                    container_id = await self._warm_one()
                    if container_id:
                        await self._warm_pool.put(container_id)
                    else:
                        break
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"预热容器失败: {e}")
                    break
        logger.info(f"沙盒预热完成，池内 {self._warm_pool.qsize()} 个容器")

    # ------------------------------------------------------------------
    # 容器生命周期
    # ------------------------------------------------------------------
    async def get_or_create_container(self, container_name: str = "") -> str:
        if not await self.is_available():
            raise SandboxUnavailableError("沙盒 Docker 不可用")
        try:
            container_id = self._warm_pool.get_nowait()
            asyncio.create_task(self._warm_and_put())
            return container_id
        except asyncio.QueueEmpty:
            container_id = await self._warm_one(container_name)
            if container_id:
                return container_id
            raise SandboxUnavailableError("沙盒容器池已达到最大容量") from None

    async def _warm_and_put(self) -> None:
        try:
            cid = await self._warm_one()
            if cid:
                try:
                    self._warm_pool.put_nowait(cid)
                except asyncio.QueueFull:
                    await self.destroy(cid)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"补充预热失败: {e}")

    async def _warm_one(self, name: str = "") -> str | None:
        client = self._get_client()
        mem_limit = self._settings.sandbox_default_memory
        cpu_shares = int(self._settings.sandbox_default_cpu * 1024)

        def _run() -> str:
            network = None
            network_mode = None
            if self._settings.sandbox_network_isolated:
                network_mode = "none"
            else:
                network = self._settings.sandbox_docker_network
            container = client.containers.run(
                image=self._settings.sandbox_image,
                command=["sleep", "infinity"],
                detach=True,
                name=name or None,
                mem_limit=mem_limit,
                cpu_shares=cpu_shares,
                network=network,
                network_mode=network_mode,
                labels={"omicshub.sandbox": "warm"},
                tty=True,
            )
            return str(container.id)

        async with self._container_lock:
            if len(self._managed_container_ids) >= self._max_pool_size():
                return None
            container_id = await asyncio.to_thread(_run)
            self._managed_container_ids.add(container_id)
            return container_id

    async def destroy(self, container_id: str | None) -> None:
        if not container_id:
            return
        client = self._get_client()

        def _destroy() -> None:
            try:
                container = client.containers.get(container_id)
                container.stop(timeout=5)
                container.remove(force=True)
            except Exception:
                pass

        await asyncio.to_thread(_destroy)
        async with self._container_lock:
            self._managed_container_ids.discard(container_id)

    async def release(self, container_id: str | None) -> None:
        if not container_id:
            return
        if not self._warm_pool.full():
            await self._warm_pool.put(container_id)
        else:
            await self.destroy(container_id)

    # ------------------------------------------------------------------
    # 代码执行（流式）
    # ------------------------------------------------------------------
    async def stream_execute(
        self, container_id: str, code: str, timeout_sec: int | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """流式执行代码：docker exec -i <container> python -，stdin 投递代码"""
        timeout = timeout_sec or self._settings.sandbox_exec_timeout
        started = datetime.now()

        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "-i",
            container_id,
            "python",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None

        proc.stdin.write(code.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        queue: asyncio.Queue[Any] = asyncio.Queue()
        returncode = -1

        async def _reader(stream: asyncio.StreamReader, channel: str) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                await queue.put((channel, line.decode("utf-8", errors="replace").rstrip("\n")))
            await queue.put(_SENTINEL)

        async def _wait() -> int:
            return await proc.wait()

        reader_out = asyncio.create_task(_reader(proc.stdout, "stdout"))
        reader_err = asyncio.create_task(_reader(proc.stderr, "stderr"))
        wait_task = asyncio.create_task(_wait())
        pending_sentinels = 2
        timed_out = False

        async def _timeout_guard() -> None:
            await asyncio.sleep(timeout)
            proc.kill()

        guard = asyncio.create_task(_timeout_guard())

        try:
            while pending_sentinels > 0:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    if wait_task.done():
                        break
                    continue
                if item is _SENTINEL:
                    pending_sentinels -= 1
                    continue
                channel, line = item
                event = self._parse_line(channel, line)
                if event is not None:
                    yield event
        except TimeoutError:
            timed_out = True
        finally:
            guard.cancel()
            if not wait_task.done():
                proc.kill()
            returncode = await proc.wait() if not timed_out else -1
            for t in (reader_out, reader_err, wait_task, guard):
                t.cancel()
            duration = int((datetime.now() - started).total_seconds() * 1000)
            if timed_out:
                yield {"type": "error", "detail": f"代码执行超时（{timeout}s）"}
            yield {"type": "done", "exit_code": returncode, "duration_ms": duration}

    @staticmethod
    def _parse_line(channel: str, line: str) -> dict[str, Any] | None:
        if channel == "stdout":
            if line.startswith(_ECHARTS_PREFIX):
                try:
                    option = json.loads(line[len(_ECHARTS_PREFIX) :].strip())
                    return {"type": "echarts", "option": option}
                except json.JSONDecodeError:
                    return {"type": "stdout", "data": line}
            if line.startswith(_IMAGE_PREFIX):
                return {"type": "image", "data": line[len(_IMAGE_PREFIX) :].strip()}
            return {"type": "stdout", "data": line}
        return {"type": "stderr", "data": line}
