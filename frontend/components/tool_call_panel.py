"""工具调用面板（FRONTEND.md 7.2）：默认收起，只显示一行摘要。"""

from __future__ import annotations

import json
from typing import Any

from nicegui import app, ui

from ..theme import icon_svg
from ..ui_utils import _as_int, tool_server


def _duration(total_ms: int) -> str:
    if total_ms >= 1000:
        return f"{total_ms / 1000:.1f}s"
    return f"{total_ms}ms"


def _icon_for(entry: dict[str, Any]) -> tuple[str, str]:
    ok = entry.get("ok")
    if ok is True:
        return "check", ""
    if ok is False:
        return "x", "failed"
    return "clock", "pending"


class ToolCallPanel:
    def __init__(self, calls: list[dict[str, Any]] | None) -> None:
        self.calls = [c for c in (calls or []) if isinstance(c, dict)]
        self.container: Any = None
        self.open_state = self._load_state()

    @staticmethod
    def _load_state() -> bool:
        try:
            return bool(app.storage.tab.get("tool_panel_open", False))
        except Exception:
            return False

    def _save_state(self, value: bool) -> None:
        try:
            app.storage.tab["tool_panel_open"] = value
        except Exception:
            pass

    def mount(self) -> None:
        if not self.calls:
            return
        total = sum(_as_int(c.get("ms")) for c in self.calls if c.get("ms") is not None)
        pending = sum(1 for c in self.calls if c.get("ok") is None)
        self.container = ui.element("div").classes("tools" + (" open" if self.open_state else ""))
        with self.container:
            head = ui.element("div").classes("tools-head").props(
                "role=button tabindex=0"
            )
            with head:
                ui.html(icon_svg("chevron-right", 13)).classes("chev")
                ui.label("工具调用").classes("tools-title")
                count = f"{len(self.calls)} 个"
                if pending:
                    count += f" · {pending} 进行中"
                ui.label(count).classes("tools-count")
                ui.element("span").classes("spacer")
                if total:
                    ui.label(f"合计 {_duration(total)}").classes("tools-dur")
            with ui.element("div").classes("tools-body"):
                for call in self.calls:
                    self._row(call)
                ui.label("点击任意一行可查看调用参数").classes("tools-note")

        def toggle(_=None) -> None:
            self.open_state = not self.open_state
            self.container.classes(add="open") if self.open_state else self.container.classes(
                remove="open"
            )
            self._save_state(self.open_state)

        head.on("click", toggle)
        head.on("keydown.enter", toggle)

    def _row(self, call: dict[str, Any]) -> None:
        icon_name, tone = _icon_for(call)
        ms = call.get("ms")
        summary = str(call.get("summary") or "").strip()
        args = call.get("args")
        row = ui.element("div").classes(
            "tool-row" + (" failed" if tone == "failed" else "")
        )
        with row:
            ui.html(icon_svg(icon_name, 12)).classes(f"tool-icon {tone}".strip())
            ui.label(str(call.get("name") or "tool")).classes("tool-name")
            ui.label(tool_server(call.get("name"))).classes("tool-server")
            ui.label(_duration(_as_int(ms)) if ms is not None else "—").classes("tool-ms")
            ui.label(summary or ("进行中…" if call.get("ok") is None else "无摘要")).classes(
                "tool-summary"
            )
        if args is not None:
            extra = ui.element("div").classes("tool-more")
            with extra:
                try:
                    text = json.dumps(args, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    text = str(args)
                ui.label("ARGUMENTS").classes("tool-args-label")
                ui.label(text).classes("tool-args")

            state = {"open": False}

            def toggle(_=None, r=row, s=state) -> None:
                s["open"] = not s["open"]
                if s["open"]:
                    r.classes(add="expanded")
                else:
                    r.classes(remove="expanded")

            row.on("click", toggle)
            row.style("cursor:pointer")


def normalize_live(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 start/end 帧合并成面板需要的 `tool_calls` 结构。"""
    merged: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        phase = event.get("phase")
        name = str(event.get("name") or "")
        if phase == "start":
            merged.append(
                {
                    "name": name,
                    "args": event.get("args"),
                    "ok": None,
                    "ms": None,
                    "summary": "",
                }
            )
        elif phase == "end":
            target = None
            for entry in reversed(merged):
                if entry.get("name") == name and entry.get("ok") is None:
                    target = entry
                    break
            if target is None:
                target = {"name": name, "args": None, "ok": None, "ms": None, "summary": ""}
                merged.append(target)
            target["ok"] = bool(event.get("ok"))
            target["ms"] = event.get("ms")
            target["summary"] = event.get("summary") or ""
    return merged
