"""消息气泡（FRONTEND.md 7.1）。用户消息纯文本，助手消息 Markdown。"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from nicegui import ui

from ..theme import icon_svg
from ..ui_utils import fmt_time, icon_button
from .itinerary_card import render_itinerary
from .tool_call_panel import ToolCallPanel

logger = logging.getLogger("tpa.frontend.bubble")

_JSON_FENCE = re.compile(r"```(?:json|JSON)?[ \t]*\r?\n(.*?)```", re.S)
_HEADING_GLUE = re.compile(r"([。！？；])\s*(#{1,4}\s+)")


def _normalize_markdown(text: str) -> str:
    """模型偶尔会把标题粘在句号后面，补一个空行让 Markdown 正确分块。"""
    return _HEADING_GLUE.sub(r"\1\n\n\2", text or "")


def _content_segments(content: str) -> list[tuple[str, str]]:
    """把很长的 fenced JSON 从正文里拆出来，默认折叠，避免一屏代码。"""
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in _JSON_FENCE.finditer(content or ""):
        body = match.group(1)
        stripped = body.lstrip()
        if len(body) < 280 or not stripped.startswith(("{", "[")):
            continue
        before = content[cursor : match.start()]
        if before.strip():
            parts.append(("md", before))
        parts.append(("json", body.strip()))
        cursor = match.end()
    rest = content[cursor:]
    if rest.strip():
        parts.append(("md", rest))
    if not parts:
        parts.append(("md", content or " "))
    return parts


def _citations(citations: list[Any] | None) -> None:
    valid = [c for c in (citations or []) if isinstance(c, dict)]
    if not valid:
        return
    block = ui.element("div").classes("cites")
    with block:
        head = ui.element("div").classes("cites-head").props(
            "role=button tabindex=0"
        )
        with head:
            ui.html(icon_svg("book", 12))
            ui.label("引用资料")
            ui.label(f"{len(valid)} 篇").classes("cite-score").style("margin-left:0")
            ui.element("span").classes("spacer").style("flex:1")
            ui.html(icon_svg("chevron-right", 12)).classes("chev")
        with ui.element("div").classes("cites-body"):
            for number, cite in enumerate(valid, start=1):
                with ui.element("div").classes("cite"):
                    ui.label(f"{number:02d}").classes("cite-num")
                    with ui.element("div").classes("cite-main"):
                        with ui.element("div").classes("cite-head"):
                            ui.label(str(cite.get("title") or "未命名资料")).classes("cite-title")
                            if cite.get("ordinal") is not None:
                                ui.label(f"块 #{cite.get('ordinal')}").classes("cite-score")
                            if cite.get("score") is not None:
                                try:
                                    score = f"{float(cite.get('score')):.3f}"
                                except (TypeError, ValueError):
                                    score = str(cite.get("score"))
                                ui.label(score).classes("cite-score")
                        snippet = str(cite.get("snippet") or "").strip()
                        if snippet:
                            ui.label(snippet).classes("cite-snippet")

        def toggle(_=None, b=block) -> None:
            b.classes(toggle="open")

        head.on("click", toggle)
        head.on("keydown.enter", toggle)


class MessageBubble:
    def __init__(
        self,
        *,
        role: str,
        content: str = "",
        created_at: str | None = None,
        status: str = "completed",
        itinerary: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        streaming: bool = False,
        error_text: str = "",
        on_retry: Any = None,
    ) -> None:
        self.role = role
        self.content = content or ""
        self.status = status
        self.streaming = streaming
        self.on_retry = on_retry
        self.markdown: Any = None
        self.content_slot: Any = None
        self.tool_slot: Any = None
        self.status_slot: Any = None
        self.card_slot: Any = None
        self.cite_slot: Any = None
        self._citations_rendered = False
        self.dom_id = f"tpaStream{uuid.uuid4().hex[:8]}"
        self.root: Any = None

        try:
            if role == "user":
                self._build_user(content, created_at)
            else:
                self._build_assistant(
                    content,
                    created_at,
                    status,
                    itinerary,
                    citations,
                    tool_calls,
                    streaming,
                    error_text,
                )
        except Exception:  # pragma: no cover
            logger.exception("消息渲染失败")
            try:
                with ui.element("div").classes("msg msg-assistant"):
                    ui.markdown(content or "（渲染失败）").classes("tpa-md")
            except Exception:
                pass

    # ------------------------------------------------------------------ 构建
    def _build_user(self, content: str, created_at: str | None) -> None:
        self.root = ui.element("div").classes("msg msg-user")
        with self.root:
            ui.label(content).classes("msg-user-box")

    def _build_assistant(
        self,
        content: str,
        created_at: str | None,
        status: str,
        itinerary: dict[str, Any] | None,
        citations: list[dict[str, Any]] | None,
        tool_calls: list[dict[str, Any]] | None,
        streaming: bool,
        error_text: str,
    ) -> None:
        self.root = ui.element("div").classes("msg msg-assistant")
        with self.root:
            with ui.element("div").classes("msg-head"):
                with ui.element("div").classes("msg-role"):
                    ui.html(icon_svg("compass", 13))
                    ui.label("行迹").classes("role-name")
                    ui.element("span").classes("rule")
                    ui.label("行程顾问")
                if created_at:
                    ui.label(fmt_time(created_at)).classes("msg-time")
                with ui.element("div").classes("msg-actions"):
                    icon_button(
                        "copy",
                        on_click=lambda: self._copy(),
                        tooltip="复制",
                        classes="mini",
                        size=13,
                    )
            self.tool_slot = ui.element("div")
            self.content_slot = ui.element("div").classes("msg-content")
            with self.content_slot:
                self.markdown = ui.markdown("").classes("tpa-md")
                self.markdown.props(f'id="{self.dom_id}"')
            self.status_slot = ui.element("div")
            self.card_slot = ui.element("div")
            self.cite_slot = ui.element("div")

        if streaming:
            self.set_stream_text(content)
        else:
            self._render_final(content)
        if tool_calls:
            self.set_tool_calls(tool_calls)
        if itinerary:
            self._render_card(itinerary)
        if citations:
            with self.cite_slot:
                _citations(citations)
            self._citations_rendered = True
        if not streaming:
            self._render_status(status, error_text)

    # ------------------------------------------------------------------ 更新
    def _render_final(self, content: str) -> None:
        if self.content_slot is None:
            return
        self.content_slot.clear()
        with self.content_slot:
            for kind, text in _content_segments(content or ""):
                if kind == "json":
                    self._json_block(text)
                else:
                    self.markdown = ui.markdown(_normalize_markdown(text)).classes("tpa-md")

    def _json_block(self, body: str) -> None:
        with ui.element("details").classes("json-block"):
            with ui.element("summary").classes("json-summary"):
                ui.html(icon_svg("code", 12))
                ui.label("结构化行程数据")
                ui.label(f"{len(body)} 字符 · 展开 / 收起").classes("json-hint")
            ui.label(body).classes("json-pre")

    def set_stream_text(self, text: str) -> None:
        self.content = text or ""
        if self.markdown is None:
            return
        self.markdown.set_content(self.content or " ")
        try:
            ui.run_javascript(f"tpaCaret('{self.dom_id}', true)")
        except Exception:
            pass

    def set_tool_calls(self, calls: list[dict[str, Any]]) -> None:
        if self.tool_slot is None:
            return
        self.tool_slot.clear()
        with self.tool_slot:
            ToolCallPanel(calls).mount()

    def finish(
        self,
        *,
        content: str,
        status: str,
        itinerary: dict[str, Any] | None = None,
        citations: list[dict[str, Any]] | None = None,
        error_text: str = "",
    ) -> None:
        self.streaming = False
        self.status = status
        self.content = content or ""
        try:
            ui.run_javascript(f"tpaCaret('{self.dom_id}', false)")
        except Exception:
            pass
        self._render_final(self.content)
        if self.status_slot is not None:
            self.status_slot.clear()
        if itinerary:
            self._render_card(itinerary)
        if citations and self.cite_slot is not None and not self._citations_rendered:
            with self.cite_slot:
                _citations(citations)
            self._citations_rendered = True
        self._render_status(status, error_text)

    def _render_card(self, itinerary: dict[str, Any]) -> None:
        if self.card_slot is None:
            return
        self.card_slot.clear()
        with self.card_slot:
            render_itinerary(itinerary)

    def _render_status(self, status: str, error_text: str) -> None:
        if self.status_slot is None:
            return
        if status == "cancelled":
            with self.status_slot:
                with ui.element("div").classes("msg-cancelled"):
                    ui.element("span").classes("dash")
                    ui.label("已停止生成")
        elif status == "pending":
            with self.status_slot:
                with ui.element("div").classes("msg-cancelled"):
                    ui.element("span").classes("dot-pending")
                    ui.label("这条回复仍在生成中…")
        elif status == "failed":
            with self.status_slot:
                with ui.element("div").classes("msg-fail"):
                    ui.html(icon_svg("warn", 14)).classes("icon")
                    ui.label(error_text or "这一轮生成失败了，可以重试")
                    ui.element("span").classes("spacer")
                    if self.on_retry is not None:
                        retry = ui.element("button").props("type=button").classes("retry")
                        retry.on("click", self.on_retry)
                        with retry:
                            ui.label("重试")

    def _copy(self) -> None:
        ui.clipboard.write(self.content or "")
        ui.notify("已复制", type="positive", position="top")
