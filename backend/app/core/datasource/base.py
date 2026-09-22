"""数据源抽象基类与通用类型"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional



class DataSourceBase(ABC):
    name: str = "base"

    @abstractmethod
    def get_klines(self, symbol: str, period: str = "day",
                   start: Optional[date] = None, end: Optional[date] = None) -> list[dict]:
        """获取K线数据 [{symbol, dt, open, high, low, close, volume, amount}]"""

    @abstractmethod
    def get_realtime(self, symbols: list[str]) -> dict[str, dict]:
        """获取实时行情 {symbol: {price, change, change_pct, volume, ...}}"""

    @abstractmethod
    def get_indices(self) -> list[dict]:
        """获取主要指数"""

    @abstractmethod
    def get_sector_money_flow(self) -> list[dict]:
        """获取板块资金流"""

    @abstractmethod
    def get_sector_speed(self) -> list[dict]:
        """获取板块涨速"""

    @abstractmethod
    def get_limit_up(self) -> list[dict]:
        """获取涨停股票"""

    @abstractmethod
    def get_dragon_tiger(self) -> list[dict]:
        """获取龙虎榜"""

    @abstractmethod
    def get_stock_basic(self, symbol: str) -> dict:
        """获取个股基本信息"""

    @abstractmethod
    def get_financial(self, symbol: str) -> list[dict]:
        """获取财务数据"""

    @abstractmethod
    def search_stocks(self, keyword: str) -> list[dict]:
        """搜索股票"""

    @abstractmethod
    def get_news(self, limit: int = 50) -> list[dict]:
        """获取重要新闻"""

    def get_market_distribution(self) -> dict:
        """获取全市场涨跌统计（真实源不可达时返回 0，不 mock）"""
        return {"up_count": 0, "down_count": 0, "flat_count": 0,
                "limit_up": 0, "limit_down": 0, "amount": 0.0, "total": 0}

    def get_stock_sector(self, symbol: str) -> dict:
        return {"symbol": symbol, "industry": None, "concepts": []}

    def get_stock_monitor(self) -> list[dict]:
        """东财重点监控池（风险警示名单）"""
        return []

    def get_price_anomaly(self) -> dict:
        """东财日内严重异常波动"""
        return {"date": "", "items": [], "count": []}

    def get_price_movers(self, top: int = 8) -> dict:
        """实时股价异动（快速拉升 / 快速下挫）"""
        return {"rise": [], "fall": []}

    def get_invest_calendar(self, days_ahead: int = 45) -> dict:
        """未来解禁 + 分红除权日历"""
        return {"date": "", "unlocks": [], "dividends": []}

    def get_dragon_tiger_seats(self, trade_date: str = None) -> list[dict]:
        """龙虎榜营业部席位明细（本地游资打标）"""
        return []
