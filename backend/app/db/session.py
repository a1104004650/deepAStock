"""数据库会话管理"""
from sqlalchemy import text, event
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


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_busy_timeout(dbapi_conn, _record):
    if dbapi_conn.__class__.__module__.startswith("sqlite3"):
        try:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA busy_timeout = 30000")
            cur.close()
        except Exception:
            pass

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
        strategy,
        laboratory,
    )
    async with engine.begin() as conn:
        # 旧版 RSS 订阅表（旧字段结构 + filter_st 等旧列）整体重建，避免迁移残留
        try:
            r = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='rss_sources'"))
            if r.scalar():
                cols = [row[1] for row in await conn.execute(text("PRAGMA table_info(rss_sources)"))]
                if not {"name", "rss_type", "url", "remark", "tags", "interval_min", "enabled", "net_status"}.issubset(set(cols)):
                    await conn.execute(text("DROP TABLE IF EXISTS rss_sources"))
                    await conn.execute(text("DROP TABLE IF EXISTS rss_items"))
        except Exception:
            pass
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：为既有库补齐新增列
        try:
            await conn.execute(text("ALTER TABLE agent_configs ADD COLUMN provider VARCHAR(20)"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE rss_sources ADD COLUMN base VARCHAR(300) DEFAULT ''"))
        except Exception:
            pass
        # 实验室新字段迁移
        try:
            await conn.execute(text("ALTER TABLE lab_competitions ADD COLUMN risk_rules TEXT"))
        except Exception:
            pass
        try:
            await conn.execute(text("ALTER TABLE lab_participants ADD COLUMN personality VARCHAR(100)"))
        except Exception:
            pass

    # 空库写入默认订阅源（部署即自带）
    async with SessionLocal() as _db:
        from app.core.rsshub.service import seed_default_sources
        await seed_default_sources(_db)
