"""Short-lived, read/prepare-only Node delegation. Never a browser access token."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import AuthenticationError, ConflictError, DependencyUnavailableError
from cygnusx.infrastructure.cache.redis_client import get_redis
from cygnusx.infrastructure.database.models.user import UserModel

ISSUER = "cygnusx-agent-tools"
AUDIENCE = "cygnusx-node-read-tools"


def _key() -> str:
    return hashlib.sha256(
        (get_settings().jwt_secret_key + ":bioops-delegation-v1").encode()
    ).hexdigest()


def _validate_claim_shapes(claims: dict[str, Any]) -> None:
    """Reject validly signed JWTs whose authorization claims have wrong types."""
    if any(not isinstance(claims.get(name), str) or not claims[name] for name in (
        "sub", "session_id", "jti",
    )):
        raise ValueError("DELEGATION_CLAIM_TYPE_INVALID")
    project_id = claims.get("project_id")
    if project_id is not None and (
        not isinstance(project_id, str) or not project_id
    ):
        raise ValueError("DELEGATION_CLAIM_TYPE_INVALID")
    scopes = claims.get("scopes")
    if not isinstance(scopes, list) or not scopes or any(
        not isinstance(scope, str) or not scope for scope in scopes
    ):
        raise ValueError("DELEGATION_CLAIM_TYPE_INVALID")
    token_version = claims.get("token_version")
    if (
        not isinstance(token_version, int)
        or isinstance(token_version, bool)
        or token_version < 0
    ):
        raise ValueError("DELEGATION_CLAIM_TYPE_INVALID")
    uuid.UUID(claims["sub"])
    if project_id is not None:
        uuid.UUID(project_id)


async def issue_delegation(context: ToolInvocationContext) -> str:
    user = await context.db.get(UserModel, uuid.UUID(context.user_id))
    if user is None or user.status != "active":
        raise AuthenticationError("用户不可用")
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": context.user_id,
            "session_id": context.session_id,
            "project_id": context.extra["project_id"],
            "scopes": context.extra["scopes"],
            "token_version": user.token_version,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(seconds=get_settings().agent_tool_delegation_ttl_seconds),
        },
        _key(),
        algorithm="HS256",
    )


async def verify_delegation(
    db: AsyncSession,
    token: str,
    capability: str,
    call_id: str,
) -> ToolInvocationContext:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            _key(),
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={
                "require": [
                    "sub",
                    "session_id",
                    "project_id",
                    "scopes",
                    "token_version",
                    "jti",
                    "iat",
                    "exp",
                ]
            },
        )
        _validate_claim_shapes(claims)
        uuid.UUID(call_id)
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise AuthenticationError("委托无效或过期") from exc
    gateway = AgentToolGateway(db)
    context = await gateway.context(
        claims["sub"], claims["session_id"], expected_agent="research_treasure_mouse"
    )
    user = await db.get(UserModel, uuid.UUID(context.user_id))
    allowed = {c["capability_id"]: c["scope"] for c in gateway.catalog(context)}
    if (
        user is None
        or user.token_version != claims["token_version"]
        or claims["project_id"] != context.extra["project_id"]
        or capability not in allowed
        or allowed[capability] not in claims["scopes"]
    ):
        raise AuthenticationError("委托授权已撤销或超出作用域")
    try:
        claimed = await get_redis().set(
            f"bioops:delegation:{claims['jti']}:{call_id}",
            "used",
            nx=True,
            ex=get_settings().agent_tool_delegation_ttl_seconds,
        )
    except (RedisError, OSError, TimeoutError) as exc:
        raise DependencyUnavailableError("委托防重放服务不可用") from exc
    if not claimed:
        raise ConflictError("工具调用已处理，禁止自动重放", code="DELEGATION_REPLAY_BLOCKED")
    context.extra["scopes"] = sorted(set(context.extra["scopes"]).intersection(claims["scopes"]))
    return context
