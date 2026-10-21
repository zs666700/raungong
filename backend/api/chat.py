"""WebSocket 对话（BACKEND.md 第 11 章）。

三条纪律：
1. **生成是后台任务**，WS 只消费它的事件队列；断连不取消任务，跑完照常落库。
2. 上行只认 text 帧；token 不放在 URL 里，连上后发 auth 帧。
3. 除认证失败外，任何错误都只回 `error` 帧，连接保持。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..db import SessionLocal
from ..errors import ApiError
from ..models import Conversation, User
from ..security import decode_token
from ..services import chat_service

logger = logging.getLogger("tpa.api.chat")

router = APIRouter(tags=["chat"])

# 11.1 / 11.5
AUTH_WINDOW_SECONDS = 10
MAX_FRAME_BYTES = 64 * 1024
CLOSE_NORMAL = 1000
CLOSE_AUTH_FAILED = 4001
CLOSE_BAD_FRAME = 4002
CLOSE_SERVER_ERROR = 1011

END_OF_STREAM = "__end__"


def frame(kind: str, data: dict[str, Any] | None) -> dict[str, Any]:
    return {"type": kind, "data": data}


class EventSink:
    """把生成任务的产出塞进队列；连接断了就静默丢弃，任务照常跑完。"""

    def __init__(self, maxsize: int = 2000) -> None:
        self.queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize)
        self.alive = True

    def push(self, kind: str, payload: dict[str, Any]) -> None:
        if not self.alive:
            return
        try:
            self.queue.put_nowait((kind, payload))
        except asyncio.QueueFull:  # pragma: no cover
            logger.warning("WS 事件队列已满，丢弃 %s 事件", kind)

    def close(self) -> None:
        self.alive = False


def _ws_frame(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """agent 事件 -> WS 帧。tool 的开始与结束共用同一个 type，靠 phase 区分。"""
    if kind == "tool_start":
        return frame(
            "tool",
            {
                "phase": "start",
                "name": payload.get("name"),
                "args": payload.get("args"),
            },
        )
    if kind == "tool_end":
        return frame(
            "tool",
            {
                "phase": "end",
                "name": payload.get("name"),
                "ok": payload.get("ok"),
                "ms": payload.get("ms"),
                "summary": payload.get("summary"),
            },
        )
    if kind == "token":
        return frame("token", {"delta": payload.get("delta")})
    if kind == "itinerary":
        return frame("itinerary", payload)
    if kind == "done":
        return frame(
            "done",
            {
                "status": payload.get("status"),
                "message": payload.get("message"),
                "title": payload.get("title"),
            },
        )
    if kind == "error":
        return frame("error", payload)
    return frame(kind, payload)


class Connection:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.user: User | None = None
        self.send_lock = asyncio.Lock()
        self.pumps: dict[str, asyncio.Task] = {}
        self.closed = False

    async def send(self, payload: dict[str, Any]) -> None:
        if self.closed:
            return
        async with self.send_lock:
            try:
                await self.ws.send_json(payload)
            except (WebSocketDisconnect, RuntimeError) as exc:
                self.closed = True
                logger.info("WS 发送失败，连接已断: %s", exc)

    async def send_error(self, code: str, message: str) -> None:
        await self.send(frame("error", {"code": code, "message": message}))


async def _authenticate(token: str) -> User:
    payload = decode_token(token)
    async with SessionLocal() as db:
        user = await db.get(User, payload["sub"])
        if user is None:
            raise ApiError("AUTH_TOKEN_INVALID", "token 无效", 401)
        if user.status != "active":
            raise ApiError("AUTH_DISABLED", "账号已被禁用", 403)
        db.expunge(user)
        return user


async def _pump(conn: Connection, conv_id: str, sink: EventSink) -> None:
    """把队列里的事件逐条推给前端；连接断了就停，但生成任务继续跑完。"""
    try:
        while True:
            kind, payload = await sink.queue.get()
            if kind == END_OF_STREAM:
                break
            await conn.send(_ws_frame(kind, payload))
            if kind == "done":
                break
    except (WebSocketDisconnect, RuntimeError):
        conn.closed = True
    finally:
        sink.close()
        conn.pumps.pop(conv_id, None)


async def _run_round_task(
    conn: Connection, conv_id: str, sink: EventSink, content: str
) -> None:
    """后台生成任务：自己开 session、自己持锁、结束后释放锁。"""
    manager = getattr(conn.ws.app.state, "mcp", None)
    try:
        await chat_service.run_round(
            conversation_id=conv_id,
            user_id=conn.user.id if conn.user else "",
            content=content,
            emit=sink.push,
            manager=manager,
        )
    except ApiError as exc:
        sink.push("error", {"code": exc.code, "message": exc.message})
    except asyncio.CancelledError:
        logger.info("会话 %s 的生成任务已取消", conv_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("会话 %s 的生成任务异常", conv_id)
        sink.push("error", {"code": "INTERNAL_ERROR", "message": str(exc)[:200]})
    finally:
        # 收尾顺序：先让消费端退出，再释放锁
        try:
            sink.queue.put_nowait((END_OF_STREAM, {}))
        except asyncio.QueueFull:  # pragma: no cover
            pass
        sink.close()
        chat_service.pop_task(conv_id)
        chat_service.release(conv_id)


async def _handle_message(conn: Connection, data: dict[str, Any]) -> None:
    conv_id = str(data.get("conversation_id") or "")
    content = str(data.get("content") or "")
    assert conn.user is not None

    if not conv_id:
        await conn.send_error("INVALID_ARGUMENT", "缺少 conversation_id")
        return
    if not content.strip():
        await conn.send_error("MSG_EMPTY", "消息内容不能为空")
        return
    if len(content) > 8000:
        await conn.send_error("INVALID_ARGUMENT", "消息内容不能超过 8000 字符")
        return

    async with SessionLocal() as db:
        conv = await db.get(Conversation, conv_id)
        if conv is None or conv.user_id != conn.user.id:
            await conn.send_error("NOT_FOUND", "会话不存在")
            return

    if not await chat_service.try_acquire(conv_id):
        await conn.send_error("CONV_BUSY", "该会话正在生成回复")
        return

    sink = EventSink()
    conn.pumps[conv_id] = asyncio.create_task(_pump(conn, conv_id, sink))
    task = asyncio.create_task(_run_round_task(conn, conv_id, sink, content))
    chat_service.register_task(conv_id, task)


async def _handle_cancel(conn: Connection, data: dict[str, Any]) -> None:
    conv_id = str(data.get("conversation_id") or "")
    if not conv_id:
        await conn.send_error("INVALID_ARGUMENT", "缺少 conversation_id")
        return
    if not chat_service.cancel_round(conv_id):
        await conn.send_error("NOT_FOUND", "该会话正在生成回复或已结束")
        return
    logger.info("用户取消生成：%s", conv_id)


async def _read_frame(text: str) -> dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
        raise ApiError("INVALID_ARGUMENT", "帧超过 64 KB", 400)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ApiError("INVALID_ARGUMENT", "帧不是合法 JSON", 400) from exc
    if not isinstance(payload, dict) or "type" not in payload:
        raise ApiError("INVALID_ARGUMENT", "帧缺少 type", 400)
    data = payload.get("data")
    return {"type": str(payload.get("type")), "data": data if isinstance(data, dict) else {}}


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    conn = Connection(ws)

    try:
        # ---- 认证窗口：10 秒内必须发 auth 帧 ----
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_WINDOW_SECONDS)
        except (asyncio.TimeoutError, TimeoutError):
            logger.info("WS 认证超时")
            await ws.close(code=CLOSE_AUTH_FAILED)
            return
        except WebSocketDisconnect:
            return

        try:
            first = await _read_frame(raw)
        except ApiError as exc:
            await conn.send_error(exc.code, exc.message)
            await ws.close(code=CLOSE_BAD_FRAME)
            return

        if first["type"] != "auth":
            await conn.send_error("AUTH_TOKEN_INVALID", "首个帧必须是 auth")
            await ws.close(code=CLOSE_AUTH_FAILED)
            return

        try:
            conn.user = await _authenticate(str(first["data"].get("token") or ""))
        except ApiError as exc:
            await conn.send_error(exc.code, exc.message)
            await ws.close(code=CLOSE_AUTH_FAILED)
            return

        await conn.send(frame("auth_ok", {"user_id": conn.user.id, "role": conn.user.role}))

        # ---- 主循环 ----
        while True:
            try:
                raw = await ws.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                break

            try:
                message = await _read_frame(raw)
            except ApiError as exc:
                await conn.send_error(exc.code, exc.message)  # 帧格式错不踢连接
                continue

            kind = message["type"]
            if kind == "message":
                await _handle_message(conn, message["data"])
            elif kind == "cancel":
                await _handle_cancel(conn, message["data"])
            elif kind == "auth":
                await conn.send_error("INVALID_ARGUMENT", "已经认证过了")
            else:
                await conn.send_error("INVALID_ARGUMENT", f"不认识的帧类型: {kind}")

    except WebSocketDisconnect:
        logger.info("WS 客户端断开")
    except Exception as exc:  # pragma: no cover
        logger.exception("WS 未捕获异常")
        try:
            await conn.send_error("INTERNAL_ERROR", str(exc)[:200])
            await ws.close(code=CLOSE_SERVER_ERROR)
        except Exception:
            pass
    finally:
        # 连接断了只停消费：**不取消后台生成任务**，它跑完会自己落库
        conn.closed = True
        for pump in list(conn.pumps.values()):
            pump.cancel()
        logger.info("WS 连接关闭")
