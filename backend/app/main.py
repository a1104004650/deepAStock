"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db
from app.api.v1 import market, watchlist, stock, replay, agent, simulation, trade, system, settings as settings_api, rss
from app.tasks.scheduler import start_scheduler
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("初始化数据库...")
    await init_db()
    from app.core.agent.registry import ensure_default_agents
    from app.core.settings import refresh_settings
    from app.core.datasource.manager import DataSourceManager
    from app.db.session import SessionLocal

    async with SessionLocal() as _db:
        await refresh_settings(_db)

    async def _background_stock_names() -> None:
        try:
            async with SessionLocal() as _db:
                await ensure_default_agents(_db)
                await DataSourceManager(_db).sync_stock_names()
        except Exception as e:
            logger.warning(f"stock name sync skipped: {e}")

    import asyncio
    asyncio.create_task(_background_stock_names())
    logger.info("启动定时任务...")
    scheduler = start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="深度A股 AI 交易平台 / 看盘 → 选股 → 交易 → 复盘 → 进化",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(watchlist.router)
app.include_router(stock.router)
app.include_router(replay.router)
app.include_router(agent.router)
app.include_router(simulation.router)
app.include_router(trade.router)
app.include_router(system.router)
app.include_router(settings_api.router)
app.include_router(rss.router)


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)