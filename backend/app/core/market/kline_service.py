"""K线数据服务"""
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.datasource.manager import DataSourceManager
from app.utils.indicators import compute_indicators, detect_chan_signals
from app.core.market.intraday_analyzer import analyze_intraday


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
        """分时主力行为分析（含 VWAP/量比/信号/摘要）"""
        rows = self.dsm.primary.get_intraday(symbol)
        return analyze_intraday(rows, pre_close)