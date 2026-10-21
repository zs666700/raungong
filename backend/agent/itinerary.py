"""结构化行程的解析与修正（BACKEND.md 16.4 / 16.5）。

原则：**能修的修，修不了就丢行程对象，但绝不丢文本。**
最差情况只是没有卡片，用户看不到任何报错。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from ..schemas import Itinerary

logger = logging.getLogger("tpa.agent.itinerary")

FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


# ---------------------------------------------------------------------------
# 1. 从文本里抠 JSON
# ---------------------------------------------------------------------------


def _candidates(text: str) -> list[str]:
    blocks = [m.group(1).strip() for m in FENCE_RE.finditer(text or "")]
    ordered = [b for b in blocks if '"days"' in b or '"title"' in b]
    ordered += [b for b in blocks if b not in ordered]

    # 没有代码块时，退化成"找第一个看起来像行程的平衡花括号片段"
    if not ordered:
        start = (text or "").find("{")
        while start != -1:
            depth = 0
            for idx in range(start, len(text)):
                char = text[idx]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : idx + 1]
                        if '"days"' in chunk:
                            ordered.append(chunk)
                        break
            start = text.find("{", start + 1)
            if ordered:
                break
    return ordered


def _loads_lenient(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        pass
    else:
        return data if isinstance(data, dict) else None

    # 常见修复：去尾随逗号、中文引号换英文、去注释
    fixed = raw.replace("\u201c", '"').replace("\u201d", '"').replace("\uff0c", ",")
    fixed = re.sub(r"//[^\n]*", "", fixed)
    fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
    try:
        data = json.loads(fixed)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# 2. 修正
# ---------------------------------------------------------------------------


def _parse_date(text: Any) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def _weekday_of(text: Any) -> str:
    parsed = _parse_date(text)
    return WEEKDAYS[parsed.weekday()] if parsed else ""


def _parse_hhmm(text: Any) -> int | None:
    match = TIME_RE.match(str(text or "").strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _free_day(day_date: str, reason: str = "自由活动") -> dict[str, Any]:
    return {
        "date": day_date,
        "weekday": _weekday_of(day_date),
        "theme": reason,
        "weather": None,
        "items": [
            {
                "index": 1,
                "start_time": None,
                "end_time": None,
                "type": "activity",
                "title": reason,
                "location": {"name": "待定", "address": None, "location": None},
                "duration_min": 120,
                "cost_cent": 0,
                "transport": None,
                "notes": "本日无具体安排，可自行调整",
                "source": "model",
            }
        ],
    }


def _fix_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(item or {})
    item["index"] = index

    start = item.get("start_time")
    end = item.get("end_time")
    start_min = _parse_hhmm(start)
    end_min = _parse_hhmm(end)
    if start is not None and start_min is None:
        item["start_time"] = None
        start_min = None
    if end is not None and end_min is None:
        item["end_time"] = None
    if start_min is not None and end_min is not None and end_min <= start_min:
        # 修不了就降级：结束时间置空，notes 追加"时间待定"
        item["end_time"] = None
        notes = str(item.get("notes") or "").strip()
        item["notes"] = (notes + "；时间待定").strip("；")[:300]

    notes = str(item.get("notes") or "")
    item["notes"] = notes[:300]

    location = item.get("location") or {}
    if not isinstance(location, dict):
        location = {"name": str(location)}
    location.setdefault("name", item.get("title") or "待定")
    location.setdefault("address", None)
    location.setdefault("location", None)
    item["location"] = location

    if item.get("transport") in ({}, [], ""):
        item["transport"] = None

    try:
        item["duration_min"] = max(1, min(720, int(item.get("duration_min") or 60)))
    except (TypeError, ValueError):
        item["duration_min"] = 60
    try:
        item["cost_cent"] = max(0, int(item.get("cost_cent") or 0))
    except (TypeError, ValueError):
        item["cost_cent"] = 0

    if item.get("type") not in (
        "attraction", "meal", "transport", "rest", "activity", "lodging",
    ):
        item["type"] = "activity"
    if item.get("source") not in ("tool", "rag", "model"):
        item["source"] = "model"
    item["title"] = str(item.get("title") or "待定安排")[:60]
    return item


def _fix_days(
    data: dict[str, Any], weather_by_date: dict[str, dict[str, Any]] | None
) -> list[dict[str, Any]]:
    raw_days = data.get("days")
    if not isinstance(raw_days, list):
        return []
    days = [d for d in raw_days if isinstance(d, dict)]
    if not days:
        return []

    start = _parse_date(data.get("start_date"))
    previous: date | None = None
    fixed: list[dict[str, Any]] = []

    for day in days:
        day = dict(day)
        current = _parse_date(day.get("date"))
        if current is None:
            current = (previous + timedelta(days=1)) if previous else (start or date.today())
            day["date"] = current.isoformat()

        # 日期跳日 -> 补一个 theme="自由活动" 的空日
        if previous is not None and (current - previous).days > 1:
            cursor = previous + timedelta(days=1)
            while cursor < current:
                fixed.append(_free_day(cursor.isoformat()))
                cursor += timedelta(days=1)

        items = day.get("items")
        if not isinstance(items, list) or not items:
            day["items"] = _free_day(day["date"])["items"]
        else:
            day["items"] = [
                _fix_item(item, idx)
                for idx, item in enumerate(items, start=1)
                if isinstance(item, dict)
            ]
            if not day["items"]:
                day["items"] = _free_day(day["date"])["items"]

        day["weekday"] = _weekday_of(day["date"])  # 按 date 重算，不信模型
        day["theme"] = str(day.get("theme") or "自由活动")[:20]

        if weather_by_date:
            truth = weather_by_date.get(day["date"])
            if truth:
                # 与工具返回不一致时**以工具为准**
                day["weather"] = {
                    "condition": truth.get("condition"),
                    "temp_low_c": truth.get("temp_low_c"),
                    "temp_high_c": truth.get("temp_high_c"),
                }
            elif day.get("weather") in ({}, [], ""):
                day["weather"] = None
        elif day.get("weather") in ({}, [], ""):
            day["weather"] = None

        fixed.append(day)
        previous = _parse_date(day["date"])

    # 乱序输入按日期排一次，保证"连续递增"
    fixed.sort(key=lambda d: d.get("date") or "")
    for day in fixed:
        day["items"] = [_fix_item(it, idx) for idx, it in enumerate(day["items"], start=1)]
    return fixed


def repair(
    data: dict[str, Any], weather_by_date: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """16.5 的自动修正表。"""
    payload = dict(data or {})

    days = _fix_days(payload, weather_by_date)
    payload["days"] = days
    payload["day_count"] = len(days)

    if days:
        payload["start_date"] = payload.get("start_date") or days[0]["date"]
        payload["end_date"] = days[-1]["date"]
        first = _parse_date(payload["start_date"])
        last = _parse_date(payload["end_date"])
        if first and last and last < first:
            payload["start_date"], payload["end_date"] = days[-1]["date"], days[0]["date"]

    destination = payload.get("destination")
    if not isinstance(destination, dict):
        destination = {"name": str(destination or "")}
    destination.setdefault("name", "")
    destination.setdefault("adcode", "")
    destination.setdefault("location", None)
    payload["destination"] = destination

    title = str(payload.get("title") or "").strip()
    if not title:
        title = f"{destination.get('name') or '目的地'}{max(len(days), 1)} 日游"
    payload["title"] = title[:40]

    summary = str(payload.get("summary") or "").strip()
    payload["summary"] = summary[:600]

    budget = payload.get("budget")
    if not isinstance(budget, dict):
        budget = {}
    breakdown = budget.get("breakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}
    for key in ("transport_cent", "lodging_cent", "food_cent", "tickets_cent", "other_cent"):
        try:
            breakdown[key] = max(0, int(breakdown.get(key) or 0))
        except (TypeError, ValueError):
            breakdown[key] = 0
    subtotal = sum(breakdown.values())
    try:
        total = max(0, int(budget.get("total_cent") or 0))
    except (TypeError, ValueError):
        total = 0
    if total == 0 or (subtotal > 0 and abs(subtotal - total) > total * 0.05):
        total = subtotal
    budget["currency"] = str(budget.get("currency") or "CNY")
    budget["total_cent"] = total
    budget["breakdown"] = breakdown
    payload["budget"] = budget

    packing = payload.get("packing_list")
    payload["packing_list"] = [str(x)[:20] for x in packing if str(x).strip()][:15] if isinstance(packing, list) else []

    risks = payload.get("risks")
    cleaned: list[dict[str, Any]] = []
    if isinstance(risks, list):
        for risk in risks:
            if isinstance(risk, str):
                cleaned.append({"type": "safety", "description": risk[:200], "mitigation": ""})
            elif isinstance(risk, dict):
                if risk.get("type") not in (
                    "weather", "reservation", "safety", "budget", "physical",
                ):
                    risk["type"] = "safety"
                risk["description"] = str(risk.get("description") or "")[:200]
                risk["mitigation"] = str(risk.get("mitigation") or "")[:200]
                cleaned.append(risk)
    payload["risks"] = cleaned

    generated_at = str(payload.get("generated_at") or "").strip()
    if not generated_at:
        generated_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
    payload["generated_at"] = generated_at

    return payload


def extract_itinerary(
    text: str, weather_by_date: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    """三段兜底：抠 JSON -> 修 -> 校验。全都失败返回 None（只返回文本）。"""
    if not text:
        return None
    for raw in _candidates(text):
        data = _loads_lenient(raw)
        if not data or not data.get("days"):
            continue
        repaired = repair(data, weather_by_date)
        if not repaired.get("days"):
            continue
        try:
            return Itinerary.model_validate(repaired).model_dump()
        except ValidationError as exc:
            logger.info("itinerary 校验失败，丢弃该候选：%s", exc.error_count())
            continue
    logger.info("itinerary 解析失败：文本里没有可用的行程 JSON")
    return None
