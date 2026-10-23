"""页面级状态与守卫（FRONTEND.md 3.2、11.1）。

token 与 user 都放在 `app.storage.user`（服务端存储），浏览器拿不到。
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import app, ui

from .api_client import ApiError, get_api

logger = logging.getLogger("tpa.frontend.state")

ERROR_TEXT: dict[str, str] = {
    "AUTH_BAD_CREDENTIALS": "用户名或密码错误",
    "AUTH_TOKEN_INVALID": "登录已过期",
    "AUTH_DISABLED": "账号已被禁用，请联系管理员",
    "AUTH_USERNAME_TAKEN": "用户名已被占用",
    "AUTH_WEAK_PASSWORD": "密码至少 8 位",
    "AUTH_REGISTER_CLOSED": "系统未开放注册，请联系管理员开号",
    "FORBIDDEN": "需要管理员权限",
    "NOT_FOUND": "会话不存在或已被删除",
    "CONV_BUSY": "正在生成回复，请稍候",
    "MSG_EMPTY": "消息不能为空",
    "INVALID_ARGUMENT": "参数不合法",
    "LLM_TIMEOUT": "生成超时，已保留部分内容",
    "LLM_FAILED": "模型暂时不可用",
    "TOOL_NOT_FOUND": "该工具不存在",
    "TOOL_FAILED": "工具调用失败",
    "TOOL_UNAVAILABLE": "该能力当前不可用",
    "RAG_DISABLED": "知识库未启用",
    "RAG_FILE_TYPE": "不支持该文件类型（支持 pdf/docx/md/txt/csv）",
    "RAG_FILE_TOO_LARGE": "文件超过 20MB",
    "RAG_EMPTY_TEXT": "未能提取到文本，可能是扫描版",
    "RAG_URL_BLOCKED": "该网址不允许抓取",
    "INTERNAL_ERROR": "服务出错了，请稍后再试",
    "NETWORK_ERROR": "无法连接服务器",
}


def human_error(exc: ApiError | None, fallback: str = "请求失败") -> str:
    if exc is None:
        return fallback
    text = ERROR_TEXT.get(exc.code)
    if text:
        return text
    return exc.message or fallback


def toast_error(exc: ApiError | None, fallback: str = "请求失败") -> None:
    text = human_error(exc, fallback)
    if exc is not None and exc.code in {"LLM_TIMEOUT", "LLM_FAILED"}:
        text = f"{text}，可点击重试"
    ui.notify(text, type="negative", position="top", multi_line=True)
    if exc is not None and exc.code == "FORBIDDEN":
        ui.navigate.to("/chat")


def save_session(token: str, user: dict[str, Any]) -> None:
    app.storage.user.update({"token": token, "user": user})


def clear_session() -> None:
    app.storage.user.pop("token", None)
    app.storage.user.pop("user", None)


def current_user() -> dict[str, Any] | None:
    return app.storage.user.get("user")


def current_token() -> str | None:
    return app.storage.user.get("token")


def logout() -> None:
    clear_session()
    ui.navigate.to("/login")


async def ensure_user() -> dict[str, Any] | None:
    """进页面先校验登录态，顺便拿最新 role（管理员可能刚改过）。"""
    token = current_token()
    if not token:
        ui.navigate.to("/login")
        return None

    cached = current_user()
    try:
        me = await get_api().get("/api/v1/auth/me")
    except ApiError as exc:
        if exc.status == 401 or exc.code in {"AUTH_TOKEN_INVALID", "AUTH_DISABLED"}:
            clear_session()
            ui.navigate.to("/login")
            return None
        if cached:
            ui.notify("无法连接服务器，正在使用缓存的登录信息", type="warning", position="top")
            return cached
        clear_session()
        ui.navigate.to("/login")
        return None

    if not isinstance(me, dict) or not me.get("role"):
        clear_session()
        ui.navigate.to("/login")
        return None
    save_session(token, me)
    if me.get("status") == "disabled":
        clear_session()
        ui.navigate.to("/login")
        return None
    return me


async def require_user() -> dict[str, Any] | None:
    return await ensure_user()


async def require_root() -> dict[str, Any] | None:
    user = await ensure_user()
    if user and user.get("role") != "root":
        ui.notify("需要管理员权限", type="warning", position="top")
        ui.navigate.to("/chat")
        return None
    return user


async def redirect_if_logged_in() -> bool:
    """登录页用：已登录直接进对话，token 失效则清掉。"""
    if not current_token():
        return False
    try:
        me = await get_api().get("/api/v1/auth/me")
    except ApiError:
        clear_session()
        return False
    if isinstance(me, dict) and me.get("role"):
        save_session(current_token() or "", me)
        ui.navigate.to("/chat")
        return True
    clear_session()
    return False
