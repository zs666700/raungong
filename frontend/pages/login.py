"""登录 / 注册页（FRONTEND.md 3.3）。"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from ..api_client import ApiError, get_api
from ..state import (
    ERROR_TEXT,
    human_error,
    redirect_if_logged_in,
    save_session,
)
from ..theme import LOGIN_MAP_SVG, apply_theme, brand_mark, icon_svg

logger = logging.getLogger("tpa.frontend.login")


class LoginPage:
    def __init__(self) -> None:
        self.mode = "login"
        self.busy = False
        self.register_available = True
        self.username: Any = None
        self.password: Any = None
        self.error: Any = None
        self.title: Any = None
        self.desc: Any = None
        self.submit: Any = None
        self.submit_label: Any = None
        self.note: Any = None
        self.tabs: dict[str, Any] = {}

    def build(self) -> None:
        apply_theme()
        with ui.element("div").classes("login-shell"):
            self._art()
            self._form()

        ui.timer(0.2, self._focus, once=True)

    # ------------------------------------------------------------------ 左半
    def _art(self) -> None:
        with ui.element("section").classes("login-art"):
            with ui.element("div").classes("login-brand"):
                ui.html(brand_mark(36)).classes("tpa-brand-mark")
                with ui.element("div").classes("tpa-brand-text"):
                    ui.label("行迹").classes("tpa-brand-name")
                    ui.label("Travel Atelier").classes("tpa-brand-sub")
            ui.html(LOGIN_MAP_SVG)
            with ui.element("div").classes("login-quote"):
                ui.label("TRAVEL ATELIER / 2026").classes("login-kicker")
                ui.html("<h1>把周末，<br>过成一段<em>旅程</em>。</h1>")
                ui.label(
                    "告诉我们去哪儿、什么时候、几个人、预算多少。"
                    "剩下的路线、天气与取舍，交给我们。"
                )
            with ui.element("div").classes("login-foot"):
                ui.label("杭州 · 成都 · 苏州")
                ui.label("从一句想法到一份行程")

    # ------------------------------------------------------------------ 右半
    def _form(self) -> None:
        with ui.element("section").classes("login-form-wrap"):
            with ui.element("div").classes("login-card"):
                with ui.element("div").classes("login-card-head"):
                    ui.label("MEMBER ACCESS / 账户").classes("login-eyebrow")
                    self.title = ui.label("欢迎回来").classes("login-title")
                    self.desc = ui.label("登录后继续你的行程。").classes("login-desc")

                with ui.element("div").classes("auth-tabs"):
                    for key, label in (("login", "登录"), ("register", "注册")):
                        tab = ui.element("button").props("type=button").classes(
                            "auth-tab active" if key == "login" else "auth-tab"
                        )
                        tab.on("click", lambda _=None, k=key: self.set_mode(k))
                        with tab:
                            ui.label(label)
                        self.tabs[key] = tab

                with ui.element("div").classes("field"):
                    with ui.element("div").classes("field-label"):
                        ui.label("用户名")
                        ui.label("USERNAME")
                    self.username = (
                        ui.input(
                            placeholder="3–32 位字母、数字、下划线",
                            on_change=self._clear_error,
                        )
                        .props("borderless autofocus")
                        .classes("field")
                    )
                    self.username.on("keydown.enter", self._submit)

                with ui.element("div").classes("field"):
                    with ui.element("div").classes("field-label"):
                        ui.label("密码")
                        ui.label("PASSWORD")
                    self.password = (
                        ui.input(
                            placeholder="至少 8 位",
                            password=True,
                            password_toggle_button=True,
                            on_change=self._clear_error,
                        )
                        .props("borderless")
                        .classes("field")
                    )
                    self.password.on("keydown.enter", self._submit)

                self.error = ui.label("").classes("auth-error")
                self.error.style("visibility:hidden")
                self.error_label = self.error

                self.submit = ui.element("button").props("type=button").classes("auth-submit")
                self.submit.on("click", self._submit)
                with self.submit:
                    self.submit_label = ui.label("进入")
                    ui.html(icon_svg("arrow-right", 15))

                self.note = ui.label(
                    "注册后会自动登录，不需要二次输入密码。"
                ).classes("auth-note")

                with ui.element("div").classes("auth-foot"):
                    ui.label("首次部署请使用 .env 中配置的 root 账号登录")
        self.set_mode("login")

    def _focus(self) -> None:
        try:
            ui.run_javascript('tpaFocus(".field input")')
        except Exception:
            pass

    def _clear_error(self, _=None) -> None:
        if self.error_label is not None:
            self.error_label.text = ""
        if self.error is not None:
            self.error.style("visibility:hidden")

    # ------------------------------------------------------------------ 状态
    def set_mode(self, mode: str) -> None:
        if mode == "register" and not self.register_available:
            mode = "login"
        self.mode = mode
        for key, tab in self.tabs.items():
            if key == mode:
                tab.classes(add="active")
            else:
                tab.classes(remove="active")
        if mode == "login":
            self.title.text = "欢迎回来"
            self.desc.text = "登录后继续你的行程。"
            self.submit_label.text = "进入"
            self.note.text = "没有账号？切换到「注册」，或联系管理员开号。"
            self.note.classes(remove="closed")
        else:
            self.title.text = "创建账号"
            self.desc.text = "注册后自动登录，立刻开始规划。"
            self.submit_label.text = "创建并进入"
            self.note.text = "用户名 3–32 位，密码至少 8 位；注册后自动登录。"
            self.note.classes(remove="closed")
        self._clear_error()
        self._focus()

    def _fail(self, message: str) -> None:
        if self.error_label is not None:
            self.error_label.text = message
        if self.error is not None:
            self.error.style("visibility:visible")

    def _hide_register(self) -> None:
        self.register_available = False
        tab = self.tabs.get("register")
        if tab is not None:
            tab.set_visibility(False)
        if self.mode == "register":
            self.set_mode("login")
        self.note.text = "系统未开放注册，请联系管理员开号。"
        self.note.classes(add="closed")

    # ------------------------------------------------------------------ 提交
    async def _submit(self) -> None:
        if self.busy:
            return
        username = (self.username.value or "").strip()
        password = self.password.value or ""
        if not username:
            self._fail("请输入用户名")
            return
        if not password:
            self._fail("请输入密码")
            return
        if self.mode == "register" and len(password) < 8:
            self._fail("密码至少 8 位")
            return

        self.busy = True
        self.submit.props("disabled")
        original = "进入" if self.mode == "login" else "创建并进入"
        self.submit_label.text = "正在进入…" if self.mode == "login" else "正在创建…"
        self._clear_error()

        path = "/api/v1/auth/login" if self.mode == "login" else "/api/v1/auth/register"
        try:
            data = await get_api().post(
                path,
                json={"username": username, "password": password},
                handle_401=False,
            )
            token = str((data or {}).get("token") or "")
            user = (data or {}).get("user") or {}
            if not token or not user:
                self._fail("登录响应异常，请稍后再试")
                return
            save_session(token, user)
            ui.navigate.to("/chat")
            return
        except ApiError as exc:
            if exc.code == "AUTH_REGISTER_CLOSED":
                self._hide_register()
                self._fail(ERROR_TEXT["AUTH_REGISTER_CLOSED"])
            else:
                self._fail(human_error(exc, "登录失败"))
        finally:
            self.busy = False
            try:
                self.submit.props(remove="disabled")
                self.submit_label.text = original if self.mode == "login" else "创建并进入"
            except Exception:
                pass


@ui.page("/login", title="登录 · 出行计划助手", response_timeout=20)
async def login_page() -> None:
    if await redirect_if_logged_in():
        return
    LoginPage().build()
