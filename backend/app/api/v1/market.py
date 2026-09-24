"""行情相关接口"""
import re
import urllib.request
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.market.quote_service import MarketService
from app.core.market.kline_service import KlineService
from app.core.market.macro_service import fetch_all_indicators
from app.core.market.regime_service import MarketRegimeService

router = APIRouter(prefix="/api/v1/market", tags=["行情"])


@router.get("/regime")
async def get_market_regime(db: AsyncSession = Depends(get_db)):
    return await MarketRegimeService(db).get_current()


@router.get("/regime/history")
async def get_market_regime_history(days: int = Query(20, ge=2, le=120), db: AsyncSession = Depends(get_db)):
    return await MarketRegimeService(db).get_history(days)

_GI_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_GI_SINA_H = {**_GI_UA, "Referer": "https://finance.sina.com.cn"}
_GI_OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _gi_open(url: str, headers: dict, timeout: float = 5.0) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    return _GI_OPEN.open(req, timeout=timeout).read()


def _gi_sina_codes(symbols: list[str]) -> list[str]:
    out = []
    for s in symbols:
        s = s.upper()
        if s.startswith(("SH", "SZ", "BJ")) and s[2:].isdigit():
            out.append("s_" + s[:2].lower() + s[2:])
    return out


def _gi_f(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


_GI_A_SHARE = [
    ("SH000001", "上证指数"), ("SZ399001", "深证成指"),
    ("SZ399006", "创业板指"), ("SH000688", "科创50"),
    ("SH000300", "沪深300"),
]


@router.get("/global-indices")
async def get_global_indices():
    result = []

    # ---- A-share indices via Sina ----
    try:
        codes = _gi_sina_codes([c for c, _ in _GI_A_SHARE])
        body = _gi_open("https://hq.sinajs.cn/list=" + ",".join(codes), _GI_SINA_H)
        text = body.decode("gbk", "ignore")
        for m in re.finditer(r'var hq_str_(\w+)="(.*?)";', text):
            code, fields = m.group(1), m.group(2).split(",")
            if len(fields) < 6 or not fields[0]:
                continue
            try:
                # 新浪指数协议（s_ 前缀）：名称,最新点位,涨跌额,涨跌幅%,成交量,成交额
                price = _gi_f(fields[1]); change = _gi_f(fields[2]); change_pct = _gi_f(fields[3])
                if not price:
                    continue
                raw = code[2:] if code.startswith("s_") else code
                sym = raw[:2].upper() + raw[2:]
                result.append({
                    "code": sym, "name": fields[0],
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "market": "A",
                })
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    # ---- HK / US / JP / EU indices via Tencent ----
    _TC = [
        ("hkHSI",  "HSI",  "恒生指数",  "HK"),
        ("usDJI",  "DJI",  "道琼斯",    "US"),
        ("usIXIC", "IXIC", "纳斯达克",  "US"),
        ("usINX",  "INX",  "标普500",   "US"),
        ("jxN225", "N225", "日经225",   "JP"),
        ("usDAX",  "DAX",  "德国DAX",   "EU"),
        ("usFTSE", "FTSE", "英国FTSE",  "EU"),
    ]
    try:
        tc_codes = ",".join(tc for tc, _, _, _ in _TC)
        body = _gi_open(f"https://qt.gtimg.cn/q={tc_codes}", _GI_UA, timeout=8)
        text = body.decode("gbk", "ignore")
        for tc, code, name, market in _TC:
            match = re.search(rf'v_{re.escape(tc)}="([^"]*)"', text)
            if not match:
                continue
            f = match.group(1).split("~")
            if len(f) < 5:
                continue
            try:
                price = _gi_f(f[3]); prev_close = _gi_f(f[4])
                if not price:
                    continue
                change = price - prev_close
                result.append({
                    "code": code, "name": f[1] or name,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_pct": round(change / prev_close * 100, 2) if prev_close else 0.0,
                    "market": market,
                })
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    return result


@router.get("/macro")
async def get_macro_indicators(refresh: int = 0):
    """宏观经济指标（每日抓取一次 akshare，缓存于 data/cache/macro_daily.json）"""
    try:
        payload = fetch_all_indicators(force=bool(refresh))
    except Exception as e:
        payload = {"indicators": [], "fetched_date": "", "fetched_at": "", "error": str(e)}
    return payload


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


@router.get("/market-stats")
async def get_market_stats(db: AsyncSession = Depends(get_db)):
    """市场情绪指标：涨跌停比/炸板率/连板率/赚钱效应"""
    svc = MarketService(db)
    dist = await svc.get_market_distribution()
    limit_up = await svc.get_limit_up()

    up = dist.get("up_count", 0)
    down = dist.get("down_count", 0)
    limit_up_count = dist.get("limit_up", 0)
    limit_down_count = dist.get("limit_down", 0)
    total = dist.get("total", 1)

    # 连板统计
    consecutive = [s for s in limit_up if s.get("consecutive_days", 1) > 1]
    first_board = [s for s in limit_up if s.get("first_limit", False)]

    # 涨跌停比
    limit_ratio = round(limit_up_count / limit_down_count, 2) if limit_down_count > 0 else None

    # 连板率 = 连板股 / 涨停总数
    consecutive_rate = round(len(consecutive) / max(limit_up_count, 1) * 100, 1)

    # 上涨占比
    up_ratio = round(up / max(total, 1) * 100, 1)

    return {
        "up_count": up,
        "down_count": down,
        "flat_count": dist.get("flat_count", 0),
        "total": total,
        "limit_up": limit_up_count,
        "limit_down": limit_down_count,
        "limit_ratio": limit_ratio,
        "consecutive_count": len(consecutive),
        "first_board_count": len(first_board),
        "consecutive_rate": consecutive_rate,
        "consecutive_rate_basis": "连板股/涨停总数",
        "limit_ratio_basis": "涨停家数/跌停家数",
        "data_available": bool(dist.get("total") or limit_up),
        "up_ratio": up_ratio,
        "limit_up_list": dist.get("limit_up_list", [])[:20],
        "amount": dist.get("amount", 0),
    }


@router.get("/news")
async def get_news(limit: int = 50, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_news(limit)


@router.get("/intraday")
async def get_intraday(symbol: str, date: str = None, db: AsyncSession = Depends(get_db)):
    svc = KlineService(db)
    return await svc.get_intraday(symbol, date)


@router.get("/quote-panel")
async def get_quote_panel(symbol: str, db: AsyncSession = Depends(get_db)):
    """个股盘口面板：五档挂单 + 逐笔成交明细（兼容旧接口）"""
    svc = MarketService(db)
    panel = await svc.dsm.get_quote_panel(symbol)
    return panel if isinstance(panel, dict) else {}


@router.get("/order-book")
async def get_order_book(symbol: str, db: AsyncSession = Depends(get_db)):
    """个股五档挂单（快，单次 Sina 请求）"""
    svc = MarketService(db)
    return await svc.dsm.get_order_book(symbol)


@router.get("/ticks")
async def get_ticks(symbol: str, db: AsyncSession = Depends(get_db)):
    """个股逐笔成交明细（慢，腾讯分页二分）"""
    svc = MarketService(db)
    return await svc.dsm.get_ticks(symbol)


@router.get("/intraday-analysis")
async def get_intraday_analysis(symbol: str, pre_close: float = 0, db: AsyncSession = Depends(get_db)):
    """分时主力行为分析（VWAP/量比/吸筹洗盘诱多诱空真拉升信号）"""
    svc = KlineService(db)
    return await svc.get_intraday_analysis(symbol, pre_close)


@router.get("/sectors/monitor")
async def get_sector_monitor(db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_monitor()


@router.get("/sectors/monitor/intraday")
async def get_sector_monitor_intraday(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = KlineService(db)
    return await svc.get_intraday(symbol)


@router.get("/sectors/constituents")
async def get_sector_constituents(symbol: str, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_sector_constituents(symbol)


@router.get("/hot-stocks")
async def get_hot_stocks(top: int = 15, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_hot_stocks(top)


@router.get("/screening")
async def screen_stocks(
    min_change: float = -10,
    max_change: float = 10,
    min_turnover: float = 0,
    min_heat: float = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """基于免费实时行情的短线初筛，不伪造基本面数据。"""
    svc = MarketService(db)
    rows = await svc.get_hot_stocks(max(100, min(500, limit * 3)))
    result = []
    for row in rows:
        change = float(row.get("change_pct") or 0)
        turnover = float(row.get("turnover") or 0)
        heat = float(row.get("heat") or 0)
        if change < min_change or change > max_change:
            continue
        if turnover < min_turnover or heat < min_heat:
            continue
        result.append({
            **row,
            "screen_reason": "热度/成交额/涨跌幅符合条件",
        })
    result.sort(key=lambda x: float(x.get("heat") or 0), reverse=True)
    return {
        "items": result[:max(1, min(200, limit))],
        "count": len(result),
        "source": "免费实时行情热度榜",
        "filters": {
            "min_change": min_change,
            "max_change": max_change,
            "min_turnover": min_turnover,
            "min_heat": min_heat,
        },
    }


@router.get("/price-movers")
async def get_price_movers(top: int = 8, db: AsyncSession = Depends(get_db)):
    """实时股价异动：快速拉升 / 快速下挫（腾讯涨速榜）"""
    svc = MarketService(db)
    return await svc.get_price_movers(top)


@router.get("/market-flow")
async def get_market_flow(days: int = 20, db: AsyncSession = Depends(get_db)):
    svc = MarketService(db)
    return await svc.get_market_money_flow(days)
