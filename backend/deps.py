"""认证依赖：current_user / require_root（BACKEND.md 7.5）。

有一条纪律：**每次请求都回库拿最新 role 与 status**，不信 token 里的值，
这样"禁用立即生效 / 改角色立即生效"都不用等 token 过期。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .errors import ApiError
from .models import User
from .security import decode_token
from .services.mcp_manager import MCPManager

_bearer = HTTPBearer(auto_error=False, description="Authorization: Bearer <token>")

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise ApiError("AUTH_TOKEN_INVALID", "未登录", 401)
    payload = decode_token(credentials.credentials)
    user = await db.get(User, payload["sub"])
    if user is None:
        raise ApiError("AUTH_TOKEN_INVALID", "token 无效", 401)
    if user.status != "active":
        raise ApiError("AUTH_DISABLED", "账号已被禁用", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_root(user: CurrentUser) -> User:
    if user.role != "root":
        raise ApiError("FORBIDDEN", "需要 root 权限", 403)
    return user


RootUser = Annotated[User, Depends(require_root)]


def get_mcp_manager(request: Request) -> MCPManager | None:
    """MCP 管理器在 lifespan 里挂到 app.state，工具路由从这里取。"""
    return getattr(request.app.state, "mcp", None)


McpManager = Annotated[MCPManager | None, Depends(get_mcp_manager)]
