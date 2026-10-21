"""FastAPI 应用：路由挂载、lifespan（建表 / 种子 root / 启动自愈 / 拉起 MCP）、健康检查。

启动顺序严格照 BACKEND.md 18.2，第 3 步（把 pending 标 failed）很重要：
服务重启后界面不会卡在"生成中"。
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import db as db_module
from .api import admin, auth, chat, conversations, rag, tools
from .config import settings
from .errors import register_exception_handlers
from .services.conversation_service import heal_stale_messages
from .services.mcp_manager import MCPManager
from .services.rag_service import rag_service

SENSITIVE_KEYS = ("password", "token", "authorization", "secret", "key")


def setup_logging() -> None:
    """标准 logging + 简单 formatter，不引 structlog（18.3）。"""
    level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


logger = logging.getLogger("tpa.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("出行计划智能助手后端启动中（env=%s）", settings.env)

    settings.ensure_dirs()
    await db_module.init_db()                       # 1. 建表（幂等）
    username, created = await db_module.ensure_root()  # 2. 种子 root
    if created:
        logger.info("已创建 root 账号：%s", username)
    else:
        logger.info("root 账号已存在，跳过创建（不覆盖密码）")

    async with db_module.SessionLocal() as session:  # 3. 启动自愈
        healed = await heal_stale_messages(session)
        if healed:
            logger.warning("启动自愈：%s 条 pending 消息已标记 failed", healed)

    app.state.mcp = await MCPManager.start()         # 4. 拉起两个 MCP 子进程
    app.state.rag = rag_service
    degraded = app.state.mcp.unavailable_servers()
    if degraded:
        logger.warning("MCP Server 不可用：%s，Agent 能力受限", ", ".join(degraded))

    if settings.rag_enabled:
        logger.info(
            "RAG 向量化：provider=%s model=%s dim=%s base_url=%s",
            settings.rag_embedding_provider,
            settings.rag_embedding_model,
            settings.rag_embedding_dim,
            settings.rag_embedding_base_url if settings.embedding_is_api else "-",
        )
        if not settings.embedding_configured:
            logger.warning(
                "RAG 已启用但缺少 TPA_RAG_EMBEDDING_API_KEY：知识库上传会失败（503 RAG_DISABLED），"
                "对话不受影响。申请 Key 后填进 .env 并重启即可"
            )
    else:
        logger.info("RAG 已关闭（TPA_RAG_ENABLED=false）")

    logger.info("后端就绪：http://127.0.0.1:%s/api/v1", settings.port)

    try:
        yield
    finally:
        await app.state.mcp.shutdown()              # 5. 关闭子进程
        await rag_service.aclose()
        await db_module.dispose_engine()
        logger.info("后端已退出")


app = FastAPI(
    title="出行计划智能助手 API",
    version="1.0.0",
    description="对话式出行规划助手后端（Demo v1.0）",
    lifespan=lifespan,
)

# 前端 NiceGUI 跑在 :8080，浏览器直连需要 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """INFO 打请求摘要；正文只记长度，不记内容；密钥一律不打（18.3）。"""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    path = request.url.path
    query = request.url.query
    if query:
        for key in SENSITIVE_KEYS:
            if key in query:
                query = "<redacted>"
                break
    logger.info(
        "%s %s%s -> %s (%sms)",
        request.method,
        path,
        f"?{query}" if query else "",
        response.status_code,
        elapsed_ms,
    )
    return response


API_PREFIX = "/api/v1"
for module in (auth, conversations, chat, tools, rag, admin):
    app.include_router(module.router, prefix=API_PREFIX)


@app.get("/healthz", tags=["ops"])
async def healthz():
    """不查依赖，进程活着就 200。"""
    return {"status": "ok"}


def _mask_secret(value: str) -> str:
    """指纹化：只露前 6 位和后 2 位 + 长度，够定位是哪把 key，又不会泄露。"""
    value = (value or "").strip()
    if not value:
        return "(未配置)"
    if len(value) <= 10:
        return value[:2] + "*" * (len(value) - 2)
    return f"{value[:6]}…{value[-2:]}(len={len(value)})"


@app.get("/readyz", tags=["ops"])
async def readyz():
    """查 DB、MCP，并把**生效中的**配置打指纹（环境变量 > .env，最容易踩的坑）。"""
    from sqlalchemy import text

    checks: dict[str, object] = {}

    try:
        async with db_module.SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["db"] = f"error: {str(exc)[:120]}"

    manager: MCPManager | None = getattr(app.state, "mcp", None)
    if manager is None:
        checks["mcp"] = {"status": "unavailable"}
        ready = False
    else:
        payload = manager.status_payload()
        checks["mcp"] = payload["servers"]
        ready = checks["db"] == "ok" and not payload["degraded"]

    checks["rag"] = rag_service.status()
    checks["config"] = {
        "env": settings.env,
        "amap_key": _mask_secret(settings.amap_key),
        "llm_model": settings.llm_model,
        "llm_key": _mask_secret(settings.llm_api_key),
        "sql_echo": os.environ.get("TPA_SQL_ECHO", "1"),
    }
    return {"status": "ok" if ready else "degraded", "checks": checks}
