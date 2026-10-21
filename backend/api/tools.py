"""工具接口（BACKEND.md 第 12 章）：列出工具状态、手动调用。

`/invoke` 不写消息、不消耗 LLM 配额，但必须要求登录（否则内网任何人可打爆高德 Key）。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

from ..config import settings
from ..deps import CurrentUser, McpManager
from ..errors import ApiError, ok
from ..schemas import ToolInvokeRequest
from ..services.rag_service import rag_service

logger = logging.getLogger("tpa.api.tools")

router = APIRouter(prefix="/tools", tags=["tools"])

KB_TOOL = {
    "name": "search_knowledge_base",
    "server": None,
    "description": "检索内置知识库，返回命中的文档片段与引用信息",
}


@router.get("")
async def list_tools(user: CurrentUser, manager: McpManager):
    """列出当前可用工具与 MCP Server 状态，前端"关于/调试"页和排障用。"""
    if manager is None:
        servers: list[dict[str, Any]] = []
        tools: list[dict[str, Any]] = []
        degraded = True
    else:
        payload = manager.status_payload()
        servers = payload["servers"]
        tools = payload["tools"]
        degraded = payload["degraded"]

    if settings.rag_enabled:
        tools = tools + [KB_TOOL]

    return ok({"servers": servers, "tools": tools, "degraded": degraded})


@router.post("/{name}/invoke")
async def invoke_tool(
    name: str,
    payload: ToolInvokeRequest,
    user: CurrentUser,
    manager: McpManager,
):
    """手动调一个工具，直接看到真实 JSON 结构。两层信封都保留。"""
    started = time.perf_counter()

    if name == KB_TOOL["name"]:
        query = str((payload.args or {}).get("query") or "")
        if not query.strip():
            raise ApiError("INVALID_ARGUMENT", "query 不能为空", 400)
        from ..db import SessionLocal

        async with SessionLocal() as db:
            result = await rag_service.search_payload(db, query)
        return ok(
            {
                "tool": name,
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "result": result,
            }
        )

    if manager is None:
        raise ApiError("TOOL_UNAVAILABLE", "MCP 不可用", 503)

    found = manager.find(name)
    if found is None:
        raise ApiError("TOOL_NOT_FOUND", f"工具 {name} 不存在", 404)
    runner, _info = found
    if runner.status != "connected":
        raise ApiError("TOOL_UNAVAILABLE", f"MCP Server {runner.name} 不可用", 503)

    try:
        envelope = await manager.invoke_raw(name, payload.args or {})
    except ApiError:
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("调用工具 %s 失败", name)
        raise ApiError("TOOL_FAILED", str(exc)[:200], 502) from exc

    return ok(
        {
            "tool": name,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "result": envelope,
        }
    )
