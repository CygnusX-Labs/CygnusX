"""AI 助手聊天文件上传接口集成测试"""

import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from omichub.core.security import create_access_token
from omichub.infrastructure.config.storage_config import StorageConfig


@pytest.fixture
def storage_path(tmp_path: Path, monkeypatch) -> Path:
    """把存储根目录指向临时目录，避免测试写 /data/omichub。"""
    root = tmp_path / "data"

    def _fake_config():
        return StorageConfig(data_root=str(root), users_subdir="users")

    monkeypatch.setattr(
        "omichub.infrastructure.config.storage_config.get_storage_config", _fake_config
    )
    return root


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """生成测试用 Token（AuthMiddleware 仅校验签名，不查库）。"""
    token = create_access_token("test-user")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_chat_upload_csv(client: AsyncClient, auth_headers: dict[str, str], storage_path: Path) -> None:
    """CSV 文件应被成功接收并保存到用户 workspace/chat-uploads。"""
    csv_content = "gene,log2FoldChange,pvalue\nA1BG,1.0,0.01\n"
    response = await client.post(
        "/api/v1/files/chat-upload",
        files={"file": ("volcano_test_data.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "id" in body
    assert body["name"] == "volcano_test_data.csv"
    assert "/api/v1/files/chat-upload/test-user/" in body["url"]

    # 验证文件真实落盘到 workspace/chat-uploads
    expected_dir = storage_path / "users" / "test-user" / "workspace" / "chat-uploads"
    file_path = expected_dir / f"{body['id']}.csv"
    assert file_path.exists()
    assert file_path.read_text() == csv_content


@pytest.mark.asyncio
async def test_chat_upload_rejects_executable(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """可执行扩展名应被拒绝。"""
    response = await client.post(
        "/api/v1/files/chat-upload",
        files={"file": ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "禁止上传可执行文件" in response.text


@pytest.mark.asyncio
async def test_chat_upload_requires_auth(client: AsyncClient) -> None:
    """未携带 Token 应返回 401。"""
    response = await client.post(
        "/api/v1/files/chat-upload",
        files={"file": ("volcano_test_data.csv", io.BytesIO(b"x"), "text/csv")},
    )
    assert response.status_code == 401
