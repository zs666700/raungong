"""会话列表（FRONTEND.md 7.3）：按更新时间分组，带重命名与删除。"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from ..api_client import ApiError, get_api
from ..theme import icon_svg
from ..ui_utils import fmt_short, group_label
from .dialogs import ConfirmDialog, PromptDialog


class ConversationList:
    def __init__(
        self,
        current_id: str | None = None,
        *,
        on_title_changed: Callable[[dict[str, Any]], Any] | None = None,
        on_deleted: Callable[[str], Any] | None = None,
    ) -> None:
        self.current_id = current_id
        self.on_title_changed = on_title_changed
        self.on_deleted = on_deleted
        self.container: Any = None
        self.items: list[dict[str, Any]] = []
        self.confirm = ConfirmDialog()
        self.prompt = PromptDialog()

    async def mount(self, parent: Any) -> None:
        with parent:
            self.container = ui.element("div")
        await self.refresh()

    async def refresh(self) -> None:
        if self.container is None:
            return
        self.container.clear()
        with self.container:
            with ui.element("div").classes("side-label"):
                ui.label("行程")
                ui.label("…").classes("count")
        try:
            data = await get_api().get("/api/v1/conversations", params={"page_size": 100})
        except ApiError as exc:
            with self.container:
                ui.label(f"列表加载失败：{exc.message}").classes("conv-empty")
            return
        self.items = list((data or {}).get("items") or [])
        self._render()

    def _render(self) -> None:
        if self.container is None:
            return
        self.container.clear()
        with self.container:
            with ui.element("div").classes("side-label"):
                ui.label("行程")
                ui.label(str(len(self.items))).classes("count")
            if not self.items:
                ui.label("还没有对话。\n从一句想法开始，行程会保存在这里。").classes(
                    "conv-empty"
                ).style("white-space:pre-line")
                return
            last_group = ""
            for conv in self.items:
                group = group_label(conv.get("updated_at"))
                if group != last_group:
                    last_group = group
                    ui.label(group).classes("side-group")
                self._render_item(conv)

    def _render_item(self, conv: dict[str, Any]) -> None:
        conv_id = str(conv.get("id") or "")
        active = conv_id == self.current_id
        row = ui.element("div").classes("conv-item" + (" active" if active else ""))
        with row:
            main = ui.element("div").classes("conv-main").props(
                "role=button tabindex=0"
            )
            main.on("click", lambda _=None, cid=conv_id: ui.navigate.to(f"/chat/{cid}"))
            main.on("keydown.enter", lambda _=None, cid=conv_id: ui.navigate.to(f"/chat/{cid}"))
            with main:
                ui.label(str(conv.get("title") or "新对话")).classes("conv-title")
                with ui.element("div").classes("conv-meta"):
                    ui.label(f"{conv.get('message_count') or 0} 条")
                    if conv.get("has_itinerary"):
                        ui.element("span").classes("trip-dot")
                        ui.label("已生成行程")
                    ui.label(fmt_short(conv.get("updated_at"))).style("margin-left:auto")

            more = ui.element("button").props("type=button aria-label=更多操作").classes(
                "conv-more"
            )
            with more:
                ui.html(icon_svg("more", 15))
                with ui.menu() as menu:
                    ui.menu_item("重命名", on_click=lambda: self._ask_rename(conv))
                    ui.menu_item("删除", on_click=lambda: self._ask_delete(conv))
            more.on("click", menu.open)

    def _ask_rename(self, conv: dict[str, Any]) -> None:
        async def action(text: str) -> bool:
            data = await get_api().patch(
                f"/api/v1/conversations/{conv['id']}", json={"title": text}
            )
            conv["title"] = (data or {}).get("title") or text
            ui.notify("已重命名", type="positive", position="top")
            if self.on_title_changed is not None:
                self.on_title_changed(conv)
            await self.refresh()
            return True

        self.prompt.open(
            "重命名行程",
            "标题会显示在左侧列表与页面顶部，最多 60 个字符。",
            str(conv.get("title") or ""),
            action,
            confirm_label="保存",
            placeholder="例如：杭州周末两天",
        )

    def _ask_delete(self, conv: dict[str, Any]) -> None:
        async def action() -> None:
            await get_api().delete(f"/api/v1/conversations/{conv['id']}")
            ui.notify("会话已删除", type="positive", position="top")
            is_current = conv.get("id") == self.current_id
            if self.on_deleted is not None:
                self.on_deleted(str(conv.get("id")))
            if is_current:
                ui.navigate.to("/chat")
            else:
                await self.refresh()

        self.confirm.open(
            "删除这段对话？",
            f"「{conv.get('title') or '新对话'}」及其全部消息会被永久删除，无法恢复。",
            "删除",
            action,
            danger=True,
        )
