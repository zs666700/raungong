"""认证接口（BACKEND.md 第 8 章）：注册、登录、当前用户、画像。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import settings
from ..deps import CurrentUser, DbSession
from ..errors import ApiError, ok
from ..models import User, utcnow
from ..schemas import (
    LoginRequest,
    ProfileIn,
    RegisterRequest,
    user_brief,
    user_me,
)
from ..security import (
    assert_password_strength,
    create_access_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger("tpa.api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# 用户不存在时也跑一次校验，让两条分支耗时相当（8.2 的判定顺序说明）
_DUMMY_HASH = hash_password("tpa-dummy-password")


def _issue_token(user: User) -> dict:
    return {
        "token": create_access_token(
            user_id=user.id, username=user.username, role=user.role
        ),
        "user": user_brief(user),
    }


async def _find_by_username(db: DbSession, username: str) -> User | None:
    return (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession):
    """自助注册普通用户（role=user），受 TPA_ALLOW_REGISTER 控制。"""
    if not settings.allow_register:
        raise ApiError("AUTH_REGISTER_CLOSED", "未开放注册", 403)

    assert_password_strength(payload.password)
    username = payload.username.strip()
    if await _find_by_username(db, username) is not None:
        raise ApiError("AUTH_USERNAME_TAKEN", "用户名已存在", 409)

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role="user",
        status="active",
        profile={},
        created_at=utcnow(),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError("AUTH_USERNAME_TAKEN", "用户名已存在", 409) from exc
    await db.refresh(user)

    logger.info("新用户注册: %s", user.username)
    return ok(_issue_token(user))


@router.post("/login")
async def login(payload: LoginRequest, db: DbSession):
    """判定顺序不能乱：不存在 -> 禁用 -> 密码错。"""
    user = await _find_by_username(db, payload.username.strip())
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)  # 耗时对齐
        raise ApiError("AUTH_BAD_CREDENTIALS", "用户名或密码错误", 401)
    if user.status == "disabled":
        raise ApiError("AUTH_DISABLED", "账号已被禁用", 403)
    if not verify_password(payload.password, user.password_hash):
        raise ApiError("AUTH_BAD_CREDENTIALS", "用户名或密码错误", 401)

    return ok(_issue_token(user))


@router.get("/me")
async def me(user: CurrentUser):
    return ok(user_me(user))


@router.put("/profile")
async def update_profile(payload: ProfileIn, user: CurrentUser, db: DbSession):
    """整体替换画像：不传某个键就是清空该项；未知键忽略；`{}` 表示清空。"""
    profile = payload.model_dump(exclude_none=True)
    user.profile = profile
    await db.commit()
    await db.refresh(user)
    return ok({"profile": user.profile})
