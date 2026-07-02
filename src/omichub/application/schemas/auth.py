"""认证相关DTO模型"""

import re

from pydantic import Field, field_validator

from omichub.application.schemas.base import OmicsHubBaseSchema


class UserRegisterRequest(OmicsHubBaseSchema):
    """用户注册请求"""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$",
        description="用户名：字母/数字/下划线，3-50字符",
    )
    email: str = Field(
        ...,
        max_length=255,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="邮箱地址",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="密码：至少8位字符",
    )
    lab_group: str | None = Field(
        default=None,
        max_length=120,
        description="所属课题组（研究组/实验室，可空）",
    )

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """密码强度校验"""
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class RefreshTokenRequest(OmicsHubBaseSchema):
    """刷新 Token 请求"""

    refresh_token: str = Field(..., description="Refresh Token")


class TokenResponse(OmicsHubBaseSchema):
    """Token 响应体"""

    access_token: str = Field(description="访问令牌（短期有效，默认30分钟）")
    refresh_token: str = Field(description="刷新令牌（长期有效，默认7天）")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(description="访问令牌过期时间（秒）")
    first_login: bool = Field(
        default=False,
        description="是否为首次登录（last_login_at 为空时判定为 True），前端据此触发迎新引导",
    )
