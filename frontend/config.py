"""前端运行配置（FRONTEND.md 第 2 章）。

只读环境变量，不 import 后端任何模块——这是硬约束。
"""

from __future__ import annotations

import os

APP_TITLE = "出行计划助手"

BACKEND_BASE_URL = os.getenv("TPA_BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_PORT = int(os.getenv("TPA_FRONTEND_PORT", "8080"))
FRONTEND_HOST = os.getenv("TPA_FRONTEND_HOST", "0.0.0.0")

API_PREFIX = "/api/v1"

# http(s) -> ws(s)，再拼后端固定端点（BACKEND.md 11.1）
WS_CHAT_URL = (
    BACKEND_BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
    + API_PREFIX
    + "/ws/chat"
)

# 没有后端时用 TPA_MOCK=1 起一套写死数据，专调行程卡片样式（FRONTEND.md 12.2）
MOCK = os.getenv("TPA_MOCK", "0").strip().lower() in {"1", "true", "yes", "on"}

ENV = os.getenv("TPA_ENV", "prod").strip().lower()
# 开发态热重载；默认关闭，避免 `python -m frontend.main` 时子进程反复重启
RELOAD = os.getenv("TPA_FRONTEND_RELOAD", "1" if ENV == "dev" else "0").strip() in {
    "1",
    "true",
    "yes",
    "on",
}

# ui.run(storage_secret=...) 必填；生产部署请用环境变量覆盖成随机串
STORAGE_SECRET = os.getenv(
    "TPA_FRONTEND_STORAGE_SECRET", "tpa-frontend-demo-storage-secret-please-change"
)

# 请求超时 90s：非流式发消息最长 60s + 余量（FRONTEND.md 5.2）
HTTP_TIMEOUT = 90.0
