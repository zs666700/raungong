"""格式化与小组件工具。所有取值都用 `.get()` + 默认值，渲染永不抛异常。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from nicegui import ui

from .theme import icon_svg

_WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def fmt_money(cent: Any) -> str:
    return f"¥{_as_int(cent) // 100}"


def fmt_money_plain(cent: Any) -> str:
    return str(_as_int(cent) // 100)


def fmt_duration(minutes: Any) -> str:
    value = _as_int(minutes)
    if value <= 0:
        return "时长待定"
    if value >= 60:
        hours, rest = divmod(value, 60)
        return f"{hours} 小时" if rest == 0 else f"{hours} 小时 {rest} 分"
    return f"{value} 分钟"


def fmt_time_range(start: Any, end: Any) -> str:
    if not start or not end:
        return "时间待定"
    return f"{start}–{end}"


def fmt_distance(metres: Any) -> str:
    value = _as_int(metres)
    if value >= 1000:
        return f"{value / 1000:.1f}km"
    return f"{value}m"


def fmt_date_range(start: Any, end: Any) -> str:
    start = str(start or "")
    end = str(end or "")
    if not start and not end:
        return "日期待定"
    if not start:
        return end
    if not end:
        return start
    if start[:4] == end[:4]:
        return f"{start} ~ {end[5:]}"
    return f"{start} ~ {end}"


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
    except (TypeError, ValueError):
        return None


def fmt_short(iso: Any) -> str:
    dt = parse_iso(iso)
    return dt.strftime("%m-%d %H:%M") if dt else ""


def fmt_time(iso: Any) -> str:
    dt = parse_iso(iso)
    return dt.strftime("%H:%M") if dt else ""


def fmt_day(iso: Any) -> str:
    dt = parse_iso(iso)
    return dt.strftime("%m-%d") if dt else ""


def fmt_weekday(iso: Any) -> str:
    dt = parse_iso(iso)
    return _WEEKDAYS[dt.weekday()] if dt else ""


def weekday_of(date_text: Any) -> str:
    try:
        return _WEEKDAYS[datetime.strptime(str(date_text), "%Y-%m-%d").weekday()]
    except (TypeError, ValueError):
        return ""


def group_label(iso: Any) -> str:
    dt = parse_iso(iso)
    if dt is None:
        return "更早"
    today = datetime.now().astimezone().date()
    day = dt.date()
    if day == today:
        return "今天"
    if day == today - timedelta(days=1):
        return "昨天"
    if today - timedelta(days=7) <= day < today:
        return "本周"
    return "更早"


def initials(name: Any) -> str:
    text = str(name or "?").strip()
    return text[:1].upper() if text else "?"


_SERVER_BY_TOOL = {
    "weather_now": "weather",
    "weather_forecast": "weather",
    "place_search": "place",
    "geo_geocode": "place",
    "route_plan": "place",
    "search_knowledge_base": "knowledge",
}


def tool_server(name: Any) -> str:
    return _SERVER_BY_TOOL.get(str(name or ""), "—")


def transport_label(mode: Any) -> str:
    return {"walking": "步行", "driving": "驾车", "transit": "公交"}.get(str(mode or ""), "前往")


def transport_icon(mode: Any) -> str:
    return {"walking": "walk", "driving": "car", "transit": "transit"}.get(str(mode or ""), "route")


def source_label(source: Any) -> str:
    return {"model": "模型推断", "rag": "知识库", "tool": "工具数据"}.get(str(source or ""), "")


def safe_filename(title: Any, fallback: str = "行程") -> str:
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(title or "")).strip()
    text = re.sub(r"\s+", " ", text)
    return (text or fallback)[:64]


def icon_button(
    name: str,
    on_click: Any = None,
    tooltip: str | None = None,
    classes: str = "",
    size: int = 16,
    disabled: bool = False,
) -> Any:
    button = ui.element("button").props("type=button").classes(f"iconbtn {classes}")
    if tooltip:
        button.props(f'aria-label="{tooltip}"')
    if disabled:
        button.props("disabled")
    elif on_click is not None:
        button.on("click", on_click)
    with button:
        ui.html(icon_svg(name, size))
        if tooltip:
            ui.tooltip(tooltip)
    return button


def icon_block(name: str, size: int = 16) -> Any:
    return ui.html(icon_svg(name, size)).classes("icon")


def badge(text: str, tone: str = "") -> Any:
    with ui.element("span").classes(f"badge {tone}".strip()) as element:
        ui.label(text)
    return element


def spinner(size: int = 15) -> Any:
    return ui.element("span").classes("spinner-mini").style(f"width:{size}px;height:{size}px")


def toast(message: str, kind: str = "info") -> None:
    ui.notify(message, type=kind, position="top", multi_line=True)


def render_notify(message: str, kind: str = "info") -> None:
    toast(message, kind)


def status_pill(text: str, tone: str = "", dot: bool = True) -> Any:
    with ui.element("span").classes(f"badge {tone}".strip()):
        if dot:
            ui.element("span").classes("badge-dot")
        ui.label(text)
