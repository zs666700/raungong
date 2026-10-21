"""建表 + 创建 root（幂等）。BACKEND.md 18.1。

    python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 必须在 import backend.db 之前设，否则 engine 已经带着 echo 建好了
os.environ.setdefault("TPA_SQL_ECHO", "0")

from backend.config import settings  # noqa: E402
from backend.db import dispose_engine, ensure_root, init_db  # noqa: E402


async def main() -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    print("=" * 60)
    print("出行计划智能助手 —— 初始化数据库")
    print("=" * 60)
    print(f"数据目录 : {settings.data_path}")
    print(f"数据库   : {settings.db_path}")
    print(f"环境     : {settings.env}")
    print()

    settings.ensure_dirs()
    await init_db()
    print("[1/2] 建表完成（4 张表，幂等）")

    username, created = await ensure_root()
    if created:
        print(f"[2/2] 已创建 root 账号：{username}（密码见 .env 的 TPA_ROOT_PASSWORD）")
    else:
        print(f"[2/2] root 已存在，跳过（不覆盖密码）：{username}")

    await dispose_engine()
    print()
    print("下一步：uvicorn backend.main:app --reload --port 8000")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"启动失败：{exc}")
        raise SystemExit(1) from exc
