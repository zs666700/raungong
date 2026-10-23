"""REST 封装（FRONTEND.md 第 5 章）。

统一三件事：自动带 token、信封解包、错误码转异常；调用点不再判断状态码。
`TPA_MOCK=1` 时换成 `MockApiClient`，字段结构与真实后端完全一致。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from nicegui import app, ui

from . import config, mock_data
from .mock_store import MOCK_STORE

logger = logging.getLogger("tpa.frontend.api")


class ApiError(Exception):
    """后端信封里的业务错误。code 与 BACKEND.md 7.4 的 22 个错误码一致。"""

    def __init__(self, code: str, message: str, status: int = 0) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{code}: {message}")


def _token() -> str | None:
    try:
        return app.storage.user.get("token")
    except Exception:  # 背景任务里没有 client 上下文时不要炸
        return None


def _expire_session() -> None:
    try:
        app.storage.user.pop("token", None)
        app.storage.user.pop("user", None)
    except Exception:
        pass
    try:
        ui.navigate.to("/login")
    except Exception:
        pass


def _decode(body: Any, status: int) -> Any:
    if not isinstance(body, dict):
        raise ApiError("INTERNAL_ERROR", "服务返回了无法识别的数据", status)
    if not body.get("ok"):
        err = body.get("error") or {}
        raise ApiError(
            str(err.get("code") or "INTERNAL_ERROR"),
            str(err.get("message") or "请求失败"),
            status,
        )
    return body.get("data")


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.HTTP_TIMEOUT,
            headers={"Accept": "application/json"},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        handle_401: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = kwargs.pop("headers", {}) or {}
        token = _token()
        if auth and token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiError("NETWORK_ERROR", "请求超时，请稍后再试", 0) from exc
        except httpx.HTTPError as exc:
            logger.warning("网络请求失败 %s %s: %s", method, path, exc)
            raise ApiError("NETWORK_ERROR", "无法连接服务器", 0) from exc

        logger.debug("%s %s -> %s", method, path, resp.status_code)

        if resp.status_code == 401 and handle_401:
            # AUTH_BAD_CREDENTIALS 是登录表单自己的错误，不能在这里跳走
            _expire_session()
            raise ApiError("AUTH_TOKEN_INVALID", "登录已过期", 401)

        try:
            body = resp.json()
        except ValueError as exc:
            raise ApiError(
                "INTERNAL_ERROR", f"服务返回异常（HTTP {resp.status_code}）", resp.status_code
            ) from exc
        return _decode(body, resp.status_code)

    async def get(self, path: str, params: dict | None = None, **kw: Any) -> Any:
        return await self._request("GET", path, params=params, **kw)

    async def post(self, path: str, json: dict | None = None, **kw: Any) -> Any:
        return await self._request("POST", path, json=json, **kw)

    async def put(self, path: str, json: dict) -> Any:
        return await self._request("PUT", path, json=json)

    async def patch(self, path: str, json: dict) -> Any:
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self._request("DELETE", path, **kw)

    async def upload(self, path: str, files: dict, data: dict) -> Any:
        return await self._request("POST", path, files=files, data=data)


class MockApiClient:
    """没有后端时的替身：延迟、错误信封、字段都与真实服务一致。"""

    def __init__(self) -> None:
        self._username = "root"

    def _actor(self) -> str:
        try:
            user = app.storage.user.get("user") or {}
            return str(user.get("username") or "root")
        except Exception:
            return "root"

    async def _wait(self, seconds: float = 0.12) -> None:
        await asyncio.sleep(seconds)

    async def get(self, path: str, params: dict | None = None, **_kw: Any) -> Any:
        await self._wait()
        username = self._actor()
        route = path.removeprefix(config.API_PREFIX)

        if route == "/auth/me":
            return MOCK_STORE.me(username)

        if route == "/conversations":
            page = int((params or {}).get("page", 1))
            size = int((params or {}).get("page_size", 100))
            items = [
                MOCK_STORE.conversation_item(conv)
                for conv in MOCK_STORE.visible_conversations(username)
            ]
            return {"items": items[(page - 1) * size : page * size], "total": len(items)}

        if route.startswith("/conversations/") and route.endswith("/messages"):
            conv_id = route.split("/")[2]
            conv = MOCK_STORE.get_conversation(conv_id, username)
            return {
                "conversation": {"id": conv["id"], "title": conv["title"]},
                "items": MOCK_STORE.messages_for(conv_id),
            }

        if route == "/tools":
            return mock_data.clone(mock_data.TOOLS)

        if route == "/rag/documents":
            return {"items": MOCK_STORE.list_documents()}

        if route == "/rag/search":
            query = str((params or {}).get("q") or "")
            hits = MOCK_STORE.search(query)
            return {"query": query, "elapsed_ms": 46, "hits": hits}

        if route == "/admin/users":
            return {"items": MOCK_STORE.list_users(), "total": len(MOCK_STORE.users)}

        raise ApiError("NOT_FOUND", f"Mock 未实现：GET {path}", 404)

    async def post(self, path: str, json: dict | None = None, **kw: Any) -> Any:
        route = path.removeprefix(config.API_PREFIX)
        payload = json or {}

        if route == "/auth/login":
            await self._wait(0.25)
            username = str(payload.get("username") or "").strip()
            user = MOCK_STORE.user_by_name(username)
            if user is None or not payload.get("password"):
                raise ApiError("AUTH_BAD_CREDENTIALS", "用户名或密码错误", 401)
            if user["status"] != "active":
                raise ApiError("AUTH_DISABLED", "账号已被禁用", 403)
            self._username = username
            return {
                "token": MOCK_STORE.token_for(username),
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"],
                },
            }

        if route == "/auth/register":
            await self._wait(0.3)
            username = str(payload.get("username") or "").strip()
            password = str(payload.get("password") or "")
            if len(password) < 8:
                raise ApiError("AUTH_WEAK_PASSWORD", "密码至少 8 位", 400)
            user = MOCK_STORE.register(username, password)
            return {
                "token": MOCK_STORE.token_for(username),
                "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            }

        if route == "/conversations":
            await self._wait()
            conv = MOCK_STORE.create_conversation(self._actor(), payload.get("title"))
            return {k: conv[k] for k in ("id", "title", "created_at", "updated_at")}

        if route.startswith("/conversations/") and route.endswith("/messages"):
            conv_id = route.split("/")[2]
            await self._wait(0.6)
            return MOCK_STORE.send_sync(conv_id, str(payload.get("content") or ""))

        if route == "/rag/documents/from-url":
            await self._wait(0.8)
            url = str(payload.get("url") or "")
            return MOCK_STORE.add_document(
                str(payload.get("title") or "网页资料"), "url", url
            )

        if route.startswith("/tools/") and route.endswith("/invoke"):
            await self._wait(0.4)
            name = route.split("/")[2]
            return {
                "tool": name,
                "duration_ms": 288,
                "result": {
                    "ok": True,
                    "tool": name,
                    "provider": "amap",
                    "latency_ms": 271,
                    "data": {"note": "Mock 工具结果：真实模式请连后端"},
                    "error": None,
                },
            }

        raise ApiError("NOT_FOUND", f"Mock 未实现：POST {path}", 404)

    async def put(self, path: str, json: dict) -> Any:
        await self._wait(0.2)
        route = path.removeprefix(config.API_PREFIX)
        if route == "/auth/profile":
            profile = {k: v for k, v in (json or {}).items() if v not in (None, "", [])}
            MOCK_STORE.profiles[self._actor()] = profile
            return {"profile": profile}
        raise ApiError("NOT_FOUND", f"Mock 未实现：PUT {path}", 404)

    async def patch(self, path: str, json: dict) -> Any:
        await self._wait(0.2)
        route = path.removeprefix(config.API_PREFIX)
        if route.startswith("/admin/users/"):
            user_id = route.split("/")[3]
            return MOCK_STORE.patch_user(user_id, json or {}, self._actor())
        if route.startswith("/conversations/"):
            conv_id = route.split("/")[2]
            return MOCK_STORE.rename(conv_id, str(json.get("title") or ""))
        raise ApiError("NOT_FOUND", f"Mock 未实现：PATCH {path}", 404)

    async def delete(self, path: str, **_kw: Any) -> Any:
        await self._wait(0.2)
        route = path.removeprefix(config.API_PREFIX)
        if route.startswith("/conversations/"):
            MOCK_STORE.delete(route.split("/")[2])
            return {"deleted": True}
        if route.startswith("/rag/documents/"):
            MOCK_STORE.delete_document(route.split("/")[3])
            return {"deleted": True}
        raise ApiError("NOT_FOUND", f"Mock 未实现：DELETE {path}", 404)

    async def upload(self, path: str, files: dict, data: dict) -> Any:
        await self._wait(1.2)
        file_tuple = files.get("file") or ("upload.txt", b"", "text/plain")
        filename = str(file_tuple[0])
        title = str(data.get("title") or filename.rsplit(".", 1)[0])
        return MOCK_STORE.add_document(title, "file", filename)


_api: ApiClient | MockApiClient | None = None


def get_api() -> ApiClient | MockApiClient:
    global _api
    if _api is None:
        _api = MockApiClient() if config.MOCK else ApiClient(config.BACKEND_BASE_URL)
    return _api
