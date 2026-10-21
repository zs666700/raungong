"""engine / session / 建表 + SQLite 三个必做设置（BACKEND.md 6.6）。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

settings.ensure_dirs()


def _sql_echo_enabled() -> bool:
    """dev 下默认开 SQL 回显（BACKEND.md 第 5 章）。

    `TPA_SQL_ECHO=0` 是给脚本用的开关，**不属于**那 19 项配置——它只是让
    `init_db.py` / `smoke.py` 的输出保持干净（echo 是 Engine 自己直接写日志的，
    改了 logger level 也压不住，只能在建 engine 时就关掉）。
    """
    if not settings.is_dev:
        return False
    return os.environ.get("TPA_SQL_ECHO", "1").strip().lower() not in {"0", "false", "no"}


engine = create_async_engine(
    settings.database_url,
    echo=_sql_echo_enabled(),
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """SQLite 三个必须做的设置，第三个（busy_timeout）在文档里也列了。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode = WAL")   # 读写不互斥
        cursor.execute("PRAGMA foreign_keys = ON")    # 级联删除生效
        cursor.execute("PRAGMA busy_timeout = 5000")  # 写冲突等 5 秒
    finally:
        cursor.close()


async def init_db() -> None:
    """建表（幂等，Demo 不用 Alembic）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_root() -> tuple[str | None, bool]:
    """种子 root。**已存在时不覆盖密码**（18.1）。

    放在 db.py 而不是单独模块：lifespan 与 scripts/init_db.py 都要用，
    这里离建表最近，也避免多一个只装一个函数的文件。

    返回 (username, created)。
    """
    from sqlalchemy import select

    from .config import settings
    from .models import User, utcnow
    from .security import hash_password

    async with SessionLocal() as session:
        existing = (
            await session.execute(
                select(User).where(User.username == settings.root_username)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.username, False

        root = User(
            username=settings.root_username,
            password_hash=hash_password(settings.root_password),
            role="root",
            status="active",
            profile={},
            created_at=utcnow(),
        )
        session.add(root)
        await session.commit()
        return root.username, True


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖用。"""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
