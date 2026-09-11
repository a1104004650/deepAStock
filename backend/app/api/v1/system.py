"""系统状态接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, engine
from app.config import settings
from app.tasks.scheduler import scheduler_jobs
from app.core.settings import source_order, get_setting

router = APIRouter(prefix="/api/v1/system", tags=["系统"])


@router.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await engine.connect()
    except Exception:
        db_ok = False
    return {"database": "ok" if db_ok else "error", "data_source": ",".join(source_order()),
            "rsshub": {"enabled": get_setting("rsshub_enabled") == "1",
                       "base": get_setting("rsshub_base")},
            "debug": settings.DEBUG, "scheduler": "apscheduler",
            "jobs": scheduler_jobs()}