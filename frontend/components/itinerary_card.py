"""行程卡片（FRONTEND.md 第 8 章）。

所有字段都按 `.get()` 取值；整个渲染包在 try/except 里，
卡片失败只静默不显示，绝不影响文本回复。
"""

from __future__ import annotations

import logging
from typing import Any

from nicegui import ui

from ..theme import icon_svg
from ..ui_utils import (
    _as_int,
    fmt_date_range,
    fmt_distance,
    fmt_duration,
    fmt_money,
    fmt_time_range,
    source_label,
    transport_icon,
    transport_label,
    weekday_of,
)
from .markdown_export import download_itinerary

logger = logging.getLogger("tpa.frontend.itinerary")

BUDGET_SEGMENTS = (
    ("transport_cent", "交通", "#AE4A27"),
    ("lodging_cent", "住宿", "#2B5647"),
    ("food_cent", "餐饮", "#A1752A"),
    ("tickets_cent", "门票", "#6E7E8F"),
    ("other_cent", "其他", "#A9A08A"),
)


def _weather_text(weather: dict[str, Any]) -> str:
    condition = str(weather.get("condition") or "").strip()
    low = weather.get("temp_low_c")
    high = weather.get("temp_high_c")
    if low is not None and high is not None:
        return f"{condition} {low}–{high}℃".strip()
    if condition:
        return condition
    return "天气未知"


def render_itinerary(itinerary: dict[str, Any] | None) -> Any:
    if not isinstance(itinerary, dict) or not itinerary.get("days"):
        return None

    card = ui.element("article").classes("trip")
    try:
        with card:
            _render_head(itinerary)
            _render_budget(itinerary.get("budget") or {})
            _render_days(itinerary.get("days") or [])
            _render_risks(itinerary.get("risks") or [])
            _render_packing(itinerary.get("packing_list") or [])
    except Exception:  # pragma: no cover - 卡片是增强显示，不能影响正文
        logger.exception("行程卡片渲染失败，已隐藏")
        try:
            card.delete()
        except Exception:
            pass
        return None
    return card


def _render_head(itinerary: dict[str, Any]) -> None:
    destination = itinerary.get("destination") or {}
    travelers = itinerary.get("travelers") or {}
    days = itinerary.get("days") or []
    adults = _as_int(travelers.get("adults"), 1)
    children = _as_int(travelers.get("children"), 0)
    people = f"{adults} 人"
    if children > 0:
        people += f" +{children} 儿童"
    day_count = _as_int(itinerary.get("day_count"), len(days)) or len(days)

    with ui.element("div").classes("trip-head"):
        with ui.element("div").classes("trip-head-top"):
            with ui.element("div").classes("trip-head-main"):
                ui.label(f"行程单 / {destination.get('name') or '未命名目的地'}").classes(
                    "trip-kicker"
                )
                ui.label(str(itinerary.get("title") or "出行计划")).classes("trip-title")
                with ui.element("div").classes("trip-sub"):
                    ui.label(fmt_date_range(itinerary.get("start_date"), itinerary.get("end_date")))
                    ui.element("span").classes("sep")
                    ui.label(f"{day_count} 天")
                    ui.element("span").classes("sep")
                    ui.label(people)
            export = ui.element("button").props("type=button").classes("trip-export")
            export.on("click", lambda: download_itinerary(itinerary))
            with export:
                ui.html(icon_svg("download", 13))
                ui.label("导出行程")
        summary = str(itinerary.get("summary") or "").strip()
        if summary:
            ui.label(summary).classes("trip-summary")


def _render_budget(budget: dict[str, Any]) -> None:
    breakdown = budget.get("breakdown") or {}
    values = {key: _as_int(breakdown.get(key)) for key, _label, _color in BUDGET_SEGMENTS}
    computed = sum(values.values())
    total = _as_int(budget.get("total_cent"), computed) or computed
    if total <= 0 and computed <= 0:
        return

    basis = computed if computed > 0 else total
    with ui.element("div").classes("budget"):
        with ui.element("div").classes("budget-top"):
            ui.label("预算合计").classes("budget-label")
            ui.label(f"¥{total // 100}").classes("budget-total")
            ui.label("CNY").classes("budget-note")
        bar = ui.element("div").classes("budget-bar")
        with bar:
            for key, label, color in BUDGET_SEGMENTS:
                value = values.get(key, 0)
                if value <= 0:
                    continue
                pct = max(0.6, value / basis * 100)
                segment = ui.element("span").classes("budget-seg").style(
                    f"width:{pct:.3f}%;background:{color}"
                )
                with segment:
                    ui.tooltip(f"{label} {fmt_money(value)}")
        with ui.element("div").classes("budget-legend"):
            for key, label, color in BUDGET_SEGMENTS:
                value = values.get(key, 0)
                with ui.element("span").classes("legend-item"):
                    ui.element("span").classes("legend-swatch").style(f"background:{color}")
                    ui.label(label)
                    ui.label(fmt_money(value)).classes("legend-amount")


def _render_days(days: list[Any]) -> None:
    for index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            continue
        day_block = ui.element("section").classes("day")
        with day_block:
            head = ui.element("div").classes("day-head").props("role=button tabindex=0")
            weather = day.get("weather") or None
            with head:
                ui.label(f"{index:02d}").classes("day-index")
                with ui.element("div").classes("day-info"):
                    with ui.element("div").classes("day-line"):
                        date_text = str(day.get("date") or "")
                        ui.label(date_text or "日期待定").classes("day-date")
                        weekday = str(day.get("weekday") or "") or weekday_of(date_text)
                        if weekday:
                            ui.label(weekday).classes("day-weekday")
                    if day.get("theme"):
                        ui.label(str(day.get("theme"))).classes("day-theme")
                if weather:
                    with ui.element("span").classes("day-weather"):
                        ui.html(icon_svg("weather", 12)).classes("icon")
                        ui.label(_weather_text(weather))
                ui.html(icon_svg("chevron-down", 14)).classes("day-chev")
            with ui.element("div").classes("day-body"):
                items = day.get("items") or []
                if not items:
                    with ui.element("div").classes("free-day"):
                        ui.html(icon_svg("walk", 14))
                        ui.label("自由活动")
                else:
                    for item in items:
                        if isinstance(item, dict):
                            _render_item(item)

            def toggle(_=None, block=day_block) -> None:
                block.classes(toggle="closed")

            head.on("click", toggle)
            head.on("keydown.enter", toggle)


def _render_item(item: dict[str, Any]) -> None:
    item_type = str(item.get("type") or "activity")
    source = str(item.get("source") or "model")
    classes = "stop"
    if item_type == "meal":
        classes += " is-meal"
    elif item_type == "transport":
        classes += " is-transport"
    if source == "model":
        classes += " model"

    stop = ui.element("div").classes(classes)
    with stop:
        ui.label(fmt_time_range(item.get("start_time"), item.get("end_time"))).classes("stop-time")
        with ui.element("div").classes("stop-spine"):
            ui.element("span").classes("stop-dot")
        with ui.element("div").classes("stop-content"):
            if source == "model":
                ui.label(source_label(source)).classes("model-tag")
            ui.label(str(item.get("title") or "未命名安排")).classes("stop-title")

            location = item.get("location") or {}
            address = str(location.get("address") or "").strip()
            place = str(location.get("name") or "").strip()
            cost = _as_int(item.get("cost_cent"))
            meta_has = (
                bool(address or place)
                or cost != 0
                or item.get("duration_min") is not None
            )
            if meta_has:
                with ui.element("div").classes("stop-meta"):
                    if address or place:
                        with ui.element("span").classes("pin"):
                            ui.html(icon_svg("pin", 12)).classes("icon")
                            ui.label(address or place)
                    if address or place:
                        ui.element("span").classes("sep")
                    if cost == 0:
                        ui.label("免费").classes("free")
                    else:
                        ui.label(fmt_money(cost))
                    ui.element("span").classes("sep")
                    ui.label(fmt_duration(item.get("duration_min")))

            transport = item.get("transport") or None
            if transport:
                with ui.element("div").classes("stop-transport"):
                    ui.label("↳")
                    ui.html(icon_svg(transport_icon(transport.get("mode")), 11)).classes("icon")
                    text = (
                        f"{transport_label(transport.get('mode'))} "
                        f"{_as_int(transport.get('duration_min'))} 分钟"
                    )
                    distance = _as_int(transport.get("distance_m"))
                    if distance > 0:
                        text += f" {fmt_distance(distance)}"
                    ui.label(text)

            notes = str(item.get("notes") or "").strip()
            if notes:
                with ui.element("div").classes("stop-note"):
                    ui.label("TIP").classes("note-mark")
                    ui.label(notes)


def _render_risks(risks: list[Any]) -> None:
    valid = [r for r in risks if isinstance(r, dict)]
    if not valid:
        return
    block = ui.element("div").classes("trip-risks open")
    with block:
        head = ui.element("div").classes("trip-risks-head").props(
            "role=button tabindex=0"
        )
        with head:
            ui.html(icon_svg("warn", 13)).classes("icon")
            ui.label("风险提示")
            ui.label(f"{len(valid)} 条").classes("tools-count")
            ui.element("span").classes("spacer")
            ui.html(icon_svg("chevron-right", 12)).classes("chev")
        with ui.element("div").classes("trip-risks-body"):
            for number, risk in enumerate(valid, start=1):
                with ui.element("div").classes("risk"):
                    ui.label(f"{number:02d}").classes("risk-num")
                    with ui.element("div"):
                        ui.label(str(risk.get("description") or "—")).classes("risk-desc")
                        mitigation = str(risk.get("mitigation") or "").strip()
                        if mitigation:
                            ui.label(f"→ {mitigation}").classes("risk-fix")

        def toggle(_=None, b=block) -> None:
            b.classes(toggle="open")

        head.on("click", toggle)
        head.on("keydown.enter", toggle)


def _render_packing(packing: list[Any]) -> None:
    items = [str(item) for item in packing if str(item).strip()]
    if not items:
        return
    with ui.element("div").classes("trip-pack"):
        ui.html(icon_svg("suitcase", 14)).classes("icon")
        ui.label("建议携带：").classes("packing-label")
        ui.label("、".join(items)).classes("packing-items")
