"""用户路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_users():
    """获取用户列表"""
    return {"message": "list users"}


@router.get("/{user_id}")
async def get_user(user_id: str):
    """获取用户详情"""
    return {"user_id": user_id}
