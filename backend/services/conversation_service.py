"""会话与消息持久化（BACKEND.md 第 6、9 章）。

越权校验必须在 service 层显式做：`conv is None` 与 `conv.user_id != user.id`
两个条件缺一不可，前者漏了报 500，后者漏了就是数据泄露。
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ApiError
from ..models import Conversation, Message, User, utcnow
from ..schemas import conversation_item

logger = logging.getLogger("tpa.conversation")

MAX_MESSAGES = 500
DEFAULT_MESSAGES = 200
DEFAULT_TITLE = "新对话"


async def create_conversation(
    db: AsyncSession, user: User, title: str | None = None
) -> Conversation:
    conv = Conversation(
        user_id=user.id,
        title=(title or DEFAULT_TITLE).strip()[:60] or DEFAULT_TITLE,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation(db: AsyncSession, conv_id: str, user: User) -> Conversation:
    """越权一律 404，避免"这个 ID 存在"的信息泄露。"""
    conv = await db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise ApiError("NOT_FOUND", "会话不存在", 404)
    return conv


async def list_conversations(
    db: AsyncSession, user: User, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))

    count_sq = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .scalar_subquery()
    )
    itinerary_sq = exists().where(
        Message.conversation_id == Conversation.id,
        Message.itinerary.is_not(None),
    )

    stmt = (
        select(Conversation, count_sq.label("mc"), itinerary_sq.label("hi"))
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    total = (
        await db.execute(
            select(func.count(Conversation.id)).where(Conversation.user_id == user.id)
        )
    ).scalar_one()

    items = [
        conversation_item(conv, int(mc or 0), bool(hi)) for conv, mc, hi in rows
    ]
    return items, int(total)


async def rename_conversation(
    db: AsyncSession, conv: Conversation, title: str
) -> Conversation:
    title = (title or "").strip()
    if not title:
        raise ApiError("INVALID_ARGUMENT", "标题不能为空", 400)
    if len(title) > 60:
        raise ApiError("INVALID_ARGUMENT", "标题不能超过 60 字符", 400)
    conv.title = title
    await db.commit()
    await db.refresh(conv)
    return conv


async def delete_conversation(db: AsyncSession, conv: Conversation) -> None:
    """显式两步删除，不依赖 `PRAGMA foreign_keys` 是否生效（更保险）。"""
    await db.execute(delete(Message).where(Message.conversation_id == conv.id))
    await db.execute(delete(Conversation).where(Conversation.id == conv.id))
    await db.commit()


async def list_messages(
    db: AsyncSession,
    conv: Conversation,
    limit: int = DEFAULT_MESSAGES,
    before_seq: int | None = None,
) -> list[Message]:
    limit = max(1, min(MAX_MESSAGES, limit))
    stmt = select(Message).where(Message.conversation_id == conv.id)
    if before_seq is not None:
        stmt = stmt.where(Message.seq < before_seq)
    stmt = stmt.order_by(Message.seq.asc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def conversation_stats(
    db: AsyncSession, conv: Conversation
) -> tuple[int, bool]:
    """9.1 的两个计算字段：消息数 + 是否已生成过行程。"""
    count = (
        await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
    ).scalar_one()
    has_itinerary = (
        await db.execute(
            select(Message.id)
            .where(Message.conversation_id == conv.id, Message.itinerary.is_not(None))
            .limit(1)
        )
    ).first()
    return int(count or 0), has_itinerary is not None


async def allocate_seq(db: AsyncSession, conversation_id: str, count: int) -> list[int]:
    """`SELECT MAX(seq)` 再 +1。用户消息与助手占位连续分配（如 5 和 6）。"""
    current = (
        await db.execute(
            select(func.max(Message.seq)).where(
                Message.conversation_id == conversation_id
            )
        )
    ).scalar_one()
    base = int(current or 0)
    return [base + i + 1 for i in range(count)]


async def heal_stale_messages(db: AsyncSession) -> int:
    """启动自愈：把 pending 改 failed，否则界面永远卡在"生成中"（18.2）。"""
    result = await db.execute(
        select(Message).where(Message.status == "pending")
    )
    stale = list(result.scalars().all())
    for message in stale:
        message.status = "failed"
        if not (message.content or "").strip():
            message.content = "[上一轮生成被中断]"
    if stale:
        await db.commit()
        logger.warning("启动自愈：%s 条 pending 消息已标记 failed", len(stale))
    return len(stale)
