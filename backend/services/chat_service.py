"""一轮对话的业务编排（BACKEND.md 第 3.1、10、11.4、16 章）。

`chat_service` 是唯一知道"一轮对话要做哪些事"的地方：
落库 user 消息 -> 建 assistant 占位 -> 装配上下文 -> 跑 Agent -> 落库最终内容。

Agent 只 yield 事件，本模块把事件转给消费者（WS 队列 / REST 忽略），
自己不认识 WebSocket。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent import graph as agent_graph
from ..agent.llm import LLMFactory
from ..agent.prompts import build_system_prompt, title_prompt
from ..agent.tools import build_kb_tool
from ..config import settings
from ..db import SessionLocal
from ..errors import ApiError
from ..models import Conversation, Message, User, utcnow
from ..schemas import message_item
from . import conversation_service
from .mcp_manager import MCPManager
from .rag_service import rag_service

logger = logging.getLogger("tpa.chat")

HISTORY_LIMIT = 20
HISTORY_KEEP_RECENT = 4
MAX_CONTENT = 8000
TITLE_MAX = 60
TITLE_FALLBACK_CHARS = 20

Emit = Callable[[str, dict[str, Any]], None]


# ---------------------------------------------------------------------------
# 会话并发控制（3.2）
# ---------------------------------------------------------------------------

_locks: dict[str, asyncio.Lock] = {}
_tasks: dict[str, asyncio.Task] = {}


def _lock_for(conversation_id: str) -> asyncio.Lock:
    lock = _locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[conversation_id] = lock
    return lock


async def try_acquire(conversation_id: str) -> bool:
    """拿不到锁就回 CONV_BUSY，连接不断。

    `asyncio.Lock.acquire()` 是协程：**未上锁时它会同步置位再返回**，
    所以"检查 + await acquire"之间没有让出点，不存在竞态。
    """
    lock = _lock_for(conversation_id)
    if lock.locked():
        return False
    await lock.acquire()
    return True


def release(conversation_id: str) -> None:
    lock = _locks.get(conversation_id)
    if lock is not None and lock.locked():
        lock.release()
    if not lock or not lock.locked():
        _locks.pop(conversation_id, None)


@asynccontextmanager
async def hold_lock(conversation_id: str) -> AsyncIterator[None]:
    if not await try_acquire(conversation_id):
        raise ApiError("CONV_BUSY", "该会话正在生成回复", 409)
    try:
        yield
    finally:
        release(conversation_id)


def register_task(conversation_id: str, task: asyncio.Task) -> None:
    _tasks[conversation_id] = task


def pop_task(conversation_id: str) -> asyncio.Task | None:
    return _tasks.pop(conversation_id, None)


def cancel_round(conversation_id: str) -> bool:
    """用户取消：取消 asyncio task，已生成内容由 run_round 标 cancelled 落库。"""
    task = _tasks.get(conversation_id)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


# ---------------------------------------------------------------------------
# 上下文装配（16.6）
# ---------------------------------------------------------------------------


def _history_line(message: Message) -> dict[str, str]:
    content = (message.content or "").strip()
    if message.status == "failed":
        content = "[上一轮生成失败]"
    elif message.status == "cancelled":
        content = content or "[上一轮生成被取消]"

    extras: list[str] = []
    itinerary = message.itinerary or {}
    if isinstance(itinerary, dict) and itinerary.get("title"):
        summary = str(itinerary.get("summary") or "")[:120]
        extras.append(f"[行程卡片：{itinerary.get('title')} — {summary}]")

    citations = message.citations or []
    if citations:
        titles = "、".join(str(c.get("title") or "") for c in citations[:3])
        if titles:
            extras.append(f"[上一轮引用：{titles}]")

    if extras:
        content = "\n".join([content, *extras])
    return {"role": message.role, "content": content}


async def load_history(
    db: AsyncSession, conv: Conversation, before_seq: int | None = None
) -> list[dict[str, str]]:
    """最近 20 条，最近 4 条永不裁剪。pending 的那条（本轮占位）不注入。"""
    messages = await conversation_service.list_messages(
        db, conv, limit=HISTORY_LIMIT, before_seq=before_seq
    )
    if not messages:
        return []

    trimmed = [m for m in messages if m.status != "pending"]
    if not trimmed:
        return []

    # 最近 4 条无论如何都保留（多轮追问的连贯性靠它们）
    keep_from = max(0, len(trimmed) - HISTORY_KEEP_RECENT)
    kept = trimmed[keep_from:]
    earlier = trimmed[:keep_from][-(HISTORY_LIMIT - len(kept)) :]
    selected = [*earlier, *kept]

    return [_history_line(m) for m in selected]


async def _build_tools(
    manager: MCPManager | None,
) -> tuple[list[Any], list[str]]:
    """工具集 = 可用的 MCP 工具 + search_knowledge_base（若 RAG 启用）。"""
    tools: list[Any] = []
    notes: list[str] = []

    if manager is not None:
        tools.extend(manager.build_langchain_tools())
        down = set(manager.unavailable_servers())
        if "weather" in down:
            notes.append("当前无法获取实时天气，不要编造天气数据。")
        if "place" in down:
            notes.append("当前无法查询地点，只能基于用户提供的信息规划。")
    else:
        notes.append("当前无法调用工具，只能基于已有知识规划，并说明能力受限。")

    if settings.rag_enabled:
        async def _search(query: str) -> dict[str, Any]:
            async with SessionLocal() as session:
                return await rag_service.search_payload(session, query)

        tools.append(build_kb_tool(_search))

    return tools, notes


# ---------------------------------------------------------------------------
# 一轮对话
# ---------------------------------------------------------------------------


def _validate_content(content: str) -> str:
    content = (content or "").strip()
    if not content:
        raise ApiError("MSG_EMPTY", "消息内容不能为空", 400)
    if len(content) > MAX_CONTENT:
        raise ApiError(
            "INVALID_ARGUMENT", f"消息内容不能超过 {MAX_CONTENT} 字符", 400
        )
    return content


async def prepare_round(
    db: AsyncSession, conv: Conversation, content: str
) -> tuple[Message, Message]:
    """落库 user 消息 + assistant 占位，seq 连续分配。"""
    content = _validate_content(content)
    seqs = await conversation_service.allocate_seq(db, conv.id, 2)

    user_message = Message(
        conversation_id=conv.id,
        seq=seqs[0],
        role="user",
        content=content,
        status="completed",
        created_at=utcnow(),
    )
    assistant_message = Message(
        conversation_id=conv.id,
        seq=seqs[1],
        role="assistant",
        content="",
        status="pending",
        created_at=utcnow(),
    )
    db.add_all([user_message, assistant_message])
    conv.updated_at = utcnow()
    try:
        await db.commit()
    except IntegrityError as exc:
        # 最后一道防线：ux_msg_seq 撞了说明同一会话真的在并发写
        await db.rollback()
        raise ApiError("CONV_BUSY", "该会话正在生成回复", 409) from exc
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    return user_message, assistant_message


class RoundOutcome:
    def __init__(self) -> None:
        self.user_message: Message | None = None
        self.assistant_message: Message | None = None
        self.title: str | None = None
        self.status = "completed"
        self.error: ApiError | None = None


async def run_round(
    *,
    conversation_id: str,
    user_id: str,
    content: str,
    emit: Emit | None = None,
    manager: MCPManager | None = None,
) -> RoundOutcome:
    """跑完整一轮。**自己开 session**，可以安全地跑在后台任务里。"""
    emit = emit or (lambda _kind, _payload: None)
    outcome = RoundOutcome()

    async with SessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise ApiError("NOT_FOUND", "会话不存在", 404)
        user = await db.get(User, user_id)
        if user is None:
            raise ApiError("NOT_FOUND", "用户不存在", 404)

        user_message, assistant_message = await prepare_round(db, conv, content)
        outcome.user_message = user_message
        outcome.assistant_message = assistant_message

        is_first_round = await _is_first_round(db, conv)

        # 历史只取本轮用户消息之前的，本轮内容单独作为 user_content 注入
        history = await load_history(db, conv, before_seq=user_message.seq)

        tools, degraded = await _build_tools(manager)

        try:
            system_prompt = build_system_prompt(
                tools=tools, profile=user.profile or {}, degraded_notes=degraded
            )
        except Exception as exc:  # pragma: no cover - 提示词拼装不应失败
            logger.exception("拼装系统提示词失败")
            raise ApiError("INTERNAL_ERROR", "拼装提示词失败", 500) from exc

        buffer: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        citations: list[dict[str, Any]] = []
        itinerary: dict[str, Any] | None = None
        status = "completed"

        request = agent_graph.AgentRequest(
            system_prompt=system_prompt,
            history=history,
            user_content=user_message.content,
        )

        try:
            async for kind, payload in agent_graph.run(request, tools):
                if kind == "token":
                    buffer.append(payload.get("delta") or "")
                    emit("token", {"delta": payload.get("delta") or ""})
                elif kind == "tool_start":
                    tool_calls.append(
                        {
                            "name": payload.get("name"),
                            "args": payload.get("args"),
                            "ok": None,
                            "ms": None,
                        }
                    )
                    emit("tool_start", payload)
                elif kind == "tool_end":
                    _merge_tool_end(tool_calls, payload)
                    emit("tool_end", payload)
                elif kind == "itinerary":
                    itinerary = payload
                    emit("itinerary", payload)
                elif kind == "done":
                    citations = payload.get("citations") or []
                    itinerary = payload.get("itinerary") or itinerary
                    status = payload.get("status") or "completed"
        except asyncio.CancelledError:
            # 用户取消：已生成内容照常落库，状态 cancelled，照常发 done
            logger.info("会话 %s 的生成被取消", conversation_id)
            status = "cancelled"
            outcome.status = "cancelled"
        except ApiError as exc:
            logger.warning("会话 %s 生成失败 %s: %s", conversation_id, exc.code, exc.message)
            status = "failed"
            outcome.error = exc
        except Exception as exc:  # pragma: no cover - 兜底
            logger.exception("会话 %s 生成时未捕获异常", conversation_id)
            status = "failed"
            outcome.error = ApiError("LLM_FAILED", "生成失败，请重试", 500)

        final_content = "".join(buffer)
        if status == "failed" and not final_content.strip():
            final_content = ""

        assistant_message.content = final_content
        assistant_message.status = status
        assistant_message.itinerary = itinerary
        assistant_message.citations = citations
        assistant_message.tool_calls = tool_calls or None
        conv.updated_at = utcnow()
        try:
            await db.commit()
            await db.refresh(assistant_message)
        except Exception as exc:  # pragma: no cover
            logger.error("落库 assistant 消息失败: %s", exc)
            await db.rollback()
            status = "failed"
            outcome.error = ApiError("INTERNAL_ERROR", "保存消息失败", 500)

        outcome.status = status

        # 16.7 会话标题：首条助手消息完成后生成；用户改过名就不再覆盖
        title = conv.title
        if is_first_round and status in ("completed", "cancelled"):
            generated = await _safe_generate_title(
                conv.id, user_message.content, (itinerary or {}).get("title")
            )
            if generated:
                title = generated
        outcome.title = title

        emit(
            "done",
            {
                "status": status,
                "message": {
                    "id": assistant_message.id,
                    "seq": assistant_message.seq,
                    "content": final_content,
                    "citations": citations,
                },
                "title": title,
                "error": (
                    {"code": outcome.error.code, "message": outcome.error.message}
                    if outcome.error
                    else None
                ),
            },
        )

    if outcome.error is not None:
        logger.info("本轮结束（失败）：%s", outcome.error.code)
    return outcome


def _merge_tool_end(tool_calls: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    name = payload.get("name")
    for entry in reversed(tool_calls):
        if entry.get("name") == name and entry.get("ok") is None:
            entry["ok"] = bool(payload.get("ok"))
            entry["ms"] = payload.get("ms")
            entry["summary"] = payload.get("summary")
            return
    tool_calls.append(
        {
            "name": name,
            "args": None,
            "ok": bool(payload.get("ok")),
            "ms": payload.get("ms"),
        }
    )


async def _is_first_round(db: AsyncSession, conv: Conversation) -> bool:
    """首轮 = 只有本轮这两人消息（seq <= 2）。"""
    from sqlalchemy import func, select

    count = (
        await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
    ).scalar_one()
    return int(count or 0) <= 2 and conv.title == conversation_service.DEFAULT_TITLE


async def _safe_generate_title(
    conversation_id: str, first_content: str, itinerary_title: str | None
) -> str | None:
    try:
        return await asyncio.wait_for(
            generate_title(conversation_id, first_content, itinerary_title), timeout=12
        )
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("生成会话标题超时，使用兜底标题")
        return await _write_fallback_title(conversation_id, first_content)
    except Exception as exc:  # pragma: no cover
        logger.warning("生成会话标题失败: %s", exc)
        return await _write_fallback_title(conversation_id, first_content)


async def generate_title(
    conversation_id: str, first_content: str, itinerary_title: str | None = None
) -> str | None:
    """一次小 LLM 调用，temperature=0，≤15 汉字。"""
    llm = LLMFactory.create_for_title()
    response = await llm.ainvoke(title_prompt(first_content, itinerary_title))
    title = _clean_title(getattr(response, "content", "") or "")
    if not title:
        return await _write_fallback_title(conversation_id, first_content)
    return await _write_title(conversation_id, title)


def _clean_title(raw: str) -> str:
    text = (raw or "").strip().splitlines()[0] if (raw or "").strip() else ""
    text = text.strip(" \"'“”「」《》。.，,")
    return text[:TITLE_MAX]


async def _write_title(conversation_id: str, title: str) -> str | None:
    async with SessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None or conv.title != conversation_service.DEFAULT_TITLE:
            return conv.title if conv else None
        conv.title = title[:TITLE_MAX]
        # 16.7：updated_at 不变
        await db.commit()
        return conv.title


async def _write_fallback_title(
    conversation_id: str, first_content: str
) -> str | None:
    fallback = (first_content or "").strip()[:TITLE_FALLBACK_CHARS] or "新对话"
    return await _write_title(conversation_id, fallback)


# ---------------------------------------------------------------------------
# 非流式发消息（第 10 章）
# ---------------------------------------------------------------------------


async def send_message(
    *,
    conversation_id: str,
    user: User,
    content: str,
    manager: MCPManager | None = None,
) -> dict[str, Any]:
    """同步等 LLM 跑完再返回。事件不外发，只为让 curl / 脚本能测通整条链路。"""
    async with hold_lock(conversation_id):
        outcome = await run_round(
            conversation_id=conversation_id,
            user_id=user.id,
            content=content,
            emit=None,
            manager=manager,
        )

    if outcome.error is not None and outcome.status == "failed":
        raise outcome.error

    assert outcome.user_message is not None
    assert outcome.assistant_message is not None
    return {
        "user_message": message_item(outcome.user_message),
        "assistant_message": message_item(outcome.assistant_message),
    }
