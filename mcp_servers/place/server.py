"""Server `place`：3 个工具（BACKEND.md 15.7）。

启动：`python -m mcp_servers.place`

⚠️ 日志一律写 stderr，stdout 只跑 JSON-RPC。
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult
from pydantic import Field

from mcp_servers.common.amap import AmapClient, AmapError
from mcp_servers.common.envelope import as_mcp_result, envelope_err, envelope_ok

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="[place-mcp] %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("tpa.mcp.place")

mcp = FastMCP("place")
_client = AmapClient()

City = Annotated[
    str | None,
    Field(max_length=32, description="城市中文名或 adcode，缺省则全国搜索"),
]
Location = Annotated[str, Field(description="经纬度，格式 \"经度,纬度\"")]


async def _run(tool: str, coro) -> dict:
    started = time.perf_counter()
    try:
        data = await coro
    except AmapError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.warning("工具 %s 失败 %s: %s", tool, exc.code, exc.message)
        return envelope_err(tool, exc.code, exc.message, latency_ms=elapsed)
    except Exception as exc:  # pragma: no cover
        elapsed = int((time.perf_counter() - started) * 1000)
        logger.exception("工具 %s 未捕获异常", tool)
        return envelope_err(tool, "UPSTREAM_ERROR", str(exc)[:200], latency_ms=elapsed)
    elapsed = int((time.perf_counter() - started) * 1000)
    return envelope_ok(tool, data, elapsed)


@mcp.tool(
    name="place_search",
    description=(
        "按关键字搜索景点、餐厅、酒店等地点，返回名称、坐标、地址、评分。"
        "规划行程时必须先用它拿到真实 POI，不要凭记忆写景点名。"
        "注意 rating 与 cost 经常缺失，缺失时如实说明未获取，不要编造。"
    ),
)
async def place_search(
    keywords: Annotated[str, Field(min_length=1, max_length=50, description="搜索关键字，如 西湖")],
    city: City = None,
    page_size: Annotated[int, Field(ge=1, le=25, description="返回条数，1–25，默认 10")] = 10,
) -> CallToolResult:
    if not keywords or not keywords.strip():
        return as_mcp_result(
            envelope_err("place_search", "INVALID_ARGUMENT", "keywords 不能为空")
        )
    size = max(1, min(25, int(page_size)))
    env = await _run(
        "place_search",
        _client.place_text(keywords.strip(), (city or "").strip() or None, size),
    )
    return as_mcp_result(env)


@mcp.tool(
    name="geo_geocode",
    description=(
        "把结构化地址转成经纬度坐标，用于计算路线。"
        "返回的 level 是匹配精度：粗于「区县」说明地址不够具体，应据此向用户确认。"
    ),
)
async def geo_geocode(
    address: Annotated[str, Field(min_length=1, max_length=100, description="结构化地址")],
    city: City = None,
) -> CallToolResult:
    if not address or not address.strip():
        return as_mcp_result(
            envelope_err("geo_geocode", "INVALID_ARGUMENT", "address 不能为空")
        )
    env = await _run(
        "geo_geocode", _client.geocode(address.strip(), (city or "").strip() or None)
    )
    return as_mcp_result(env)


@mcp.tool(
    name="route_plan",
    description=(
        "计算两点之间的距离、耗时与分段路线，用于判断行程是否排得下。"
        "origin / destination 均为 \"经度,纬度\"。mode 支持 driving / walking。"
    ),
)
async def route_plan(
    origin: Location,
    destination: Location,
    mode: Annotated[
        Literal["driving", "walking", "transit"],
        Field(description="出行方式，默认 driving；transit 暂未实现"),
    ] = "driving",
) -> CallToolResult:
    env = await _run("route_plan", _client.route(mode, origin or "", destination or ""))
    return as_mcp_result(env)


def main() -> None:
    logger.info("place-mcp 启动，stdio 就绪")
    mcp.run()


if __name__ == "__main__":
    main()
