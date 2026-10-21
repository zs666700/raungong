"""Pydantic 请求模型 + 行程 Schema + 出参序列化（BACKEND.md 第 6、7、9、16.4 章）。

出参一律显式返回 null，不省略键（7.1）。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Conversation, Message, RagDocument, User

# ---------------------------------------------------------------------------
# 时间与基础序列化
# ---------------------------------------------------------------------------

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def iso(dt: datetime | None) -> str | None:
    """DB 里是 naive UTC，出参统一 ISO-8601 带 Z。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def user_brief(user: User) -> dict[str, Any]:
    return {"id": user.id, "username": user.username, "role": user.role}


def user_me(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "profile": user.profile or {},
    }


def conversation_brief(conv: Conversation) -> dict[str, Any]:
    """9.2 / 9.5 用的最小对象。"""
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": iso(conv.created_at),
        "updated_at": iso(conv.updated_at),
    }


def conversation_item(conv: Conversation, message_count: int, has_itinerary: bool) -> dict[str, Any]:
    """9.1 的 Conversation，含两个计算字段。"""
    return {
        "id": conv.id,
        "title": conv.title,
        "message_count": message_count,
        "has_itinerary": has_itinerary,
        "created_at": iso(conv.created_at),
        "updated_at": iso(conv.updated_at),
    }


def message_item(msg: Message) -> dict[str, Any]:
    """9.1 的 Message。"""
    return {
        "id": msg.id,
        "seq": msg.seq,
        "role": msg.role,
        "content": msg.content or "",
        "status": msg.status,
        "itinerary": msg.itinerary,
        "citations": msg.citations,
        "tool_calls": msg.tool_calls,
        "created_at": iso(msg.created_at),
    }


def rag_document_item(doc: RagDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "filename": doc.filename,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "error": doc.error,
        "created_at": iso(doc.created_at),
    }


def admin_user_item(user: User, conversation_count: int) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
        "conversation_count": conversation_count,
        "created_at": iso(user.created_at),
    }


# ---------------------------------------------------------------------------
# 认证（第 8 章）
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    # 长度交给 security.assert_password_strength 判，才能回 AUTH_WEAK_PASSWORD
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("用户名只能包含字母、数字、下划线、点和短横线")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


# 6.5 允许的键与值
BUDGET_LEVELS = ("economy", "comfortable", "luxury")
PACES = ("relaxed", "balanced", "packed")


class ProfileIn(BaseModel):
    """只接受 6.5 的 6 个键，未知键忽略（extra=ignore）。整体替换语义。"""

    model_config = ConfigDict(extra="ignore")

    home_city: str | None = Field(None, max_length=20)
    budget_level: Literal["economy", "comfortable", "luxury"] | None = None
    pace: Literal["relaxed", "balanced", "packed"] | None = None
    interests: list[str] | None = Field(None, max_length=8)
    dietary: list[str] | None = Field(None, max_length=8)
    avoid: list[str] | None = Field(None, max_length=8)

    @field_validator("interests", "dietary", "avoid")
    @classmethod
    def _check_items(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for item in v:
            if not isinstance(item, str):
                raise ValueError("数组元素必须是字符串")
            if len(item) > 20:
                raise ValueError("每一项不能超过 20 字符")
        return v


# ---------------------------------------------------------------------------
# 会话与消息（第 9、10 章）
# ---------------------------------------------------------------------------


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(None, max_length=60)


class ConversationPatchRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=60)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("标题不能为空")
        return v


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)


class ToolInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    args: dict[str, Any] = Field(default_factory=dict)


class RagUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    title: str | None = Field(None, max_length=200)


class AdminUserPatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["root", "user"] | None = None
    status: Literal["active", "disabled"] | None = None


# ---------------------------------------------------------------------------
# 行程 Schema（16.4）—— 校验从宽、修复在 agent/itinerary.py 里做
# ---------------------------------------------------------------------------

ItemType = Literal["attraction", "meal", "transport", "rest", "activity", "lodging"]
TransportMode = Literal["walking", "driving", "transit"]
ItemSource = Literal["tool", "rag", "model"]
RiskType = Literal["weather", "reservation", "safety", "budget", "physical"]


class ItineraryLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    address: str | None = None
    location: str | None = None


class ItineraryTransport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: TransportMode = "walking"
    duration_min: int = 0
    distance_m: int = 0


class ItineraryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int = 1
    start_time: str | None = None
    end_time: str | None = None
    type: ItemType = "activity"
    title: str = ""
    location: ItineraryLocation = Field(default_factory=ItineraryLocation)
    duration_min: int = 60
    cost_cent: int = 0
    transport: ItineraryTransport | None = None
    notes: str = ""
    source: ItemSource = "model"


class DayWeather(BaseModel):
    model_config = ConfigDict(extra="ignore")

    condition: str = ""
    temp_low_c: int | None = None
    temp_high_c: int | None = None


class ItineraryDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str = ""
    weekday: str = ""
    theme: str = ""
    weather: DayWeather | None = None
    items: list[ItineraryItem] = Field(default_factory=list)


class Destination(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    adcode: str = ""
    location: str | None = None


class Travelers(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adults: int = 1
    children: int = 0


class BudgetBreakdown(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transport_cent: int = 0
    lodging_cent: int = 0
    food_cent: int = 0
    tickets_cent: int = 0
    other_cent: int = 0


class Budget(BaseModel):
    model_config = ConfigDict(extra="ignore")

    currency: str = "CNY"
    total_cent: int = 0
    breakdown: BudgetBreakdown = Field(default_factory=BudgetBreakdown)


class Risk(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: RiskType = "safety"
    description: str = ""
    mitigation: str = ""


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    destination: Destination = Field(default_factory=Destination)
    start_date: str = ""
    end_date: str = ""
    day_count: int = 1
    travelers: Travelers = Field(default_factory=Travelers)
    budget: Budget = Field(default_factory=Budget)
    summary: str = ""
    days: list[ItineraryDay] = Field(default_factory=list)
    packing_list: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    generated_at: str = ""
