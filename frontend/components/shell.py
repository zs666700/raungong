"""页面骨架：左侧导航、品牌、用户菜单与移动端抽屉。"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import app, ui

from ..state import logout
from ..theme import apply_theme, brand_mark, icon_svg
from ..ui_utils import icon_button, initials
from .dialogs import ProfileDialog, StatusDialog


class AppShell:
    def __init__(
        self,
        user: dict[str, Any],
        active: str,
        *,
        on_new_chat: Callable[[], Any] | None = None,
        conversations_slot: bool = False,
    ) -> None:
        self.user = user
        self.active = active
        self.on_new_chat = on_new_chat
        self.conversations_slot = conversations_slot
        self.root: Any = None
        self.main: Any = None
        self.conv_slot: Any = None
        self.profile_dialog: ProfileDialog | None = None
        self.status_dialog: StatusDialog | None = None

    # ------------------------------------------------------------------ 构建
    def build(self) -> Any:
        apply_theme()
        with ui.element("div").classes("tpa-shell") as self.root:
            self._sidebar()
            self.main = ui.element("div").classes("tpa-main")
        scrim = ui.element("div").classes("tpa-scrim")
        scrim.on("click", lambda: ui.run_javascript("tpaToggleNav(false)"))
        return self.main

    def _sidebar(self) -> None:
        is_root = self.user.get("role") == "root"
        with ui.element("aside").classes("tpa-sidebar"):
            # 品牌
            brand = ui.element("div").classes("tpa-brand")
            brand.on("click", lambda: ui.navigate.to("/chat"))
            brand.style("cursor:pointer")
            with brand:
                ui.html(brand_mark(34)).classes("tpa-brand-mark")
                with ui.element("div").classes("tpa-brand-text"):
                    ui.label("行迹").classes("tpa-brand-name")
                    ui.label("Travel Atelier").classes("tpa-brand-sub")

            # 新建
            new_btn = ui.element("button").props("type=button").classes("tpa-newbtn")
            if self.on_new_chat is not None:
                new_btn.on("click", self.on_new_chat)
            else:
                new_btn.on("click", lambda: ui.navigate.to("/chat"))
            with new_btn:
                with ui.element("span").classes("tpa-newbtn-left"):
                    ui.html(icon_svg("plus", 15))
                    ui.label("新建行程")
                ui.html(icon_svg("arrow-right", 15))

            # 滚动区
            with ui.element("div").classes("side-scroll"):
                if self.conversations_slot:
                    self.conv_slot = ui.element("div")
                else:
                    self._nav_section(
                        "工作台",
                        [("chat", "对话工作台", "/chat", self.active == "chat", None)],
                    )
                if is_root:
                    self._nav_section(
                        "管理",
                        [
                            ("book", "知识库", "/knowledge", self.active == "knowledge", "RAG"),
                            ("users", "用户", "/users", self.active == "users", None),
                        ],
                    )

            self._user_card()

            if self.profile_dialog is None:
                self.profile_dialog = ProfileDialog()
            if self.status_dialog is None:
                self.status_dialog = StatusDialog()

    def _nav_section(
        self,
        title: str,
        items: list[tuple[str, str, str, bool, str | None]],
    ) -> None:
        with ui.element("div").classes("side-section"):
            with ui.element("div").classes("side-label"):
                ui.label(title)
                ui.label(str(len(items))).classes("count")
            with ui.element("div").classes("side-nav"):
                for icon_name, label, target, active, sub in items:
                    item = ui.element("button").props("type=button").classes(
                        "side-nav-item" + (" active" if active else "")
                    )
                    item.on("click", lambda _=None, t=target: ui.navigate.to(t))
                    with item:
                        ui.html(icon_svg(icon_name, 16)).classes("side-nav-icon")
                        ui.label(label)
                        if sub:
                            ui.label(sub).classes("side-nav-sub")

    def _user_card(self) -> None:
        with ui.element("div").classes("side-user"):
            identity = ui.element("button").props(
                "type=button aria-label=账号菜单"
            ).classes("side-user-id")
            with identity:
                ui.label(initials(self.user.get("username"))).classes("avatar")
                with ui.element("div").classes("side-user-info"):
                    ui.label(str(self.user.get("username") or "—")).classes("side-user-name")
                    role = "管理员" if self.user.get("role") == "root" else "普通用户"
                    ui.label(role).classes("side-user-role")
            trigger = ui.element("button").props("type=button aria-label=更多").classes(
                "side-user-btn"
            )
            with trigger:
                ui.html(icon_svg("more", 16))
                with ui.menu() as menu:
                    ui.menu_item(
                        "旅行偏好",
                        on_click=lambda: self._open_profile(),
                    )
                    ui.menu_item(
                        "系统状态",
                        on_click=lambda: self._open_status(),
                    )
                    ui.separator().style("background:var(--line);margin:4px 0")
                    ui.menu_item("退出登录 / 切换账号", on_click=logout)
            trigger.on("click", menu.open)
            identity.on("click", menu.open)

    def _open_profile(self) -> None:
        if self.profile_dialog is None:
            return
        user = app.storage.user.get("user") or self.user
        self.profile_dialog.open(user)

    def _open_status(self) -> None:
        if self.status_dialog is not None:
            ui.timer(0.01, self.status_dialog.open, once=True)

    def open_status(self) -> None:
        self._open_status()

    # ------------------------------------------------------------------ 顶栏
    def topbar(
        self,
        title: str,
        subtitle: str = "",
        right: Callable[[], None] | None = None,
        *,
        menu: bool = True,
    ) -> Any:
        with ui.element("div").classes("tpa-topbar") as bar:
            with ui.element("div").classes("topbar-left"):
                if menu:
                    mobile_menu_button()
                with ui.element("div").classes("topbar-text"):
                    ui.label(title).classes("topbar-title")
                    if subtitle:
                        ui.label(subtitle).classes("topbar-sub")
            with ui.element("div").classes("topbar-right"):
                if right:
                    right()
        return bar

    def admin_topbar(self, title: str) -> Any:
        def _right() -> None:
            back = ui.element("button").props("type=button").classes("btn-ghost")
            back.on("click", lambda: ui.navigate.to("/chat"))
            with back:
                ui.html(icon_svg("chat", 14))
                ui.label("返回对话")
            icon_button(
                "settings",
                on_click=lambda: self._open_status(),
                tooltip="系统状态",
                size=16,
            )

        return self.topbar("管理工作台", title, _right)


def mobile_menu_button() -> Any:
    button = ui.element("button").props("type=button aria-label=打开导航").classes(
        "iconbtn tpa-menu-btn"
    )
    button.on("click", lambda: ui.run_javascript("tpaToggleNav()"))
    with button:
        ui.html(icon_svg("menu", 18))
    return button


def bind_page_js() -> None:
    """页面构建完再绑定滚动与输入框快捷键。"""
    ui.timer(0.25, lambda: ui.run_javascript("tpaBindTextarea()"), once=True)
