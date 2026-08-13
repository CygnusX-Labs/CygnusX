"""聊天轻量沙盒产物收集与下载测试。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from omichub.api.v1.chat import download_chat_sandbox_artifact
from omichub.application.services import chat_sandbox_tools
from omichub.core.exceptions import ValidationError


def test_collect_artifacts_persists_files_and_builds_download_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = SimpleNamespace(
        copy_dir_out=AsyncMock(
            return_value=[
                {
                    "path": "carcinogenic pathways.xlsx",
                    "size": 128,
                    "mtime": 1.0,
                }
            ]
        )
    )
    monkeypatch.setattr(
        "omichub.core.config.get_settings",
        lambda: SimpleNamespace(storage_path=str(tmp_path)),
    )
    monkeypatch.setattr("omichub.infrastructure.sandbox.get_sandbox_pool", lambda: pool)

    artifacts = asyncio.run(
        chat_sandbox_tools._collect_artifacts("container-1", "user-1", "sandbox-1")
    )

    pool.copy_dir_out.assert_awaited_once_with(
        "container-1",
        "/tmp/chat_output",
        tmp_path / "chat_sandbox" / "user-1" / "sandbox-1" / "output",
    )
    assert artifacts == [
        {
            "path": "carcinogenic pathways.xlsx",
            "size": 128,
            "mtime": 1.0,
            "url": (
                "/api/v1/chat/sandbox-sessions/sandbox-1/artifacts/download"
                "?path=carcinogenic%20pathways.xlsx"
            ),
        }
    ]


def test_download_chat_sandbox_artifact_resolves_current_user_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "chat_sandbox" / "user-1" / "sandbox-1" / "output" / "result.xlsx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"xlsx")
    monkeypatch.setattr(
        "omichub.core.config.get_settings",
        lambda: SimpleNamespace(storage_path=str(tmp_path)),
    )

    response = asyncio.run(
        download_chat_sandbox_artifact("sandbox-1", "user-1", "result.xlsx")
    )

    assert Path(response.path) == target
    assert response.filename == "result.xlsx"


def test_download_chat_sandbox_artifact_blocks_path_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "omichub.core.config.get_settings",
        lambda: SimpleNamespace(storage_path=str(tmp_path)),
    )

    with pytest.raises(ValidationError, match="产物路径无效"):
        asyncio.run(
            download_chat_sandbox_artifact("sandbox-1", "user-1", "../../secret.txt")
        )
