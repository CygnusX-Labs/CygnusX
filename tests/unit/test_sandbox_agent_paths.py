"""sandbox-agent 路径防护单元测试（无需 Docker，直接导入纯函数）"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_AGENT_PATH = Path(__file__).resolve().parents[2] / "deploy" / "studio" / "sandbox_agent.py"
_spec = importlib.util.spec_from_file_location("sandbox_agent", _AGENT_PATH)
assert _spec is not None and _spec.loader is not None
sandbox_agent = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("sandbox_agent", sandbox_agent)
_spec.loader.exec_module(sandbox_agent)

resolve_workspace_path = sandbox_agent.resolve_workspace_path
PathEscapeError = sandbox_agent.PathEscapeError


@pytest.mark.unit
def test_relative_path_resolves_inside_root(tmp_path: Path):
    """普通相对路径解析到工作区内"""
    resolved = resolve_workspace_path("output/plot.png", root=tmp_path)
    assert resolved == tmp_path / "output" / "plot.png"


@pytest.mark.unit
def test_dotdot_escape_rejected(tmp_path: Path):
    """../ 逃逸被拒绝"""
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("../etc/passwd", root=tmp_path)
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("a/../../outside", root=tmp_path)


@pytest.mark.unit
def test_absolute_path_outside_root_rejected(tmp_path: Path):
    """工作区外的绝对路径被拒绝"""
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("/etc/passwd", root=tmp_path)


@pytest.mark.unit
def test_absolute_path_inside_root_allowed(tmp_path: Path):
    """工作区内的绝对路径允许"""
    resolved = resolve_workspace_path(str(tmp_path / "input" / "data.csv"), root=tmp_path)
    assert resolved == tmp_path / "input" / "data.csv"


@pytest.mark.unit
def test_symlink_escape_rejected(tmp_path: Path):
    """软链解析后越界同样被拒绝"""
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    try:
        link = tmp_path / "evil-link"
        link.symlink_to(outside)
        with pytest.raises(PathEscapeError):
            resolve_workspace_path("evil-link/secret.txt", root=tmp_path)
    finally:
        (tmp_path / "evil-link").unlink(missing_ok=True)
        outside.rmdir()


@pytest.mark.unit
def test_root_itself_allowed(tmp_path: Path):
    """工作区根目录本身合法"""
    assert resolve_workspace_path(".", root=tmp_path) == tmp_path


# ===== 读路径放行（P1 数据不搬家：input/ 软链 → /data/platform 只读挂载） =====

resolve_workspace_read_path = sandbox_agent.resolve_workspace_read_path
PLATFORM_MOUNT_ROOT = sandbox_agent.PLATFORM_MOUNT_ROOT


@pytest.mark.unit
def test_read_path_inside_workspace_not_via_platform(tmp_path: Path):
    """工作区内读路径照常放行，via_platform=False"""
    resolved, via_platform = resolve_workspace_read_path("output/a.png", root=tmp_path)
    assert resolved == tmp_path / "output" / "a.png"
    assert via_platform is False


@pytest.mark.unit
def test_read_path_platform_symlink_allowed(tmp_path: Path):
    """input/ 下指向平台挂载的软链：读放行，返回容器内 /data/platform 路径"""
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "x.csv").symlink_to(str(PLATFORM_MOUNT_ROOT / "raw/x.csv"))
    resolved, via_platform = resolve_workspace_read_path("input/x.csv", root=tmp_path)
    assert via_platform is True
    assert resolved == PLATFORM_MOUNT_ROOT / "raw/x.csv"


@pytest.mark.unit
def test_read_path_direct_platform_absolute_rejected(tmp_path: Path):
    """直接拼平台挂载绝对路径被拒绝（只允许经工作区内软链跳转）"""
    with pytest.raises(PathEscapeError):
        resolve_workspace_read_path(str(PLATFORM_MOUNT_ROOT / "raw/x.csv"), root=tmp_path)


@pytest.mark.unit
def test_read_path_write_guard_unaffected(tmp_path: Path):
    """写守卫 resolve_workspace_path 对平台软链依然拒绝"""
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "x.csv").symlink_to(str(PLATFORM_MOUNT_ROOT / "raw/x.csv"))
    with pytest.raises(PathEscapeError):
        resolve_workspace_path("input/x.csv", root=tmp_path)

# ===== 执行输出边界 =====


@pytest.mark.unit
async def test_exec_stream_caps_output_and_persists_full_log(tmp_path: Path, monkeypatch):
    """流式 data 严格不超过 10KB，截断时 .logs 保存完整原始输出。"""
    monkeypatch.setattr(sandbox_agent, "WORKSPACE_ROOT", tmp_path)
    (tmp_path / "output").mkdir()
    payload = "x" * 30000
    request = sandbox_agent.ExecRequest(
        language="python", code=f'print("{payload}")', timeout=10
    )

    events = [
        json.loads(chunk.decode("utf-8"))
        async for chunk in sandbox_agent._stream_exec(request)
    ]

    streamed = "".join(
        event.get("data", "") for event in events if event.get("type") == "stdout"
    )
    result = next(event for event in events if event.get("type") == "result")
    assert len(streamed.encode("utf-8")) <= sandbox_agent.STREAM_CAP_BYTES
    assert result["exit_code"] == 0
    assert result["truncated_output_files"]
    log_path = tmp_path / result["truncated_output_files"][0]
    assert log_path.read_text(encoding="utf-8") == payload + "\n"


# ===== workspace_edit 反向上下文 =====

_reverse_edit_payload = sandbox_agent._reverse_edit_payload


@pytest.mark.unit
def test_reverse_edit_payload_uses_context_for_repeated_replacement():
    old = "alpha\nvalue = 1\nomega\nvalue = 2\n"
    old_string = "value = 1"
    new_string = "value = 2"
    index = old.index(old_string)
    new = old.replace(old_string, new_string, 1)

    reverse = _reverse_edit_payload(old, new, index, old_string, new_string)

    assert reverse is not None
    assert new.count(reverse["old_string"]) == 1
    assert new.replace(reverse["old_string"], reverse["new_string"], 1) == old


@pytest.mark.unit
def test_reverse_edit_payload_supports_deletion():
    old = "before\nremove me\nafter\n"
    old_string = "remove me\n"
    index = old.index(old_string)
    new = old.replace(old_string, "", 1)

    reverse = _reverse_edit_payload(old, new, index, old_string, "")

    assert reverse is not None
    assert reverse["old_string"]
    assert new.replace(reverse["old_string"], reverse["new_string"], 1) == old


@pytest.mark.unit
def test_reverse_edit_payload_returns_none_for_empty_result():
    assert _reverse_edit_payload("all", "", 0, "all", "") is None
