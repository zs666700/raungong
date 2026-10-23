"""通用弹窗：二次确认、单行输入、旅行偏好、系统状态。"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from nicegui import app, ui

from ..api_client import ApiError, get_api
from ..state import human_error, toast_error
from ..ui_utils import badge

Action = Callable[[], Awaitable[None]]

BUDGET_OPTIONS = {"economy": "经济", "comfortable": "舒适", "luxury": "品质"}
PACE_OPTIONS = {"relaxed": "松弛", "balanced": "适中", "packed": "紧凑"}
INTEREST_OPTIONS = ["博物馆", "历史", "美食", "自然风光", "城市漫步", "摄影", "亲子", "夜生活"]
DIETARY_OPTIONS = ["不吃辣", "不吃海鲜", "素食", "清真", "不吃香菜", "少油少盐"]
AVOID_OPTIONS = ["长途大巴", "爬山", "人多排队", "早起", "红眼航班", "购物点"]


class ConfirmDialog:
    def __init__(self) -> None:
        self._action: Action | None = None
        with ui.dialog() as self.dialog, ui.card().classes("dialog-card"):
            self.title = ui.label("").classes("dialog-title")
            self.body = ui.label("").classes("dialog-sub")
            with ui.element("div").classes("dialog-actions"):
                ui.button("取消", color=None, on_click=self.dialog.close).classes("btn-ghost").props(
                    "flat no-caps"
                )
                self.confirm = ui.button("确认", color=None, on_click=self._confirm).classes(
                    "btn-ink"
                ).props("unelevated no-caps")

    def open(
        self,
        title: str,
        body: str,
        confirm_label: str = "确认",
        action: Action | None = None,
        danger: bool = False,
    ) -> None:
        self.title.text = title
        self.body.text = body
        self.confirm.text = confirm_label
        self._action = action
        if danger:
            self.confirm.style("background:var(--danger);border-color:var(--danger)")
        else:
            self.confirm.style("")
        self.dialog.open()

    async def _confirm(self) -> None:
        action = self._action
        self.dialog.close()
        if action is None:
            return
        try:
            await action()
        except ApiError as exc:
            toast_error(exc)


class PromptDialog:
    def __init__(self) -> None:
        self._action: Callable[[str], Awaitable[bool]] | None = None
        with ui.dialog() as self.dialog, ui.card().classes("dialog-card"):
            self.title = ui.label("").classes("dialog-title")
            self.desc = ui.label("").classes("dialog-sub")
            self.input = ui.input(placeholder="").props("borderless").classes("dialog-field").style(
                "width:100%"
            )
            self.input.on("keydown.enter", lambda: self._save())
            self.error = ui.label("").classes("auth-error").style(
                "min-height:0;margin-top:6px;visibility:hidden"
            )
            with ui.element("div").classes("dialog-actions"):
                ui.button("取消", color=None, on_click=self.dialog.close).classes("btn-ghost").props(
                    "flat no-caps"
                )
                self.save = ui.button("保存", color=None, on_click=self._save).classes("btn-ink").props(
                    "unelevated no-caps"
                )

    def open(
        self,
        title: str,
        desc: str,
        value: str,
        action: Callable[[str], Awaitable[bool]],
        confirm_label: str = "保存",
        placeholder: str = "",
    ) -> None:
        self.title.text = title
        self.desc.text = desc
        self.input.value = value
        self.input.props(f'placeholder="{placeholder or "请输入"}"')
        self.save.text = confirm_label
        self.error.text = ""
        self.error.style("visibility:hidden")
        self._action = action
        self.dialog.open()

    async def _save(self) -> None:
        text = (self.input.value or "").strip()
        if not text:
            self.error.text = "不能为空"
            self.error.style("visibility:visible")
            return
        if len(text) > 60:
            self.error.text = "不能超过 60 个字符"
            self.error.style("visibility:visible")
            return
        self.error.text = ""
        self.error.style("visibility:hidden")
        self.save.props("loading disable")
        try:
            assert self._action is not None
            ok = await self._action(text)
            if ok:
                self.dialog.close()
        except ApiError as exc:
            self.error.text = human_error(exc)
            self.error.style("visibility:visible")
        finally:
            self.save.props(remove="loading disable")


class ProfileDialog:
    def __init__(self) -> None:
        self._profile: dict[str, Any] = {}
        self._body: Any = None
        with ui.dialog() as self.dialog, ui.card().classes("dialog-card").style("width:min(620px,92vw)"):
            ui.label("旅行偏好").classes("dialog-title")
            ui.label(
                "这些信息会随每轮对话交给助手，用来减少重复提问。整体替换：留空即清空该项。"
            ).classes("dialog-sub")
            self._body = ui.element("div").style("width:100%")
            with ui.element("div").classes("dialog-actions"):
                ui.label("保存后立即生效").classes("note").style("margin-right:auto")
                ui.button("取消", color=None, on_click=self.dialog.close).classes("btn-ghost").props(
                    "flat no-caps"
                )
                self.save = ui.button("保存偏好", color=None, on_click=self._save).classes("btn-ink").props(
                    "unelevated no-caps"
                )

    def open(self, user: dict[str, Any]) -> None:
        self._profile = dict(user.get("profile") or {})
        self._build()
        self.dialog.open()

    def _build(self) -> None:
        self._body.clear()
        profile = self._profile
        with self._body:
            with ui.element("div").classes("profile-grid"):
                with ui.element("div").classes("wide"):
                    ui.label("常住城市").classes("field-label")
                    self.home_city = (
                        ui.input(placeholder="例如：上海")
                        .props("borderless dense maxlength=20")
                        .classes("dialog-field")
                    )
                    self.home_city.value = profile.get("home_city") or ""
                with ui.element("div"):
                    ui.label("预算档位").classes("field-label")
                    self.budget = ui.select(
                        BUDGET_OPTIONS,
                        value=profile.get("budget_level"),
                        clearable=True,
                    ).props("borderless dense options-dense")
                with ui.element("div"):
                    ui.label("节奏").classes("field-label")
                    self.pace = ui.select(
                        PACE_OPTIONS,
                        value=profile.get("pace"),
                        clearable=True,
                    ).props("borderless dense options-dense")
                with ui.element("div").classes("wide"):
                    ui.label("感兴趣").classes("field-label")
                    self.interests = ui.select(
                        INTEREST_OPTIONS,
                        value=list(profile.get("interests") or []),
                        multiple=True,
                        with_input=True,
                        new_value_mode="add-unique",
                    ).props("borderless dense use-chips options-dense")
                with ui.element("div").classes("wide"):
                    ui.label("饮食限制").classes("field-label")
                    self.dietary = ui.select(
                        DIETARY_OPTIONS,
                        value=list(profile.get("dietary") or []),
                        multiple=True,
                        with_input=True,
                        new_value_mode="add-unique",
                    ).props("borderless dense use-chips options-dense")
                with ui.element("div").classes("wide"):
                    ui.label("尽量避开").classes("field-label")
                    self.avoid = ui.select(
                        AVOID_OPTIONS,
                        value=list(profile.get("avoid") or []),
                        multiple=True,
                        with_input=True,
                        new_value_mode="add-unique",
                    ).props("borderless dense use-chips options-dense")

    async def _save(self) -> None:
        payload = {
            "home_city": (self.home_city.value or "").strip() or None,
            "budget_level": self.budget.value or None,
            "pace": self.pace.value or None,
            "interests": list(self.interests.value or []) or None,
            "dietary": list(self.dietary.value or []) or None,
            "avoid": list(self.avoid.value or []) or None,
        }
        self.save.props("loading disable")
        try:
            data = await get_api().put("/api/v1/auth/profile", payload)
            user = dict(app.storage.user.get("user") or {})
            user["profile"] = (data or {}).get("profile") or {}
            app.storage.user["user"] = user
            ui.notify("偏好已保存", type="positive", position="top")
            self.dialog.close()
        except ApiError as exc:
            toast_error(exc)
        finally:
            self.save.props(remove="loading disable")


class StatusDialog:
    def __init__(self) -> None:
        self._body: Any = None
        self._tool_options: dict[str, str] = {}
        with ui.dialog() as self.dialog, ui.card().classes("dialog-card").style("width:min(680px,92vw)"):
            ui.label("系统状态").classes("dialog-title")
            ui.label("当前工具与 MCP Server 的可用情况。降级时对话仍可继续，只是会缺少部分数据。").classes(
                "dialog-sub"
            )
            self._body = ui.element("div").style("width:100%")
            with ui.element("div").classes("dialog-actions"):
                ui.label("GET /api/v1/tools").classes("note").style(
                    "margin-right:auto;font-family:var(--mono)"
                )
                ui.button("关闭", color=None, on_click=self.dialog.close).classes("btn-ghost").props(
                    "flat no-caps"
                )

    async def open(self) -> None:
        self.dialog.open()
        self._body.clear()
        with self._body:
            with ui.row().classes("items-center gap-2").style("padding:8px 0"):
                ui.element("span").classes("spinner-mini")
                ui.label("正在读取工具状态…").classes("note")
        try:
            data = await get_api().get("/api/v1/tools")
        except ApiError as exc:
            self._body.clear()
            with self._body:
                ui.label(human_error(exc)).classes("auth-error")
            return
        self._render(data or {})

    def _render(self, data: dict[str, Any]) -> None:
        self._body.clear()
        servers = data.get("servers") or []
        tools = data.get("tools") or []
        degraded = bool(data.get("degraded"))
        with self._body:
            with ui.row().classes("items-center gap-2").style("padding:6px 0"):
                badge("降级运行" if degraded else "全部就绪", "fail" if degraded else "ok")
                ui.label(f"{len(servers)} 个 Server · {len(tools)} 个工具").classes("note")
            if servers:
                with ui.element("div").classes("status-list"):
                    for server in servers:
                        status = str(server.get("status") or "")
                        tone = "ok" if status == "connected" else "fail"
                        with ui.element("div").classes("status-row"):
                            ui.label(str(server.get("name") or "—")).classes("name")
                            ui.label(f"{server.get('tool_count', 0)} 个工具").classes("desc")
                            badge(status, tone)
            if tools:
                ui.label("可用工具").classes("field-label").style("margin-top:16px")
                with ui.element("div").classes("status-list"):
                    for tool in tools:
                        with ui.element("div").classes("status-row"):
                            ui.label(str(tool.get("name") or "—")).classes("name")
                            ui.label(str(tool.get("description") or "")).classes("desc")
                            ui.label(str(tool.get("server") or "native")).classes("cell-muted")
            if tools:
                self._render_invoke(tools)

    def _render_invoke(self, tools: list[dict[str, Any]]) -> None:
        self._tool_options = {
            str(tool.get("name")): f"{tool.get('name')} · {tool.get('server') or 'native'}"
            for tool in tools
            if tool.get("name")
        }
        with ui.element("div").classes("invoke-box"):
            ui.label("手动调用（排障）").classes("panel-kicker")
            first = next(iter(self._tool_options), None)
            with ui.element("div").classes("profile-grid"):
                with ui.element("div"):
                    self.tool_select = (
                        ui.select(self._tool_options, value=first)
                        .props("borderless dense options-dense")
                        .style("width:100%")
                    )
                with ui.element("div"):
                    self.args_input = (
                        ui.input(value="{}", placeholder='{"city": "杭州"}')
                        .props("borderless dense")
                        .style("width:100%")
                    )
            self.invoke_output = ui.label("").classes("invoke-out").style("display:none")
            with ui.element("div").classes("dialog-actions").style("margin-top:10px"):
                self.invoke_btn = ui.button(
                    "调用工具", color=None, on_click=self._invoke
                ).classes("btn-ghost").props("flat no-caps")
                self.invoke_btn.style("margin-right:auto")

    async def _invoke(self) -> None:
        name = self.tool_select.value
        if not name:
            return
        try:
            args = json.loads(self.args_input.value or "{}")
            if not isinstance(args, dict):
                raise ValueError("args 必须是对象")
        except ValueError as exc:
            ui.notify(f"参数不是合法 JSON：{exc}", type="negative", position="top")
            return
        self.invoke_btn.props("loading disable")
        try:
            data = await get_api().post(f"/api/v1/tools/{name}/invoke", json={"args": args})
            self.invoke_output.text = json.dumps(data, ensure_ascii=False, indent=2)
            self.invoke_output.style("display:block")
        except ApiError as exc:
            toast_error(exc)
        finally:
            self.invoke_btn.props(remove="loading disable")
