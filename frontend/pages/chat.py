"""对话页（FRONTEND.md 3.1、7、9 章）。

页面维护「当前轮次」的累积状态；WS 回调只往队列里塞帧，
所有 DOM 更新都在 60ms 的 `ui.timer` 里做。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from nicegui import background_tasks, ui

from ..api_client import ApiError, get_api
from ..components.conversation_list import ConversationList
from ..components.message_bubble import MessageBubble
from ..components.shell import AppShell, bind_page_js, mobile_menu_button
from ..components.thinking_bar import ThinkingBar
from ..components.tool_call_panel import normalize_live
from ..state import (
    clear_session,
    current_token,
    human_error,
    require_user,
    toast_error,
)
from ..theme import icon_svg
from ..ui_utils import icon_button
from ..ws_client import ChatSocket, MockChatSocket, create_chat_socket

logger = logging.getLogger("tpa.frontend.chat")

PROMPTS = (
    ("这周末去杭州玩两天，两个人，预算 1500", "周末短途", "01"),
    ("下周去成都出差三天，有什么值得去的地方", "出差顺游", "02"),
    ("带爸妈去苏州一日游，不想走太多路", "陪爸妈慢走", "03"),
)

BUSY_STATES = {"SENDING", "STREAMING", "CANCELLING"}


class ChatPage:
    def __init__(self, user: dict[str, Any], conversation_id: str | None) -> None:
        self.user = user
        self.conv_id = conversation_id
        self.state = "IDLE"
        self.messages: list[dict[str, Any]] = []
        self.buf = ""
        self.flushed = ""
        self.frames: list[dict[str, Any]] = []
        self.tool_events: list[dict[str, Any]] = []
        self.pending_itinerary: dict[str, Any] | None = None
        self.last_has_card = False
        self.bubble: MessageBubble | None = None
        self.socket: ChatSocket | MockChatSocket | None = None
        self.retry_text = ""
        self.pumping = False
        self.pending_seen = False
        self.last_pending_poll = 0.0
        self.cancel_deadline = 0.0
        self._cancelled_notified = False

        self.shell: AppShell | None = None
        self.conv_list: ConversationList | None = None
        self.title_label: Any = None
        self.sub_label: Any = None
        self.conn_dot: Any = None
        self.conn_text: Any = None
        self.conn_slot: Any = None
        self.degraded_slot: Any = None
        self.thinking: ThinkingBar | None = None
        self.scroll: Any = None
        self.inner: Any = None
        self.empty_slot: Any = None
        self.messages_slot: Any = None
        self.composer: Any = None
        self.input: Any = None
        self.action_btn: Any = None
        self.btn_icon: Any = None
        self.count_label: Any = None
        self.hint_label: Any = None

    # ------------------------------------------------------------------ 构建
    async def build(self) -> None:
        self.shell = AppShell(
            self.user,
            "chat",
            on_new_chat=self.new_chat,
            conversations_slot=True,
        )
        main = self.shell.build()

        with main:
            self._build_topbar()
            with ui.element("div").classes("banner-area"):
                self.conn_slot = ui.element("div")
                self.degraded_slot = ui.element("div")
            self.thinking = ThinkingBar()
            self._build_scroll()
            self._build_composer()

        if self.shell.conv_slot is not None:
            self.conv_list = ConversationList(
                current_id=self.conv_id,
                on_title_changed=self._on_conversation_renamed,
            )
            await self.conv_list.mount(self.shell.conv_slot)

        if self.conv_id:
            ok = await self._load_conversation(self.conv_id)
            if not ok:
                return
        else:
            self._render_empty()
            self._set_header("新的行程", "告诉我目的地、日期、人数和预算")

        bind_page_js()
        ui.timer(0.1, self._boot, once=True)
        ui.timer(0.06, self._pump)
        try:
            ui.context.client.on_disconnect(self._on_client_disconnect)
        except Exception:
            pass

    def _build_topbar(self) -> None:
        with ui.element("div").classes("tpa-topbar"):
            with ui.element("div").classes("topbar-left"):
                mobile_menu_button()
                with ui.element("div").classes("topbar-text"):
                    self.title_label = ui.label("新的行程").classes("topbar-title")
                    self.sub_label = ui.label("开始一段新的行程").classes("topbar-sub")
            with ui.element("div").classes("topbar-right"):
                with ui.element("span").classes("conn"):
                    self.conn_dot = ui.element("span").classes("conn-dot warn")
                    self.conn_text = ui.label("连接中")
                ui.element("span").classes("topbar-divider")
                icon_button(
                    "settings",
                    on_click=lambda: self.shell.open_status() if self.shell else None,
                    tooltip="系统状态",
                    size=16,
                )
                icon_button(
                    "plus",
                    on_click=self.new_chat,
                    tooltip="新建行程",
                    size=17,
                )

    def _build_scroll(self) -> None:
        self.scroll = ui.element("div").classes("tpa-chat-scroll").props("id=tpaChatScroll")
        with self.scroll:
            self.inner = ui.element("div").classes("tpa-chat-inner")
            with self.inner:
                self.empty_slot = ui.element("div")
                self.messages_slot = ui.element("div")

        to_bottom = ui.element("button").props("type=button aria-label=回到底部").classes(
            "tpa-tobottom"
        )
        to_bottom.on("click", lambda: ui.run_javascript("tpaScrollBottom(true)"))
        with to_bottom:
            ui.html(icon_svg("arrow-down", 15))

    def _build_composer(self) -> None:
        with ui.element("div").classes("tpa-composer-wrap"):
            self.composer = ui.element("div").classes("tpa-composer").props("id=tpaComposer")
            with self.composer:
                with ui.element("div").classes("composer-row"):
                    with ui.element("div").classes("composer-field"):
                        self.input = (
                            ui.textarea(
                                placeholder="描述你的行程，例如：这周末去杭州两天，两个人，预算 1500",
                                on_change=self._update_count,
                            )
                            .props("borderless autogrow rows=1")
                            .style("width:100%")
                        )
                    self.action_btn = (
                        ui.element("button")
                        .props("type=button id=tpaSendBtn aria-label=发送")
                        .classes("tpa-send")
                    )
                    self.action_btn.on("click", self._on_action)
                    with self.action_btn:
                        self.btn_icon = ui.html(icon_svg("arrow-up", 18))
                with ui.element("div").classes("composer-hint"):
                    self.hint_label = ui.label("Enter 发送 · Shift + Enter 换行")
                    ui.element("span").classes("spacer")
                    self.count_label = ui.label("")

    async def _boot(self) -> None:
        await self._connect_ws()
        await self._load_tools()
        await self._focus_input()
        if self.last_has_card:
            await self._scroll_last_assistant()
        else:
            await self._scroll_bottom(False)

    # ------------------------------------------------------------------ 头部
    def _set_header(self, title: str, subtitle: str | None = None) -> None:
        if self.title_label is not None:
            self.title_label.text = title or "新的行程"
        if self.sub_label is not None and subtitle is not None:
            self.sub_label.text = subtitle

    def _on_conversation_renamed(self, conv: dict[str, Any]) -> None:
        if conv.get("id") == self.conv_id:
            self._set_header(str(conv.get("title") or "新的行程"))

    # ------------------------------------------------------------------ 空态
    def _render_empty(self) -> None:
        if self.empty_slot is None:
            return
        if self.inner is not None:
            self.inner.classes(add="is-empty")
        self.empty_slot.clear()
        with self.empty_slot:
            with ui.element("div").classes("tpa-hero"):
                ui.label("NEW ITINERARY / 新行程").classes("tpa-kicker")
                ui.html("<h1>想去哪儿，<em>什么时候出发？</em></h1>")
                ui.label(
                    "把目的地、日期、人数和预算告诉我。我会先查天气和真实地点，"
                    "再给出一份能直接照着走的行程；哪句话是模型推断的，也会标出来。"
                )
                with ui.element("div").classes("prompt-grid"):
                    for text, tag, index in PROMPTS:
                        card = (
                            ui.element("button")
                            .props("type=button")
                            .classes("prompt-card")
                        )
                        card.on("click", lambda _=None, t=text: self._fill_prompt(t))
                        with card:
                            with ui.element("div").classes("prompt-top"):
                                ui.label(index).classes("prompt-index")
                                ui.html(icon_svg("arrow-right", 14)).classes("prompt-arrow")
                            ui.label(text).classes("prompt-text")
                            ui.label(tag).classes("prompt-index").style("letter-spacing:.08em")
                with ui.element("div").classes("hero-note"):
                    ui.label("点击示例会填入输入框，不会直接发送")
        self.messages_slot.clear()

    def _fill_prompt(self, text: str) -> None:
        if self.state in BUSY_STATES:
            return
        self.input.value = text
        self._update_count()
        ui.run_javascript('tpaFocus("#tpaComposer textarea")')

    # ------------------------------------------------------------------ 会话加载
    async def _load_conversation(self, conv_id: str) -> bool:
        try:
            data = await get_api().get(f"/api/v1/conversations/{conv_id}/messages")
        except ApiError as exc:
            toast_error(exc)
            if exc.code in {"NOT_FOUND", "FORBIDDEN"}:
                ui.navigate.to("/chat")
            return False

        conversation = (data or {}).get("conversation") or {}
        items = list((data or {}).get("items") or [])
        self.messages = items
        self.last_has_card = bool(
            items
            and items[-1].get("role") == "assistant"
            and items[-1].get("itinerary")
        )
        self._set_header(
            str(conversation.get("title") or "新的行程"),
            f"对话 · {len(items)} 条消息" if items else "还没有消息，写下第一句需求",
        )
        if items:
            self._render_messages(items)
        else:
            self._render_empty()
        return True

    def _render_messages(self, items: list[dict[str, Any]]) -> None:
        if self.messages_slot is None:
            return
        if self.inner is not None:
            self.inner.classes(remove="is-empty")
        self.empty_slot.clear()
        self.messages_slot.clear()
        self.bubble = None
        last_user = ""
        self.pending_seen = False
        with self.messages_slot:
            for message in items:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "assistant")
                status = str(message.get("status") or "completed")
                content = str(message.get("content") or "")
                if role == "user":
                    last_user = content
                    MessageBubble(
                        role="user",
                        content=content,
                        created_at=message.get("created_at"),
                    )
                    continue

                if status == "pending":
                    self.pending_seen = True
                    content = content or "正在生成…"
                retry = None
                if status == "failed" and last_user:
                    async def retry_action(t: str = last_user) -> None:
                        await self._retry(t)

                    retry = retry_action
                error_text = ""
                if status == "failed":
                    error_text = (
                        "上一轮生成被中断，可以重试"
                        if content.startswith("[")
                        else "这一轮生成失败了，可以重试"
                    )
                MessageBubble(
                    role="assistant",
                    content=content,
                    created_at=message.get("created_at"),
                    status=status,
                    itinerary=message.get("itinerary"),
                    citations=message.get("citations"),
                    tool_calls=message.get("tool_calls"),
                    error_text=error_text,
                    on_retry=retry,
                )
        if self.pending_seen:
            self.thinking.show("上一轮回复仍在服务端生成，完成后会自动刷新…")

    # ------------------------------------------------------------------ 发送
    def _update_count(self, _=None) -> None:
        if self.input is None or self.count_label is None:
            return
        length = len(self.input.value or "")
        self.count_label.text = f"{length} / 8000" if length else ""
        if length > 8000:
            self.count_label.classes(add="over")
        else:
            self.count_label.classes(remove="over")

    async def _on_action(self) -> None:
        if self.state == "STREAMING":
            await self._cancel()
        elif self.state in {"CANCELLING", "SENDING", "DISCONNECTED"}:
            return
        else:
            await self.send()

    async def send(self) -> None:
        if self.state in BUSY_STATES:
            return
        text = (self.input.value or "").strip()
        if not text:
            ui.notify("先写点什么再发送", type="warning", position="top")
            await self._focus_input()
            return
        if len(text) > 8000:
            ui.notify("消息不能超过 8000 字符", type="negative", position="top")
            return
        self.input.value = ""
        self._update_count()
        await self._send_text(text)

    async def _retry(self, text: str) -> None:
        if self.state in BUSY_STATES:
            return
        if not text.strip():
            return
        await self._send_text(text)

    async def _send_text(self, text: str) -> None:
        if not self.conv_id:
            self._set_state("SENDING", "正在创建会话…")
            try:
                conv = await get_api().post("/api/v1/conversations", json={})
            except ApiError as exc:
                toast_error(exc)
                self.input.value = text
                self._update_count()
                self._set_state("IDLE")
                return
            self.conv_id = str((conv or {}).get("id") or "") or None
            if not self.conv_id:
                self._fail_current("创建会话失败")
                return
            self._set_url(self.conv_id)
            self._set_header(str((conv or {}).get("title") or "新的行程"))
            if self.conv_list is not None:
                self.conv_list.current_id = self.conv_id
                await self.conv_list.refresh()

        self.retry_text = text
        self._append_user(text)
        self.buf = ""
        self.flushed = ""
        self.tool_events = []
        self.pending_itinerary = None
        self.bubble = self._append_streaming()
        self._set_state("SENDING", "正在发送…")
        await self._scroll_bottom(True)

        try:
            await self._ensure_socket()
            assert self.socket is not None
            await self.socket.send_message(self.conv_id, text)
            self._set_state("STREAMING", "正在思考…")
        except ApiError as exc:
            if exc.status == 401 or exc.code.startswith("AUTH_"):
                clear_session()
                ui.navigate.to("/login")
                return
            if exc.status == 0 or exc.code == "NETWORK_ERROR":
                await self._send_via_rest(text)
            else:
                self._fail_current(human_error(exc))
                toast_error(exc)

    async def _send_via_rest(self, text: str) -> None:
        """WS 连不上时的备用通道（FRONTEND.md 第 4 章）。"""
        if not self.conv_id:
            self._fail_current("会话不存在")
            return
        self._set_state("SENDING", "正在生成（备用通道）…")
        try:
            data = await get_api().post(
                f"/api/v1/conversations/{self.conv_id}/messages",
                json={"content": text},
            )
        except ApiError as exc:
            self._fail_current(human_error(exc))
            toast_error(exc)
            return

        assistant = (data or {}).get("assistant_message") or {}
        status = str(assistant.get("status") or "completed")
        if self.bubble is not None:
            calls = assistant.get("tool_calls") or []
            if calls:
                self.bubble.set_tool_calls(calls)
            self.bubble.finish(
                content=str(assistant.get("content") or ""),
                status=status,
                itinerary=assistant.get("itinerary"),
                citations=assistant.get("citations"),
                error_text="这一轮生成失败了，可以重试" if status == "failed" else "",
            )
        self._set_state("IDLE" if status != "failed" else "FAILED")
        self.thinking.hide()
        self.bubble = None
        self.buf = ""
        await self._refresh_sidebar()
        if assistant.get("itinerary"):
            await self._scroll_last_assistant()
        else:
            await self._scroll_bottom(True)
        await self._focus_input()

    def _append_user(self, text: str) -> None:
        self.empty_slot.clear()
        if self.inner is not None:
            self.inner.classes(remove="is-empty")
        with self.messages_slot:
            MessageBubble(
                role="user",
                content=text,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

    def _append_streaming(self) -> MessageBubble:
        with self.messages_slot:
            bubble = MessageBubble(
                role="assistant",
                content="",
                created_at=datetime.now(timezone.utc).isoformat(),
                streaming=True,
                status="streaming",
            )
        return bubble

    # ------------------------------------------------------------------ 状态机
    def _set_state(self, state: str, thinking: str | None = None) -> None:
        self.state = state
        busy = state in BUSY_STATES
        locked = busy or state == "DISCONNECTED"
        if self.input is not None:
            if locked:
                self.input.disable()
            else:
                self.input.enable()
        if self.composer is not None:
            if locked:
                self.composer.classes(add="is-disabled")
            else:
                self.composer.classes(remove="is-disabled")

        if self.action_btn is not None and self.btn_icon is not None:
            if state == "STREAMING":
                self.action_btn.props(remove="disabled")
                self.action_btn.classes(add="stop")
                self.action_btn.props("aria-label=停止生成")
                self.btn_icon.set_content(icon_svg("stop", 16))
            elif state in {"SENDING", "CANCELLING", "DISCONNECTED"}:
                self.action_btn.props("disabled")
                self.action_btn.classes(remove="stop")
                if state == "DISCONNECTED":
                    self.btn_icon.set_content(icon_svg("arrow-up", 18))
                else:
                    self.btn_icon.set_content('<span class="spinner-mini"></span>')
            else:
                self.action_btn.props(remove="disabled")
                self.action_btn.classes(remove="stop")
                self.action_btn.props("aria-label=发送")
                self.btn_icon.set_content(icon_svg("arrow-up", 18))

        if self.hint_label is not None:
            self.hint_label.text = (
                "连接已断开，重连后可继续"
                if state == "DISCONNECTED"
                else ("正在生成，完成后可继续输入" if busy else "Enter 发送 · Shift + Enter 换行")
            )

        if self.thinking is not None:
            if thinking and state in BUSY_STATES:
                self.thinking.show(thinking)
            elif state in {"IDLE", "FAILED", "DISCONNECTED"}:
                self.thinking.hide()

    async def _cancel(self) -> None:
        if self.state != "STREAMING":
            return
        if self.socket is None or not self.socket.connected:
            ui.notify("连接已断开，正在重连", type="warning", position="top")
            return
        assert self.conv_id is not None
        await self.socket.send_cancel(self.conv_id)
        self._set_state("CANCELLING", "正在停止…")
        self.cancel_deadline = time.monotonic() + 12
        self._cancelled_notified = False

    def _check_cancel_timeout(self) -> None:
        if self.state != "CANCELLING":
            return
        now = time.monotonic()
        if not self._cancelled_notified and self.cancel_deadline - now < 9:
            self._cancelled_notified = True
            ui.notify("停止请求已发出，正在收尾", type="info", position="top")
        if now > self.cancel_deadline:
            self._fail_current("已停止接收，刷新页面可查看最终结果")
            self.thinking.hide()

    # ------------------------------------------------------------------ 帧处理
    def _on_frame(self, frame: dict[str, Any]) -> None:
        """WS 协程里只入队，绝不直接碰 DOM（FRONTEND.md 6.6）。"""
        self.frames.append(frame)

    async def _pump(self) -> None:
        if self.pumping:
            return
        self.pumping = True
        try:
            while self.frames:
                frame = self.frames.pop(0)
                try:
                    await self._handle_frame(frame)
                except Exception:  # pragma: no cover
                    logger.exception("处理 WS 帧失败：%s", frame.get("type"))
            if self.bubble is not None and self.buf and self.buf != self.flushed:
                self.flushed = self.buf
                self.bubble.set_stream_text(self.buf)
                await self._auto_scroll()
            self._check_cancel_timeout()
            await self._maybe_poll_pending()
        finally:
            self.pumping = False

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        kind = str(frame.get("type") or "")
        data = frame.get("data") or {}
        if kind == "auth_ok":
            return
        if kind == "token":
            delta = str(data.get("delta") or "")
            if not self.buf and self.thinking is not None:
                self.thinking.token()
            self.buf += delta
            return
        if kind == "tool":
            self._handle_tool(data)
            return
        if kind == "itinerary":
            self.pending_itinerary = data if isinstance(data, dict) else None
            return
        if kind == "done":
            await self._handle_done(data)
            return
        if kind == "error":
            await self._handle_error(data)
            return
        if kind == "_disconnected":
            self._handle_disconnected()
            return
        if kind == "_reconnected":
            await self._handle_reconnected()
            return
        if kind == "_gaveup":
            self._handle_gaveup()
            return
        if kind == "_closed":
            self._handle_closed()
            return
        if kind == "_auth_failed":
            clear_session()
            ui.navigate.to("/login")
            return

    def _handle_tool(self, data: dict[str, Any]) -> None:
        self.tool_events.append(data)
        if self.bubble is not None:
            self.bubble.set_tool_calls(normalize_live(self.tool_events))
        phase = str(data.get("phase") or "")
        name = str(data.get("name") or "")
        if self.thinking is not None:
            if phase == "start":
                self.thinking.tool_start(name)
            elif phase == "end":
                self.thinking.tool_end()

    async def _handle_done(self, data: dict[str, Any]) -> None:
        status = str(data.get("status") or "completed")
        if status not in {"completed", "failed", "cancelled"}:
            status = "completed"
        message = data.get("message") or {}
        content = str(message.get("content") or self.buf)
        citations = message.get("citations") or []
        error_text = "这一轮生成失败了，可以重试" if status == "failed" else ""
        has_card = bool(self.pending_itinerary)
        if self.bubble is not None:
            self.bubble.finish(
                content=content,
                status=status,
                itinerary=self.pending_itinerary,
                citations=citations,
                error_text=error_text,
            )
        self.last_has_card = has_card
        self.buf = ""
        self.flushed = ""
        self.tool_events = []
        self.pending_itinerary = None
        self.bubble = None
        self._set_state("IDLE" if status != "failed" else "FAILED")
        if self.thinking is not None:
            self.thinking.hide()

        title = str(data.get("title") or "").strip()
        if title:
            self._set_header(title)
        await self._refresh_sidebar()
        if has_card:
            await self._scroll_last_assistant()
        else:
            await self._scroll_bottom(True)
        await self._focus_input()

    async def _handle_error(self, data: dict[str, Any]) -> None:
        code = str(data.get("code") or "INTERNAL_ERROR")
        message = str(data.get("message") or "请求失败")
        exc = ApiError(code, message, 400)
        ui.notify(human_error(exc), type="negative", position="top", multi_line=True)

        if self.bubble is not None:
            self.bubble.finish(
                content=self.buf,
                status="failed",
                error_text=human_error(exc),
            )
            self.bubble = None
            self._set_state("FAILED")
        if self.thinking is not None:
            self.thinking.hide()
        await self._refresh_sidebar()

    def _handle_disconnected(self) -> None:
        self._set_conn("warn", "重连中")
        self._show_conn_banner(
            "连接已断开，正在自动重连…",
            danger=False,
            action=None,
        )
        if self.state not in BUSY_STATES:
            self._set_state("DISCONNECTED")
        if self.state == "DISCONNECTED" and self.thinking is not None:
            self.thinking.hide()

    async def _handle_reconnected(self) -> None:
        self._set_conn("ok", "已连接")
        self._clear_conn_banner()
        ui.notify("连接已恢复", type="positive", position="top")
        self._set_state("IDLE")
        await self._backfill()

    def _handle_gaveup(self) -> None:
        self._set_conn("off", "已断开")
        self._show_conn_banner(
            "连接已断开，请刷新页面后继续。已生成的内容仍保存在服务端。",
            danger=True,
            action=("刷新页面", lambda: ui.run_javascript("window.location.reload()")),
        )
        if self.bubble is not None:
            self.bubble.finish(
                content=self.buf,
                status="failed",
                error_text="连接已断开，已保留部分内容。刷新页面可查看最终结果。",
            )
            self.bubble = None
        if self.thinking is not None:
            self.thinking.hide()
        self._set_state("DISCONNECTED")

    def _handle_closed(self) -> None:
        self._set_conn("off", "已关闭")
        self._show_conn_banner(
            "实时连接已关闭，请刷新页面继续。",
            danger=True,
            action=("刷新页面", lambda: ui.run_javascript("window.location.reload()")),
        )
        self._set_state("DISCONNECTED")

    # ------------------------------------------------------------------ 连接
    async def _connect_ws(self) -> None:
        token = current_token()
        if not token:
            ui.navigate.to("/login")
            return
        if self.socket is None:
            self.socket = create_chat_socket(self._on_frame)
        self._set_conn("warn", "连接中")
        try:
            await self.socket.connect(token)
        except ApiError as exc:
            if exc.status == 401 or exc.code.startswith("AUTH_"):
                clear_session()
                ui.navigate.to("/login")
                return
            logger.info("实时通道不可用：%s", exc.message)
            self._set_conn("warn", "备用通道")
            self._show_conn_banner(
                "实时通道暂时不可用。发送消息会自动改用备用通道，功能不受影响。",
                danger=False,
                action=("重试连接", self._retry_connect),
            )
            return
        self._set_conn("ok", "已连接")
        self._clear_conn_banner()

    async def _retry_connect(self) -> None:
        await self._connect_ws()

    async def _ensure_socket(self) -> None:
        if self.socket is not None and self.socket.connected:
            return
        token = current_token()
        if not token:
            raise ApiError("AUTH_TOKEN_INVALID", "登录已过期", 401)
        if self.socket is None:
            self.socket = create_chat_socket(self._on_frame)
        await self.socket.connect(token)
        self._set_conn("ok", "已连接")
        self._clear_conn_banner()

    def _set_conn(self, kind: str, text: str) -> None:
        if self.conn_text is None or self.conn_dot is None:
            return
        self.conn_text.text = text
        self.conn_dot.classes(remove="warn off")
        if kind == "warn":
            self.conn_dot.classes(add="warn")
        elif kind == "off":
            self.conn_dot.classes(add="off")

    def _show_conn_banner(
        self,
        text: str,
        danger: bool,
        action: tuple[str, Any] | None,
    ) -> None:
        if self.conn_slot is None:
            return
        self.conn_slot.clear()
        with self.conn_slot:
            with ui.element("div").classes("tpa-banner" + (" danger" if danger else "")):
                ui.html(icon_svg("warn", 14)).classes("icon")
                ui.label(text)
                ui.element("span").classes("spacer")
                if action is not None:
                    label, handler = action
                    button = ui.element("button").props("type=button").classes("btn-link")
                    button.style("color:inherit;text-decoration:underline;text-underline-offset:3px")
                    button.on("click", handler)
                    with button:
                        ui.label(label)

    def _clear_conn_banner(self) -> None:
        if self.conn_slot is not None:
            self.conn_slot.clear()

    async def _load_tools(self) -> None:
        try:
            data = await get_api().get("/api/v1/tools")
        except ApiError:
            return
        servers = (data or {}).get("servers") or []
        if not (data or {}).get("degraded"):
            return
        place_down = any(
            str(s.get("name")) == "place" and str(s.get("status")) != "connected"
            for s in servers
        )
        text = (
            "地点服务暂时不可用，本次规划可能缺少景点信息"
            if place_down
            else "部分工具服务暂时不可用，规划结果可能不完整"
        )
        if self.degraded_slot is None:
            return
        self.degraded_slot.clear()
        with self.degraded_slot:
            with ui.element("div").classes("tpa-banner"):
                ui.html(icon_svg("warn", 14)).classes("icon")
                ui.label(text)
                ui.element("span").classes("spacer")
                button = ui.element("button").props("type=button").classes("btn-link")
                button.style("color:inherit;text-decoration:underline")
                button.on("click", lambda: self.shell.open_status() if self.shell else None)
                with button:
                    ui.label("查看状态")

    # ------------------------------------------------------------------ 辅助
    async def _refresh_sidebar(self) -> None:
        if self.conv_list is None:
            return
        await self.conv_list.refresh()
        for item in self.conv_list.items:
            if item.get("id") == self.conv_id:
                count = int(item.get("message_count") or 0)
                self._set_header(
                    str(item.get("title") or "新的行程"),
                    f"对话 · {count} 条消息",
                )
                break

    async def _backfill(self, quiet: bool = False) -> None:
        if not self.conv_id:
            return
        try:
            data = await get_api().get(f"/api/v1/conversations/{self.conv_id}/messages")
        except ApiError as exc:
            if not quiet:
                toast_error(exc)
            return
        conversation = (data or {}).get("conversation") or {}
        items = list((data or {}).get("items") or [])
        self.messages = items
        self.last_has_card = bool(
            items
            and items[-1].get("role") == "assistant"
            and items[-1].get("itinerary")
        )
        self._render_messages(items)
        self._set_header(
            str(conversation.get("title") or "新的行程"),
            f"对话 · {len(items)} 条消息",
        )
        if not items:
            self._render_empty()
        if not self.pending_seen:
            if self.thinking is not None:
                self.thinking.hide()
            if self.last_has_card:
                await self._scroll_last_assistant()
            else:
                await self._scroll_bottom(False)
        await self._refresh_sidebar()

    async def _poll_pending_once(self) -> None:
        if not self.pending_seen or self.conv_id is None:
            return
        await self._backfill(quiet=True)
        if not self.pending_seen and self.thinking is not None:
            self.thinking.hide()
            ui.notify("上一轮回复已生成", type="positive", position="top")

    async def _maybe_poll_pending(self) -> None:
        if not self.pending_seen or self.state in BUSY_STATES:
            return
        now = time.monotonic()
        if now - self.last_pending_poll < 3.0:
            return
        self.last_pending_poll = now
        await self._poll_pending_once()

    async def _focus_input(self) -> None:
        try:
            await ui.run_javascript('tpaFocus("#tpaComposer textarea")')
        except Exception:
            pass

    async def _scroll_bottom(self, smooth: bool) -> None:
        try:
            await ui.run_javascript(
                f"tpaScrollBottom({'true' if smooth else 'false'})"
            )
        except Exception:
            pass

    async def _auto_scroll(self) -> None:
        try:
            await ui.run_javascript("tpaAutoScroll()")
        except Exception:
            pass

    async def _scroll_last_assistant(self) -> None:
        try:
            await ui.run_javascript("tpaScrollToLastAssistant()")
        except Exception:
            pass

    def _set_url(self, conv_id: str) -> None:
        try:
            ui.run_javascript(
                f"history.replaceState(null, '', '/chat/{conv_id}')"
            )
        except Exception:
            pass

    def _fail_current(self, message: str) -> None:
        if self.bubble is not None:
            self.bubble.finish(
                content=self.buf,
                status="failed",
                error_text=message,
            )
            self.bubble = None
        self.buf = ""
        self._set_state("FAILED")
        if self.thinking is not None:
            self.thinking.hide()

    async def new_chat(self) -> None:
        if self.state in BUSY_STATES:
            ui.notify("正在生成回复，请稍候", type="warning", position="top")
            return
        if not self.conv_id:
            self.input.value = ""
            self._update_count()
            self._render_empty()
            await self._focus_input()
            return
        try:
            conv = await get_api().post("/api/v1/conversations", json={})
        except ApiError as exc:
            toast_error(exc)
            return
        target = str((conv or {}).get("id") or "")
        ui.navigate.to(f"/chat/{target}" if target else "/chat")

    def _on_client_disconnect(self) -> None:
        if self.socket is not None:
            background_tasks.create(self._shutdown())

    async def _shutdown(self) -> None:
        try:
            if self.socket is not None:
                await self.socket.close()
        except Exception:
            pass


@ui.page("/chat", title="出行计划助手", response_timeout=20)
@ui.page("/chat/{conversation_id}", title="出行计划助手", response_timeout=20)
async def chat_page(conversation_id: str | None = None) -> None:
    user = await require_user()
    if not user:
        return
    page = ChatPage(user, conversation_id)
    await page.build()
