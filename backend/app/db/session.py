"""数据库会话管理"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path

from app.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> str:
    if url.startswith("sqlite"):
        db_path = url.split("///")[-1]
        p = Path(db_path)
        if p.suffix == ".db":
            p.parent.mkdir(parents=True, exist_ok=True)
    return url


engine = create_async_engine(_ensure_sqlite_dir(settings.DATABASE_URL), echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db():
    # 导入模型以注册
    from app.models import (  # noqa: F401
        user,
        watchlist,
        market,
        agent,
        simulation,
        trade,
        replay,
        system,
        rss,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：为既有库补齐新增列
        try:
            await conn.execute(text("ALTER TABLE agent_configs ADD COLUMN provider VARCHAR(20)"))
        except Exception:
            pass
