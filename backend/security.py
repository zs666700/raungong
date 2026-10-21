"""密码哈希（argon2id）+ JWT 编解码（HS256）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash

from .config import settings
from .errors import ApiError

_ISSUER = "tpa"
_ALGORITHM = "HS256"
_MIN_PASSWORD_LEN = 8

_password_hash = PasswordHash.recommended()  # pwdlib[argon2] -> Argon2id


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:  # 哈希损坏等，一律按不匹配处理
        return False


def assert_password_strength(password: str) -> None:
    if len(password or "") < _MIN_PASSWORD_LEN:
        raise ApiError("AUTH_WEAK_PASSWORD", f"密码至少 {_MIN_PASSWORD_LEN} 位", 400)


def create_access_token(*, user_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expire_hours)).timestamp()),
        "iss": _ISSUER,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """解不开/过期都算 AUTH_TOKEN_INVALID。

    注意：权限判断**不依赖** payload 里的 role——每次请求都回库查最新值。
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("AUTH_TOKEN_INVALID", "登录已过期，请重新登录", 401) from exc
    except jwt.PyJWTError as exc:
        raise ApiError("AUTH_TOKEN_INVALID", "token 无效", 401) from exc

    if not payload.get("sub"):
        raise ApiError("AUTH_TOKEN_INVALID", "token 无效", 401)
    return payload
