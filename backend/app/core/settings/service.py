"""设置服务中心 - DB 持久化覆盖 env 默认值，内存快照 + 异步刷新"""
import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.system import Setting
from app.utils.logger import logger

# 可用数据源 token（注册到 DataSourceManager 的注册表）
SOURCE_OPTIONS = ["sina", "tencent"]

DEFAULTS = {
    "database_url": settings.DATABASE_URL,
    "primary_source": settings.PRIMARY_SOURCE or "sina",
    "backup_source_1": settings.BACKUP_SOURCE or "",
    "backup_source_2": "",
    "backup_source_3": "",
    "source_timeout": str(settings.SOURCE_TIMEOUT),
    "rsshub_base": settings.RSSHUB_BASE,
    "rsshub_enabled": "1" if settings.RSSHUB_ENABLED else "0",
    "rsshub_poll_seconds": str(settings.RSSHUB_POLL_SECONDS),
    "rsshub_item_retention_days": str(settings.RSSHUB_ITEM_RETENTION_DAYS),
}

# 内存快照：DB 中的覆盖值（key -> value）
EFFECTIVE: dict[str, str] = {}


def get_setting(key: str, default: str | None = None) -> str:
    """同步读取生效设置（DB 覆盖优先，其次 env 默认）"""
    if key in EFFECTIVE:
        return EFFECTIVE[key]
    return default if default is not None else DEFAULTS.get(key, "")


def get_setting_int(key: str, fallback: int = 0) -> int:
    try:
        return int(float(get_setting(key, str(fallback))))
    except (TypeError, ValueError):
        return fallback


async def refresh_settings(db: AsyncSession) -> None:
    """启动时/变更后从 DB 刷新快照"""
    try:
        rows = (await db.execute(select(Setting.key, Setting.value))).all()
        EFFECTIVE.clear()
        for k, v in rows:
            EFFECTIVE[k] = v or ""
    except Exception as e:
        logger.warning(f"刷新系统设置失败: {e}")


async def update_settings(db: AsyncSession, updates: dict) -> dict:
    """批量更新设置（仅接受已知 key），写入 DB 并刷新快照"""
    known = set(DEFAULTS.keys())
    for k in updates:
        if k not in known:
            raise ValueError(f"未知设置项: {k}")
    for k, v in updates.items():
        obj = (await db.execute(select(Setting).where(Setting.key == k))).scalars().first()
        if obj is None:
            obj = Setting(key=k, value="")
            db.add(obj)
        obj.value = str(v)
    await db.commit()
    await refresh_settings(db)
    return snapshot()


def snapshot() -> dict:
    """默认值 / 已覆盖 / 生效值 三份视图"""
    return {
        "defaults": dict(DEFAULTS),
        "overridden": [k for k in EFFECTIVE
                       if EFFECTIVE[k] != DEFAULTS.get(k, "")],
        "effective": {k: get_setting(k) for k in DEFAULTS},
        "source_options": SOURCE_OPTIONS,
    }


def source_order() -> list[str]:
    """按 主源+备用1/2/3 拆分 token（支持 sina+tencent 这类组合写法）"""
    toks: list[str] = []

    def _push(t: str):
        t = t.strip().lower()
        if t and t not in toks:
            toks.append(t)

    for tok in (get_setting("primary_source") or "").replace("+", ",").split(","):
        _push(tok)
    for k in ("backup_source_1", "backup_source_2", "backup_source_3"):
        for tok in (get_setting(k) or "").replace("+", ",").split(","):
            _push(tok)
    return toks or ["sina"]


async def test_database_url(url: str) -> dict:
    """测试外部数据库 URL 连通性（sqlite/postgres 均可）"""
    import sqlalchemy
    try:
        eng = sqlalchemy.create_engine(url.replace("+aiosqlite", "").replace("+asyncpg", ""), pool_pre_ping=True)
        with eng.connect():
            pass
        eng.dispose()
        return {"ok": True, "error": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}