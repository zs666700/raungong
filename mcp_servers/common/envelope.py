"""工具统一返回信封（BACKEND.md 15.2 / 15.3）。

所有 MCP 工具**必须**返回同一个结构，不许返回裸数组或裸对象。
同时做 MCP 双写：`structuredContent` 与 `content[0].text` 完全一致。
"""

from __future__ import annotations

import json
from typing import Any

PROVIDER = "amap"

# 工具层错误码（与 REST 错误码不是一套，由 mcp_manager 做映射）
RETRYABLE: dict[str, bool] = {
    "INVALID_ARGUMENT": False,
    "NOT_FOUND": False,
    "UPSTREAM_ERROR": True,
    "UPSTREAM_RATE_LIMITED": True,
    "UPSTREAM_AUTH_FAILED": False,
    "TIMEOUT": True,
    "NOT_IMPLEMENTED": False,
}


def envelope_ok(tool: str, data: dict, latency_ms: int) -> dict:
    return {
        "ok": True,
        "tool": tool,
        "provider": PROVIDER,
        "latency_ms": latency_ms,
        "data": data,
        "error": None,
    }


def envelope_err(
    tool: str, code: str, message: str, retryable: bool | None = None, latency_ms: int = 0
) -> dict:
    return {
        "ok": False,
        "tool": tool,
        "provider": PROVIDER,
        "latency_ms": latency_ms,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "retryable": RETRYABLE.get(code, True) if retryable is None else retryable,
        },
    }


def as_mcp_result(env: dict) -> Any:
    """双写：structuredContent 与文本内容一致，`isError` 跟随 ok。

    MCP SDK 的 FastMCP 会原样透传 `CallToolResult`，所以这里优先返回它；
    如果 SDK 版本不认，就退回文档里写的裸 dict（FastMCP 会自动包一层文本内容）。
    """
    payload = {
        "structuredContent": env,
        "content": [{"type": "text", "text": json.dumps(env, ensure_ascii=False)}],
        "isError": not env["ok"],
    }
    try:
        from mcp.types import CallToolResult, TextContent

        return CallToolResult(
            content=[TextContent(type="text", text=payload["content"][0]["text"])],
            structuredContent=env,
            isError=payload["isError"],
        )
    except Exception:  # pragma: no cover - 仅在 SDK 缺类型时触发
        return payload


def parse_envelope(text_or_obj: Any) -> dict | None:
    """把工具返回的文本解析回信封，供 mcp_manager / 摘要在下游使用。"""
    if isinstance(text_or_obj, dict):
        return text_or_obj
    if not isinstance(text_or_obj, str):
        return None
    try:
        data = json.loads(text_or_obj)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) and "ok" in data else None
