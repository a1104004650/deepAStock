"""K线数据服务"""
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.datasource.manager import DataSourceManager
from app.utils.indicators import compute_indicators, detect_chan_signals
from app.core.market.intraday_analyzer import analyze_intraday
import time


_INTRADAY_DAILY_CACHE: dict[str, tuple[float, list[dict]]] = {}
_INTRADAY_DAILY_TTL = 300


class KlineService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    async def get_klines(self, symbol: str, period: str = "day",
                         start: date = None, end: date = None, with_indicators: bool = True) -> dict:
        """获取K线（带技术指标）"""
        data = await self.dsm.get_klines(symbol, period, start, end)
        payload = {
            "symbol": symbol,
            "period": period,
            "data": data,
            "count": len(data),
        }
        if with_indicators and len(data) >= 5:
            payload["indicators"] = compute_indicators(data)
        return payload

    async def get_intraday(self, symbol: str, date_str: str = None) -> list[dict]:
        """当日分时数据（腾讯真实数据，源不可达时返回空）"""
        return self.dsm.primary.get_intraday(symbol)

    async def get_intraday_analysis(self, symbol: str, pre_close: float = 0) -> dict:
        """分时主力行为分析（含 VWAP/量比/信号/摘要/日K位置）"""
        rows = self.dsm.primary.get_intraday(symbol)
        # 日K位置变化慢，短缓存避免自选股分时轮询重复请求60天日K。
        cache_key = symbol.upper()
        cached = _INTRADAY_DAILY_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < _INTRADAY_DAILY_TTL:
            daily_bars = cached[1]
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=60)
            daily_bars = await self.dsm.get_klines(symbol, "day", start_date, end_date)
            _INTRADAY_DAILY_CACHE[cache_key] = (time.monotonic(), daily_bars)
        return analyze_intraday(rows, pre_close, daily_bars)
