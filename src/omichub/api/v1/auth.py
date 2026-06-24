"""认证路由 - 登录、注册、令牌刷新"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login():
    """用户登录"""
    # TODO: 实现登录逻辑
    return {"message": "login endpoint"}


@router.post("/register")
async def register():
    """用户注册"""
    # TODO: 实现注册逻辑
    return {"message": "register endpoint"}


@router.post("/refresh")
async def refresh_token():
    """刷新访问令牌"""
    # TODO: 实现 refresh 逻辑
    return {"message": "refresh endpoint"}


@router.get("/me")
async def get_me():
    """获取当前用户信息"""
    # TODO: 实现获取当前用户
    return {"message": "me endpoint"}
