"""Docker 沙盒预热池的容量与生命周期测试。"""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.infrastructure.sandbox.pool import SandboxPool, SandboxUnavailableError


class _FakeContainer:
    def __init__(
        self,
        container_id: str,
        labels: dict[str, str] | None = None,
        status: str = "running",
    ) -> None:
        self.id = container_id
        self.labels = labels or {"cygnusx.sandbox": "warm"}
        self.status = status
        self.removed = False

    def stop(self, timeout: int = 5) -> None:
        self.status = "exited"

    def remove(self, force: bool = False) -> None:
        self.removed = True


class _FakeContainers:
    def __init__(self) -> None:
        self.created: list[_FakeContainer] = []

    def run(self, **kwargs: object) -> _FakeContainer:
        container = _FakeContainer(f"sandbox-{len(self.created) + 1}", kwargs["labels"])
        self.created.append(container)
        return container

    def get(self, container_id: str) -> _FakeContainer:
        return next(container for container in self.created if container.id == container_id)

    def list(self, all: bool = False, filters: dict | None = None) -> list[_FakeContainer]:
        label = (filters or {}).get("label")
        key, _, value = (label or "").partition("=")
        return [
            c
            for c in self.created
            if not c.removed and (not key or c.labels.get(key) == value)
        ]


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
        sandbox_docker_network="cygnusx_default",
        sandbox_image="cygnusx-sandbox-copilot:v0.0.2dev",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("language", "expected_prefix"),
    [
        ("python", ["python", "-c"]),
        ("r", ["/bin/sh", "-lc"]),
        ("bash", ["/bin/sh", "-lc"]),
    ],
)
def test_build_exec_command_supports_declared_languages(
    language: str, expected_prefix: list[str]
) -> None:
    command = SandboxPool._build_exec_command(language, "print('ok')")

    assert command[:2] == expected_prefix


@pytest.mark.unit
def test_build_exec_command_rejects_unknown_language() -> None:
    with pytest.raises(ValueError, match="不支持的沙盒语言"):
        SandboxPool._build_exec_command("julia", "println(1)")


@pytest.mark.unit
def test_parse_line_routes_plotly_marker_to_plotly_event() -> None:
    """show_plotly(fig) 的 %%PLOTLY%% 标记行解析为 plotly 事件（聊天轻量沙盒链路）"""
    figure = {"data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}], "layout": {}}
    line = "%%PLOTLY%%" + json.dumps(figure)

    assert SandboxPool._parse_line("stdout", line) == {"type": "plotly", "data": figure}
    # 坏 JSON 回退为普通 stdout，不丢输出
    assert SandboxPool._parse_line("stdout", "%%PLOTLY%%{bad") == {
        "type": "stdout",
        "data": "%%PLOTLY%%{bad",
    }
    # 非标记行不受影响
    assert SandboxPool._parse_line("stdout", "hello") == {"type": "stdout", "data": "hello"}
    assert SandboxPool._parse_line("stderr", "warn") == {"type": "stderr", "data": "warn"}


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


@pytest.mark.unit
async def test_initialize_adopts_orphan_containers_into_warm_pool() -> None:
    """重启后遗留的 running 孤儿容器应被收养复用，而不是重复新建"""
    pool = SandboxPool()
    client = _FakeClient()
    client.containers.created.extend(
        [_FakeContainer("orphan-1"), _FakeContainer("orphan-2")]
    )
    pool._settings = _settings(warm_size=2, max_size=4)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True

    await pool.initialize()

    assert pool._warm_pool.qsize() == 2
    assert {pool._warm_pool.get_nowait() for _ in range(2)} == {"orphan-1", "orphan-2"}
    # 没有新建容器
    assert [c.id for c in client.containers.list()] == ["orphan-1", "orphan-2"]


@pytest.mark.unit
async def test_initialize_destroys_orphans_beyond_pool_limit() -> None:
    """超出 max_pool_size 的孤儿容器应被销毁"""
    pool = SandboxPool()
    client = _FakeClient()
    orphans = [_FakeContainer(f"orphan-{i}") for i in range(1, 5)]
    client.containers.created.extend(orphans)
    pool._settings = _settings(warm_size=2, max_size=2)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True

    await pool.initialize()

    assert pool._warm_pool.qsize() == 2
    remaining = [c.id for c in client.containers.list()]
    assert len(remaining) == 2
    destroyed = [c for c in orphans if c.removed]
    assert len(destroyed) == 2


@pytest.mark.unit
async def test_initialize_keeps_active_session_containers_out_of_warm_queue() -> None:
    """活跃会话绑定的容器只登记计数，不进 warm 队列也不被销毁"""
    pool = SandboxPool()
    client = _FakeClient()
    client.containers.created.append(_FakeContainer("session-bound"))
    pool._settings = _settings(warm_size=2, max_size=3)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True

    await pool.initialize(keep_container_ids={"session-bound"})

    assert "session-bound" in pool._managed_container_ids
    assert pool._warm_pool.qsize() == 2
    remaining = {c.id for c in client.containers.list()}
    assert remaining == {"session-bound", "sandbox-2", "sandbox-3"}


@pytest.mark.unit
async def test_initialize_destroys_stopped_orphans() -> None:
    """已退出的孤儿容器直接销毁，不收养"""
    pool = SandboxPool()
    client = _FakeClient()
    client.containers.created.append(_FakeContainer("dead-1", status="exited"))
    pool._settings = _settings(warm_size=1, max_size=2)
    pool._warm_pool = asyncio.Queue(maxsize=pool._warm_pool_target())
    pool._client = client
    pool._available = True

    await pool.initialize()

    assert client.containers.get("dead-1").removed
    assert pool._warm_pool.qsize() == 1
    assert pool._warm_pool.get_nowait() == "sandbox-2"


# ===== copy_dir_out 产物落盘 =====


def _tar_bytes(top: str, entries: dict[str, bytes | None]) -> bytes:
    """模拟 docker get_archive 的输出：tar 以目录 basename 为顶层。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, content in entries.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            if content is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            else:
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


class _FakeArchiveAPI:
    def __init__(self, archives: dict[str, bytes]) -> None:
        self._archives = archives

    def get_archive(self, container_id: str, path: str):
        return iter([self._archives[path]]), {}


class _FakeArchiveClient:
    def __init__(self, archives: dict[str, bytes]) -> None:
        self.api = _FakeArchiveAPI(archives)


@pytest.mark.unit
async def test_copy_dir_out_second_empty_source_does_not_delete_first_outputs(
    tmp_path: Path,
) -> None:
    """回归：/tmp/chat_output 的产物先落盘后，/workspace/output 里的空
    figures/results 子目录上提时不得把同名目录连同文件一起删掉。"""
    archives = {
        "/tmp/chat_output": _tar_bytes(
            "chat_output",
            {"figures/a.png": b"png-bytes", "results": None},
        ),
        "/workspace/output": _tar_bytes(
            "output",
            {"figures": None, "results": None},
        ),
    }
    pool = SandboxPool()
    pool._client = _FakeArchiveClient(archives)
    host_dest = tmp_path / "host" / "output"

    first = await pool.copy_dir_out("container-1", "/tmp/chat_output", host_dest)
    assert [item["path"] for item in first] == ["figures/a.png"]

    second = await pool.copy_dir_out("container-1", "/workspace/output", host_dest)

    # 第一次落盘的文件必须仍在，且出现在第二次的全量清单里
    assert (host_dest / "figures" / "a.png").read_bytes() == b"png-bytes"
    assert [item["path"] for item in second] == ["figures/a.png"]


@pytest.mark.unit
async def test_copy_dir_out_merges_files_from_both_sources(tmp_path: Path) -> None:
    """两个来源目录的同名子目录应合并，同名文件以后到者为准。"""
    archives = {
        "/tmp/chat_output": _tar_bytes(
            "chat_output",
            {"figures/a.png": b"old", "results/t1.tsv": b"t1"},
        ),
        "/workspace/output": _tar_bytes(
            "output",
            {"figures/b.png": b"new-file", "results/t1.tsv": b"t1-v2"},
        ),
    }
    pool = SandboxPool()
    pool._client = _FakeArchiveClient(archives)
    host_dest = tmp_path / "host" / "output"

    await pool.copy_dir_out("container-1", "/tmp/chat_output", host_dest)
    items = await pool.copy_dir_out("container-1", "/workspace/output", host_dest)

    assert (host_dest / "figures" / "a.png").read_bytes() == b"old"
    assert (host_dest / "figures" / "b.png").read_bytes() == b"new-file"
    assert (host_dest / "results" / "t1.tsv").read_bytes() == b"t1-v2"
    assert sorted(item["path"] for item in items) == [
        "figures/a.png",
        "figures/b.png",
        "results/t1.tsv",
    ]
