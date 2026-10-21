"""MCP 子进程生命周期、工具发现与调用（BACKEND.md 15.1 / 18.4）。

设计要点
--------
* 每个 Server 的 stdio 会话固定跑在**一个专属后台任务**里：既避开 anyio
  cancel scope 跨任务的老问题，也天然把同一条 stdio 管道上的调用串起来。
* 调用方只往队列里塞请求，拿 asyncio.Future 等结果。
* 崩了自动重启，最多 3 次；超了标记 failed，`/tools` 里 `degraded=true`。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, create_model

from ..config import BASE_DIR, settings
from ..errors import ApiError

logger = logging.getLogger("tpa.mcp_manager")

START_TIMEOUT = 20.0
CALL_TIMEOUT = 15.0
MAX_RESTARTS = 3

SERVER_SPECS: dict[str, list[str]] = {
    "weather": ["-m", "mcp_servers.weather"],
    "place": ["-m", "mcp_servers.place"],
}

# 环境变量白名单：子进程只继承这些（+ 系统必需项），Key 不进命令行，防 ps 看到
_ENV_WHITELIST = (
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME", "USERPROFILE",
    "PYTHONPATH", "LANG", "LC_ALL",
)


@dataclass
class ToolInfo:
    name: str
    server: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


def _subprocess_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_WHITELIST if k in os.environ}
    env["TPA_AMAP_KEY"] = settings.amap_key
    env["TPA_AMAP_TIMEOUT"] = str(settings.amap_timeout)
    env["PYTHONPATH"] = str(BASE_DIR)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@dataclass
class _Call:
    name: str
    args: dict[str, Any]
    future: asyncio.Future


class MCPServerRunner:
    """一个 Server 子进程的管家。"""

    def __init__(self, name: str, args: list[str]) -> None:
        self.name = name
        self.args = args
        self.status = "disconnected"  # connected / disconnected / failed
        self.tools: dict[str, ToolInfo] = {}
        self._queue: asyncio.Queue[_Call | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._session: Any = None
        self._pending: set[asyncio.Future] = set()
        self._closed = False
        self._ready = asyncio.Event()
        self.last_error: str | None = None
        # 子进程 stderr 落盘：stdout 是协议通道，排障全靠这个文件
        self.stderr_path = settings.data_path / "logs" / f"{name}-mcp.log"

    def stderr_tail(self, lines: int = 20) -> str:
        try:
            with open(self.stderr_path, encoding="utf-8", errors="ignore") as fh:
                return "".join(fh.readlines()[-lines:]).strip()
        except OSError:
            return ""

    # ------------------------------------------------------------------ 生命周期

    async def start(self) -> None:
        self._task = asyncio.create_task(self._supervise(), name=f"mcp-{self.name}")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=START_TIMEOUT)
        except asyncio.TimeoutError:
            self.status = "failed"
            self.last_error = "启动超时"
            logger.error("MCP Server %s 启动超时（%ss）", self.name, START_TIMEOUT)

    async def stop(self) -> None:
        self._closed = True
        await self._queue.put(None)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        self.status = "disconnected"

    # ------------------------------------------------------------------ 内部

    async def _supervise(self) -> None:
        restarts = 0
        while not self._closed:
            try:
                await self._run_session()
            except asyncio.CancelledError:
                self._fail_pending("会话已关闭")
                raise
            except Exception as exc:
                self._fail_pending(f"会话异常: {exc}")
                self.last_error = str(exc)[:300]
                self.status = "disconnected"
                self._session = None
                self._tools_clear()
                if self._closed:
                    return
                restarts += 1
                if restarts > MAX_RESTARTS:
                    self.status = "failed"
                    logger.error(
                        "MCP Server %s 连续崩溃 %s 次，标记 failed：%s",
                        self.name, restarts - 1, self.last_error,
                    )
                    return
                logger.warning(
                    "MCP Server %s 崩溃，第 %s 次重启：%s", self.name, restarts, exc
                )
                await asyncio.sleep(min(restarts, 3))

    def _tools_clear(self) -> None:
        self.tools.clear()

    async def _run_session(self) -> None:
        """建立会话 -> 发现工具 -> 服务调用队列，直到断开。"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params_kwargs: dict[str, Any] = {
            "command": sys.executable,
            "args": self.args,
            "env": _subprocess_env(),
        }
        try:
            params = StdioServerParameters(cwd=str(BASE_DIR), **params_kwargs)
        except TypeError:  # 老版本 SDK 没有 cwd 参数
            params = StdioServerParameters(**params_kwargs)

        async with AsyncExitStack() as stack:
            self.stderr_path.parent.mkdir(parents=True, exist_ok=True)
            errlog = stack.enter_context(
                open(self.stderr_path, "a", encoding="utf-8", errors="replace")
            )
            read, write = await stack.enter_async_context(
                stdio_client(params, errlog=errlog)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=START_TIMEOUT)
            listed = await asyncio.wait_for(session.list_tools(), timeout=START_TIMEOUT)

            self.tools = {
                tool.name: ToolInfo(
                    name=tool.name,
                    server=self.name,
                    description=(tool.description or "").strip(),
                    input_schema=getattr(tool, "inputSchema", None) or {},
                )
                for tool in listed.tools
            }
            self._session = session
            self.status = "connected"
            self.last_error = None
            self._ready.set()
            logger.info(
                "MCP Server %s 已连接，发现 %s 个工具: %s",
                self.name, len(self.tools), ", ".join(sorted(self.tools)),
            )

            await self._serve(session)

    async def _serve(self, session: Any) -> None:
        while not self._closed:
            call = await self._queue.get()
            if call is None:
                return
            try:
                result = await asyncio.wait_for(
                    session.call_tool(call.name, call.args), timeout=CALL_TIMEOUT
                )
                if not call.future.done():
                    call.future.set_result(result)
            except asyncio.TimeoutError:
                if not call.future.done():
                    call.future.set_exception(
                        ApiError("TOOL_FAILED", f"工具 {call.name} 调用超时", 504)
                    )
            except Exception as exc:
                # 管道级异常 -> 让上层看到，同时退出会话触发重启
                if not call.future.done():
                    call.future.set_exception(exc)
                raise

    def _fail_pending(self, reason: str) -> None:
        for fut in list(self._pending):
            if not fut.done():
                fut.set_exception(ApiError("TOOL_UNAVAILABLE", reason, 503))
        self._pending.clear()

    async def call_raw(self, name: str, args: dict[str, Any]) -> Any:
        """调用并把原始 MCP 结果返回（scripts/smoke.py 用它断言双写一致）。"""
        if self.status != "connected" or self._session is None:
            raise ApiError(
                "TOOL_UNAVAILABLE", f"MCP Server {self.name} 不可用", 503
            )
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending.add(future)
        await self._queue.put(_Call(name=name, args=args, future=future))
        try:
            return await asyncio.wait_for(future, timeout=CALL_TIMEOUT + 5)
        finally:
            self._pending.discard(future)

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.call_raw(name, args)
        return _result_to_envelope(name, result)


def _result_to_envelope(name: str, result: Any) -> dict[str, Any]:
    """MCP 结果 -> 工具信封。双写取任意一份，两边必须一致。"""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "ok" in structured:
        return structured

    contents = getattr(result, "content", None) or []
    for block in contents:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and "ok" in parsed:
            return parsed

    is_error = bool(getattr(result, "isError", False))
    message = "工具返回无法解析"
    if contents:
        text = getattr(contents[0], "text", None)
        if text:
            message = str(text)[:300]
    return {
        "ok": False,
        "tool": name,
        "provider": "amap",
        "latency_ms": 0,
        "data": None,
        "error": {
            "code": "UPSTREAM_ERROR" if is_error else "INVALID_ARGUMENT",
            "message": message,
            "retryable": False,
        },
    }


# ---------------------------------------------------------------------------
# LangChain 工具封装
# ---------------------------------------------------------------------------


def _json_type_to_python(spec: dict[str, Any]) -> Any:
    kind = (spec or {}).get("type")
    if kind == "integer":
        return int
    if kind == "number":
        return float
    if kind == "boolean":
        return bool
    if kind == "array":
        return list
    if kind == "object":
        return dict
    return str


def schema_to_model(tool: ToolInfo) -> type[BaseModel]:
    """把 MCP 的 JSON Schema 转成 pydantic 模型，供 LangChain 校验参数。"""
    schema = tool.input_schema or {}
    properties: dict[str, Any] = schema.get("properties") or {}
    required: list[str] = schema.get("required") or []

    fields: dict[str, Any] = {}
    for prop_name, spec in properties.items():
        py_type = _json_type_to_python(spec)
        description = (spec or {}).get("description") or ""
        if prop_name in required:
            fields[prop_name] = (py_type, Field(..., description=description))
        else:
            fields[prop_name] = (py_type | None, Field(None, description=description))

    if not fields:
        fields["_dummy"] = (str | None, Field(None, description="无参数"))
    model_name = "".join(part.capitalize() for part in tool.name.split("_")) + "Args"
    return create_model(model_name, **fields)


def _build_lc_tools(manager: "MCPManager") -> list[Any]:
    from langchain_core.tools import BaseTool

    class _MCPTool(BaseTool):
        """把一次 MCP 调用包成 LangChain 工具。

        失败也返回结构化结果（ok=false），**不抛异常**——这是 16.2 的核心
        健壮性要求：模型自己决定换参数重试还是告诉用户查不到。
        """

        name: str
        description: str
        args_schema: type[BaseModel]
        tool_name: str
        manager: Any = None

        def _run(self, *args, **kwargs) -> str:  # pragma: no cover
            raise RuntimeError("MCP 工具只支持异步调用")

        async def _arun(self, **kwargs) -> str:
            payload = {k: v for k, v in kwargs.items() if v is not None and k != "_dummy"}
            try:
                envelope = await self.manager.invoke_raw(self.tool_name, payload)
            except ApiError as exc:
                envelope = {
                    "ok": False,
                    "tool": self.tool_name,
                    "provider": "mcp",
                    "latency_ms": 0,
                    "data": None,
                    "error": {
                        "code": "TIMEOUT" if exc.status == 504 else "UPSTREAM_ERROR",
                        "message": exc.message,
                        "retryable": exc.status in (503, 504),
                    },
                }
            except Exception as exc:  # pragma: no cover - 兜底
                envelope = {
                    "ok": False,
                    "tool": self.tool_name,
                    "provider": "mcp",
                    "latency_ms": 0,
                    "data": None,
                    "error": {
                        "code": "UPSTREAM_ERROR",
                        "message": str(exc)[:200],
                        "retryable": True,
                    },
                }
            return json.dumps(envelope, ensure_ascii=False)

    tools: list[Any] = []
    for info in manager.iter_tools():
        tools.append(
            _MCPTool(
                name=info.name,
                description=info.description or info.name,
                args_schema=schema_to_model(info),
                tool_name=info.name,
                manager=manager,
            )
        )
    return tools


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------


class MCPManager:
    def __init__(self) -> None:
        self.runners: dict[str, MCPServerRunner] = {}

    @classmethod
    async def start(cls) -> "MCPManager":
        """拉起两个子进程；失败不阻塞主服务启动（16.2 降级）。"""
        manager = cls()
        for name, args in SERVER_SPECS.items():
            manager.runners[name] = MCPServerRunner(name, args)
        await asyncio.gather(
            *(runner.start() for runner in manager.runners.values()),
            return_exceptions=True,
        )
        return manager

    async def shutdown(self) -> None:
        await asyncio.gather(
            *(runner.stop() for runner in self.runners.values()),
            return_exceptions=True,
        )

    # ------------------------------------------------------------------ 查询

    def iter_tools(self) -> list[ToolInfo]:
        out: list[ToolInfo] = []
        for runner in self.runners.values():
            if runner.status != "connected":
                continue
            out.extend(runner.tools.values())
        return sorted(out, key=lambda t: t.name)

    def find(self, name: str) -> tuple[MCPServerRunner, ToolInfo] | None:
        for runner in self.runners.values():
            if name in runner.tools:
                return runner, runner.tools[name]
        return None

    def unavailable_servers(self) -> list[str]:
        return [name for name, r in self.runners.items() if r.status != "connected"]

    def status_payload(self) -> dict[str, Any]:
        servers = []
        for name, runner in self.runners.items():
            servers.append(
                {
                    "name": name,
                    "status": runner.status,
                    "tool_count": len(runner.tools),
                }
            )
        tools = [
            {"name": t.name, "server": t.server, "description": t.description}
            for t in self.iter_tools()
        ]
        degraded = any(s["status"] != "connected" for s in servers)
        return {"servers": servers, "tools": tools, "degraded": degraded}

    # ------------------------------------------------------------------ 调用

    async def invoke_raw(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """调一个 MCP 工具，返回工具信封。找不到 -> TOOL_NOT_FOUND。"""
        found = self.find(name)
        if found is None:
            raise ApiError("TOOL_NOT_FOUND", f"工具 {name} 不存在", 404)
        runner, _info = found
        return await runner.call(name, args)

    def build_langchain_tools(self) -> list[Any]:
        return _build_lc_tools(self)
