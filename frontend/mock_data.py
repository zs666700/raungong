"""Mock 数据（FRONTEND.md 12.2）：没有后端时也能完整走 UI。

所有结构严格照 BACKEND.md 第 9、11、13、14 章的字段来写，
唯一目的就是把行程卡片和各种状态调到满意。
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

NOW = datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


TOOLS = {
    "servers": [
        {"name": "weather", "status": "connected", "tool_count": 2},
        {"name": "place", "status": "connected", "tool_count": 3},
    ],
    "tools": [
        {"name": "weather_now", "server": "weather", "description": "查询城市实时天气"},
        {"name": "weather_forecast", "server": "weather", "description": "查询未来 1–4 天天气预报"},
        {"name": "place_search", "server": "place", "description": "按关键字搜索地点"},
        {"name": "geo_geocode", "server": "place", "description": "地址转坐标"},
        {"name": "route_plan", "server": "place", "description": "计算两点距离与耗时"},
        {"name": "search_knowledge_base", "server": None, "description": "检索内置知识库"},
    ],
    "degraded": False,
}

ITINERARY: dict[str, Any] = {
    "title": "杭州周末 2 日游",
    "destination": {"name": "杭州", "adcode": "330100", "location": "120.155070,30.274084"},
    "start_date": "2026-10-24",
    "end_date": "2026-10-25",
    "day_count": 2,
    "travelers": {"adults": 2, "children": 0},
    "budget": {
        "currency": "CNY",
        "total_cent": 150000,
        "breakdown": {
            "transport_cent": 40000,
            "lodging_cent": 50000,
            "food_cent": 32000,
            "tickets_cent": 18000,
            "other_cent": 10000,
        },
    },
    "summary": "第一天围绕西湖步行，晚上住湖滨；第二天早去灵隐避开人流，午后留一个室内备选应对阵雨。",
    "days": [
        {
            "date": "2026-10-24",
            "weekday": "星期六",
            "theme": "西湖环线 · 慢走",
            "weather": {"condition": "多云", "temp_low_c": 18, "temp_high_c": 24},
            "items": [
                {
                    "index": 1,
                    "start_time": "09:00",
                    "end_time": "11:30",
                    "type": "attraction",
                    "title": "断桥残雪 → 白堤 → 孤山",
                    "location": {"name": "西湖风景名胜区", "address": "西湖区北山街", "location": "120.148,30.259"},
                    "duration_min": 150,
                    "cost_cent": 0,
                    "transport": {"mode": "walking", "duration_min": 5, "distance_m": 380},
                    "notes": "建议 9 点前到，10 点后人流明显增多；白堤中段有长椅，适合中途休息。",
                    "source": "tool",
                },
                {
                    "index": 2,
                    "start_time": "12:00",
                    "end_time": "13:00",
                    "type": "meal",
                    "title": "午餐：知味观（仁和路店）",
                    "location": {"name": "知味观", "address": "上城区仁和路 83 号", "location": "120.166,30.247"},
                    "duration_min": 60,
                    "cost_cent": 16000,
                    "transport": {"mode": "walking", "duration_min": 12, "distance_m": 850},
                    "notes": "一楼小吃、二楼点菜；12:30 后需要排号，建议提前十分钟到。",
                    "source": "tool",
                },
                {
                    "index": 3,
                    "start_time": "14:00",
                    "end_time": "16:30",
                    "type": "attraction",
                    "title": "浙江省博物馆（孤山馆区）",
                    "location": {"name": "浙江省博物馆", "address": "西湖区孤山路 25 号", "location": "120.142,30.253"},
                    "duration_min": 150,
                    "cost_cent": 0,
                    "transport": {"mode": "walking", "duration_min": 8, "distance_m": 600},
                    "notes": "周一闭馆；周末需提前在公众号预约，带身份证入场。",
                    "source": "rag",
                },
                {
                    "index": 4,
                    "start_time": "17:30",
                    "end_time": "19:00",
                    "type": "meal",
                    "title": "晚餐：新白鹿（湖滨店）",
                    "location": {"name": "新白鹿餐厅", "address": "上城区延安路 258 号", "location": "120.168,30.252"},
                    "duration_min": 90,
                    "cost_cent": 18000,
                    "transport": {"mode": "walking", "duration_min": 15, "distance_m": 1100},
                    "notes": "周末排队约 40 分钟，可先取号再去湖滨步行街逛一圈。",
                    "source": "tool",
                },
                {
                    "index": 5,
                    "start_time": "19:30",
                    "end_time": "20:30",
                    "type": "activity",
                    "title": "宝石山看城市夜景",
                    "location": {"name": "宝石山", "address": "西湖区宝石山路", "location": "120.152,30.267"},
                    "duration_min": 60,
                    "cost_cent": 0,
                    "transport": {"mode": "walking", "duration_min": 18, "distance_m": 1300},
                    "notes": "视体力决定，山路有石阶，雨后湿滑不建议上去。",
                    "source": "model",
                },
            ],
        },
        {
            "date": "2026-10-25",
            "weekday": "星期日",
            "theme": "灵隐 · 龙井 · 雨天备选",
            "weather": {"condition": "阵雨", "temp_low_c": 16, "temp_high_c": 21},
            "items": [
                {
                    "index": 1,
                    "start_time": "08:30",
                    "end_time": "10:30",
                    "type": "attraction",
                    "title": "灵隐寺 · 飞来峰",
                    "location": {"name": "灵隐寺", "address": "西湖区灵隐路法云弄 1 号", "location": "120.101,30.240"},
                    "duration_min": 120,
                    "cost_cent": 7500,
                    "transport": {"mode": "transit", "duration_min": 25, "distance_m": 7800},
                    "notes": "飞来峰景区与灵隐寺分开购票；8:30 前进山几乎不用排队。",
                    "source": "tool",
                },
                {
                    "index": 2,
                    "start_time": "11:00",
                    "end_time": "12:00",
                    "type": "activity",
                    "title": "龙井村茶园漫步",
                    "location": {"name": "龙井村", "address": "西湖区龙井路", "location": "120.108,30.226"},
                    "duration_min": 60,
                    "cost_cent": 0,
                    "transport": {"mode": "driving", "duration_min": 15, "distance_m": 4200},
                    "notes": "山路较窄，雨天不建议自驾；可在村口茶室避雨。",
                    "source": "model",
                },
                {
                    "index": 3,
                    "start_time": "12:30",
                    "end_time": "13:30",
                    "type": "meal",
                    "title": "午餐：绿茶餐厅（龙井店）",
                    "location": {"name": "绿茶餐厅", "address": "西湖区龙井路 83 号", "location": "120.112,30.231"},
                    "duration_min": 60,
                    "cost_cent": 15000,
                    "transport": {"mode": "walking", "duration_min": 6, "distance_m": 450},
                    "notes": "靠窗位置能看到茶园，11:30 前到基本不用排队。",
                    "source": "tool",
                },
                {
                    "index": 4,
                    "start_time": "15:00",
                    "end_time": "16:30",
                    "type": "attraction",
                    "title": "中国丝绸博物馆",
                    "location": {"name": "中国丝绸博物馆", "address": "西湖区玉皇山路 73-1 号", "location": "120.155,30.226"},
                    "duration_min": 90,
                    "cost_cent": 0,
                    "transport": {"mode": "driving", "duration_min": 18, "distance_m": 6500},
                    "notes": "免费，需提前预约；雨天作为户外项目的替代很合适。",
                    "source": "rag",
                },
            ],
        },
    ],
    "packing_list": ["雨伞", "舒适步行鞋", "薄外套", "充电宝"],
    "risks": [
        {
            "type": "weather",
            "description": "周日有阵雨，龙井村与宝石山等户外项目受影响",
            "mitigation": "把龙井村改为中国丝绸博物馆，出发前再看一次逐小时预报",
        },
        {
            "type": "reservation",
            "description": "灵隐寺与浙江省博物馆周末限流",
            "mitigation": "提前 1 天在官方公众号预约，带好身份证",
        },
        {
            "type": "safety",
            "description": "西湖周边周末停车紧张，湖滨一带容易堵",
            "mitigation": "地铁 1 号线到龙翔桥，景区内以步行和公交为主",
        },
    ],
    "generated_at": "2026-10-19T02:42:00Z",
}

ASSISTANT_TEXT = """根据这周末的天气预报，杭州周六多云、周日有阵雨，**第一天安排环西湖步行，第二天把户外项目往上午挪**，下午留一个室内备选。

几个关键取舍：

1. **住宿放在湖滨**，两天都不用拖着行李换酒店，晚上吃饭也方便。
2. **灵隐放在周日 8:30**，比旅行团早半小时进山，排队时间差很多。
3. **预算按两个人 1500 元**做，住宿占大头；如果想把预算压到 1200，可以把湖滨换成龙翔桥地铁站附近。

详细安排见下方行程卡，点「导出行程」可以存成 Markdown 带走。"""

CITATIONS = [
    {
        "document_id": "d_01",
        "title": "杭州西湖景区 2026 年预约须知",
        "ordinal": 3,
        "score": 0.8123,
        "snippet": "自 2026 年 3 月 1 日起，西湖景区实行分时段预约，灵隐飞来峰景区周末单日限流 3 万人次……",
    },
    {
        "document_id": "d_02",
        "title": "杭州地铁周末运营调整通知",
        "ordinal": 1,
        "score": 0.7345,
        "snippet": "周末 1 号线龙翔桥站末班车延后至 23:30，景区周边公交专线加密至 10 分钟一班……",
    },
]

TOOL_CALLS = [
    {
        "name": "weather_forecast",
        "args": {"city": "杭州", "days": 2},
        "ok": True,
        "ms": 312,
        "summary": "10/24 多云 18–24℃；10/25 阵雨 16–21℃",
    },
    {
        "name": "place_search",
        "args": {"keywords": "西湖 景点", "city": "杭州"},
        "ok": True,
        "ms": 402,
        "summary": "命中 128 条，取前 10",
    },
    {
        "name": "geo_geocode",
        "args": {"address": "西湖区北山街"},
        "ok": True,
        "ms": 180,
        "summary": "已定位北山街",
    },
    {
        "name": "route_plan",
        "args": {"origin": "120.148,30.259", "destination": "120.166,30.247", "mode": "walking"},
        "ok": True,
        "ms": 620,
        "summary": "0.85km / 12 分钟",
    },
]


def _conversation(
    cid: str,
    title: str,
    count: int,
    has_itinerary: bool,
    updated_minutes: int,
    created_days: int,
) -> dict[str, Any]:
    return {
        "id": cid,
        "title": title,
        "message_count": count,
        "has_itinerary": has_itinerary,
        "created_at": _iso(NOW - timedelta(days=created_days)),
        "updated_at": _iso(NOW - timedelta(minutes=updated_minutes)),
    }


CONVERSATIONS: list[dict[str, Any]] = [
    _conversation("c_hz", "杭州周末两天", 4, True, 12, 1),
    _conversation("c_cd", "成都出差三天", 2, False, 60 * 26, 4),
    _conversation("c_sz", "带爸妈苏州一日游", 2, False, 60 * 24 * 6, 9),
]

MESSAGES: dict[str, list[dict[str, Any]]] = {
    "c_hz": [
        {
            "id": "m_01",
            "seq": 1,
            "role": "user",
            "content": "这周末去杭州玩两天，两个人，预算 1500，住湖滨附近，帮我排个行程。",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(days=1, minutes=18)),
        },
        {
            "id": "m_02",
            "seq": 2,
            "role": "assistant",
            "content": ASSISTANT_TEXT,
            "status": "completed",
            "itinerary": ITINERARY,
            "citations": CITATIONS,
            "tool_calls": TOOL_CALLS,
            "created_at": _iso(NOW - timedelta(days=1, minutes=12)),
        },
        {
            "id": "m_03",
            "seq": 3,
            "role": "user",
            "content": "第二天如果下雨，室内备选怎么换？不要博物馆也行，最好能坐下来喝茶。",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(minutes=40)),
        },
        {
            "id": "m_04",
            "seq": 4,
            "role": "assistant",
            "content": "下雨的话，把 **龙井村茶园漫步** 换成龙井路一带的茶室更稳妥：\n\n- 上午灵隐不变，10:30 下山后直接去「龙井草堂」或「青藤茶楼」，都能坐一下午。\n- 原定的中国丝绸博物馆保留在 15:00，从茶室过去打车约 18 分钟。\n- 雨大的话，把宝石山夜景直接删掉，湖滨吃完晚饭回酒店，不绕路。\n\n这样调整后，周日的步行量从 6.2km 降到 3.5km 左右，带伞也不会太狼狈。",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(minutes=12)),
        },
    ],
    "c_cd": [
        {
            "id": "m_11",
            "seq": 1,
            "role": "user",
            "content": "下周去成都出差三天，晚上和周末有一点空，有什么值得去的地方？",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(days=4)),
        },
        {
            "id": "m_12",
            "seq": 2,
            "role": "assistant",
            "content": "你住在天府三街的话，工作日晚上的活动半径建议控制在 **地铁 1 号线沿线**：\n\n1. **周二晚**：金融城打车去望平街，沿河吃饭，回酒店 20 分钟。\n2. **周三晚**：宽窄巷子人太多，换成小通巷，安静一些。\n3. **周六**：如果要跑远一点，青城山当天往返来得及，但需要 8 点前出发。\n\n要我把周六的半天排成一条路线吗？",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(days=4) + timedelta(minutes=3)),
        },
    ],
    "c_sz": [
        {
            "id": "m_21",
            "seq": 1,
            "role": "user",
            "content": "带爸妈去苏州一日游，不想走太多路，从上海出发。",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(days=9)),
        },
        {
            "id": "m_22",
            "seq": 2,
            "role": "assistant",
            "content": "建议只排 **拙政园 + 平江路** 两个点，中间打车，不走回头路：\n\n- 上海站 8:00 高铁到苏州站，打车 15 分钟到拙政园。\n- 拙政园逛 90 分钟，出园后步行 10 分钟到平江路吃午饭。\n- 下午在平江路找一家评弹茶馆坐到 15:30，再打车回苏州站。\n\n全程步行约 2.5km，中间有两段可以坐车。需要我把高铁班次和餐厅一起排进去吗？",
            "status": "completed",
            "itinerary": None,
            "citations": None,
            "tool_calls": None,
            "created_at": _iso(NOW - timedelta(days=9) + timedelta(minutes=2)),
        },
    ],
}

RAG_DOCUMENTS: list[dict[str, Any]] = [
    {
        "id": "d_01",
        "title": "杭州西湖景区 2026 年预约须知",
        "source_type": "file",
        "filename": "西湖预约须知.pdf",
        "status": "ready",
        "chunk_count": 24,
        "error": None,
        "created_at": _iso(NOW - timedelta(days=2, hours=3)),
    },
    {
        "id": "d_02",
        "title": "杭州地铁周末运营调整通知",
        "source_type": "url",
        "filename": "https://example.gov.cn/notice/2026-10-15.html",
        "status": "ready",
        "chunk_count": 12,
        "error": None,
        "created_at": _iso(NOW - timedelta(days=3, hours=1)),
    },
    {
        "id": "d_03",
        "title": "景区交通管制通知（扫描件）",
        "source_type": "file",
        "filename": "交通管制通知.pdf",
        "status": "failed",
        "chunk_count": 0,
        "error": "未能提取到文本，可能是扫描版 PDF，请先 OCR",
        "created_at": _iso(NOW - timedelta(days=5)),
    },
]

USERS: list[dict[str, Any]] = [
    {
        "id": "u_root",
        "username": "root",
        "role": "root",
        "status": "active",
        "conversation_count": 3,
        "created_at": _iso(NOW - timedelta(days=30)),
    },
    {
        "id": "u_alice",
        "username": "alice",
        "role": "user",
        "status": "active",
        "conversation_count": 12,
        "created_at": _iso(NOW - timedelta(days=18)),
    },
    {
        "id": "u_bob",
        "username": "bob",
        "role": "user",
        "status": "disabled",
        "conversation_count": 0,
        "created_at": _iso(NOW - timedelta(days=12)),
    },
    {
        "id": "u_carol",
        "username": "carol",
        "role": "root",
        "status": "active",
        "conversation_count": 5,
        "created_at": _iso(NOW - timedelta(days=6)),
    },
]

SEARCH_HITS = [
    {
        "document_id": "d_01",
        "title": "杭州西湖景区 2026 年预约须知",
        "ordinal": 3,
        "score": 0.8123,
        "snippet": "自 2026 年 3 月 1 日起，西湖景区实行分时段预约。灵隐飞来峰景区周末单日限流 3 万人次，建议提前 1–7 天通过「西湖景区」官方公众号预约……",
    },
    {
        "document_id": "d_02",
        "title": "杭州地铁周末运营调整通知",
        "ordinal": 1,
        "score": 0.7345,
        "snippet": "周末 1 号线龙翔桥站末班车延后至 23:30，景区周边公交专线加密至 10 分钟一班。节假日期间，北山街部分路段禁止机动车通行……",
    },
]

PROFILE: dict[str, Any] = {
    "home_city": "上海",
    "budget_level": "comfortable",
    "pace": "balanced",
    "interests": ["博物馆", "城市漫步"],
    "dietary": ["不吃辣"],
    "avoid": ["长途大巴"],
}


def clone(value: Any) -> Any:
    return copy.deepcopy(value)
