"""行程导出（FRONTEND.md 8.5）：本地拼 Markdown，不走后端接口。"""

from __future__ import annotations

from typing import Any

from nicegui import ui

from ..ui_utils import safe_filename


def build_markdown(itinerary: dict[str, Any]) -> str:
    it = itinerary or {}
    destination = it.get("destination") or {}
    travelers = it.get("travelers") or {}
    budget = it.get("budget") or {}

    lines: list[str] = [f"# {it.get('title') or '出行计划'}", ""]
    lines.append(
        f"- 目的地：{destination.get('name') or '—'}"
        f"（adcode {destination.get('adcode') or '—'}）"
    )
    lines.append(
        f"- 日期：{it.get('start_date') or '—'} ~ {it.get('end_date') or '—'}"
        f"（{it.get('day_count') or 0} 天）"
    )
    adults = travelers.get("adults") or 0
    children = travelers.get("children") or 0
    people = f"{adults} 成人"
    if children:
        people += f" + {children} 儿童"
    lines.append(f"- 出行人数：{people}")
    if budget.get("total_cent") is not None:
        lines.append(f"- 预算：¥{int(budget.get('total_cent') or 0) // 100}")

    summary = (it.get("summary") or "").strip()
    if summary:
        lines.extend(["", summary])

    lines.extend(["", "## 行程"])
    for index, day in enumerate(it.get("days") or [], start=1):
        d = day or {}
        date = d.get("date") or ""
        theme = (d.get("theme") or "").strip()
        lines.append("")
        lines.append(
            f"### 第 {index} 天 · {date} · {d.get('weekday') or ''} · {theme}"
        )
        weather = d.get("weather") or None
        if weather:
            low = weather.get("temp_low_c")
            high = weather.get("temp_high_c")
            temp = f"{low}–{high}℃" if low is not None and high is not None else "温度未知"
            lines.append(f"> 天气：{weather.get('condition') or ''} {temp}".rstrip())
        for item in d.get("items") or []:
            item = item or {}
            start = item.get("start_time") or "—"
            end = item.get("end_time") or "—"
            cost = (
                "免费"
                if int(item.get("cost_cent") or 0) == 0
                else f"¥{int(item.get('cost_cent') or 0) // 100}"
            )
            lines.append(f"- {start}–{end} **{item.get('title') or '未命名安排'}**")
            location = item.get("location") or {}
            if location.get("address"):
                lines.append(f"  - 位置：{location['address']}")
            lines.append(
                f"  - 费用：{cost}｜时长：{item.get('duration_min') or 0} 分钟"
            )
            transport = item.get("transport") or None
            if transport:
                mode = {"walking": "步行", "driving": "驾车", "transit": "公交"}.get(
                    str(transport.get("mode") or ""), "前往"
                )
                distance = int(transport.get("distance_m") or 0)
                distance_text = f"{distance / 1000:.1f}km" if distance >= 1000 else f"{distance}m"
                lines.append(
                    f"  - 交通：{mode} {transport.get('duration_min') or 0} 分钟 {distance_text}"
                )
            if item.get("notes"):
                lines.append(f"  - 备注：{item['notes']}")

    risks = it.get("risks") or []
    if risks:
        lines.extend(["", "## 风险提示"])
        for risk in risks:
            risk = risk or {}
            lines.append(
                f"- {risk.get('description') or ''} → {risk.get('mitigation') or ''}"
            )
    packing = it.get("packing_list") or []
    if packing:
        lines.extend(["", f"**建议携带**：{'、'.join(str(p) for p in packing)}"])
    if not lines:
        lines = ["# 出行计划", "", "暂无内容"]
    return "\n".join(lines)


def download_itinerary(itinerary: dict[str, Any]) -> None:
    markdown = build_markdown(itinerary)
    filename = f"{safe_filename((itinerary or {}).get('title'))}.md"
    ui.download.content(markdown.encode("utf-8"), filename=filename, media_type="text/markdown")
