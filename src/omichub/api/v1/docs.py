"""文档与知识库 API"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from omichub.application.services.docs_service import DocsService

router = APIRouter()

service = DocsService()


@router.get("/knowledge", tags=["Docs"])
async def list_knowledge() -> dict[str, Any]:
    """获取实验室知识库导航列表"""
    return service.list_knowledge()


@router.get("/knowledge/{doc_id}", tags=["Docs"])
async def get_knowledge_doc(doc_id: str) -> dict[str, Any]:
    """获取指定知识库文档内容"""
    return service.get_knowledge_doc(doc_id)


@router.get("/docs", tags=["Docs"])
async def list_docs() -> dict[str, Any]:
    """获取文档中心导航列表"""
    return service.list_docs()


@router.get("/docs/{doc_id}", tags=["Docs"])
async def get_doc(doc_id: str) -> dict[str, Any]:
    """获取指定文档内容"""
    return service.get_doc(doc_id)
