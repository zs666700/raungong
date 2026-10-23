"""Mock 后端的内存状态。仅供 `TPA_MOCK=1` 时使用。"""

from __future__ import annotations

import copy
import itertools
import time
from datetime import datetime, timezone
from typing import Any

from . import mock_data

_PREFIX = "/api/v1"
_ids = itertools.count(100)


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _uid(prefix: str) -> str:
    return f"{prefix}_{next(_ids)}"


class MockStore:
    def __init__(self) -> None:
        self.conversations: list[dict[str, Any]] = copy.deepcopy(mock_data.CONVERSATIONS)
        self.messages: dict[str, list[dict[str, Any]]] = copy.deepcopy(mock_data.MESSAGES)
        self.documents: list[dict[str, Any]] = copy.deepcopy(mock_data.RAG_DOCUMENTS)
        self.users: list[dict[str, Any]] = copy.deepcopy(mock_data.USERS)
        self.profiles: dict[str, dict[str, Any]] = {"root": copy.deepcopy(mock_data.PROFILE)}
        # Mock 模式专用密码（TPA_MOCK=1 时生效），与后端 .env 的 TPA_ROOT_PASSWORD 无关
        self.passwords: dict[str, str] = {"root": "mock-pass"}

    # ---------------------------------------------------------------- auth
    def user_by_name(self, username: str) -> dict[str, Any] | None:
        for user in self.users:
            if user["username"] == username:
                return user
        return None

    def token_for(self, username: str) -> str:
        return f"mock-token-{username}"

    def username_from_token(self, token: str) -> str:
        return (token or "").removeprefix("mock-token-") or "root"

    def me(self, username: str) -> dict[str, Any]:
        user = self.user_by_name(username) or self.users[0]
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "status": user["status"],
            "profile": copy.deepcopy(self.profiles.get(username, {})),
        }

    def register(self, username: str, password: str) -> dict[str, Any]:
        if self.user_by_name(username):
            from .api_client import ApiError

            raise ApiError("AUTH_USERNAME_TAKEN", "用户名已存在", 409)
        user = {
            "id": _uid("u"),
            "username": username,
            "role": "user",
            "status": "active",
            "conversation_count": 0,
            "created_at": _iso_now(),
        }
        self.users.append(user)
        self.passwords[username] = password
        return user

    # -------------------------------------------------------- conversations
    def visible_conversations(self, username: str) -> list[dict[str, Any]]:
        if username != "root":
            return []
        return sorted(self.conversations, key=lambda c: c["updated_at"], reverse=True)

    def stats(self, conv_id: str) -> tuple[int, bool]:
        items = self.messages.get(conv_id, [])
        return len(items), any(item.get("itinerary") for item in items)

    def conversation_item(self, conv: dict[str, Any]) -> dict[str, Any]:
        count, has = self.stats(conv["id"])
        return {
            **conv,
            "message_count": count,
            "has_itinerary": has,
        }

    def create_conversation(self, username: str, title: str | None = None) -> dict[str, Any]:
        conv = {
            "id": _uid("c"),
            "title": (title or "新对话")[:60],
            "message_count": 0,
            "has_itinerary": False,
            "created_at": _iso_now(),
            "updated_at": _iso_now(),
        }
        self.conversations.append(conv)
        self.messages[conv["id"]] = []
        return conv

    def get_conversation(self, conv_id: str, username: str = "root") -> dict[str, Any]:
        from .api_client import ApiError

        for conv in self.conversations:
            if conv["id"] == conv_id and username == "root":
                return conv
        raise ApiError("NOT_FOUND", "会话不存在", 404)

    def rename(self, conv_id: str, title: str) -> dict[str, Any]:
        conv = self.get_conversation(conv_id)
        conv["title"] = title.strip()[:60] or conv["title"]
        conv["updated_at"] = _iso_now()
        return self.conversation_item(conv)

    def delete(self, conv_id: str) -> None:
        conv = self.get_conversation(conv_id)
        self.conversations.remove(conv)
        self.messages.pop(conv_id, None)

    def messages_for(self, conv_id: str) -> list[dict[str, Any]]:
        self.get_conversation(conv_id)
        return self.messages[conv_id]

    def append_message(self, conv_id: str, role: str, content: str, **extra: Any) -> dict[str, Any]:
        items = self.messages.setdefault(conv_id, [])
        message = {
            "id": _uid("m"),
            "seq": (items[-1]["seq"] + 1) if items else 1,
            "role": role,
            "content": content,
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso_now(),
            **extra,
        }
        items.append(message)
        conv = self.get_conversation(conv_id)
        conv["updated_at"] = _iso_now()
        first_round = len(items) <= 2
        if first_round and role == "user" and conv["title"] == "新对话":
            conv["title"] = content.strip().replace("\n", " ")[:24] or "新对话"
        return message

    def send_sync(self, conv_id: str, content: str) -> dict[str, Any]:
        user_message = self.append_message(conv_id, "user", content)
        items = self.messages_for(conv_id)
        first_round = len(items) <= 1
        if first_round:
            text = mock_data.ASSISTANT_TEXT
            extra = {
                "itinerary": copy.deepcopy(mock_data.ITINERARY),
                "citations": copy.deepcopy(mock_data.CITATIONS),
                "tool_calls": copy.deepcopy(mock_data.TOOL_CALLS),
            }
        else:
            text = (
                "可以。把这半天空出来，按 **一个主点 + 一段散步** 来排最省力：\n\n"
                "- 先去你住的地方附近解决午饭，避免中午跨城。\n"
                "- 下午只安排一个景点，留 40 分钟在附近咖啡馆休息。\n"
                "- 晚上如果还有体力，再去河边走 20 分钟，随时可以回酒店。\n\n"
                "需要我把这个安排补进现有的行程卡里吗？"
            )
            extra = {}
        assistant = self.append_message(conv_id, "assistant", text, **extra)
        return {"user_message": user_message, "assistant_message": assistant}

    # ---------------------------------------------------------------- rag
    def list_documents(self) -> list[dict[str, Any]]:
        return sorted(self.documents, key=lambda d: d["created_at"], reverse=True)

    def add_document(self, title: str, source_type: str, filename: str) -> dict[str, Any]:
        doc = {
            "id": _uid("d"),
            "title": title or filename or "未命名资料",
            "source_type": source_type,
            "filename": filename,
            "status": "ready",
            "chunk_count": 18,
            "error": None,
            "created_at": _iso_now(),
        }
        self.documents.insert(0, doc)
        return {
            **doc,
            "chunk_preview": [
                "第一章 总则：景区实行分时段预约，游客需提前 1–7 天在官方渠道完成预约……",
                "预约时需填写姓名、身份证号与手机号，入园时刷身份证核验……",
                "周末与法定节假日单日限流 3 万人次，约满即止……",
            ],
        }

    def delete_document(self, doc_id: str) -> None:
        from .api_client import ApiError

        for doc in list(self.documents):
            if doc["id"] == doc_id:
                self.documents.remove(doc)
                return
        raise ApiError("NOT_FOUND", "文档不存在", 404)

    def search(self, query: str) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        hits = copy.deepcopy(mock_data.SEARCH_HITS)
        for hit in hits:
            hit["score"] = round(hit["score"] * (0.98 + (len(query) % 5) * 0.01), 4)
        return hits

    # -------------------------------------------------------------- users
    def list_users(self) -> list[dict[str, Any]]:
        for user in self.users:
            if user["username"] == "root":
                user["conversation_count"] = len(self.conversations)
        return self.users

    def patch_user(self, user_id: str, patch: dict[str, Any], actor: str = "root") -> dict[str, Any]:
        from .api_client import ApiError

        target = next((u for u in self.users if u["id"] == user_id), None)
        if target is None:
            raise ApiError("NOT_FOUND", "用户不存在", 404)
        if target["username"] == actor:
            raise ApiError("FORBIDDEN", "不能修改自己的角色或状态", 403)

        new_role = patch.get("role") or target["role"]
        new_status = patch.get("status") or target["status"]
        losing_root = (
            target["role"] == "root"
            and target["status"] == "active"
            and (new_role != "root" or new_status != "active")
        )
        active_roots = sum(
            1 for u in self.users if u["role"] == "root" and u["status"] == "active"
        )
        if losing_root and active_roots <= 1:
            raise ApiError("FORBIDDEN", "系统必须保留至少一个可用的 root 账号", 403)

        target["role"] = new_role
        target["status"] = new_status
        return {k: target[k] for k in ("id", "username", "role", "status")}


MOCK_STORE = MockStore()


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
