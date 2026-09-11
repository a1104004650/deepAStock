"""行情相关接口"""
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.market.quote_service import MarketService
from app.core.market.kline_service import KlineService

router = APIRouter(prefix="/api/v1/market", tags=["行情"])


@router.get("/indices")
async def get_indices(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_indices()


@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_market_overview()


@router.get("/kline")
async def get_kline(symbol: str, period: str = "day",
                    start: date = None, end: date = None,
                    db: AsyncSession = Depends(get_db)):
    svc = KlineService(db)
    return await svc.get_klines(symbol, period, start, end)


@router.get("/realtime")
async def get_realtime(symbols: str, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    symbol_list = [s for s in symbols.split(",") if s]
    return await svc.dsm.get_realtime(symbol_list)


@router.get("/sectors/money-flow")
async def get_sector_flow(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_money_flow()


@router.get("/sectors/flow-top")
async def get_sector_flow_top(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_flow_top()


@router.get("/etf/flow")
async def get_etf_flow(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_etf_flow()


@router.get("/sectors/speed")
async def get_sector_speed(limit: int = 10, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_speed(limit)


@router.get("/limit-up/ladder")
async def get_limit_ladder(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_limit_up_ladder()


@router.get("/dragon-tiger")
async def get_dragon_tiger(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_dragon_tiger()


@router.get("/dragon-tiger/seats")
async def get_dragon_tiger_seats(trade_date: str = None, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_dragon_tiger_seats(trade_date)


@router.get("/regulatory")
async def get_regulatory(db: AsyncSession = Depends(get_db)):
    """监管异动：重点监控池 + 日内严重异常波动"""
    svc = MarketService(db)
    return {
        "monitor": await svc.get_stock_monitor(),
        "anomaly": await svc.get_price_anomaly(),
    }


@router.get("/invest-calendar")
async def get_invest_calendar(days: int = 45, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_invest_calendar(days)


@router.get("/distribution")
async def get_distribution(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_market_distribution()


@router.get("/news")
async def get_news(limit: int = 50, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_news(limit)


@router.get("/intraday")
async def get_intraday(symbol: str, date: str = None, db: AsyncSession = Depends(get_db)):
    svc = KlineService(db)
    return await svc.get_intraday(symbol, date)


@router.get("/sectors/monitor")
async def get_sector_monitor(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_monitor()


@router.get("/sectors/monitor/intraday")
async def get_sector_monitor_intraday(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = KlineService(db)
    return await svc.get_intraday(symbol)


@router.get("/hot-stocks")
async def get_hot_stocks(top: int = 10, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_hot_stocks(top)


@router.get("/market-flow")
async def get_market_flow(days: int = 20, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_market_money_flow(days)