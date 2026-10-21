"""用户管理接口（BACKEND.md 第 14 章）。全部仅 root，且**不返回任何对话内容**。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from ..deps import DbSession, RootUser
from ..errors import ApiError, ok
from ..models import Conversation, User
from ..schemas import AdminUserPatchRequest, admin_user_item, user_brief

logger = logging.getLogger("tpa.api.admin")

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    user: RootUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """只返回会话**数量**，绝不返回对话内容——这是隐私边界。"""
    count_sq = (
        select(func.count(Conversation.id))
        .where(Conversation.user_id == User.id)
        .scalar_subquery()
    )
    stmt = (
        select(User, count_sq.label("cc"))
        .order_by(User.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()
    total = (await db.execute(select(func.count(User.id)))).scalar_one()

    items = [admin_user_item(u, int(cc or 0)) for u, cc in rows]
    return ok({"items": items, "total": int(total)})


async def _active_root_count(db: DbSession) -> int:
    return int(
        (
            await db.execute(
                select(func.count(User.id)).where(
                    User.role == "root", User.status == "active"
                )
            )
        ).scalar_one()
        or 0
    )


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: str, payload: AdminUserPatchRequest, user: RootUser, db: DbSession
):
    """改角色或启用/禁用。三条规则顺序不能省。"""
    target = await db.get(User, user_id)
    if target is None:
        raise ApiError("NOT_FOUND", "用户不存在", 404)

    # 1. 不能改自己
    if target.id == user.id:
        raise ApiError("FORBIDDEN", "不能修改自己的角色或状态", 403)

    new_role = payload.role or target.role
    new_status = payload.status or target.status

    # 2. 必须留至少一个 root + active
    losing_root = (
        target.role == "root"
        and target.status == "active"
        and (new_role != "root" or new_status != "active")
    )
    if losing_root and await _active_root_count(db) <= 1:
        raise ApiError("FORBIDDEN", "系统必须保留至少一个可用的 root 账号", 403)

    target.role = new_role
    target.status = new_status
    await db.commit()
    await db.refresh(target)

    logger.info("root %s 修改用户 %s -> role=%s status=%s", user.username, target.username, new_role, new_status)
    return ok(user_brief(target) | {"status": target.status})
