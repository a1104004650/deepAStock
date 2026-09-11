"""个股详情服务"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.datasource.manager import DataSourceManager
from app.core.market.kline_service import KlineService
from app.models.stock import Stock, FinancialQuarterly, Shareholder, SentimentDaily
from app.utils.logger import logger


class StockService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)
        self.kline_svc = KlineService(db)

    async def get_basic(self, symbol: str) -> dict:
        # 尝试DB缓存
        stock = (await self.db.execute(
            select(Stock).where(Stock.symbol == symbol)
        )).scalars().first()
        if stock:
            base = {
                "symbol": stock.symbol, "name": stock.name, "market": stock.market,
                "industry": stock.industry, "list_date": stock.list_date.isoformat() if stock.list_date else None,
            }
        else:
            info = await self.dsm.get_stock_basic(symbol)
            base = {**info,
                    "name": info.get("name", symbol),
                    "industry": info.get("industry", "未分类")}
        if not base.get("industry") or base.get("industry") == "未分类":
            sec = await self.dsm.get_stock_sector(symbol)
            if sec.get("industry"):
                base["industry"] = sec["industry"]
        # 实时
        rt = await self.dsm.get_realtime([symbol])
        data = rt.get(symbol, {})
        return {**base, "realtime": data}

    async def get_kline(self, symbol: str, period: str = "day") -> dict:
        return await self.kline_svc.get_klines(symbol, period)

    async def get_financial(self, symbol: str, limit: int = 8) -> list[dict]:
        cached = (await self.db.execute(
            select(FinancialQuarterly).where(FinancialQuarterly.symbol == symbol)
            .order_by(FinancialQuarterly.report_date.desc()).limit(limit)
        )).scalars().all()
        if cached:
            return [{
                "report_date": c.report_date.isoformat(), "revenue": c.revenue,
                "revenue_yoy": c.revenue_yoy, "net_profit": c.net_profit,
                "net_profit_yoy": c.net_profit_yoy, "gross_margin": c.gross_margin,
                "roe": c.roe, "debt_ratio": c.debt_ratio, "eps": c.eps, "bps": c.bps,
            } for c in cached]

        rows = await self.dsm.get_financial(symbol)
        try:
            for r in rows:
                if "report_date" in r:
                    self.db.add(FinancialQuarterly(symbol=symbol, report_date=r.get("report_date"),
                                                   revenue=r.get("revenue"), revenue_yoy=r.get("revenue_yoy"),
                                                   net_profit=r.get("net_profit"), net_profit_yoy=r.get("net_profit_yoy"),
                                                   gross_margin=r.get("gross_margin"), roe=r.get("roe"),
                                                   debt_ratio=r.get("debt_ratio"), eps=r.get("eps"), bps=r.get("bps")))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
        return rows

    async def get_financial_overview(self, symbol: str) -> dict:
        """财务估值概览：腾讯实时估值字段；季度报表(东财)可达时补充财务指标"""
        overview = await self.dsm.get_financial_overview(symbol)
        try:
            rows = await self.dsm.get_financial(symbol, limit=1)
            if rows:
                overview["latest_quarter"] = rows[0]
        except Exception:
            pass
        return overview

    async def get_industry_ranking(self, symbol: str) -> dict:
        """行业对比/排名：同行按净利增速/ROE 排名与中位数"""
        return await self.dsm.get_industry_ranking(symbol)

    async def get_industry_chain(self, symbol: str) -> dict:
        """产业链：行业板块 + 板块市值TOP成分 + 所属概念板块（涨幅/主力净额/领涨）"""
        return await self.dsm.get_industry_chain(symbol)

    async def get_money_flow(self, symbol: str) -> list[dict]:
        """个股每日主力净流入（新浪真实接口按交易日聚合，新→旧）"""
        return await self.dsm.get_stock_money_flow(symbol, 20)

    async def get_money_flow_summary(self, symbol: str) -> dict:
        return await self.dsm.get_stock_flow_summary(symbol)

    async def get_stock_news(self, symbol: str) -> list[dict]:
        """个股相关新闻（名称/行业/概念 关键词匹配，利好/利空启发式标注）"""
        basic = await self.get_basic(symbol)
        sector = await self.get_sector(symbol)
        return await self.dsm.get_stock_related_news(
            symbol, basic.get("name", symbol),
            sector.get("industry") or "", sector.get("concepts") or [])

    async def get_shareholders(self, symbol: str) -> list[dict]:
        rows = (await self.db.execute(
            select(Shareholder).where(Shareholder.symbol == symbol).order_by(Shareholder.report_date.desc()).limit(20)
        )).scalars().all()
        return [{"holder_name": r.holder_name, "hold_count": r.hold_count,
                 "hold_ratio": r.hold_ratio, "change_count": r.change_count,
                 "report_date": r.report_date.isoformat()} for r in rows]

    async def get_sentiment(self, symbol: str) -> dict:
        return {"symbol": symbol, "news_count": 0, "positive_score": 0.0,
                "negative_score": 0.0, "attention_rank": None, "forum_activity": 0}

    async def get_sector(self, symbol: str) -> dict:
        info = await self.dsm.get_stock_sector(symbol)
        changes = await self.dsm.get_sector_changes(info.get("industry"), info.get("concepts") or [])
        return {"symbol": symbol,
                "industry": info.get("industry"),
                "concepts": info.get("concepts") or [],
                "changes": changes}

    async def get_technic_forms(self, symbol: str) -> list[dict]:
        kline = await self.get_kline(symbol, "day")
        data = kline.get("data", [])
        if len(data) < 60:
            return []
        closes = [float(k["close"]) for k in data]
        from app.utils.indicators import sma, macd, rsi
        ma5 = sma(closes, 5); ma20 = sma(closes, 20); ma60 = sma(closes, 60)
        dif, dea, hist = macd(closes)
        forms = []
        c = closes[-1]
        m5, m20, m60 = ma5[-1], ma20[-1], ma60[-1]

        if m5 and m20 and m60:
            if m5 >= m20 >= m60:
                forms.append({"name": "均线多头排列", "level": "bullish", "desc": "5/20/60日均线多头排列，趋势向上"})
            elif m5 <= m20 <= m60:
                forms.append({"name": "均线空头排列", "level": "bearish", "desc": "5/20/60日均线空头排列，趋势向下"})
        if m5 and m20:
            if m5 > m20 and ma5[-2] <= ma20[-2]:
                forms.append({"name": "5日线上穿20日线", "level": "bullish", "desc": "近期形成金叉，短线转强"})
            elif m5 < m20 and ma5[-2] >= ma20[-2]:
                forms.append({"name": "5日线下穿20日线", "level": "bearish", "desc": "近期形成死叉，短线走弱"})
        if dif[-1] is not None and dea[-1] is not None:
            if dif[-1] > dea[-1]:
                forms.append({"name": "MACD金叉状态", "level": "bullish", "desc": "DIF位于DEA上方，动能偏多"})
            else:
                forms.append({"name": "MACD死叉状态", "level": "bearish", "desc": "DIF位于DEA下方，动能偏空"})
        r = rsi(closes, 14)[-1]
        if r is not None:
            if r > 80:
                forms.append({"name": "RSI超买", "level": "overbought", "desc": f"RSI={r:.1f}，短期需防回调"})
            elif r < 20:
                forms.append({"name": "RSI超卖", "level": "oversold", "desc": f"RSI={r:.1f}，存在反弹机会"})
        # 近期涨跌
        if len(closes) >= 5:
            chg5 = (c - closes[-6]) / closes[-6] * 100
            forms.append({"name": "5日涨跌", "level": "neutral", "desc": f"{chg5:+.2f}%"})
        return forms