"""LangGraph ReAct 图 + 事件流（BACKEND.md 16.1 / 16.9）。

`agent.run()` 是**纯异步生成器**：只 yield 事件，不碰 WebSocket、不写数据库。
所以 WS 接口、非流式接口、断连后继续生成，都只是同一个生成器的不同消费者。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..errors import ApiError
from .itinerary import extract_itinerary
from .llm import LLMFactory
from .tools import summarize_tool_result, truncate, truncate_obj

logger = logging.getLogger("tpa.agent.graph")

LLM_DEADLINE = 60.0  # 16.9：LLM 超时 60 秒


@dataclass
class AgentRequest:
    system_prompt: str
    history: list[dict[str, str]]
    user_content: str
    max_iterations: int = field(default_factory=lambda: settings.agent_max_iterations)


def _build_graph(llm: Any, tools: list[Any], system_prompt: str) -> Any:
    """兼容两代 API：langgraph.prebuilt.create_react_agent / langchain.agents.create_agent。"""
    try:
        from langgraph.prebuilt import create_react_agent

        return create_react_agent(llm, tools, prompt=system_prompt)
    except Exception as exc:  # ImportError 或签名变化
        logger.info("langgraph.prebuilt 不可用（%s），尝试 langchain.agents", exc)

    from langchain.agents import create_agent

    return create_agent(llm, tools, system_prompt=system_prompt)


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def _tool_envelope(output: Any) -> dict[str, Any]:
    """工具输出在 LangChain 里可能已经是 dict，也可能是 ToolMessage 文本。"""
    content = getattr(output, "content", output)
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _citations_from(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    data = envelope.get("data")
    if not isinstance(data, dict):
        data = envelope  # 原生 KB 工具把 hits 挂在顶层
    hits = data.get("hits")
    if not isinstance(hits, list):
        return []
    out = []
    for hit in hits:
        if not isinstance(hit, dict) or not hit.get("document_id"):
            continue
        out.append(
            {
                "document_id": str(hit.get("document_id")),
                "title": str(hit.get("title") or ""),
                "ordinal": int(hit.get("ordinal") or 0),
                "score": float(hit.get("score") or 0.0),
                "snippet": truncate(str(hit.get("snippet") or ""), 200),
            }
        )
    return out


def _weather_by_date(envelope: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = envelope.get("data")
    if not isinstance(data, dict):
        return {}
    casts = data.get("forecast")
    if not isinstance(casts, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for cast in casts:
        if not isinstance(cast, dict) or not cast.get("date"):
            continue
        high = cast.get("day_temp_c")
        low = cast.get("night_temp_c")
        out[str(cast["date"])] = {
            "condition": cast.get("day_weather"),
            "temp_low_c": low,
            "temp_high_c": high,
        }
    return out


async def run(
    request: AgentRequest, tools: list[Any]
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """跑一轮 ReAct，逐事件 yield。

    事件：tool_start / tool_end / token / itinerary / done。
    `asyncio.CancelledError` 直接向上抛，由 chat_service 把消息标 cancelled。
    """
    llm = LLMFactory.create(streaming=True)
    graph = _build_graph(llm, tools, request.system_prompt)

    messages = list(request.history) + [{"role": "user", "content": request.user_content}]
    config = {
        "recursion_limit": max(request.max_iterations * 2 + 2, 4),
        "metadata": {"max_iterations": request.max_iterations},
    }

    buffer: list[str] = []
    started: dict[str, float] = {}
    weather: dict[str, dict[str, Any]] = {}
    citations: list[dict[str, Any]] = []
    hit_limit = False

    emitted = False
    attempt = 0
    while True:
        attempt += 1
        try:
            async with asyncio.timeout(LLM_DEADLINE):
                async for event in graph.astream_events(
                    {"messages": messages}, config=config, version="v2"
                ):
                    kind = event.get("event")

                    if kind == "on_chat_model_stream":
                        delta = _chunk_text(event.get("data", {}).get("chunk"))
                        if delta:
                            emitted = True
                            buffer.append(delta)
                            yield "token", {"delta": delta}
                        continue

                    if kind == "on_tool_start":
                        name = event.get("name") or ""
                        run_id = event.get("run_id") or name
                        started[run_id] = time.perf_counter()
                        emitted = True
                        yield "tool_start", {
                            "name": name,
                            "args": truncate_obj(event.get("data", {}).get("input") or {}),
                        }
                        continue

                    if kind == "on_tool_end":
                        name = event.get("name") or ""
                        run_id = event.get("run_id") or name
                        elapsed_ms = int(
                            (time.perf_counter() - started.pop(run_id, time.perf_counter()))
                            * 1000
                        )
                        envelope = _tool_envelope(event.get("data", {}).get("output"))
                        if name == "weather_forecast":
                            weather.update(_weather_by_date(envelope))
                        if name == "search_knowledge_base":
                            citations.extend(_citations_from(envelope))
                        # 摘要函数自己崩了也不能拖垮对话（16.2）
                        try:
                            summary = summarize_tool_result(name, envelope)
                        except Exception:  # pragma: no cover - 兜底
                            logger.warning("生成工具摘要失败: %s", name, exc_info=True)
                            summary = "已返回结果"
                        yield "tool_end", {
                            "name": name,
                            "ok": bool(envelope.get("ok")),
                            "ms": int(envelope.get("latency_ms") or elapsed_ms),
                            "summary": summary,
                        }
                        continue

                    if kind == "on_tool_error":
                        name = event.get("name") or ""
                        run_id = event.get("run_id") or name
                        elapsed_ms = int(
                            (time.perf_counter() - started.pop(run_id, time.perf_counter()))
                            * 1000
                        )
                        yield "tool_end", {
                            "name": name,
                            "ok": False,
                            "ms": elapsed_ms,
                            "summary": truncate(str(event.get("data", {}).get("error"))[:200]),
                        }
                        continue

            break  # 正常跑完
        except (TimeoutError, asyncio.TimeoutError) as exc:
            # 已经吐过 token 就没法回退（前端已 append），只能如实报超时
            if attempt == 1 and not emitted:
                logger.warning("LLM 超时，重试一次")
                continue
            raise ApiError("LLM_TIMEOUT", "模型响应超时，请稍后重试", 504) from exc
        except Exception as exc:
            if _is_recursion_error(exc):
                logger.warning("达到最大迭代次数，强制收尾：%s", exc)
                hit_limit = True
                emitted = True
                break
            if isinstance(exc, ApiError):
                raise
            # 认证/配额类错误不需要 60 行 traceback，一行足够定位
            logger.warning("LLM 调用失败: %s: %s", type(exc).__name__, str(exc)[:200])
            raise ApiError("LLM_FAILED", f"模型调用失败：{str(exc)[:160]}", 500) from exc

    content = "".join(buffer)
    if hit_limit:
        suffix = "（本轮工具调用次数已达上限，如需更细的规划请继续追问）"
        content = f"{content}\n\n{suffix}".strip()
        yield "token", {"delta": f"\n\n{suffix}"}

    status = "completed"
    itinerary = extract_itinerary(content, weather) if content else None
    if itinerary:
        yield "itinerary", itinerary

    yield "done", {
        "content": content,
        "citations": citations,
        "status": status,
        "itinerary": itinerary,
    }


def _is_recursion_error(exc: Exception) -> bool:
    name = type(exc).__name__
    if name in ("GraphRecursionError", "RecursionError"):
        return True
    return "recursion limit" in str(exc).lower()
