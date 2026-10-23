"""前端入口（FRONTEND.md 第 3 章、第 12 章）。

启动：`python -m frontend.main`
"""

from __future__ import annotations

import logging
from pathlib import Path

from nicegui import ui

from . import config
from .pages import chat, knowledge, login, users  # noqa: F401  注册 @ui.page
from .state import current_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

BASE_DIR = Path(__file__).resolve().parent
FAVICON = BASE_DIR / "static" / "favicon.svg"


@ui.page("/", title="出行计划助手", response_timeout=10)
def index_page() -> None:
    """已登录进对话，未登录进登录页。"""
    if current_token():
        ui.navigate.to("/chat")
    else:
        ui.navigate.to("/login")


def run() -> None:
    ui.run(
        host=config.FRONTEND_HOST,
        port=config.FRONTEND_PORT,
        title=config.APP_TITLE,
        favicon=FAVICON if FAVICON.exists() else None,
        language="zh-CN",
        storage_secret=config.STORAGE_SECRET,
        reload=config.RELOAD,
        show=False,
        reconnect_timeout=10.0,
        uvicorn_logging_level="warning",
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
