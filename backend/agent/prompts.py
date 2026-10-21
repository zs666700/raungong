"""系统提示词 6 块（BACKEND.md 16.3）+ 会话标题提示词（16.7）。

Prompt 缓存的排法：**常量块在前、变量块在后**，顺序固定，方便命中 DeepSeek 的
前缀缓存。因此实际拼接顺序是 1 → 5 → 6 → 2 → 3 → 4，而不是表格里的 1–6。
每一块的语义编号与文档一致，便于对照单测。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

CN_TZ = timezone(timedelta(hours=8))
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

BUDGET_LABELS = {"economy": "经济", "comfortable": "舒适", "luxury": "高端"}
PACE_LABELS = {"relaxed": "轻松", "balanced": "适中", "packed": "紧凑"}

# ---- 第 1 块：角色（常量）----
BLOCK_ROLE = (
    "你是中国境内的出行规划助手，用中文回答，输出可执行的行程。"
    "你熟悉国内热门目的地，但一切事实性信息必须来自工具返回的数据。"
)

# ---- 第 5 块：工具使用策略（常量）----
BLOCK_TOOL_POLICY = """工具使用策略：
1. 涉及具体日期和目的地，先调用 weather_forecast，天数要覆盖行程天数。用户没给日期就先问，或按"本周末"默认并说明。
2. 目的地必须先调用 place_search 拿真实 POI，不要凭记忆写景点名。
3. 相邻景点调用 route_plan 算真实耗时，不要凭感觉估。
4. 政策类问题（要不要预约、限行、门票）先调用 search_knowledge_base。
5. 工具返回 ok=false 时如实说明查不到，不要假装成功，也不要把错误码抛给用户。
6. 营业时间、票价、评分缺失时说"未获取到"，绝对不要编造。
7. 单轮工具调用不超过 8 次。"""

# ---- 第 6 块：输出要求（常量）----
BLOCK_OUTPUT_RULES = """输出要求：
1. 先 2–4 句自然语言总结（目的地、日期、人数、预算、天气结论、关键约束），不要复述工具原始 JSON。
2. 然后按天输出 Markdown 时间轴，同时给出结构化行程 JSON（```json 代码块）供前端渲染卡片。
3. 天气信息必须来自 weather_forecast，并注明数据的发布时间。
4. 用了知识库就在句末标注 [doc:文档标题]。
5. 结尾给 1–3 条风险提示（雨天备选、预约要求、体力强度）。
6. 价格一律标注"为估算值，实际以现场为准"。

结构化行程 JSON 的字段（严格照抄这些键名，缺失不编造）：
title, destination{name,adcode,location}, start_date, end_date, day_count,
travelers{adults,children}, budget{currency,total_cent,breakdown{transport_cent,
lodging_cent,food_cent,tickets_cent,other_cent}}, summary, days[{date,weekday,theme,
weather{condition,temp_low_c,temp_high_c},items[{index,start_time,end_time,type,title,
location{name,address,location},duration_min,cost_cent,transport{mode,duration_min,
distance_m},notes,source}]}], packing_list, risks[{type,description,mitigation}],
generated_at。
其中 type 取 attraction/meal/transport/rest/activity/lodging，source 取 tool/rag/model，
transport.mode 取 walking/driving/transit，risks[].type 取 weather/reservation/safety/budget/physical。
金额一律整数分（*_cent），时间 HH:MM，日期 YYYY-MM-DD。"""


def now_in_cn(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(CN_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=CN_TZ)
    return now.astimezone(CN_TZ)


def render_clock(now: datetime | None = None) -> str:
    """第 2 块：当前时间。"""
    current = now_in_cn(now)
    weekday = WEEKDAYS[current.weekday()]
    return f"今天是 {current:%Y-%m-%d} {weekday}，时区 Asia/Shanghai。"


def render_profile(profile: dict[str, Any] | None) -> str:
    """第 4 块：用户画像，渲染成一句话（6.5）。空画像给"未填写"。"""
    profile = profile or {}
    parts: list[str] = []

    home_city = (profile.get("home_city") or "").strip()
    if home_city:
        parts.append(f"常住{home_city}")

    budget = profile.get("budget_level")
    if budget in BUDGET_LABELS:
        parts.append(f"预算档位：{BUDGET_LABELS[budget]}")

    pace = profile.get("pace")
    if pace in PACE_LABELS:
        parts.append(f"节奏：{PACE_LABELS[pace]}")

    for key, label in (("interests", "兴趣"), ("dietary", "忌口"), ("avoid", "规避")):
        values = [str(v) for v in (profile.get(key) or []) if str(v).strip()]
        if values:
            parts.append(f"{label}：{'、'.join(values)}")

    return "；".join(parts) + "。" if parts else "用户还没有填写出行偏好。"


def render_tools(tools: list[Any]) -> str:
    """第 3 块：只列**实际挂载**的工具名与一句话说明。"""
    if not tools:
        return "当前没有可用的工具，请仅基于用户提供的信息作答，并说明能力受限。"
    lines = ["当前可用的工具："]
    for tool in tools:
        name = getattr(tool, "name", "?")
        description = (getattr(tool, "description", "") or "").strip().splitlines()
        summary = description[0] if description else name
        lines.append(f"- {name}：{summary}")
    return "\n".join(lines)


def render_degraded(notes: list[str]) -> str:
    if not notes:
        return ""
    return "\n能力受限说明：\n" + "\n".join(f"- {note}" for note in notes)


def build_system_prompt(
    *,
    tools: list[Any],
    profile: dict[str, Any] | None,
    degraded_notes: list[str] | None = None,
    now: datetime | None = None,
) -> str:
    """按 16.3 拼 6 块。常量在前（缓存友好），变量在后。"""
    blocks = [
        BLOCK_ROLE,                     # 1 常量
        BLOCK_TOOL_POLICY,              # 5 常量
        BLOCK_OUTPUT_RULES,             # 6 常量
        render_clock(now),              # 2 变量
        render_tools(tools),            # 3 变量
        "用户画像：" + render_profile(profile),  # 4 变量
    ]
    prompt = "\n\n".join(blocks)
    degraded = render_degraded(degraded_notes or [])
    if degraded:
        prompt += "\n" + degraded
    return prompt


def title_prompt(first_message: str, itinerary_title: str | None = None) -> str:
    """16.7 会话标题生成。"""
    material = first_message.strip()[:500]
    extra = f"\n行程标题参考：{itinerary_title}" if itinerary_title else ""
    return (
        "用不超过 15 个汉字概括这次出行需求，只输出标题本身，不要引号和句号。\n\n"
        f"用户需求：{material}{extra}"
    )
