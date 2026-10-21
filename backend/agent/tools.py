"""Agent 侧工具：原生 `search_knowledge_base` + 工具结果的人话摘要。

`search_knowledge_base` 不走 MCP——它要直接读 Chroma，放独立进程反而要跨进程
传向量数据。检索函数由 services 注入，这样 `agent/` 不反向依赖 `services/`。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("tpa.agent.tools")

MAX_SUMMARY_CHARS = 2048  # args / summary 各截断到 2 KB（11.2）


class KnowledgeSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="要检索的问题或关键词")


def build_kb_tool(
    search: Callable[[str], Awaitable[dict[str, Any]]],
) -> Any:
    """把 RagService.search 包成 LangChain 工具。

    输出**不套** tool/provider/latency_ms 信封，只有 ok + hits（15.8）。
    """
    from langchain_core.tools import StructuredTool

    async def _run(query: str) -> str:
        try:
            payload = await search(query)
        except Exception as exc:  # 检索失败也要让对话继续
            logger.warning("search_knowledge_base 失败: %s", exc)
            payload = {"ok": False, "hits": [], "error": str(exc)[:200]}
        return json.dumps(payload, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=_run,
        name="search_knowledge_base",
        description=(
            "检索内置知识库，用于回答预约、限行、门票等政策类问题。"
            "返回命中的文档片段与引用信息；hits 为空表示知识库里没有相关内容。"
        ),
        args_schema=KnowledgeSearchArgs,
    )


def truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def truncate_obj(value: Any, limit: int = MAX_SUMMARY_CHARS) -> Any:
    """args 也要截断，避免一个超长参数把 WS 帧撑爆。"""
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)[:limit]
    if len(text) <= limit:
        return value
    return truncate(text, limit)


# ---------------------------------------------------------------------------
# 工具结果 -> 人话摘要（11.2：不是原始 JSON）
# ---------------------------------------------------------------------------


def _error_text(error: Any) -> str:
    """工具信封的 error 有两种形状：

    * MCP 工具：`{"code": ..., "message": ..., "retryable": ...}`
    * 原生 search_knowledge_base（15.8）：**就是一个字符串**

    两种都要接住——摘要函数自己崩了会把整轮对话拖成 failed。
    """
    if isinstance(error, dict):
        return str(error.get("message") or "未知错误")
    if error:
        return str(error)
    return "未知错误"


def _payload_of(envelope: dict[str, Any]) -> dict[str, Any]:
    """取 data；原生 KB 工具没有 data 层，hits 直接挂在顶层。"""
    data = envelope.get("data")
    return data if isinstance(data, dict) else envelope


def summarize_tool_result(name: str, envelope: dict[str, Any]) -> str:
    if not isinstance(envelope, dict) or not envelope:
        return "工具没有返回结果"
    if not envelope.get("ok"):
        return truncate(f"调用失败：{_error_text(envelope.get('error'))}")

    data = _payload_of(envelope)

    if name == "weather_forecast":
        city = data.get("city") or ""
        casts = data.get("forecast") or []
        parts = []
        for cast in casts[:4]:
            if not isinstance(cast, dict):
                continue
            date = cast.get("date") or ""
            day = cast.get("day_weather") or ""
            low = cast.get("night_temp_c")
            high = cast.get("day_temp_c")
            temp = f"{low}–{high}℃" if low is not None and high is not None else ""
            parts.append(" ".join(x for x in (date[5:], day, temp) if x))
        head = f"{city}预报：" if city else "预报："
        return truncate(head + "；".join(parts) if parts else head + "无可用数据")

    if name == "weather_now":
        return truncate(
            "{city} {weather} {temp}℃ 湿度 {humidity}% {wind}{power}".format(
                city=data.get("city") or "",
                weather=data.get("weather") or "",
                temp=data.get("temperature_c"),
                humidity=data.get("humidity"),
                wind=data.get("wind_direction") or "",
                power=data.get("wind_power") or "",
            ).strip()
        )

    if name == "place_search":
        pois = data.get("pois") or []
        names = "、".join(str(p.get("name")) for p in pois[:3] if isinstance(p, dict))
        return truncate(f"命中 {data.get('total', len(pois))} 个地点：" + (names or "无"))

    if name == "geo_geocode":
        return truncate(
            f"解析到 {data.get('formatted_address') or '未知地址'}"
            f"（{data.get('location')}，精度 {data.get('level') or '未知'}）"
        )

    if name == "route_plan":
        distance = data.get("distance_m")
        duration = data.get("duration_s")
        text = f"{data.get('mode') or ''} "
        if distance is not None:
            text += f"距离 {distance / 1000:.1f} km "
        if duration is not None:
            text += f"耗时 {round(duration / 60)} 分钟"
        return truncate(text.strip() or "无路线数据")

    if name == "search_knowledge_base":
        hits = data.get("hits") or []
        if not hits:
            return "知识库未命中"
        titles = "、".join(str(h.get("title")) for h in hits[:3] if isinstance(h, dict))
        return truncate(f"命中 {len(hits)} 条知识库片段：{titles}")

    if data:
        try:
            return truncate(json.dumps(data, ensure_ascii=False))
        except (TypeError, ValueError):
            return truncate(str(data))
    return "工具返回空结果"
