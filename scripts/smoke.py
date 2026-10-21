"""M0 冒烟脚本：30 秒内回答"这个环境能不能跑起来"（BY BACKEND.md 第 2 章 / TESTING.md 第 3 章）。

    python scripts/smoke.py

四步：数据库 -> MCP Servers -> 高德 API -> LLM 调用。

不需要起服务、不需要起前端。第 4 步只断言**行为**（模型有没有发起工具调用），
不断言回答内容——那是内容断言，脆弱且容易误报。
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 冒烟输出要一眼看懂：必须在 import backend.db 之前关掉 SQL 回显
os.environ.setdefault("TPA_SQL_ECHO", "0")

TOTAL_STEPS = 4


class Reporter:
    def __init__(self) -> None:
        self.failed: list[tuple[str, str]] = []
        self.passed = 0

    def ok(self, step: str, detail: str = "") -> None:
        self.passed += 1
        self._line(step, "OK", detail)

    def fail(self, step: str, detail: str, hint: str = "") -> None:
        self.failed.append((step, detail))
        self._line(step, "FAIL", detail)
        if hint:
            print(f"      → {hint}")

    @staticmethod
    def _line(step: str, status: str, detail: str) -> None:
        dots = "." * max(3, 34 - len(step))
        print(f"{step} {dots} {status:<5}({detail})" if detail else f"{step} {dots} {status}")


def _fail_hint(code: str) -> str:
    return {
        # 工具层错误码
        "UPSTREAM_AUTH_FAILED": "TPA_AMAP_KEY 无效或过期，确认是「Web 服务」类型 Key，且开通了天气/POI/路径规划权限",
        "UPSTREAM_RATE_LIMITED": "高德配额或频率超限，稍后重试",
        "UPSTREAM_ERROR": "高德接口异常，看子进程 stderr 与网络代理",
        "TIMEOUT": "高德接口超时，检查网络或代理",
        "NOT_FOUND": "城市解析不出 adcode，检查参数",
        # 原始 infocode（日志里会出现）
        "10001": "Key 无效或过期",
        "10005": "Key 的 IP 白名单不包含本机出口 IP",
        "10009": "Key 没有开通这个 API 的权限",
        "10003": "高德日访问量超限",
        "10004": "访问过于频繁，稍后重试",
        "10044": "账号日调用量超限",
    }.get(code, "")


# ---------------------------------------------------------------- 第 1 步


async def step_database(reporter: Reporter) -> bool:
    from sqlalchemy import func, select

    from backend.config import settings
    from backend.db import SessionLocal, dispose_engine, ensure_root, init_db
    from backend.models import Base, User

    try:
        settings.ensure_dirs()
        await init_db()
        username, created = await ensure_root()
        async with SessionLocal() as session:
            tables = len(Base.metadata.tables)
            root_count = (
                await session.execute(
                    select(func.count(User.id)).where(User.role == "root")
                )
            ).scalar_one()
    except Exception as exc:
        reporter.fail(
            "1/4 数据库", f"{type(exc).__name__}: {exc}",
            "初始化数据库：python scripts/init_db.py",
        )
        return False
    finally:
        await dispose_engine()

    if int(root_count) < 1:
        reporter.fail("1/4 数据库", "没有 root 账号", "python scripts/init_db.py")
        return False

    reporter.ok(
        "1/4 数据库",
        f"{tables} 张表，root {username} {'已创建' if created else '已存在'}，{settings.db_path.name}",
    )
    return True


# ---------------------------------------------------------------- 第 2 步


async def step_mcp(reporter: Reporter):
    from backend.services.mcp_manager import MCPManager

    manager = await MCPManager.start()
    servers = {name: runner for name, runner in manager.runners.items()}
    counts = {name: len(runner.tools) for name, runner in servers.items()}
    statuses = {name: runner.status for name, runner in servers.items()}

    if counts.get("weather") != 2 or counts.get("place") != 3:
        detail = f"weather={counts.get('weather')} place={counts.get('place')} status={statuses}"
        reporter.fail("2/4 MCP Servers", detail, "子进程 stderr 最后 20 行如下：")
        for name, runner in servers.items():
            tail = runner.stderr_tail(20)
            if tail:
                print(f"      ---- {name} ----")
                for line in tail.splitlines():
                    print(f"      {line}")
        await manager.shutdown()
        return None

    reporter.ok("2/4 MCP Servers", f"weather 2 工具 / place 3 工具")
    return manager


# ---------------------------------------------------------------- 第 3 步


async def step_amap(reporter: Reporter, manager) -> None:
    if manager is None:
        reporter.fail("3/4 高德 API", "上一步没有连上 MCP Server", "先修好第 2 步")
        return

    found = manager.find("weather_now")
    if found is None:
        reporter.fail("3/4 高德 API", "找不到 weather_now 工具")
        return

    runner, _info = found
    started = asyncio.get_running_loop().time()
    try:
        envelope = await runner.call("weather_now", {"city": "杭州"})
    except Exception as exc:
        reporter.fail("3/4 高德 API", f"{type(exc).__name__}: {exc}", "看后端日志里的子进程 stderr")
        return
    elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)

    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        message = f"{error.get('code')}: {error.get('message')}"
        reporter.fail("3/4 高德 API", message, _fail_hint(error.get("code", "")))
        return

    data = envelope.get("data") or {}
    temperature = data.get("temperature_c")
    if not isinstance(temperature, int):
        reporter.fail("3/4 高德 API", f"temperature_c 不是 int：{temperature!r}")
        return

    reporter.ok(
        "3/4 高德 API",
        f"{data.get('city')} {temperature}℃ {data.get('weather')}，{elapsed_ms}ms",
    )


# ---------------------------------------------------------------- 第 4 步


async def step_llm(reporter: Reporter, manager) -> None:
    from backend.agent import graph as agent_graph
    from backend.agent.prompts import build_system_prompt

    tools = manager.build_langchain_tools() if manager is not None else []
    if not tools:
        reporter.fail("4/4 LLM 调用", "没有挂到任何工具，无法验证 function calling")
        return

    request = agent_graph.AgentRequest(
        system_prompt=build_system_prompt(tools=tools, profile={}),
        history=[],
        user_content="杭州今天天气怎么样？请直接查一下再回答。",
    )

    tool_called = False
    tokens = 0
    error: tuple[str, str] | None = None
    started = asyncio.get_running_loop().time()
    try:
        async for kind, payload in agent_graph.run(request, tools):
            if kind == "tool_start":
                tool_called = True
            elif kind == "token":
                tokens += len(payload.get("delta") or "")
    except Exception as exc:
        error = (type(exc).__name__, str(exc)[:200])
    elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)

    if error is not None:
        reporter.fail(
            "4/4 LLM 调用",
            f"{error[0]}: {error[1]}",
            "检查 TPA_LLM_API_KEY / TPA_LLM_BASE_URL；模型必须支持 function calling"
            "（别用 deepseek-reasoner）",
        )
        return

    if not tool_called:
        reporter.fail(
            "4/4 LLM 调用",
            f"模型没有调用任何工具（输出了 {tokens} 字）",
            "提示词约束不够强，或模型不支持 function calling",
        )
        return

    reporter.ok("4/4 LLM 调用", f"模型调用了工具，{tokens} 字输出，{elapsed_ms}ms")


# ---------------------------------------------------------------- main


async def main() -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    reporter = Reporter()
    print("=" * 64)
    print("出行计划智能助手 —— M0 冒烟")
    print("=" * 64)

    ok = await step_database(reporter)
    if not ok:
        print()
        print("配置没过，后面几步没有意义。先按提示修好第 1 步。")
        return 1

    manager = await step_mcp(reporter)
    try:
        await step_amap(reporter, manager)
        await step_llm(reporter, manager)
    finally:
        if manager is not None:
            await manager.shutdown()

    print()
    if reporter.failed:
        print(f"通过 {reporter.passed}/{TOTAL_STEPS}。失败项：")
        for step, detail in reporter.failed:
            print(f"  - {step}: {detail}")
        return 1

    print(f"通过 {reporter.passed}/{TOTAL_STEPS}。可以启动服务了：")
    print("  uvicorn backend.main:app --reload --port 8000")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"启动失败：{exc}")
        raise SystemExit(1) from exc
