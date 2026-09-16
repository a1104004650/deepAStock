"""Hithink (THS) financial data source - fallback source #4.

Only used when sina / tencent / akshare all return empty.
Reads HITHINK_API_KEY from environment variable; NEVER hardcodes or logs the key.
Base URL: https://fuyao.aicubes.cn  (official HiThink-Tech/Financial-API)
Endpoints confirmed in official docs:
  GET /api/a-share/prices/snapshot    (realtime snapshot, thscodes comma-separated)
  GET /api/a-share/prices/historical  (daily kline, thscode + start/end ms, adjust=forward)
Not yet confirmed (dragon-tiger / limit-up pool paths): return empty, implemented later.
"""
import os
import json
import time
import ssl
import logging
import urllib.request
import urllib.parse

from .base import DataSourceBase

logger = logging.getLogger(__name__)

BASE = "https://fuyao.aicubes.cn"


def _api_key() -> str:
    return (os.environ.get("HITHINK_API_KEY") or "").strip()


def _envelope(path: str, params: dict, timeout: float = 8.0):
    """Call hithink REST and return the ApiResponse envelope dict, or None on any failure."""
    key = _api_key()
    if not key:
        logger.warning("hithink: HITHINK_API_KEY not set, skip fallback call")
        return None
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "X-api-key": key,
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read().decode("utf-8", "replace")
        env = json.loads(body)
        return env if isinstance(env, dict) else None
    except Exception as e:
        logger.warning("hithink %s failed: %s", path, e)
        return None


class HithinkSource(DataSourceBase):
    name = "hithink"

    def get_klines(self, symbol: str, period: str = "day",
                   start=None, end=None) -> list[dict]:
        thscode = symbol if "." in symbol else symbol + ".SH"
        end_ms = int(time.time() * 1000)
        start_ms = (end or 0) if isinstance(end, int) else end_ms - 400 * 86400 * 1000
        env = _envelope("/api/a-share/prices/historical", {
            "thscode": thscode,
            "interval": "1d" if period in ("day", "week") else "1m",
            "start": start_ms,
            "end": end_ms,
            "adjust": "forward",
        })
        if not env or env.get("code") not in (0, None):
            return []
        rows = ((env.get("data") or {}).get("item") or []) if env.get("data") else []
        out = []
        for it in rows:
            dt = it.get("date_ms")
            try:
                dt = time.strftime("%Y-%m-%d", time.localtime(dt / 1000)) if dt else ""
            except Exception:
                dt = ""
            out.append({
                "symbol": symbol,
                "dt": dt,
                "open": it.get("open_price"),
                "high": it.get("high_price"),
                "low": it.get("low_price"),
                "close": it.get("close_price"),
                "volume": it.get("volume") or 0,
                "amount": it.get("turnover") or 0,
            })
        return out

    def get_realtime(self, symbols=None) -> dict:
        if not symbols:
            return {}
        thscodes = []
        for s in (symbols if isinstance(symbols, list) else [symbols])[:50]:
            thscodes.append(s if "." in s else s + ".SH")
        env = _envelope("/api/a-share/prices/snapshot", {"thscodes": ",".join(thscodes)})
        if not env or env.get("code") not in (0, None):
            return {}
        rows = ((env.get("data") or {}).get("item") or []) if env.get("data") else []
        out = {}
        for it in rows:
            code = it.get("thscode") or ""
            sym = code.split(".")[0] if code else ""
            out[sym] = {
                "symbol": sym,
                "price": it.get("last_price"),
                "change": it.get("price_change"),
                "change_pct": it.get("price_change_ratio_pct"),
                "volume": it.get("volume") or 0,
                "amount": it.get("turnover") or 0,
                "open": it.get("open_price"),
                "high": it.get("high_price"),
                "low": it.get("low_price"),
                "prev": it.get("prev_price"),
            }
        return out

    def get_indices(self) -> list:
        return []

    def get_sector_money_flow(self) -> list:
        return []

    def get_sector_speed(self) -> list:
        return []

    def get_limit_up(self) -> list:
        return []

    def get_dragon_tiger(self) -> list:
        return []
