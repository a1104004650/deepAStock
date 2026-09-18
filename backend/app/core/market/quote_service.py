"""行情服务 - 指数 / 板块 / 涨停 / 龙虎榜 / 新闻"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.datasource.manager import DataSourceManager
from app.utils.logger import logger

# 四大指数映射
MAIN_INDICES = [
    {"code": "SH000001", "name": "上证指数"},
    {"code": "SZ399001", "name": "深证成指"},
    {"code": "SZ399006", "name": "创业板指"},
    {"code": "SH000688", "name": "科创50"},
]


class MarketService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    async def get_indices(self, markets: str = "A,HK,US") -> list[dict]:
        return await self.dsm.get_indices()

    async def get_market_overview(self) -> dict:
        return {
            "indices": await self.dsm.get_indices(),
            "sectors_flow": await self.dsm.get_sector_money_flow(),
            "sectors_flow_top": await self.dsm.get_sector_flow_top(),
            "sectors_speed": await self.dsm.get_sector_speed(),
            "etf_flow": await self.dsm.get_etf_flow(),
            "limit_up": await self.dsm.get_limit_up(),
            "news": await self.dsm.get_news(30),
        }

    async def get_sector_money_flow(self, limit: float = None) -> list[dict]:
        return await self.dsm.get_sector_money_flow()

    async def get_sector_flow_top(self) -> dict:
        return await self.dsm.get_sector_flow_top()

    async def get_etf_flow(self) -> dict:
        return await self.dsm.get_etf_flow()

    async def get_sector_speed(self, limit: int = 10) -> list[dict]:
        rows = await self.dsm.get_sector_speed()
        return (rows or [])[:limit]

    async def get_limit_up(self) -> list[dict]:
        return await self.dsm.get_limit_up()

    async def get_limit_up_ladder(self) -> dict:
        lst = await self.dsm.get_limit_up()
        ladder = {}
        for item in lst:
            days = int(item.get("consecutive_days", 1))
            ladder.setdefault(days, []).append(item)
        first_board = [i for i in lst if i.get("first_limit") or int(i.get("consecutive_days", 1)) <= 1]
        return {
            "ladder": {str(k): v for k, v in sorted(ladder.items(), reverse=True)},
            "first_board": first_board[:20],
            "total": len(lst),
        }

    async def get_dragon_tiger(self) -> list[dict]:
        rows = await self.dsm.get_dragon_tiger()
        return rows

    async def get_dragon_tiger_seats(self, trade_date: str = None) -> list[dict]:
        rows = await self.dsm.get_dragon_tiger_seats(trade_date)
        return rows

    async def get_stock_monitor(self) -> list[dict]:
        return await self.dsm.get_stock_monitor()

    async def get_price_anomaly(self) -> dict:
        return await self.dsm.get_price_anomaly()

    async def get_invest_calendar(self, days: int = 45) -> dict:
        return await self.dsm.get_invest_calendar(days)

    async def get_market_distribution(self) -> dict:
        # 全市场涨跌家数/涨停跌停/成交额：腾讯全部A股真实统计（源不可达时返回全 0，不 mock）
        return await self.dsm.get_market_distribution()

    async def get_news(self, limit: int = 50) -> list[dict]:
        return await self.dsm.get_news(limit)

    async def get_sector_monitor(self) -> list[dict]:
        return await self.dsm.get_sector_monitor()

    async def get_sector_constituents(self, sector_symbol: str) -> list[dict]:
        try:
            return await self.dsm.get_sector_constituents(sector_symbol)
        except Exception as e:
            logger.warning(f"get_sector_constituents failed: {e}")
            return []

    async def get_hot_stocks(self, top: int = 10) -> list[dict]:
        try:
            return await self.dsm.get_hot_stocks(top)
        except Exception as e:
            logger.warning(f"get_hot_stocks failed: {e}")
            return []

    async def get_price_movers(self) -> dict:
        return await self.dsm.get_price_movers()

    async def get_market_money_flow(self, days: int = 20) -> dict:
        return await self.dsm.get_market_money_flow(days)