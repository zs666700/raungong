"""行程导出为 Markdown（R7）。

前台导出由前端本地生成，这里只留作脚本用（比如演示前批量出样例文件）。
用标准库字符串模板，不引额外库。
"""

from __future__ import annotations

from typing import Any

TYPE_LABELS = {
    "attraction": "景点",
    "meal": "用餐",
    "transport": "交通",
    "rest": "休息",
    "activity": "活动",
    "lodging": "住宿",
}
MODE_LABELS = {"walking": "步行", "driving": "驾车", "transit": "公共交通"}


def _yuan(cent: Any) -> str:
    try:
        value = int(cent or 0)
    except (TypeError, ValueError):
        value = 0
    return f"{value / 100:.2f} 元"


def _time_range(item: dict[str, Any]) -> str:
    start = item.get("start_time")
    end = item.get("end_time")
    if start and end:
        return f"{start}–{end}"
    if start:
        return f"{start} 起"
    return "时间待定"


def render_itinerary_markdown(itinerary: dict[str, Any]) -> str:
    """行程 JSON -> Markdown 文本。"""
    if not itinerary:
        return "# 行程\n\n（没有可导出的行程）\n"

    lines: list[str] = []
    title = itinerary.get("title") or "行程"
    lines.append(f"# {title}")
    lines.append("")

    destination = itinerary.get("destination") or {}
    start = itinerary.get("start_date") or ""
    end = itinerary.get("end_date") or ""
    travelers = itinerary.get("travelers") or {}
    budget = itinerary.get("budget") or {}

    meta = []
    if destination.get("name"):
        meta.append(f"目的地：{destination['name']}")
    if start or end:
        meta.append(f"日期：{start} → {end}")
    meta.append(
        f"出行人：成人 {travelers.get('adults', 1)} / 儿童 {travelers.get('children', 0)}"
    )
    meta.append(f"预算：{_yuan(budget.get('total_cent'))}")
    lines.append("　".join(meta))
    lines.append("")

    summary = itinerary.get("summary")
    if summary:
        lines.append(f"> {summary}")
        lines.append("")

    for day in itinerary.get("days") or []:
        header = f"## {day.get('date', '')} {day.get('weekday', '')}　{day.get('theme', '')}".strip()
        lines.append(header)
        weather = day.get("weather") or {}
        if weather:
            low = weather.get("temp_low_c")
            high = weather.get("temp_high_c")
            temp = f"{low}–{high}℃" if low is not None and high is not None else ""
            lines.append(f"天气：{weather.get('condition') or '未获取'} {temp}".strip())
        lines.append("")
        for item in day.get("items") or []:
            label = TYPE_LABELS.get(item.get("type", ""), "安排")
            location = item.get("location") or {}
            place = location.get("name") or ""
            address = location.get("address")
            heading = f"- **{_time_range(item)}**　[{label}] {item.get('title', '')}"
            if place and place != item.get("title"):
                heading += f"（{place}）"
            lines.append(heading)
            if address:
                lines.append(f"  - 地址：{address}")
            duration = item.get("duration_min")
            if duration:
                lines.append(f"  - 时长：{duration} 分钟")
            cost = item.get("cost_cent")
            if cost:
                lines.append(f"  - 费用：{_yuan(cost)}")
            transport = item.get("transport")
            if transport:
                lines.append(
                    "  - 转场：{} {} 分钟 / {} 米".format(
                        MODE_LABELS.get(transport.get("mode", ""), "移动"),
                        transport.get("duration_min", 0),
                        transport.get("distance_m", 0),
                    )
                )
            if item.get("notes"):
                lines.append(f"  - 备注：{item['notes']}")
        lines.append("")

    packing = itinerary.get("packing_list") or []
    if packing:
        lines.append("## 装备清单")
        lines.extend(f"- {entry}" for entry in packing)
        lines.append("")

    risks = itinerary.get("risks") or []
    if risks:
        lines.append("## 风险提示")
        for risk in risks:
            mitigation = f"　对策：{risk.get('mitigation')}" if risk.get("mitigation") else ""
            lines.append(f"- {risk.get('description', '')}{mitigation}")
        lines.append("")

    lines.append("---")
    lines.append("价格均为估算值，实际以现场为准。")
    return "\n".join(lines) + "\n"


def render_message_markdown(content: str, itinerary: dict[str, Any] | None) -> str:
    """整条回复（正文 + 行程）导出。"""
    parts = [content.strip()] if content else []
    if itinerary:
        parts.append(render_itinerary_markdown(itinerary))
    return "\n\n".join(parts) + "\n"
