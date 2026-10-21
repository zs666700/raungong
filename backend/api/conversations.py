"""会话与消息接口（BACKEND.md 第 9、10 章）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from ..deps import CurrentUser, DbSession, McpManager
from ..errors import ApiError, ok
from ..schemas import (
    ConversationCreateRequest,
    ConversationPatchRequest,
    MessageCreateRequest,
    conversation_brief,
    conversation_item,
    message_item,
)
from ..services import chat_service, conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user: CurrentUser,
    db: DbSession,
    payload: ConversationCreateRequest | None = None,
):
    """新建空会话。请求体可为空对象，也可以完全不传。"""
    title = payload.title if payload else None
    conv = await conversation_service.create_conversation(db, user, title)
    return ok(conversation_brief(conv))


@router.get("")
async def list_conversations(
    user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = await conversation_service.list_conversations(
        db, user, page=page, page_size=page_size
    )
    return ok({"items": items, "total": total})


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    payload: ConversationPatchRequest,
    user: CurrentUser,
    db: DbSession,
):
    conv = await conversation_service.get_conversation(db, conversation_id, user)
    conv = await conversation_service.rename_conversation(db, conv, payload.title)
    count, has_itinerary = await conversation_service.conversation_stats(db, conv)
    return ok(conversation_item(conv, count, has_itinerary))


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession):
    conv = await conversation_service.get_conversation(db, conversation_id, user)
    await conversation_service.delete_conversation(db, conv)
    return ok({"deleted": True})


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    """取会话全部消息，不分页（Demo 会话不会超 200 条）。"""
    conv = await conversation_service.get_conversation(db, conversation_id, user)
    messages = await conversation_service.list_messages(db, conv, limit=limit)
    return ok(
        {
            "conversation": {"id": conv.id, "title": conv.title},
            "items": [message_item(m) for m in messages],
        }
    )


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    user: CurrentUser,
    db: DbSession,
    manager: McpManager,
):
    """非流式发消息：同步等 LLM 跑完后返回完整结果（curl 排障非常好用）。"""
    conv = await conversation_service.get_conversation(db, conversation_id, user)
    if not (payload.content or "").strip():
        raise ApiError("MSG_EMPTY", "消息内容不能为空", 400)

    result = await chat_service.send_message(
        conversation_id=conv.id,
        user=user,
        content=payload.content,
        manager=manager,
    )
    return ok(result)
