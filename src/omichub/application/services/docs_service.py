"""文档/知识库应用服务 —— 加载 docs/ 目录下的 YAML 配置与 Markdown 文件。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omichub.core.exceptions import NotFoundError

DOCS_ROOT = Path("docs")


class DocsService:
    """文档与知识库服务"""

    def __init__(self, docs_root: Path | str | None = None):
        self._root = Path(docs_root) if docs_root else DOCS_ROOT.resolve()

    def list_knowledge(self) -> dict[str, Any]:
        """获取实验室知识库导航配置"""
        return self._load_nav_config("knowledge", "meta.yaml")

    def get_knowledge_doc(self, doc_id: str) -> dict[str, Any]:
        """获取指定知识库文档内容"""
        return self._load_doc("knowledge", "meta.yaml", doc_id)

    def list_docs(self) -> dict[str, Any]:
        """获取文档中心导航配置"""
        return self._load_nav_config("docs", "nav.yaml")

    def get_doc(self, doc_id: str) -> dict[str, Any]:
        """获取指定文档内容"""
        return self._load_doc("docs", "nav.yaml", doc_id)

    def _load_nav_config(self, section: str, filename: str) -> dict[str, Any]:
        config_path = self._root / section / filename
        if not config_path.exists():
            raise NotFoundError(f"{section} 导航配置不存在")
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        # 仅返回导航信息，不包含文件正文
        return {
            "title": config.get("title", section),
            "items": [
                {"id": item.get("id"), "title": item.get("title")}
                for item in config.get("items", [])
                if item.get("id") and item.get("title")
            ],
        }

    def _load_doc(self, section: str, filename: str, doc_id: str) -> dict[str, Any]:
        config_path = self._root / section / filename
        if not config_path.exists():
            raise NotFoundError(f"{section} 导航配置不存在")

        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        items = config.get("items", [])
        target = next((item for item in items if item.get("id") == doc_id), None)
        if target is None:
            raise NotFoundError(f"文档 '{doc_id}' 不存在")

        file_name = target.get("file")
        if not file_name:
            raise NotFoundError(f"文档 '{doc_id}' 未配置文件")

        doc_path = self._root / section / file_name
        # 防止路径遍历：确保解析后的路径仍在 section 目录内
        try:
            doc_path.resolve().relative_to((self._root / section).resolve())
        except ValueError as exc:
            raise NotFoundError(f"非法文档路径: {file_name}") from exc

        if not doc_path.exists():
            raise NotFoundError(f"文档文件不存在: {file_name}")

        with doc_path.open("r", encoding="utf-8") as f:
            content = f.read()

        return {
            "id": doc_id,
            "title": target.get("title", doc_id),
            "content": content,
        }
