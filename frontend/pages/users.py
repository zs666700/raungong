"""用户管理页（FRONTEND.md 10.2）。仅 root 可见，且只显示会话数量。"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from ..api_client import ApiError, get_api
from ..components.dialogs import ConfirmDialog
from ..components.shell import AppShell
from ..state import human_error, require_root, toast_error
from ..theme import icon_svg
from ..ui_utils import badge, fmt_short

logger = logging.getLogger("tpa.frontend.users")


class UsersPage:
    def __init__(self, user: dict[str, Any]) -> None:
        self.user = user
        self.users: list[dict[str, Any]] = []
        self.table_slot: Any = None
        self.stats_slot: Any = None
        self.confirm = ConfirmDialog()

    async def build(self) -> None:
        shell = AppShell(self.user, "users")
        main = shell.build()
        with main:
            shell.admin_topbar("用户")
            with ui.element("div").classes("admin-scroll"):
                with ui.element("div").classes("admin-inner"):
                    self._head()
                    self.stats_slot = ui.element("div")
                    with ui.element("div").classes("tpa-table"):
                        with ui.element("div").classes("thead user-head"):
                            ui.label("用户名")
                            ui.label("角色")
                            ui.label("状态")
                            ui.label("会话数")
                            ui.label("注册时间")
                            ui.label("操作")
                        self.table_slot = ui.element("div")
                    ui.label(
                        "出于隐私边界，这里只显示每个人的会话数量，不提供查看对话内容的入口。"
                    ).classes("note").style("margin-top:14px")
        await self.refresh()

    def _head(self) -> None:
        with ui.element("div").classes("page-head"):
            with ui.element("div").classes("page-head-main"):
                ui.label("ADMIN / PEOPLE").classes("page-kicker")
                ui.label("用户").classes("page-title")
                ui.label(
                    "管理账号的角色与启用状态。禁用会立即生效——后端每次请求都会查库校验，不依赖 token 内容。"
                ).classes("page-sub")

    async def refresh(self) -> None:
        if self.table_slot is None:
            return
        self.table_slot.clear()
        with self.table_slot:
            for width in (34, 28, 26, 20, 32):
                with ui.element("div").classes("skeleton-row"):
                    ui.element("span").classes("skeleton-bar").style(f"width:{width}%")
        try:
            data = await get_api().get("/api/v1/admin/users", params={"page_size": 100})
        except ApiError as exc:
            self.table_slot.clear()
            with self.table_slot:
                with ui.element("div").classes("empty-box"):
                    ui.html(icon_svg("warn", 34)).classes("empty-icon")
                    ui.label("加载失败").classes("empty-title")
                    ui.label(human_error(exc, "无法读取用户列表")).classes("empty-text")
            return
        self.users = list((data or {}).get("items") or [])
        self._render_stats()
        self._render_table()

    def _render_stats(self) -> None:
        roots = sum(1 for u in self.users if u.get("role") == "root")
        active = sum(1 for u in self.users if u.get("status") == "active")
        disabled = len(self.users) - active
        self.stats_slot.clear()
        with self.stats_slot:
            with ui.element("div").classes("stats"):
                for index, (value, label) in enumerate(
                    (
                        (len(self.users), "总用户"),
                        (roots, "管理员"),
                        (active, "可用"),
                        (disabled, "已禁用"),
                    )
                ):
                    if index:
                        ui.element("div").classes("stat-div")
                    with ui.element("div").classes("stat"):
                        ui.label(str(value)).classes("stat-num")
                        ui.label(label).classes("stat-label")

    def _render_table(self) -> None:
        self.table_slot.clear()
        if not self.users:
            with self.table_slot:
                with ui.element("div").classes("empty-box"):
                    ui.html(icon_svg("users", 34)).classes("empty-icon")
                    ui.label("暂无用户").classes("empty-title")
                    ui.label("正常情况下至少会有一个 root 账号。").classes("empty-text")
            return

        active_roots = sum(
            1
            for u in self.users
            if u.get("role") == "root" and u.get("status") == "active"
        )
        with self.table_slot:
            for target in self.users:
                self._render_user(target, active_roots)

    def _render_user(self, target: dict[str, Any], active_roots: int) -> None:
        is_self = target.get("id") == self.user.get("id")
        is_root = target.get("role") == "root"
        is_active = target.get("status") == "active"
        row = ui.element("div").classes("trow user-row" + (" self" if is_self else ""))
        with row:
            with ui.element("div").classes("cell"):
                with ui.element("div").classes("cell-title"):
                    ui.label(str(target.get("username") or "—"))
                    if is_self:
                        ui.label("这是你").classes("self-tag")
                ui.label(
                    f"{'管理员' if is_root else '普通用户'} · "
                    f"{'可用' if is_active else '已禁用'} · "
                    f"{target.get('conversation_count') or 0} 条会话 · "
                    f"注册 {fmt_short(target.get('created_at'))}"
                ).classes("mobile-meta")
            with ui.element("div").classes("cell"):
                badge("root" if is_root else "user", "root" if is_root else "")
            with ui.element("div").classes("cell"):
                with ui.element("span").classes(
                    "status-text " + ("active" if is_active else "disabled")
                ):
                    ui.element("span").classes("status-dot")
                    ui.label("可用" if is_active else "已禁用")
            with ui.element("div").classes("cell cell-mono"):
                ui.label(str(target.get("conversation_count") or 0))
            with ui.element("div").classes("cell cell-muted"):
                ui.label(fmt_short(target.get("created_at")))
            with ui.element("div").classes("cell row-actions"):
                if is_self:
                    self._disabled_action("降为普通", "不能修改自己的账号")
                    self._disabled_action("禁用", "不能修改自己的账号")
                else:
                    would_lose_root = (
                        is_root and is_active and active_roots <= 1
                    )
                    role_label = "降为普通" if is_root else "设为管理员"
                    if would_lose_root:
                        self._disabled_action(role_label, "系统必须保留一个可用的 root")
                    else:
                        self._action(
                            role_label,
                            lambda t=target, r=("user" if is_root else "root"): self._confirm_role(t, r),
                        )
                    status_label = "禁用" if is_active else "启用"
                    if would_lose_root and is_active:
                        self._disabled_action(status_label, "系统必须保留一个可用的 root")
                    else:
                        self._action(
                            status_label,
                            lambda t=target, s=("disabled" if is_active else "active"): self._confirm_status(t, s),
                            danger=is_active,
                        )

    def _action(self, label: str, handler: Any, danger: bool = False) -> None:
        button = ui.element("button").props("type=button").classes(
            "btn-link" + (" danger" if danger else "")
        )
        button.on("click", handler)
        with button:
            ui.label(label)

    def _disabled_action(self, label: str, reason: str) -> None:
        wrap = ui.element("span").style("display:inline-flex")
        with wrap:
            button = ui.element("button").props("type=button disabled").classes("btn-link muted")
            with button:
                ui.label(label)
            ui.tooltip(reason)

    def _confirm_role(self, target: dict[str, Any], role: str) -> None:
        name = str(target.get("username") or "该用户")
        if role == "root":
            body = (
                f"把「{name}」设为管理员后，该账号可以管理知识库、查看用户列表，"
                "也可以修改其他用户的角色。"
            )
            title = "设为管理员？"
            label = "设为管理员"
        else:
            body = f"把「{name}」降为普通用户后，该账号会立即失去知识库与用户管理入口。"
            title = "降为普通用户？"
            label = "降为普通"
        self.confirm.open(title, body, label, lambda: self._patch(target, {"role": role}))

    def _confirm_status(self, target: dict[str, Any], status: str) -> None:
        name = str(target.get("username") or "该用户")
        if status == "disabled":
            body = (
                f"禁用「{name}」会立即生效：该账号无法再登录，已登录的会话也会被后端拒绝。"
                "随时可以重新启用。"
            )
            self.confirm.open(
                "禁用这个账号？",
                body,
                "禁用",
                lambda: self._patch(target, {"status": "disabled"}),
                danger=True,
            )
        else:
            body = f"启用「{name}」后，该账号可以重新登录。"
            self.confirm.open(
                "启用这个账号？",
                body,
                "启用",
                lambda: self._patch(target, {"status": "active"}),
            )

    async def _patch(self, target: dict[str, Any], payload: dict[str, Any]) -> None:
        try:
            await get_api().patch(
                f"/api/v1/admin/users/{target.get('id')}", json=payload
            )
            ui.notify("已更新", type="positive", position="top")
            await self.refresh()
        except ApiError as exc:
            toast_error(exc)


@ui.page("/users", title="用户 · 出行计划助手", response_timeout=20)
async def users_page() -> None:
    user = await require_root()
    if not user:
        return
    page = UsersPage(user)
    await page.build()
