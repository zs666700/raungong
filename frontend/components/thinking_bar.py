"""顶部思考状态条（FRONTEND.md 7.4）。"""

from __future__ import annotations

from nicegui import ui

TOOL_HUMAN = {
    "weather_now": "正在查询实时天气…",
    "weather_forecast": "正在查询天气预报…",
    "place_search": "正在搜索地点…",
    "geo_geocode": "正在定位地址…",
    "route_plan": "正在计算路线…",
    "search_knowledge_base": "正在检索知识库…",
}


def human_tool(name: str) -> str:
    return TOOL_HUMAN.get(name, f"正在调用 {name}…")


class ThinkingBar:
    def __init__(self) -> None:
        self.container = ui.element("div").classes("tpa-thinking hidden")
        with self.container:
            ui.element("span").classes("dot")
            self.label = ui.label("").classes("thinking-text")
        self._visible = False
        self._seq = 0
        self._token_seen = False

    def show(self, text: str = "正在思考…") -> None:
        self._seq += 1
        self.label.text = text
        if not self._visible:
            self.container.classes(remove="hidden")
            self._visible = True
        self._token_seen = False

    def set_text(self, text: str) -> None:
        self.label.text = text

    def hide(self) -> None:
        self._seq += 1
        if self._visible:
            self.container.classes(add="hidden")
            self._visible = False

    def tool_start(self, name: str) -> None:
        self._token_seen = False
        self.show(human_tool(name))

    def tool_end(self) -> None:
        seq = self._seq

        def revert() -> None:
            if seq == self._seq and self._visible and not self._token_seen:
                self.label.text = "正在组织答案…"

        ui.timer(0.5, revert, once=True)

    def token(self) -> None:
        self._token_seen = True
        self.hide()

    def cancelled(self) -> None:
        self.show("正在停止…")
