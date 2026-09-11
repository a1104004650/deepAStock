"""个股详情接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.market.stock_service import StockService
from app.core.czsc_engine.analyzer import CZSCAnalyzer
from app.core.datasource.manager import DataSourceManager

router = APIRouter(prefix="/api/v1/stocks", tags=["个股详情"])


@router.get("/search")
async def search(keyword: str, db: AsyncSession = Depends(get_db)):
    dsm = DataSourceManager(db)
    local = await dsm.search_stocks_local(keyword)
    if local:
        return local
    try:
        remote = await dsm.search_stocks(keyword)
    except Exception:
        remote = []
    return remote or []


@router.get("/{symbol}/basic")
async def get_basic(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_basic(symbol)


@router.get("/{symbol}/kline")
async def get_kline(symbol: str, period: str = "day", db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_kline(symbol, period)


@router.get("/{symbol}/financial")
async def get_financial(symbol: str, limit: int = 8, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_financial(symbol, limit)


@router.get("/{symbol}/financial-overview")
async def get_financial_overview(symbol: str, db: AsyncSession = Depends(get_db)):
    """财务估值概览：市盈率/市净率/总市值/流通市值/换手率/振幅（腾讯实时真实数据 + 最新季度指标）"""
    svc = StockService(db)
    return await svc.get_financial_overview(symbol)


@router.get("/{symbol}/industry-ranking")
async def get_industry_ranking(symbol: str, db: AsyncSession = Depends(get_db)):
    """行业对比/排名：同行按净利增速/ROE 排名与行业中位数"""
    svc = StockService(db)
    return await svc.get_industry_ranking(symbol)


@router.get("/{symbol}/industry-chain")
async def get_industry_chain(symbol: str, db: AsyncSession = Depends(get_db)):
    """产业链：行业板块 + 板块市值TOP成分 + 所属概念板块（涨幅/主力净额/领涨）"""
    svc = StockService(db)
    return await svc.get_industry_chain(symbol)


@router.get("/{symbol}/money-flow")
async def get_money_flow(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_money_flow(symbol)


@router.get("/{symbol}/money-flow-summary")
async def get_money_flow_summary(symbol: str, db: AsyncSession = Depends(get_db)):
    """多日资金流入摘要：1/5/20日主力净流入（亿元）与趋势"""
    svc = StockService(db)
    return await svc.get_money_flow_summary(symbol)


@router.get("/{symbol}/news")
async def get_stock_news(symbol: str, db: AsyncSession = Depends(get_db)):
    """个股相关新闻：名称/行业/概念关键词匹配，利好/利空启发式标注（真实标题）"""
    svc = StockService(db)
    return await svc.get_stock_news(symbol)


@router.get("/{symbol}/shareholders")
async def get_shareholders(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_shareholders(symbol)


@router.get("/{symbol}/sentiment")
async def get_sentiment(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_sentiment(symbol)


@router.get("/{symbol}/forms")
async def get_forms(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_technic_forms(symbol)


@router.get("/{symbol}/sector")
async def get_sector(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    return await svc.get_sector(symbol)


@router.get("/{symbol}/czsc")
async def get_czsc(symbol: str, period: str = "day", db: AsyncSession = Depends(get_db)):
    analyzer = CZSCAnalyzer(db)
    return await analyzer.analyze(symbol, period)


@router.get("/{symbol}/czsc/multi")
async def get_czsc_multi(symbol: str, db: AsyncSession = Depends(get_db)):
    analyzer = CZSCAnalyzer(db)
    return await analyzer.multi_period_analysis(symbol)


@router.get("/{symbol}/czsc/plugin")
async def get_czsc_plugin(symbol: str, plot: bool = False, db: AsyncSession = Depends(get_db)):
    """官方 czsc 插件：状态 / 单级别全量分析 / 多级别联立综合 / 可选离线HTML缠论图"""
    from app.core.czsc_plugin import plugin as czsc_plugin
    from app.core.market.kline_service import KlineService
    status = czsc_plugin.plugin_status()
    result = {"status": status, "analysis": None, "multi": None, "synthesis": None, "html": None}
    if not status.get("available"):
        return result
    analyzer = CZSCAnalyzer(db)
    try:
        result["analysis"] = await analyzer.analyze(symbol, "day")
    except Exception as e:
        result["analysis"] = {"error": str(e)}
    try:
        multi = await analyzer.multi_period_analysis(symbol)
        result["multi"] = multi.get("detail")
        result["synthesis"] = multi.get("synthesis")
    except Exception as e:
        logger.error(f"czsc plugin multi failed {symbol}: {e}")
    if plot:
        try:
            kline_svc = KlineService(db)
            days = await kline_svc.get_klines(symbol, "day")
            result["html"] = czsc_plugin.plot_html(days.get("data", []), "day", f"{symbol} 日线缠论")
        except Exception as e:
            logger.warning(f"czsc plugin plot failed {symbol}: {e}")
    return result


@router.get("/{symbol}/indicators")
async def get_indicators(symbol: str, period: str = "day", db: AsyncSession = Depends(get_db)):
    svc = StockService(db)
    data = await svc.get_kline(symbol, period)
    return data.get("indicators", {})