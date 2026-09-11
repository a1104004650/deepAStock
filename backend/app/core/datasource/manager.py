"""数据源管理器 - 主备切换 + 数据库缓存"""
import asyncio
from datetime import date, timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.datasource.base import DataSourceBase
from app.core.datasource.sina_source import SinaSource, to_standard_symbol
from app.models.market import Kline, SectorMoneyFlow, DragonTiger, LimitUp
from app.models.cache import CacheMetadata
from app.utils.logger import logger

PERIOD_STEP = {"day": 1, "week": 7, "month": 30, "1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


class DataSourceManager:
    """数据源管理器 - 缓存优先 + 主备切换"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.primary: DataSourceBase = SinaSource()
        self.backup: DataSourceBase = SinaSource()  # 同一真实源重试，无 mock 兜底
        self.timeout = 15.0

    async def _call(self, method: str, *args, **kwargs):
        """带超时的数据源调用，失败自动降级"""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(getattr(self.primary, method), *args, **kwargs),
                timeout=self.timeout,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"primary {method} failed/timeout: {e}")
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(getattr(self.backup, method), *args, **kwargs),
                    timeout=self.timeout,
                )
            except (asyncio.TimeoutError, Exception) as e2:
                logger.error(f"backup {method} also failed: {e2}")
                return []

    async def get_klines(self, symbol: str, period: str = "day",
                         start: date = None, end: date = None) -> list[dict]:
        """带缓存的多源K线获取。历史数据不重复请求，昨日之前的数据不可变"""
        symbol = to_standard_symbol(symbol)
        if period in ("m5", "m15", "m30", "m60"):
            # 分钟K线实时性强，不走数据库缓存
            return await self._call("get_klines", symbol, period, None, None) or []
        cached = await self._load_klines_db(symbol, period)
        if cached:
            last_date = cached[-1]["dt"]
            today = date.today()
            # 若缓存已经包含今天，直接返回
            if last_date >= today.isoformat() if isinstance(last_date, str) else last_date >= today:
                return cached

        # 请求增量
        start_date = date.today() - timedelta(days=400) if not start else start
        new_data = await self._call("get_klines", symbol, period, start_date, end or date.today())

        if new_data:
            await self._save_klines_db(symbol, period, new_data)

        # 合并
        merged = self._merge(cached, new_data)
        return merged or new_data

    async def get_realtime(self, symbols: list[str]) -> dict[str, dict]:
        ans = await self._call("get_realtime", list(dict.fromkeys(symbols)))
        return ans if isinstance(ans, dict) else dict(ans)

    async def get_indices(self) -> list[dict]:
        ans = await self._call("get_indices")
        return ans or []

    async def get_sector_money_flow(self) -> list[dict]:
        ans = await self._call("get_sector_money_flow")
        return ans or []

    async def get_sector_speed(self) -> list[dict]:
        ans = await self._call("get_sector_speed")
        return ans or []

    async def get_limit_up(self) -> list[dict]:
        ans = await self._call("get_limit_up")
        return ans or []

    async def get_dragon_tiger(self) -> list[dict]:
        ans = await self._call("get_dragon_tiger")
        return ans or []

    async def get_stock_basic(self, symbol: str) -> dict:
        ans = await self._call("get_stock_basic", symbol)
        return ans if isinstance(ans, dict) else {}

    async def get_financial(self, symbol: str) -> list[dict]:
        ans = await self._call("get_financial", symbol)
        return ans or []

    async def search_stocks(self, keyword: str) -> list[dict]:
        ans = await self._call("search_stocks", keyword)
        return ans or []

    async def get_news(self, limit: int = 50) -> list[dict]:
        ans = await self._call("get_news", limit)
        return ans or []

    async def get_market_distribution(self) -> dict:
        ans = await self._call("get_market_distribution")
        return ans if isinstance(ans, dict) else {"up_count": 0, "down_count": 0, "flat_count": 0}

    async def get_stock_sector(self, symbol: str) -> dict:
        ans = await self._call("get_stock_sector", symbol)
        return ans if isinstance(ans, dict) else {"symbol": symbol, "industry": None, "concepts": []}

    async def get_sector_flow_top(self) -> dict:
        ans = await self._call("get_sector_flow_top")
        return ans if isinstance(ans, dict) else {"industries": {"in": [], "out": []}, "concepts": {"in": [], "out": []}}

    async def get_etf_flow(self) -> dict:
        ans = await self._call("get_etf_flow")
        return ans if isinstance(ans, dict) else {"in_top": [], "out_top": [], "all": []}

    async def get_market_money_flow(self, days: int = 20) -> dict:
        ans = await self._call("get_market_money_flow", days)
        return ans if isinstance(ans, dict) else {"date": "", "intraday": [], "daily": []}

    async def get_stock_money_flow(self, symbol: str, limit: int = 20) -> list[dict]:
        ans = await self._call("get_stock_money_flow", symbol, limit)
        return ans or []

    async def get_stock_flow_summary(self, symbol: str) -> dict:
        ans = await self._call("get_stock_flow_summary", symbol)
        return ans if isinstance(ans, dict) else {"net_1d": 0, "net_5d": 0, "net_20d": 0, "trend": "unknown"}

    async def get_financial_overview(self, symbol: str) -> dict:
        ans = await self._call("get_financial_overview", symbol)
        return ans if isinstance(ans, dict) else {"available": False}

    async def get_stock_related_news(self, symbol: str, name: str, industry: str = "", concepts: list = None) -> list[dict]:
        ans = await self._call("get_stock_related_news", symbol, name, industry, concepts or [])
        return ans or []

    async def get_sector_changes(self, industry: str = "", concepts: list = None) -> dict:
        ans = await self._call("get_sector_changes", industry, concepts or [])
        return ans if isinstance(ans, dict) else {"industry": None, "concepts": []}

    async def get_sector_monitor(self) -> list[dict]:
        ans = await self._call("get_sector_monitor")
        return ans or []

    async def get_hot_stocks(self, top: int = 5) -> list[dict]:
        ans = await self._call("get_hot_stocks", top)
        return [r for r in ans if isinstance(r, dict)] if isinstance(ans, list) else []

    async def get_industry_chain(self, symbol: str) -> dict:
        ans = await self._call("get_industry_chain", symbol)
        return ans if isinstance(ans, dict) else {"industry": None, "peers": [], "concepts": []}

    async def get_industry_ranking(self, symbol: str) -> dict:
        ans = await self._call("get_industry_ranking", symbol)
        return ans if isinstance(ans, dict) else {"available": False}

    # ---------- A股全量名称本地库（每月刷新，搜索走本地） ----------
    async def sync_stock_names(self, force: bool = False) -> int:
        from datetime import datetime
        from app.models.market import StockName
        from sqlalchemy import func, update
        try:
            stale = True
            newest = await self.db.execute(
                select(func.max(StockName.updated_at)))
            newest = newest.scalar()
            if newest and not force:
                stale = (datetime.utcnow() - newest).days >= 30
            if not stale:
                return 0
            rows = await self._call("_all_stock_names", force)
            if not rows:
                return 0
            count = 0
            for r in rows:
                sym = (r.get("symbol") or "").upper()
                name = (r.get("name") or "").strip()
                if not sym or not name:
                    continue
                await self.db.execute(update(StockName).where(StockName.symbol == sym)
                                      .values(name=name, updated_at=datetime.utcnow()))
                if not (await self.db.execute(select(StockName.symbol).where(StockName.symbol == sym))).first():
                    self.db.add(StockName(symbol=sym, name=name, updated_at=datetime.utcnow()))
                count += 1
            await self.db.commit()
            logger.info(f"A股名称库同步 {count} 条")
            return count
        except Exception as e:
            logger.error(f"sync stock names failed: {e}")
            await self.db.rollback()
            return 0

    async def search_stocks_local(self, keyword: str, limit: int = 30) -> list[dict]:
        from app.models.market import StockName
        kw = (keyword or "").strip()
        if not kw:
            return []
        try:
            kw_pat = f"%{kw}%"
            rows = (await self.db.execute(
                select(StockName).where(StockName.symbol.like(kw_pat) | StockName.name.like(kw_pat))
                .order_by(StockName.symbol).limit(limit))).scalars().all()
            return [{"symbol": r.symbol, "name": r.name, "code": r.symbol[-6:],
                     "source": "local"} for r in rows]
        except Exception as e:
            logger.warning(f"local search failed {kw}: {e}")
            return []

    # ---------- 数据库缓存操作 ----------
    async def _load_klines_db(self, symbol: str, period: str) -> list[dict]:
        try:
            rows = (await self.db.execute(
                select(Kline).where(Kline.symbol == symbol, Kline.period == period).order_by(Kline.timestamp)
            )).scalars().all()
            return [{
                "symbol": r.symbol, "dt": r.timestamp.strftime("%Y-%m-%d"), "period": r.period,
                "open": float(r.open), "high": float(r.high), "low": float(r.low),
                "close": float(r.close), "volume": int(r.volume or 0), "amount": float(r.amount or 0),
            } for r in rows]
        except Exception as e:
            logger.warning(f"load kline cache failed {symbol}: {e}")
            return []

    async def _save_klines_db(self, symbol: str, period: str, data: list[dict]) -> None:
        try:
            existing_dates = set()
            rows = (await self.db.execute(
                select(Kline.timestamp).where(Kline.symbol == symbol, Kline.period == period)
            )).scalars().all()
            for ts in rows:
                existing_dates.add(ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts))

            new_rows = []
            for d in data:
                day = d["dt"] if isinstance(d["dt"], str) else d["dt"].strftime("%Y-%m-%d")
                if day in existing_dates:
                    continue
                from datetime import datetime
                new_rows.append(Kline(
                    symbol=symbol, period=period,
                    timestamp=datetime.strptime(day, "%Y-%m-%d"),
                    open=d["open"], high=d["high"], low=d["low"], close=d["close"],
                    volume=d["volume"], amount=d["amount"],
                ))
                existing_dates.add(day)
            if new_rows:
                self.db.add_all(new_rows)
                await self.db.commit()
        except Exception as e:
            logger.warning(f"save kline cache failed {symbol}: {e}")
            await self.db.rollback()

    @staticmethod
    def _merge(cached: list[dict], new: list[dict]) -> list[dict]:
        if not cached:
            return new
        if not new:
            return cached
        seen = {d["dt"] for d in cached}
        combined = list(cached)
        for d in new:
            if d["dt"] not in seen:
                combined.append(d)
        combined.sort(key=lambda x: x["dt"])
        return combined
