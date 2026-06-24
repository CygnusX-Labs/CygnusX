"""流程定义路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_flows():
    """获取流程列表"""
    return {"message": "list flows"}


@router.get("/{flow_id}/schema")
async def get_flow_schema(flow_id: str):
    """获取流程的 JSON Schema（用于前端动态表单渲染）"""
    return {"flow_id": flow_id}
