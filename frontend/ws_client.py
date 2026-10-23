"""WebSocket 封装（FRONTEND.md 第 6 章）。

只管连接、收发、重连；不碰 UI，帧一律通过回调交给页面。
`TPA_MOCK=1` 时用 `MockChatSocket` 模拟同样的 5 种下行帧。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from . import config
from .api_client import ApiError
from .mock_store import MOCK_STORE

logger = logging.getLogger("tpa.frontend.ws")

FrameHandler = Callable[[dict[str, Any]], None]

RECONNECT_DELAYS = (1, 2, 4, 8, 8)


def _frame(kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": kind, "data": data}


class ChatSocket:
    def __init__(self, ws_url: str, on_frame: FrameHandler) -> None:
        self._url = ws_url
        self._on_frame = on_frame
        self._ws: Any = None
        self._reader: asyncio.Task | None = None
        self._reconnect: asyncio.Task | None = None
        self._token = ""
        self._closing = False
        self.connected = False

    # ------------------------------------------------------------ 连接
    async def connect(self, token: str) -> None:
        self._token = token
        self._closing = False
        self.connected = False

        try:
            ws = await websockets.connect(
                self._url,
                max_size=1 << 20,
                open_timeout=10,
                close_timeout=5,
            )
        except asyncio.TimeoutError as exc:
            raise ApiError("NETWORK_ERROR", "连接对话服务超时", 0) from exc
        except (OSError, ConnectionClosed) as exc:
            raise ApiError("NETWORK_ERROR", "无法连接对话服务", 0) from exc

        self._ws = ws
        try:
            await ws.send(json.dumps({"type": "auth", "data": {"token": token}}))
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError as exc:
            await self._safe_close()
            raise ApiError("AUTH_TOKEN_INVALID", "认证超时", 401) from exc
        except ConnectionClosed as exc:
            await self._safe_close()
            raise self._auth_error(exc) from exc

        try:
            frame = json.loads(raw)
        except (TypeError, ValueError) as exc:
            await self._safe_close()
            raise ApiError("AUTH_TOKEN_INVALID", "认证响应异常", 401) from exc

        if frame.get("type") == "auth_ok":
            self.connected = True
            self._reader = asyncio.create_task(self._reader_loop())
            return

        data = frame.get("data") or {}
        code = str(data.get("code") or "AUTH_TOKEN_INVALID")
        await self._safe_close()
        raise ApiError(code, str(data.get("message") or "登录已过期"), 401)

    async def _reader_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    frame = json.loads(raw)
                except (TypeError, ValueError):
                    logger.warning("收到非 JSON 帧，已忽略")
                    continue
                if isinstance(frame, dict) and frame.get("type"):
                    self._emit(frame)
        except ConnectionClosed as exc:
            self.connected = False
            if self._closing:
                return
            code = getattr(exc, "code", 1006)
            if code == 4001:
                self._emit(_frame("_auth_failed", {"code": "AUTH_TOKEN_INVALID"}))
                return
            if code == 4002:
                self._emit(_frame("_gaveup", {"reason": "帧格式错误"}))
                return
            if code == 1000:
                self._emit(_frame("_closed"))
                return
            self._emit(_frame("_disconnected"))
            await self._reconnect_loop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.warning("WS 读取异常：%s", exc)
            self.connected = False
            if not self._closing:
                self._emit(_frame("_disconnected"))
                await self._reconnect_loop()

    async def _reconnect_loop(self) -> None:
        for delay in RECONNECT_DELAYS:
            await asyncio.sleep(delay)
            if self._closing:
                return
            try:
                await self.connect(self._token)
                self._emit(_frame("_reconnected"))
                return
            except ApiError as exc:
                if exc.status == 401 or exc.code.startswith("AUTH_"):
                    self._emit(_frame("_auth_failed", {"code": exc.code}))
                    return
                logger.info("WS 重连失败：%s", exc.message)
            except Exception as exc:  # pragma: no cover
                logger.info("WS 重连失败：%s", exc)
        if not self._closing:
            self._emit(_frame("_gaveup", {"reason": "连接已断开"}))

    async def _safe_close(self) -> None:
        self.connected = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    def _auth_error(self, exc: ConnectionClosed) -> ApiError:
        code = getattr(exc, "code", 4001)
        if code == 4001:
            return ApiError("AUTH_TOKEN_INVALID", "登录已过期", 401)
        return ApiError("NETWORK_ERROR", "连接对话服务失败", 0)

    def _emit(self, frame: dict[str, Any]) -> None:
        try:
            self._on_frame(frame)
        except Exception:  # pragma: no cover
            logger.exception("帧回调异常")

    # ------------------------------------------------------------ 发送
    async def send_message(self, conversation_id: str, content: str) -> None:
        if not self.connected or self._ws is None:
            raise ApiError("NETWORK_ERROR", "连接已断开", 0)
        try:
            await self._ws.send(
                json.dumps(
                    {
                        "type": "message",
                        "data": {"conversation_id": conversation_id, "content": content},
                    },
                    ensure_ascii=False,
                )
            )
        except ConnectionClosed as exc:
            self.connected = False
            raise ApiError("NETWORK_ERROR", "连接已断开，正在重连", 0) from exc

    async def send_cancel(self, conversation_id: str) -> None:
        if not self.connected or self._ws is None:
            return
        try:
            await self._ws.send(
                json.dumps(
                    {"type": "cancel", "data": {"conversation_id": conversation_id}},
                    ensure_ascii=False,
                )
            )
        except ConnectionClosed:
            self.connected = False

    async def close(self) -> None:
        self._closing = True
        self.connected = False
        if self._reconnect and not self._reconnect.done():
            self._reconnect.cancel()
        if self._reader and self._reader is not asyncio.current_task():
            self._reader.cancel()
        await self._safe_close()


class MockChatSocket:
    """模拟一轮流式生成：工具 → token → itinerary → done。"""

    def __init__(self, on_frame: FrameHandler) -> None:
        self._on_frame = on_frame
        self._task: asyncio.Task | None = None
        self._cancelled = asyncio.Event()
        self.connected = False

    async def connect(self, token: str) -> None:
        await asyncio.sleep(0.12)
        self.connected = True
        self._emit("auth_ok", {"user_id": "u_root", "role": "root"})

    async def send_message(self, conversation_id: str, content: str) -> None:
        if not self.connected:
            raise ApiError("NETWORK_ERROR", "连接已断开", 0)
        self._cancelled.clear()
        if self._task and not self._task.done():
            raise ApiError("CONV_BUSY", "该会话正在生成回复", 409)
        self._task = asyncio.create_task(self._simulate(conversation_id, content))

    async def send_cancel(self, conversation_id: str) -> None:
        self._cancelled.set()

    async def close(self) -> None:
        self.connected = False
        if self._task and not self._task.done():
            self._task.cancel()

    def _emit(self, kind: str, data: dict[str, Any] | None = None) -> None:
        try:
            self._on_frame({"type": kind, "data": data})
        except Exception:  # pragma: no cover
            logger.exception("Mock 帧回调异常")

    async def _simulate(self, conversation_id: str, content: str) -> None:
        from . import mock_data

        store = MOCK_STORE
        conv = store.get_conversation(conversation_id)
        first_round = len(store.messages_for(conversation_id)) == 0
        store.append_message(conversation_id, "user", content)

        tool_calls: list[dict[str, Any]] = []
        if first_round:
            script = [
                ("weather_forecast", "weather", {"city": "杭州", "days": 2},
                 "10/24 多云 18–24℃；10/25 阵雨 16–21℃", 0.32),
                ("place_search", "place", {"keywords": "西湖 景点", "city": "杭州"},
                 "命中 128 条，取前 10", 0.42),
                ("geo_geocode", "place", {"address": "西湖区北山街"},
                 "已定位北山街", 0.24),
                ("route_plan", "place",
                 {"origin": "120.148,30.259", "destination": "120.166,30.247", "mode": "walking"},
                 "0.85km / 12 分钟", 0.36),
            ]
        else:
            script = [
                ("place_search", "place", {"keywords": "雨天 茶室", "city": "杭州"},
                 "命中 36 条，取前 6", 0.38),
            ]

        try:
            for name, _server, args, summary, seconds in script:
                if self._cancelled.is_set():
                    await self._finish_cancelled(conversation_id, "", tool_calls)
                    return
                self._emit("tool", {"phase": "start", "name": name, "args": args})
                await asyncio.sleep(seconds)
                self._emit(
                    "tool",
                    {
                        "phase": "end",
                        "name": name,
                        "ok": True,
                        "ms": int(seconds * 1000),
                        "summary": summary,
                    },
                )
                tool_calls.append(
                    {"name": name, "args": args, "ok": True, "ms": int(seconds * 1000), "summary": summary}
                )

            text = mock_data.ASSISTANT_TEXT if first_round else (
                "可以。把这半天空出来，按 **一个主点 + 一段散步** 来排最省力：\n\n"
                "- 先去你住的地方附近解决午饭，避免中午跨城。\n"
                "- 下午只安排一个景点，留 40 分钟在附近咖啡馆休息。\n"
                "- 晚上如果还有体力，再去河边走 20 分钟，随时可以回酒店。\n\n"
                "需要我把这个安排补进现有的行程卡里吗？"
            )
            buffer: list[str] = []
            step = 7
            for index in range(0, len(text), step):
                if self._cancelled.is_set():
                    await self._finish_cancelled(conversation_id, "".join(buffer), tool_calls)
                    return
                delta = text[index : index + step]
                buffer.append(delta)
                self._emit("token", {"delta": delta})
                await asyncio.sleep(0.022)

            itinerary = mock_data.clone(mock_data.ITINERARY) if first_round else None
            citations = mock_data.clone(mock_data.CITATIONS) if first_round else []
            if itinerary:
                self._emit("itinerary", itinerary)
                await asyncio.sleep(0.18)

            final = "".join(buffer)
            store.append_message(
                conversation_id,
                "assistant",
                final,
                status="completed",
                itinerary=itinerary,
                citations=citations,
                tool_calls=tool_calls or None,
            )
            conv = store.get_conversation(conversation_id)
            self._emit(
                "done",
                {
                    "status": "completed",
                    "message": {
                        "id": f"mock_{conversation_id}",
                        "seq": 2,
                        "content": final,
                        "citations": citations,
                    },
                    "title": conv["title"],
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("Mock 生成异常")
            self._emit("error", {"code": "INTERNAL_ERROR", "message": str(exc)[:200]})

    async def _finish_cancelled(
        self, conversation_id: str, partial: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        store = MOCK_STORE
        store.append_message(
            conversation_id,
            "assistant",
            partial,
            status="cancelled",
            tool_calls=tool_calls or None,
        )
        conv = store.get_conversation(conversation_id)
        self._emit(
            "done",
            {
                "status": "cancelled",
                "message": {
                    "id": f"mock_{conversation_id}",
                    "seq": 2,
                    "content": partial,
                    "citations": [],
                },
                "title": conv["title"],
            },
        )


def create_chat_socket(on_frame: FrameHandler) -> ChatSocket | MockChatSocket:
    if config.MOCK:
        return MockChatSocket(on_frame)
    return ChatSocket(config.WS_CHAT_URL, on_frame)
