"""Server `weather`：2 个工具（BACKEND.md 15.6）。

启动：`python -m mcp_servers.weather`

⚠️ 日志一律写 stderr。stdout 是 JSON-RPC 通道，`print()` 会直接搞坏通信
—— 这是最常见的集成事故。
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult
from pydantic import Field

from mcp_servers.common.amap import AmapClient, AmapError
from mcp_servers.common.envelope import as_mcp_result, envelope_err, envelope_ok

# stdout 留给 JSON-RPC，日志只进 stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[weather-mcp] %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tpa.mcp.weather")

mcp = FastMCP("weather")
_client = AmapClient()

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

City = Annotated[
    str,
    Field(
        min_length=1,
        max_length=32,
        description="城市中文名（如 杭州）或 6 位 adcode（如 330100）",
    ),
]


def _derive_advice(condition: str | None, day_temp_c: int | None) -> tuple[str, str]:
    """纯函数：(advice, rain_risk)，对应 15.6 的派生规则表。

    让服务器算好"要不要带伞"比让模型自己推更准，也省 token。
    """
    text = condition or ""

    if any(k in text for k in ("暴雨", "大暴雨", "雷阵雨")):
        return "建议改为室内活动，注意积水与交通管制", "high"
    if any(k in text for k in ("阵雨", "中雨", "大雨", "雪", "雨夹雪")):
        return "建议安排室内活动并携带雨具", "high"
    if any(k in text for k in ("小雨", "毛毛雨")):
        return "建议携带雨具，户外安排留弹性", "medium"
    if any(k in text for k in ("雾", "霾", "沙尘")):
        return "减少长时间户外活动", "medium"
    if day_temp_c is not None and day_temp_c >= 35:
        return "避开正午户外，注意补水防晒", "low"
    return "适合户外活动", "low"


def _weekday(date_text: str | None) -> str | None:
    if not date_text:
        return None
    try:
        return WEEKDAYS[date.fromisoformat(date_text).weekday()]
    except ValueError:
        return None


async def _run(tool: str, coro) -> dict:
    """统一收口：把 AmapError 与未捕获异常都转成信封，绝不抛给 MCP 层。"""
    started = time.perf_counter()
    try:
        data = await coro
    except AmapError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.warning("工具 %s 失败 %s: %s", tool, exc.code, exc.message)
        return envelope_err(tool, exc.code, exc.message, latency_ms=elapsed)
    except Exception as exc:  # pragma: no cover - 兜底
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.exception("工具 %s 未捕获异常", tool)
        return envelope_err(tool, "UPSTREAM_ERROR", str(exc)[:200], latency_ms=elapsed)
    elapsed = int((time.perf_counter() - started) * 1000)
    return envelope_ok(tool, data, elapsed)


@mcp.tool(
    name="weather_now",
    description=(
        "查询中国境内城市当前实时天气，返回天气现象、温度、风向风力、湿度。"
        "city 可传城市中文名（如 杭州）或 6 位 adcode（如 330100）。"
    ),
)
async def weather_now(city: City) -> CallToolResult:
    if not city or not city.strip():
        return as_mcp_result(
            envelope_err("weather_now", "INVALID_ARGUMENT", "city 不能为空")
        )
    env = await _run("weather_now", _client.weather_live(city.strip()))
    return as_mcp_result(env)


@mcp.tool(
    name="weather_forecast",
    description=(
        "查询城市未来 1–4 天天气预报，含每日天气、温度区间、出行建议与降水风险。"
        "规划行程前应先调用它确认天气。"
    ),
)
async def weather_forecast(
    city: City,
    days: Annotated[
        int, Field(ge=1, le=4, description="预报天数，1–4，默认 3")
    ] = 3,
) -> CallToolResult:
    if not city or not city.strip():
        return as_mcp_result(
            envelope_err("weather_forecast", "INVALID_ARGUMENT", "city 不能为空")
        )
    if not 1 <= int(days) <= 4:
        return as_mcp_result(
            envelope_err("weather_forecast", "INVALID_ARGUMENT", "days 必须在 1–4 之间")
        )

    env = await _run(
        "weather_forecast", _client.weather_forecast(city.strip(), int(days))
    )
    if env["ok"]:
        for cast in env["data"]["forecast"]:
            advice, rain_risk = _derive_advice(
                cast.get("day_weather"), cast.get("day_temp_c")
            )
            cast["weekday"] = _weekday(cast.get("date"))
            cast["advice"] = advice
            cast["rain_risk"] = rain_risk
    return as_mcp_result(env)


def main() -> None:
    logger.info("weather-mcp 启动，stdio 就绪")
    mcp.run()


if __name__ == "__main__":
    main()
