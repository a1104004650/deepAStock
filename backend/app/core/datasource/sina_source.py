"""真实行情数据源 - 新浪(Sina) + 腾讯(Tencent) 直连 + 东财镜像主机

可访问真实数据端点：
  * 新浪实时行情  https://hq.sinajs.cn/list=sh600519,...
  * 腾讯K线      https://ifzq.gtimg.cn/appstock/app/newfqkline/get?param=sh600519,day,,,N,qfq
  * 腾讯分时      https://ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519
  * 腾讯指数      https://qt.gtimg.cn/q=hkHSI,usIXIC,usDJI
  * 新浪联想搜索  https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key=...
  * 东财板块/资金流 https://push2delay.eastmoney.com / push2his (板块成分) / datacenter-web (龙虎榜、财报)
"""

import json
import re
import urllib.request
import html
from datetime import date, timedelta
from typing import Optional

from app.core.datasource.base import DataSourceBase
from app.utils.logger import logger

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_SINA_HEADERS = {**_UA, "Referer": "https://finance.sina.com.cn"}

_TENCENT_PERIOD = {"day": "day", "week": "week", "month": "month",
                   "m5": "m5", "m15": "m15", "m30": "m30", "m60": "m60"}
_KLINE_COUNT = {"day": 400, "week": 200, "month": 120,
                "m5": 480, "m15": 480, "m30": 240, "m60": 160}
_MINUTE_PERIODS = {"m5", "m15", "m30", "m60"}

_STOCK_RE = re.compile(r"var hq_str_(\w+)=\"(.*?)\";", re.S)

_INDICES = [
    ("SH000001", "上证指数", "A"), ("SZ399001", "深证成指", "A"),
    ("SZ399006", "创业板指", "A"), ("SH000688", "科创50", "A"),
    ("SH000300", "沪深300", "A"),
    ("HSI", "恒生指数", "H"), ("IXIC", "纳斯达克", "US"), ("DJI", "道琼斯", "US"),
]

# 指数代码 -> 腾讯K线代码
_INDEX_TC = {"HSI": "hkHSI", "IXIC": "usIXIC", "DJI": "usDJI"}

# 极少数合法代码但实时源无名称时的兜底显示名（仅名称，非行情数据）
_NAME_MAP = {
    "SH600519": "贵州茅台", "SH600036": "招商银行", "SH601318": "中国平安",
    "SZ000001": "平安银行", "SZ300750": "宁德时代", "SZ002594": "比亚迪",
    "SH688981": "中芯国际",
}


_OPEN = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open(url: str, headers: dict, timeout: float = 5.0) -> bytes:
    # 直连（绕过系统/环境代理），避免本机代理不稳定导致 WinError 10061 / SSL EOF
    req = urllib.request.Request(url, headers=headers)
    return _OPEN.open(req, timeout=timeout).read()


def _sina_codes(symbols: list[str]) -> list[str]:
    out = []
    for s in symbols:
        s = s.upper()
        if s.startswith(("SH", "SZ", "BJ")) and s[2:].isdigit():
            out.append(s[:2].lower() + s[2:])
    return out


def to_standard_symbol(code: str) -> str:
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2].upper() + c[2:]
    if c.isdigit() and len(c) == 6:
        if c.startswith("6") or c.startswith("900"):
            return "SH" + c
        if c.startswith(("0", "3")) or c.startswith("200"):
            return "SZ" + c
        return "BJ" + c
    return code.upper()


class SinaSource(DataSourceBase):
    name = "sina"

    # ---------- K线（腾讯，前复权） ----------
    def get_klines(self, symbol: str, period: str = "day",
                   start: Optional[date] = None, end: Optional[date] = None) -> list[dict]:
        symbol = to_standard_symbol(symbol)
        tc_period = _TENCENT_PERIOD.get(period)
        if not tc_period:
            return []
        code = _INDEX_TC.get(symbol.upper())
        if not code:
            code = _sina_codes([symbol])[0] if _sina_codes([symbol]) else symbol.lower()
        count = _KLINE_COUNT.get(period, 200)
        minute = period in _MINUTE_PERIODS
        if minute:
            # 分钟K线走腾讯 mkline 接口（无复权）
            url = (f"https://ifzq.gtimg.cn/appstock/app/kline/mkline"
                   f"?param={code},{tc_period},,{count}")
        else:
            url = (f"https://ifzq.gtimg.cn/appstock/app/newfqkline/get"
                   f"?param={code},{tc_period},,,{count},qfq")
        try:
            body = _open(url, _UA)
            payload = json.loads(body.decode("utf-8", "ignore"))
            data_node = payload.get("data")
            if not isinstance(data_node, dict):
                # 腾讯风控/限流有时返回 {"data": [], ...}
                return []
            d = data_node.get(code, {})
            if minute:
                key = tc_period
                rows = d.get(key) or []
            else:
                key = next((k for k in (f"qfq{tc_period}", tc_period) if d.get(k)), None)
                rows = d.get(key) or []
            result = []
            for r in rows:
                try:
                    raw_dt = str(r[0])
                    o, c, h, l = float(r[1]), float(r[2]), float(r[3]), float(r[4])
                    vol = int(float(r[5])) if len(r) > 5 else 0
                except (ValueError, IndexError):
                    continue
                if minute:
                    if len(raw_dt) == 12:
                        day = f"{raw_dt[0:4]}-{raw_dt[4:6]}-{raw_dt[6:8]} {raw_dt[8:10]}:{raw_dt[10:12]}"
                    else:
                        day = raw_dt
                else:
                    day = raw_dt
                if not minute and start and day < start.isoformat():
                    continue
                if not minute and end and day > end.isoformat():
                    break
                result.append({"symbol": symbol, "dt": day, "period": period,
                               "open": o, "high": h, "low": l, "close": c,
                               "volume": vol, "amount": 0.0})
            return result
        except Exception as e:
            logger.warning(f"tencent kline failed {symbol}/{period}: {e}")
            return []

    # ---------- 实时（新浪批量） ----------
    def get_realtime(self, symbols: list[str]) -> dict[str, dict]:
        std = [to_standard_symbol(s) for s in symbols]
        codes = _sina_codes(std)
        out: dict[str, dict] = {}
        if not codes:
            return out
        try:
            body = _open("https://hq.sinajs.cn/list=" + ",".join(codes), _SINA_HEADERS)
            text = body.decode("gbk", "ignore")
        except Exception as e:
            logger.warning(f"sina realtime failed {symbols}: {e}")
            return out
        for m in _STOCK_RE.finditer(text):
            code, fields = m.group(1), m.group(2).split(",")
            if code.startswith("s_"):
                code = code[2:]  # 还原 sina 指数 s_ 前缀
            if len(fields) < 18 or not fields[0]:
                continue
            sym = to_standard_symbol(code)
            try:
                name = fields[0]
                open_p = _f(fields[1]); prev_close = _f(fields[2]); price = _f(fields[3])
                high = _f(fields[4]); low = _f(fields[5])
                volume = round(_f(fields[8]) / 100, 2)  # 新浪个股量为股，归一为手
                amount = _f(fields[9])
                change = round(price - prev_close, 4)
                change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
                out[sym] = {"symbol": sym, "name": name, "price": round(price,2),
                            "change": round(change,2), "change_pct": round(change_pct,2),
                            "volume": volume, "amount": amount, "high": round(high,2),
                            "low": round(low,2), "open": round(open_p,2),
                            "prev_close": round(prev_close,2), "turnover": 0.0, "pe": None}
            except (ValueError, IndexError):
                continue
        return out

    def get_indices(self) -> list[dict]:
        result: list[dict] = []
        # 新浪指数必须用 s_ 前缀（如 s_sh000001），否则返回个股协议行→字段全部错位
        a_codes = ["s_" + c for c in _sina_codes([c for c, _, m in _INDICES if m == "A"])]
        try:
            body = _open("https://hq.sinajs.cn/list=" + ",".join(a_codes), _SINA_HEADERS)
            for m in _STOCK_RE.finditer(body.decode("gbk", "ignore")):
                code, fields = m.group(1), m.group(2).split(",")
                if code.startswith("s_"):
                    code = code[2:]   # 指数实时查询走的 s_sh000001 → 还原 SH000001
                if len(fields) < 6 or not fields[0]:
                    continue
                sym = to_standard_symbol(code)
                # 新浪指数行布局(与个股不同): 名称,最新点位,涨跌额,涨跌幅%,成交量,成交额,...
                try:
                    price = _f(fields[1]); change = _f(fields[2]); change_pct = _f(fields[3])
                    if not price:
                        continue
                    prev_close = round(price - change, 4)
                    result.append({"code": sym, "name": fields[0], "price": round(price, 2),
                                   "change": round(change, 2),
                                   "change_pct": round(change_pct, 2)})
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            logger.warning(f"sina index failed: {e}")
        hk_us = [c for c, _, m in _INDICES if m != "A"]
        try:
            body = _open("https://qt.gtimg.cn/q=" + ",".join("hk" + c if c == "HSI" else "us" + c for c in hk_us), _UA)
            text = body.decode("gbk", "ignore")
            for c in hk_us:
                tc = "hkHSI" if c == "HSI" else "us" + c
                m = re.search(rf'v_{tc}="([^"]*)"', text)
                if not m:
                    continue
                f = m.group(1).split("~")
                if len(f) < 5:
                    continue
                try:
                    name = f[1]
                    price = _f(f[3]); prev_close = _f(f[4])
                    change = price - prev_close
                    result.append({"code": c, "name": name, "price": round(price, 2),
                                   "change": round(change, 2),
                                   "change_pct": round(change / prev_close * 100, 2) if prev_close else 0.0})
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            logger.warning(f"tencent index failed: {e}")
        return result

    # ---------- 东方财富系数据（本机网络不可达 -> 空，不 mock） ----------
    def get_sector_money_flow(self) -> list[dict]:
        return []

    def get_sector_speed(self) -> list[dict]:
        return []

    def get_limit_up(self) -> list[dict]:
        return []

    def get_dragon_tiger(self) -> list[dict]:
        return []

    def get_financial(self, symbol: str) -> list[dict]:
        return []

    def get_financial_overview(self, symbol: str) -> dict:
        """财务估值概览：解析腾讯实时行情字段 换手/市盈率/振幅/流通市值/总市值/市净率。
        网络只达腾讯/新浪，三大报表(东财)不可达，故用真实估值字段代替 营收/净利润 行情。"""
        code = symbol.upper()
        if not code.startswith(("SH", "SZ", "BJ")):
            code = ("SH" if code.startswith(("6", "9")) else "SZ") + code
        tc = code[:2].lower() + code[2:]
        try:
            body = _open("https://qt.gtimg.cn/q=" + tc, _UA, timeout=8).decode("gbk", "ignore")
            m = re.search(rf'v_{tc}="([^"]*)"', body)
            if not m:
                return {"available": False, "reason": "暂无行情"}
            f = m.group(1).split("~")
            if len(f) < 47:
                return {"available": False, "reason": "暂无行情"}
            price = _f(f[3])
            total_mv = _f(f[45])  # 总市值(亿)
            return {
                "available": True, "name": f[1], "price": price,
                "pe": _f(f[39]), "pb": _f(f[46]),
                "total_mv": total_mv, "float_mv": _f(f[44]),
                "turnover": _f(f[38]), "amplitude": _f(f[43]),
                "market_cap_class": "大盘" if total_mv >= 1000 else
                                    "中盘" if total_mv >= 100 else "小盘",
                "quote_source": "腾讯实时行情",
            }
        except Exception as e:
            logger.warning(f"tencent financial overview failed {symbol}: {e}")
            return {"available": False, "reason": "数据获取失败"}

    def get_news(self, limit: int = 50) -> list[dict]:
        return []

    # ---------- 基本面（名称来自实时行情） ----------
    def get_stock_basic(self, symbol: str) -> dict:
        code = symbol.lower()
        name = _NAME_MAP.get(code.upper(), symbol)
        try:
            rt = self.get_realtime([code])
            hit = next((v.get("name") for v in rt.values() if v.get("name")), None)
            if hit:
                name = hit
        except Exception:
            pass
        return {"symbol": symbol.upper(), "name": name, "industry": "未分类"}

    # ---------- 搜索（新浪联想接口） ----------
    def search_stocks(self, keyword: str) -> list[dict]:
        import urllib.parse
        kw = urllib.parse.quote(keyword)
        url = ("https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15"
               f"&key={kw}&name=suggestdata_{kw}")
        try:
            body = _open(url, _SINA_HEADERS).decode("gbk", "ignore")
        except Exception as e:
            logger.warning(f"sina search failed {keyword}: {e}")
            return []
        result = []
        for seg in body.split(";"):
            if '"' not in seg or seg.count('"') < 2:
                continue
            seg = seg.split('"')[1].strip()
            parts = seg.split(",")
            if len(parts) < 4:
                continue
            name, typ, code, full = parts[0], parts[1], parts[2], parts[3]
            if not (code.isdigit() and len(code) == 6 and full.startswith(("sh", "sz", "bj"))):
                continue
            try:
                if int(typ) not in (11, 12, 13, 14):
                    continue
            except ValueError:
                continue
            result.append({"symbol": to_standard_symbol(full), "name": name, "code": code})
            if len(result) >= 30:
                break
        return result

    # ---------- 分时（腾讯，供 KlineService 使用） ----------
    def get_intraday(self, symbol: str) -> list[dict]:
        symbol = to_standard_symbol(symbol)
        code = _sina_codes([symbol])[0] if _sina_codes([symbol]) else symbol.lower()
        try:
            body = _open(f"https://ifzq.gtimg.cn/appstock/app/minute/query?code={code}", _UA, timeout=8)
            payload = json.loads(body.decode("utf-8", "ignore"))
            data = payload.get("data", {}).get(code, {}).get("data", {})
            rows = data.get("data") or []
            result = []
            for r in rows:
                parts = r.split()
                if len(parts) < 3:
                    continue
                try:
                    t = int(parts[0]); hh, mm = t // 100, t % 100
                    price = round(float(parts[1]), 2)
                    volume = float(parts[2])          # 累计成交量(手)
                    amount = float(parts[3]) if len(parts) > 3 else 0.0  # 累计成交额(元)
                    avg = round(amount / (volume * 100), 2) if volume > 0 else price  # 均价线
                    rec = {"time": f"{hh:02d}:{mm:02d}", "price": price,
                           "volume": volume, "amount": amount, "avg": avg}
                    if price > 0:
                        result.append(rec)
                except ValueError:
                    continue
            return result
        except Exception as e:
            logger.warning(f"tencent minute failed {symbol}: {e}")
            return []

    # ---------- 新浪板块行情（概念 + 行业，真实涨幅/成交额） ----------
    _SECTOR_CACHE: Optional[list[dict]] = None
    _SECTOR_CACHE_TS = 0.0

    def _fljk_sectors(self) -> list[dict]:
        import time as _t
        now = _t.time()
        if self._SECTOR_CACHE and (now - self._SECTOR_CACHE_TS) < 30:
            return self._SECTOR_CACHE
        rows = []
        for param, stype in (("class", "concept"), ("industry", "industry")):
            try:
                body = _open("https://money.finance.sina.com.cn/q/view/newFLJK.php?param=" + param,
                             _SINA_HEADERS, timeout=8).decode("gbk", "ignore")
                m = re.search(r"=\s*(\{.*?\});?\s*$", body, re.S)
                if not m:
                    continue
                data = json.loads(m.group(1))
                for code, val in data.items():
                    parts = val.split(",")
                    if len(parts) < 13:
                        continue
                    try:
                        rows.append({
                            "code": parts[0], "name": parts[1], "count": int(float(parts[2])),
                            "change_pct": round(float(parts[5]), 2),
                            "change": round(float(parts[4]), 2),
                            "volume": float(parts[6]), "amount": float(parts[7]),
                            "leader_code": parts[8], "leader_name": parts[12].strip(),
                            "type": stype,
                        })
                    except (ValueError, IndexError):
                        continue
            except Exception as e:
                logger.warning(f"sina FLJK failed {param}: {e}")
        self._SECTOR_CACHE = rows
        self._SECTOR_CACHE_TS = now
        return rows

    def get_sector_money_flow(self) -> list[dict]:
        rows = self._fljk_sectors()
        rows = sorted(rows, key=lambda r: r.get("amount") or 0, reverse=True)[:12]
        return [{"sector_name": r["name"], "net_inflow": r["amount"], "change_pct": r["change_pct"],
                 "leader": r["leader_name"], "count": r["count"]} for r in rows]

    def get_sector_speed(self) -> list[dict]:
        rows = self._fljk_sectors()
        rows = sorted(rows, key=lambda r: r.get("change_pct") or 0, reverse=True)[:12]
        return [{"sector_name": r["name"], "change_pct": r["change_pct"], "net_inflow": r["amount"],
                 "leader": r["leader_name"], "count": r["count"]} for r in rows]

    # ---------- 个股所属板块真实涨幅（FLJK 板块行情查询） ----------
    _SECTOR_CHANGE_CACHE: dict = {}
    _SECTOR_CHANGE_TS = 0.0

    def get_sector_changes(self, industry: str = "", concepts: list = None) -> dict:
        """返回行业/概念在 FLJK 中的真实 change_pct 与领涨股。"""
        import time as _t
        now = _t.time()
        if self._SECTOR_CHANGE_CACHE and (now - self._SECTOR_CHANGE_TS) < 30:
            return self._SECTOR_CHANGE_CACHE
        rows = self._fljk_sectors()
        by_name = {r["name"]: r for r in rows}
        out = {"industry": None, "concepts": []}
        if industry and industry in by_name:
            r = by_name[industry]
            out["industry"] = {"name": industry, "change_pct": r["change_pct"],
                               "leader": r["leader_name"], "amount": round(r["amount"] / 1e8, 2)}
        for c in (concepts or []):
            r = by_name.get(c)
            if r:
                out["concepts"].append({"name": c, "change_pct": r["change_pct"],
                                        "leader": r["leader_name"], "amount": round(r["amount"] / 1e8, 2)})
        self._SECTOR_CHANGE_CACHE = out
        self._SECTOR_CHANGE_TS = now
        return out

    def get_sector_flow_top(self, top: int = 5) -> dict:
        """行业/概念 资金流入、流出 各前 N。
        真实板块主力净流入接口（MoneyFlow.ssl_bkzj_zdfp）已下线，改用新浪板块真实成交额 + 板块涨跌方向
        作为净流入/流出排序口径（涨→流入、跌→流出），数据全部来自真实行情。"""
        rows = self._fljk_sectors()
        out = {"industries": {"in": [], "out": []}, "concepts": {"in": [], "out": []}}
        for stype, key in (("industry", "industries"), ("concept", "concepts")):
            seg = [r for r in rows if r.get("type") == stype]
            inflow = sorted([r for r in seg if (r.get("change_pct") or 0) > 0],
                            key=lambda r: r.get("amount") or 0, reverse=True)[:top]
            outflow = sorted([r for r in seg if (r.get("change_pct") or 0) < 0],
                             key=lambda r: r.get("amount") or 0, reverse=True)[:top]
            out[key]["in"] = [{"name": r["name"], "amount": round((r.get("amount") or 0) / 1e8, 2),
                               "change_pct": r["change_pct"], "leader": r["leader_name"],
                               "leader_symbol": self._norm_symbol(r.get("leader_code")),
                               "count": r["count"]} for r in inflow]
            out[key]["out"] = [{"name": r["name"], "amount": round((r.get("amount") or 0) / 1e8, 2),
                                "change_pct": r["change_pct"], "leader": r["leader_name"],
                                "leader_symbol": self._norm_symbol(r.get("leader_code")),
                                "count": r["count"]} for r in outflow]
        return out

    # ---------- 人气股票排行（腾讯成交额 Top200 里按 换手×量比×涨幅 综合热度重排） ----------
    _HOT_CACHE: Optional[list[dict]] = None
    _HOT_TS = 0.0

    def get_hot_stocks(self, top: int = 10) -> list[dict]:
        import time as _t
        now = _t.time()
        if self._HOT_CACHE and (now - self._HOT_TS) < 60:
            return self._HOT_CACHE[:top]
        rows = []
        try:
            import concurrent.futures
            offsets = [p * 200 for p in range(10)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                parts = list(ex.map(lambda off: self._tencent_rank_page(off, 200, "turnover"), offsets))
            for part in parts:
                if not part:
                    break
                rows += part
        except Exception as e:
            logger.warning(f"tencent hot rank failed: {e}")
        scored = []
        for r in rows:
            code = (r.get("code") or "").strip().lower()
            uname = r.get("name") or ""
            if not code or not uname:
                continue
            try:
                hsl = float(r.get("hsl") or 0)
                lb = float(r.get("lb") or 0)
                zdf = float(r.get("zdf") or 0)
                zxj = float(r.get("zxj") or 0)
                turn = float(r.get("turnover") or 0)  # 万元
            except (TypeError, ValueError):
                continue
            heat = min(100.0, round(hsl * 2 + lb * 14 + abs(zdf) + turn / 10000 * 0.2, 1))
            scored.append({
                "symbol": code.upper(), "name": uname, "price": round(zxj, 2),
                "change_pct": round(zdf, 2),
                "heat": heat, "turnover": round(turn, 0),
                "hsl": round(hsl, 2), "lb": round(lb, 2),
            })
        scored.sort(key=lambda x: x["heat"], reverse=True)
        self._HOT_CACHE = scored
        self._HOT_TS = now
        return scored[:top]

    # ---------- 实时股价异动（腾讯涨速榜：快速拉升 / 快速下挫） ----------
    _MOVERS_CACHE: Optional[dict] = None
    _MOVERS_TS = 0.0

    def get_price_movers(self, top: int = 5) -> dict:
        import time as _t
        now = _t.time()
        if self._MOVERS_CACHE is not None and (now - self._MOVERS_TS) < 60:
            return self._MOVERS_CACHE

        def _rank(direct: str) -> list[dict]:
            try:
                url = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
                       f"?board_code=aStock&sort_type=speed&direct={direct}&offset=0&count={top}")
                body = _open(url, {**_UA, "Referer": "https://gu.qq.com"}, timeout=8).decode("utf-8", "ignore")
                return (json.loads(body).get("data", {}).get("rank_list") or [])
            except Exception as e:
                logger.warning(f"price movers failed (direct={direct}): {e}")
                return []

        out = {"rise": [], "fall": []}
        for direct, key in (("down", "rise"), ("up", "fall")):
            for r in _rank(direct):
                code = (r.get("code") or "").strip().lower()
                if not code:
                    continue
                try:
                    speed = float(r.get("speed") or 0.0)
                    zdf = float(r.get("zdf") or 0.0)
                except (TypeError, ValueError):
                    continue
                out[key].append({
                    "symbol": code.upper(), "name": r.get("name") or "",
                    "price": round(float(r.get("zxj") or 0), 2),
                    "change_pct": round(zdf, 2),
                    "speed": round(speed, 2),
                    "lb": round(float(r.get("lb") or 0), 2),
                    "hsl": round(float(r.get("hsl") or 0), 2),
                    "turnover": round(float(r.get("turnover") or 0), 0),
                })
        self._MOVERS_CACHE = out
        self._MOVERS_TS = now
        return out

    # ---------- ETF 资金流（东方财富实时含今日 + 新浪兜底） ----------
    _ETF_FLOW_CACHE: Optional[dict] = None
    _ETF_FLOW_TS = 0.0
    _ETF_FFLOW_CACHE: dict = {}
    _ETF_FFLOW_TS = 0.0
    _EM_FFLOW_HOSTS = ["10.push2his.eastmoney.com", "push2his.eastmoney.com",
                       "2.push2his.eastmoney.com", "push2delay.eastmoney.com",
                       "9.push2his.eastmoney.com"]
    _EM_FFLOW_IDX = 0

    @classmethod
    def _em_fflow_kline(cls, secid: str, limit: int = 30, timeout: float = 10.0, klt: int = 101) -> list[str]:
        """东财资金流K线 rows（新→旧）。每行：date,主力net,小单net,中单net,大单net,超大单net。
        klt=101 按日（含今日实时，盘中累计值）；klt=1 按分钟（升序返回，取最近 limit 反转为新→旧）。
        klt=1 优先走 push2delay（本网络下可达且含今日分时累计）；klt=101 优先 10.push2his（历史最全）。
        全部失败返回 []。"""
        import time as _t
        first_err = None
        base = ("https://%s/api/qt/stock/fflow/kline/get?lmt=0&klt=%d"
                "&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
                "&secid=%s")
        hosts = (cls._EM_FFLOW_HOSTS if klt == 101 else
                 ["push2delay.eastmoney.com", "push2his.eastmoney.com", "10.push2his.eastmoney.com",
                  "2.push2his.eastmoney.com", "9.push2his.eastmoney.com"])
        for off in range(len(hosts)):
            host = hosts[(cls._EM_FFLOW_IDX + off) % len(hosts)]
            try:
                req = urllib.request.Request(base % (host, klt, secid), headers={**_UA, "Referer": "https://quote.eastmoney.com/"})
                body = urllib.request.urlopen(req, timeout=timeout).read()
                data = json.loads(body.decode("utf-8", "ignore"))
                kl = (data.get("data") or {}).get("klines") or []
                if kl:
                    cls._EM_FFLOW_IDX = hosts.index(host)
                    return list(reversed(kl[-limit:]))
                return []
            except Exception as e:
                first_err = first_err or e
                _t.sleep(0.4)
                continue
        logger.warning(f"em fflow kline {secid} klt={klt} failed: {first_err}")
        return []

    @staticmethod
    def _em_secid(symbol: str) -> str:
        """sh510300 → 1.510300，sz159915 → 0.159915"""
        s = (symbol or "").lower()
        if s.startswith(("sh", "bj")):
            return "1." + s[2:]
        if s.startswith("sz"):
            return "0." + s[2:]
        return s

    @classmethod
    def _parse_em_fflow(cls, klines: list[str]) -> list[dict]:
        """东财资金流 rows 解析为主力净流入序列（新→旧）。"""
        out = []
        for line in klines or []:
            parts = (line or "").split(",")
            if len(parts) < 2:
                continue
            date = parts[0][:10]
            if not date or not date.replace("-", "").isdigit():
                continue
            try:
                out.append({"date": date, "netamount": float(parts[1])})
            except (ValueError, TypeError):
                continue
        return out

    @staticmethod
    def _etf_watchlist() -> list[dict]:
        return [
            {"symbol": "sh510300", "name": "沪深300ETF"},
            {"symbol": "sh510050", "name": "上证50ETF"},
            {"symbol": "sh510500", "name": "中证500ETF"},
            {"symbol": "sh512100", "name": "中证1000ETF"},
            {"symbol": "sz159915", "name": "创业板ETF"},
            {"symbol": "sh588000", "name": "科创50ETF"},
            {"symbol": "sz159949", "name": "创业板50ETF"},
            {"symbol": "sh512880", "name": "证券ETF"},
            {"symbol": "sh512760", "name": "芯片ETF"},
            {"symbol": "sh513050", "name": "中概互联ETF"},
        ]

    def _etf_net_flows(self, code: str) -> list[dict]:
        """返回该标的最近交易日主力净流入序列（新→旧），字段 netamount(元)"""
        url = ("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               "MoneyFlow.ssl_qsfx_zjlrqs?pc=1&cc=30&daima=" + code)
        body = _open(url, _SINA_HEADERS, timeout=12).decode("gbk", "ignore")
        start, end = body.find("["), body.rfind("]")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(body[start:end + 1])
        except Exception:
            return []
        out = []
        for r in data:
            try:
                out.append({"date": (r.get("opendate") or ""), "netamount": float(r.get("netamount") or 0)})
            except (TypeError, ValueError):
                continue
        return out

    # ---------- 个股资金流（新浪真实，按交易日聚合） ----------
    _STOCK_FLOW_CACHE: dict = {}
    _STOCK_FLOW_TS = 0.0

    def get_stock_money_flow(self, symbol: str, limit: int = 20) -> list[dict]:
        """个股每日主力净流入（新→旧），并附 1/5/20 日累计（亿元）。"""
        import time as _t
        now = _t.time()
        cache_key = f"{symbol}:{limit}"
        if self._STOCK_FLOW_CACHE.get(cache_key) and (now - self._STOCK_FLOW_TS) < 600:
            return self._STOCK_FLOW_CACHE[cache_key]
        code = symbol.lower()
        flows = self._etf_net_flows(code)[:limit]
        net_1d = sum(x["netamount"] for x in flows[:1])
        net_5d = sum(x["netamount"] for x in flows[:5])
        net_20d = sum(x["netamount"] for x in flows[:20])
        rows = [
            {"date": x["date"], "netamount": x["netamount"],
             "net_1d": round(net_1d / 1e8, 2), "net_5d": round(net_5d / 1e8, 2),
             "net_20d": round(net_20d / 1e8, 2)} for x in flows
        ]
        self._STOCK_FLOW_CACHE = {cache_key: rows}
        self._STOCK_FLOW_TS = now
        return rows

    def get_stock_flow_summary(self, symbol: str) -> dict:
        rows = self.get_stock_money_flow(symbol, limit=20)
        if not rows:
            return {"latest_date": "", "net_1d": 0, "net_5d": 0, "net_20d": 0, "trend": "unknown"}
        trend = "unknown"
        if len(rows) >= 5:
            recent = (rows[0]["netamount"] + rows[1]["netamount"]) / 2
            older = sum(x["netamount"] for x in rows[2:5]) / 3
            trend = "inflow" if older >= 0 and recent >= 0 else ("outflow" if older < 0 and recent < 0 else "mixed")
        return {
            "latest_date": rows[0]["date"], "net_1d": rows[0]["net_1d"],
            "net_5d": rows[0]["net_5d"], "net_20d": rows[0]["net_20d"], "trend": trend,
        }

    # ---------- 大盘资金流向（沪深两市，东财：分钟累计曲线 + 逐日历史） ----------
    _MARKET_FLOW_CACHE: Optional[dict] = None
    _MARKET_FLOW_TS = 0.0

    def get_market_money_flow(self, days: int = 20) -> dict:
        """沪深两市大盘资金流向：
        date/dt = 当日；intraday = 分时累计曲线（time, 主力/超大/大/中/小净流入，元，盘中实时）；
        daily = 近N个交易日逐日净流入（date + 各档），新→旧。
        数据 = 上证(1.000001) + 深证成指(0.399001) 两指数相加；任一信源失败则以另一近似。"""
        import time as _t
        now = _t.time()
        if self._MARKET_FLOW_CACHE and (now - self._MARKET_FLOW_TS) < 300:
            return self._MARKET_FLOW_CACHE
        KEYS = ("main_net", "super_net", "large_net", "mid_net", "small_net")
        SECIDS = ["1.000001", "0.399001"]

        def step_rows(klt: int, limit: int) -> dict:
            out = {}
            for secid in SECIDS:
                try:
                    rows = self._em_fflow_kline(secid, limit=limit, klt=klt)
                except Exception as e:
                    logger.warning(f"em market flow {secid} klt={klt}: {e}")
                    continue
                for line in rows:
                    p = (line or "").split(",")
                    if len(p) < 6:
                        continue
                    if klt == 1:
                        key = p[0][11:16] if len(p[0]) >= 16 else p[0]
                    else:
                        key = p[0][:10] if len(p[0]) >= 10 else p[0]
                    try:
                        vals = [float(p[1]), float(p[5]), float(p[4]), float(p[3]), float(p[2])]
                    except (ValueError, TypeError, IndexError):
                        continue
                    agg = out.setdefault(key, {"t": key})
                    for k, v in zip(KEYS, vals):
                        agg[k] = agg.get(k, 0.0) + v
            return out

        daily = step_rows(101, min(max(days, 5), 40))
        intraday = step_rows(1, 400)
        # 分时按时间正序（供前端直接画折线）
        intraday_list = [
            {"time": k, **{k2: round(v, 2) for k2, v in a.items() if k2 in KEYS}}
            for k, a in sorted(intraday.items())
        ]
        daily_list = [
            {"date": k, **{k2: round(v, 2) for k2, v in a.items() if k2 in KEYS}}
            for k, a in sorted(daily.items(), reverse=True)
        ]
        flow_date = daily_list[0]["date"] if daily_list else (intraday_list[-1]["time"][:10] if intraday_list else "")
        result = {"date": flow_date, "intraday": intraday_list, "daily": daily_list}
        self._MARKET_FLOW_CACHE = result
        self._MARKET_FLOW_TS = now
        return result

    # ---------- 个股相关新闻（新浪财经滚动按 名称/行业/概念 关键词匹配，真实标题） ----------
    _STOCK_NEWS_CACHE: dict = {}
    _STOCK_NEWS_TS = 0.0

    @staticmethod
    def _news_sentiment(title: str, intro: str = "") -> str:
        text = title + " " + (intro or "")
        pos = ["预增", "净利大增", "增长", "中标", "签约", "回购", "增持", "主力净流入", "涨停", "突破",
               "获批", "投产", "涨价", "高分红", "分红", "创新高", "订单", "合作", "战略合作", "注入",
               "重组获批", "扭亏", "减亏", "超预期", "护盘", "低估", "评级上调", "买入评级"]
        neg = ["预亏", "亏损", "业绩下滑", "净利润下降", "减持", "解禁", "立案", "处罚", "诉讼",
               "退市", "ST", "下调", "质押", "爆仓", "商誉减值", "违约", "暴跌", "跌停", "召回",
               "质量问题", "警告", "警示函", "问询", "跌破", "暴雷", "造假", "欠薪", "裁员"]
        score = sum(1 for kw in pos if kw in text) - sum(1 for kw in neg if kw in text)
        if score > 0:
            return "bullish"
        if score < 0:
            return "bearish"
        return "neutral"

    def get_stock_related_news(self, symbol: str, name: str, industry: str = "",
                               concepts: list = None, limit: int = 15) -> list[dict]:
        """个股相关新闻（新浪个股页 nc.shtml 服务端渲染的真实标题，利好/利空启发式标注）。
        按股票名片段/行业/概念 过滤无关标题；页面本身即该个股“相关新闻”聚合。"""
        import time as _t
        now = _t.time()
        cached = self._STOCK_NEWS_CACHE.get(symbol)
        if cached and (now - self._STOCK_NEWS_TS) < 600:
            return cached[:limit]
        items = []
        try:
            code = symbol.lower()
            body = _open(f"https://finance.sina.com.cn/realstock/company/{code}/nc.shtml",
                         _SINA_HEADERS, timeout=10).decode("gbk", "ignore")
            body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.S)
            body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.S)
            pairs = re.findall(r'<a[^>]+href="(https?://[^"]*?/doc-[^"]+\.shtml)"[^>]*>(.*?)</a>', body, re.S)
            base_name = (name or "").replace("股份", "").replace("集团", "").replace("科技", "").replace("发展", "").strip()
            names = {base_name, (name or "").strip()}
            if len(base_name) >= 3:
                names.add(base_name[-2:])
            elif base_name:
                names.add(base_name)
            keywords = names | {(w or "").strip() for w in [industry] + list(concepts or []) if w}
            keywords.discard("")
            seen = set()
            for url, txt in pairs:
                txt = html.unescape(re.sub(r"<[^>]+>", "", txt)).strip()
                if not txt or len(txt) < 4 or url in seen:
                    continue
                if keywords and not any(kw in txt for kw in keywords):
                    continue
                seen.add(url)
                items.append({
                    "title": txt, "url": url, "time": "最新",
                    "sentiment": self._news_sentiment(txt, ""),
                    "matched": sorted(kw for kw in keywords if kw in txt)[:3],
                })
        except Exception as e:
            logger.warning(f"sina stock news failed {symbol}: {e}")
        if items:
            self._STOCK_NEWS_CACHE[symbol] = items
            self._STOCK_NEWS_TS = now
        return items[:limit]

    def get_etf_flow(self, top: int = 5) -> dict:
        """各ETF主力资金流：东财当日实时(含今日)优先，新浪(最多T-1)兜底。"""
        import time as _t
        now = _t.time()
        if self._ETF_FLOW_CACHE and (now - self._ETF_FLOW_TS) < 300:
            return self._ETF_FLOW_CACHE
        rows = []
        _ETF_FFLOW_CACHE = getattr(SinaSource, "_ETF_FFLOW_CACHE", {})
        _ETF_FFLOW_TS = getattr(SinaSource, "_ETF_FFLOW_TS", 0.0)
        for etf in self._etf_watchlist():
            symbol = etf["symbol"].lower()
            flows = []
            cached_rows = (_ETF_FFLOW_CACHE.get(symbol) or []) if (now - _ETF_FFLOW_TS) < 300 else []
            if not cached_rows:
                try:
                    cached_rows = self._parse_em_fflow(self._em_fflow_kline(self._em_secid(symbol), 30))
                except Exception as e:
                    logger.warning(f"em fflow kline {symbol}: {e}")
                    cached_rows = []
                if cached_rows:
                    _ETF_FFLOW_CACHE[symbol] = cached_rows
                    _ETF_FFLOW_TS = now
            if cached_rows:
                flows = cached_rows
            else:
                try:
                    flows = self._etf_net_flows(symbol)
                except Exception as e:
                    logger.warning(f"sina fflow fallback {symbol}: {e}")
                    continue
            if not flows:
                continue
            sums = {}
            for label, n in (("net_1d", 1), ("net_5d", 5), ("net_20d", 20)):
                seg = flows[:n]
                sums[label] = round(sum(x["netamount"] for x in seg) / 1e8, 2)
            rows.append({"symbol": etf["symbol"].upper(), "name": etf["name"],
                         "net_1d": sums["net_1d"], "net_5d": sums["net_5d"],
                         "net_20d": sums["net_20d"],
                         "flow_date": flows[0]["date"] if flows else ""})
        ranked = sorted(rows, key=lambda r: r.get("net_1d") or 0, reverse=True)
        result = {"in_top": ranked[:top], "out_top": ranked[-top:][::-1], "all": rows[:top * 2]}
        SinaSource._ETF_FFLOW_CACHE = _ETF_FFLOW_CACHE
        SinaSource._ETF_FFLOW_TS = _ETF_FFLOW_TS
        self._ETF_FLOW_CACHE = result
        self._ETF_FLOW_TS = now
        return result

    # ---------- 新闻（新浪财经滚动） ----------
    _NEWS_CACHE: Optional[list[dict]] = None
    _NEWS_CACHE_TS = 0.0

    def get_news(self, limit: int = 50) -> list[dict]:
        import time as _t
        now = _t.time()
        if self._NEWS_CACHE and (now - self._NEWS_CACHE_TS) < 60:
            return self._NEWS_CACHE[:limit]
        items = []
        try:
            body = _open("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=60&page=1",
                         _SINA_HEADERS, timeout=8).decode("utf-8", "ignore")
            payload = json.loads(body)
            for it in (payload.get("result", {}).get("data") or []):
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                t = it.get("ctime")
                if isinstance(t, int):
                    from datetime import datetime as _dt
                    t = _dt.fromtimestamp(t).strftime("%H:%M")
                items.append({"title": title, "url": it.get("url") or "", "time": str(t or ""),
                              "importance": self._news_importance(title),
                              "category": self._news_category(title)})
        except Exception as e:
            logger.warning(f"sina news failed: {e}")
        self._NEWS_CACHE = items
        self._NEWS_CACHE_TS = now
        return items[:limit]

    @staticmethod
    def _news_importance(title: str) -> int:
        """新闻重要性 1=高 2=中 3=一般（关键词规则，基于真实标题文本判定）"""
        high = ["央行", "证监会", "国务院", "国常会", "突发", "重磅", "宣布", "下调", "上调",
                "降准", "降息", "加息", "回购", "救市", "退市", "立案", "处罚", "关税", "禁令",
                "禁止", "断供", "大涨", "暴跌", "涨停", "跌停", "财报预增", "业绩预亏", "暴雷",
                "重组", "并购", "停牌", "复牌", "增持", "减持"]
        low = ["点评", "观点", "怎么看", "解读", "复盘", "闲聊", "杂谈", "收评", "午评", "指数播报"]
        for kw in high:
            if kw in title:
                return 1
        for kw in low:
            if kw in title:
                return 3
        return 2

    @staticmethod
    def _news_category(title: str) -> str:
        cates = [
            ("银行", ["银行", "存款", "贷款", "房贷", "LPR"]),
            ("证券", ["券商", "证券", "投行", "经纪"]),
            ("保险", ["保险", "保费", "投保"]),
            ("地产", ["地产", "房地产", "楼市", "房价", "土地"]),
            ("医药", ["医药", "医保", "医疗", "疫苗", "创新药", "集采"]),
            ("半导体", ["半导体", "芯片", "晶圆", "光刻"]),
            ("AI", ["人工智能", "AI", "大模型", "机器人", "算力", "英伟达", "OpenAI"]),
            ("新能源", ["新能源", "光伏", "锂电", "储能", "电动车", "电池", "风电"]),
            ("汽车", ["汽车", "车企", "特斯拉", "比亚迪", "新能源车"]),
            ("白酒消费", ["白酒", "茅台", "五粮液", "消费", "零售", "电商", "618", "双11"]),
            ("军工", ["军工", "国防", "导弹", "战机", "航母"]),
            ("黄金原油", ["黄金", "原油", "石油", "布伦特", "金价"]),
            ("债券", ["债券", "国债", "利率债", "信用债", "净值"]),
            ("汇市", ["汇率", "人民币", "美元指数", "离岸", "在岸", "外汇"]),
            ("美股", ["美股", "纳斯达克", "标普", "道指", "美联储", "中概股"]),
            ("港股", ["港股", "恒生", "南向", "北向", "AH"]),
        ]
        for cat, kws in cates:
            for kw in kws:
                if kw.lower() in title.lower():
                    return cat
        return "财经综合"

    # ---------- 全市场涨跌统计（腾讯全部A股排行，真实统计） ----------
    _BREADTH: Optional[dict] = None
    _BREADTH_TS = 0.0

    def _tencent_rank_page(self, offset: int, count: int = 200, sort: str = "price") -> list[dict]:
        url = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
               f"?board_code=aStock&sort_type={sort}&direct=down&offset={offset}&count={count}")
        body = _open(url, {**_UA, "Referer": "https://gu.qq.com"}, timeout=8).decode("utf-8", "ignore")
        payload = json.loads(body)
        return (payload.get("data", {}).get("rank_list") or [])

    def _breadth_data(self, force: bool = False) -> dict:
        import time as _t
        now = _t.time()
        if self._BREADTH and not force and (now - self._BREADTH_TS) < 120:
            return self._BREADTH
        try:
            url0 = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
                    "?board_code=aStock&sort_type=price&direct=down&offset=0&count=200")
            payload0 = json.loads(_open(url0, {**_UA, "Referer": "https://gu.qq.com"}, timeout=8)
                                   .decode("utf-8", "ignore"))
            first = (payload0.get("data", {}).get("rank_list") or [])
            total = int((payload0.get("data", {}).get("total") or len(first)) or 0)
            pages = max(1, int(total / 200) + 1)
            import concurrent.futures
            parts = [first]
            offsets = [p * 200 for p in range(1, pages)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                fetched = list(ex.map(self._tencent_rank_page, offsets))
            for part in fetched:
                if not part:
                    break
                parts.append(part)
            rows = [r for part in parts for r in part]
            up = down = flat = lim_up = lim_down = 0
            lim_list = []
            amount = 0.0
            seen = set()
            buckets = {}
            bucket_defs = [
                ("≤-9%", lambda z: z <= -9.0),
                ("-9%~-7%", lambda z: -9.0 < z <= -7.0),
                ("-7%~-5%", lambda z: -7.0 < z <= -5.0),
                ("-5%~-3%", lambda z: -5.0 < z <= -3.0),
                ("-3%~0%", lambda z: -3.0 < z < 0.0),
                ("平盘", lambda z: z == 0.0),
                ("0%~+3%", lambda z: 0.0 < z < 3.0),
                ("+3%~+5%", lambda z: 3.0 <= z < 5.0),
                ("+5%~+7%", lambda z: 5.0 <= z < 7.0),
                ("+7%~+9%", lambda z: 7.0 <= z < 9.0),
                ("≥+9%", lambda z: z >= 9.0),
            ]
            for label, _fn in bucket_defs:
                buckets[label] = 0
            for r in rows:
                code = (r.get("code") or "").lower()
                name = (r.get("name") or "")
                if not code or code in seen:
                    continue
                seen.add(code)
                try:
                    zdf = float(r.get("zdf") or 0)
                    amount += float(r.get("turnover") or 0) * 1e4
                except (TypeError, ValueError):
                    zdf = 0.0
                bk_found = False
                for label, fn in bucket_defs:
                    if fn(zdf):
                        buckets[label] += 1
                        bk_found = True
                        break
                if not bk_found:
                    buckets["平盘"] += 1
                if zdf > 0:
                    up += 1
                elif zdf < 0:
                    down += 1
                else:
                    flat += 1
                thr = self._limit_threshold(code, name)
                if zdf >= thr:
                    lim_up += 1
                    try:
                        lim_list.append({"symbol": code.upper(), "name": name,
                                         "price": round(float(r.get("zxj") or 0), 2),
                                         "change_pct": zdf})
                    except (TypeError, ValueError):
                        pass
                elif zdf <= -thr:
                    lim_down += 1
            self._BREADTH = {"up_count": up, "down_count": down, "flat_count": flat,
                             "limit_up": lim_up, "limit_down": lim_down,
                             "limit_up_list": lim_list, "amount": round(amount, 2),
                             "total": len(seen), "buckets": buckets}
            self._BREADTH_TS = now
            self._limit_up_cache = lim_list
        except Exception as e:
            logger.warning(f"tencent breadth failed: {e}")
            if not self._BREADTH:
                self._BREADTH = {"up_count": 0, "down_count": 0, "flat_count": 0,
                                 "limit_up": 0, "limit_down": 0, "limit_up_list": [],
                                 "amount": 0.0, "total": 0, "buckets": {}}
        return self._BREADTH

    @staticmethod
    def _limit_threshold(code: str, name: str) -> float:
        digits = code[-6:]
        if digits[:2] in {"83", "87", "88", "92", "43", "46"} or code.startswith("bj"):
            return 29.5
        if digits.startswith("688") or digits.startswith("300"):
            return 19.5
        if "ST" in name.upper():
            return 4.7
        return 9.8

    def get_market_distribution(self) -> dict:
        d = self._breadth_data()
        return {"up_count": d["up_count"], "down_count": d["down_count"],
                "flat_count": d["flat_count"], "limit_up": d["limit_up"],
                "limit_down": d["limit_down"], "amount": d["amount"], "total": d["total"],
                "buckets": d.get("buckets") or {}}

    def get_limit_up(self) -> list[dict]:
        d = self._breadth_data()
        rows = [r for r in d.get("limit_up_list", [])]

        def _count_boards(item: dict) -> int:
            try:
                sym = item["symbol"]
                tc = sym[:2].lower() + sym[2:]
                url = f"https://ifzq.gtimg.cn/appstock/app/newfqkline/get?param={tc},day,,,15,qfq"
                payload = json.loads(_open(url, _UA, timeout=6).decode("utf-8", "ignore"))
                data = (payload.get("data") or {}).get(tc) or {}
                key = next((k for k in ("qfqday", "day", "qfq") if data.get(k)), None)
                if not key:
                    return 1
                kls = [r[:6] for r in data[key] if isinstance(r, (list, tuple))]
                thr = self._limit_threshold(tc, item["name"])
                closes = []
                for r in kls:
                    try:
                        closes.append(float(r[2]))
                    except (TypeError, ValueError):
                        closes.append(0.0)
                # 锚定最近一个涨停交易日，向前回溯连续涨停天数（今日盘中非涨停则忽略）
                anchor = None
                for i in range(len(closes) - 1, 0, -1):
                    if closes[i] <= 0 or closes[i - 1] <= 0:
                        continue
                    if (closes[i] - closes[i - 1]) / closes[i - 1] * 100 >= thr:
                        anchor = i
                        break
                if anchor is None:
                    return 1
                boards = 1
                for i in range(anchor, 1, -1):
                    if closes[i - 1] <= 0 or closes[i - 2] <= 0:
                        break
                    chg = (closes[i - 1] - closes[i - 2]) / closes[i - 2] * 100
                    if chg >= thr:
                        boards += 1
                    else:
                        break
                return boards
            except Exception:
                return 1

        if len(rows) > 1:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                boards = list(ex.map(_count_boards, rows))
        else:
            boards = [_count_boards(r) for r in rows]
        out = []
        for r, b in zip(rows, boards):
            item = {"symbol": r["symbol"], "name": r["name"], "price": r["price"],
                    "change_pct": r["change_pct"], "consecutive_days": b,
                    "first_limit": b <= 1}
            out.append(item)
        out.sort(key=lambda x: x["consecutive_days"], reverse=True)
        return out

    # ---------- 个股所属行业/概念（新浪公司资料，真实） ----------
    _SECTOR_INFO: dict = {}

    def get_stock_sector(self, symbol: str) -> dict:
        cached = self._SECTOR_INFO.get(symbol)
        if cached:
            return cached
        result = {"symbol": symbol, "industry": None, "concepts": []}
        digits = symbol[-6:]
        if not digits.isdigit():
            return result
        try:
            url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpOtherInfo/stockid/{digits}.phtml"
            body = _open(url, _SINA_HEADERS, timeout=8).decode("gbk", "ignore")
            txt = re.sub(r"<script.*?</script>", "", body, flags=re.S)
            txt = re.sub(r"<style.*?</style>", "", txt, flags=re.S)
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = re.sub(r"\s+", " ", txt)
            m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9\u3000]{1,14})\s*点击查看\s*备注：此为申万行业分类", txt)
            if m:
                result["industry"] = m.group(1).strip()
            seg = txt.split("同概念个股", 1)
            if len(seg) > 1:
                tail = seg[1].split("客户服务热线", 1)[0]
                for tok in re.split(r"\s*点击查看\s*", tail):
                    tok = tok.strip()
                    if 1 < len(tok) <= 14 and tok not in result["concepts"]:
                        result["concepts"].append(tok)
                result["concepts"] = result["concepts"][:15]
        except Exception as e:
            logger.warning(f"sina sector info failed {symbol}: {e}")
        self._SECTOR_INFO[symbol] = result
        return result

    # ---------- 板块监控（ETF 实时行情 + 概念/行业关键词实时行情） ----------
    SECTOR_MONITOR_MAP = [
        {"sector": "银行", "symbol": "SH512800", "name": "银行ETF"},
        {"sector": "证券", "symbol": "SH512880", "name": "证券ETF"},
        {"sector": "半导体", "symbol": "SH512480", "name": "半导体ETF"},
        {"sector": "医药", "symbol": "SH512010", "name": "医药ETF"},
        {"sector": "房地产", "symbol": "SH512200", "name": "房地产ETF"},
        {"sector": "黄金", "symbol": "SH518880", "name": "黄金ETF"},
        {"sector": "军工", "symbol": "SH512660", "name": "军工ETF"},
        {"sector": "新能源", "symbol": "SH516160", "name": "新能源ETF"},
        {"sector": "白酒", "symbol": "SH512690", "name": "白酒ETF"},
        {"sector": "芯片", "symbol": "SH512760", "name": "芯片ETF"},
        {"sector": "光伏", "symbol": "SH515790", "name": "光伏ETF"},
        {"sector": "CPO", "symbol": "SZ159515", "name": "CPO概念"},
        {"sector": "机器人", "symbol": "SH562500", "name": "机器人ETF"},
        {"sector": "AI", "symbol": "SH515070", "name": "人工智能ETF"},
        # ---- v1.0.0 扩充（无对应东财板块，用ETF代替） ----
        {"sector": "国债", "symbol": "SH511010", "name": "十年国债ETF"},
        {"sector": "恒生", "symbol": "SZ159920", "name": "恒生ETF"},
        {"sector": "恒科", "symbol": "SH513130", "name": "恒生科技ETF"},
    ]
    # 大盘看板「板块监控」追加的概念/行业监控板块（东方财富板块信源）
    _EM_SECTOR_GROUPS = [
        ["跨境电商"],
        ["液冷服务器", "液冷"],
        ["培育钻石", "钻石培育", "钻石"],
        ["稀土永磁", "稀土"],
        ["贵金属"],
        ["铜"],
        ["白银"],
        ["风电设备", "风电"],
        ["火电设备", "火电"],
        ["文化传媒", "传媒"],
        ["旅游酒店", "旅游概念", "旅游"],
        ["航运港口", "航运"],
        ["IT服务", "软件开发", "软件"],
        ["网络游戏", "云游戏"],
        # ---- v1.0.0 扩充（+15） ----
        ["先进封装", "芯片封装", "封装"],
        ["光纤概念", "光纤光缆", "光缆"],
        ["通信"],
        ["CRO"],
        ["人形机器人", "机器人概念", "机器人"],
        ["纺织服饰", "纺织制造", "纺织"],
        ["消费电子概念", "消费电子"],
        ["乡村振兴"],
        ["新型工业化", "工业互联网", "工业"],
        ["天然气"],
    ]
    _EM_BOARD_FIELDS = "f3,f6,f8,f12,f14,f128,f136"
    _EM_TRACKED_CACHE: list = []
    _EM_TRACKED_CACHE_TS = 0.0
    _EM_LEADER_SYMBOL_CACHE: dict = {}
    _EM_HOSTS = ["2.push2.eastmoney.com", "9.push2.eastmoney.com",
                 "push2delay.eastmoney.com", "push2.eastmoney.com"]
    _EM_HOST_IDX = 0

    @staticmethod
    def _em_clist_page(fs: str, page: int) -> list:
        """东方财富板块分页数据，多镜像主机轮询兜底（部分网络环境 push2 主域被掐断）。"""
        import urllib.parse as _p
        params = {"pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                  "fid": "f3", "fs": fs, "fields": SinaSource._EM_BOARD_FIELDS}
        qs = _p.urlencode(params)
        first_err = None
        for off in range(len(SinaSource._EM_HOSTS)):
            host = SinaSource._EM_HOSTS[(SinaSource._EM_HOST_IDX + off) % len(SinaSource._EM_HOSTS)]
            url = "https://%s/api/qt/clist/get?%s" % (host, qs)
            try:
                req = urllib.request.Request(url, headers={**_UA, "Referer": "https://quote.eastmoney.com/"})
                body = urllib.request.urlopen(req, timeout=8).read()
                data = json.loads(body.decode("utf-8", "ignore"))
                diff = (data.get("data") or {}).get("diff") or []
                if diff:
                    SinaSource._EM_HOST_IDX = SinaSource._EM_HOSTS.index(host)
                    return diff
                return []
            except Exception as e:
                first_err = first_err or e
                continue
        raise (first_err or Exception("all em hosts down"))

    @staticmethod
    def _norm_symbol(code: str) -> str:
        """新浪领涨股代码 → 标准 SH/SZ 符号（sh600519 → SH600519；600519 → SH600519）"""
        code = (code or "").strip().lower()
        if len(code) >= 8 and code.startswith(("sh", "sz", "bj")):
            return code[:2].upper() + code[2:]
        if len(code) >= 6:
            digits = code[-6:]
            return ("SH" if digits[0] in "69" or digits.startswith(("15", "50")) else
                    "BJ" if digits.startswith(("43", "87", "92")) else "SZ") + digits
        return ""

    @staticmethod
    def _em_boards(fs: str) -> list[dict]:
        """东方财富板块列表（概念 m:90+t:3 / 行业 m:90+t:2），每页100自动翻页拉全。"""
        rows = []
        for page in range(1, 6):
            try:
                diff = SinaSource._em_clist_page(fs, page)
            except Exception as e:
                logger.warning(f"em boards {fs} p{page}: {e}")
                break
            if not diff:
                break
            rows.extend(diff)
            if len(diff) < 100:
                break
        return rows

    def _em_sector_groups_rows(self) -> list[dict]:
        """按 _EM_SECTOR_GROUPS 聚合东方财富板块：实时涨跌幅/成交额 + 领涨股。
        板块无 ETF 分时，前端展示实时行情与可点击的领涨股。"""
        import time as _t
        import concurrent.futures
        now = _t.time()
        if self._EM_TRACKED_CACHE and (now - self._EM_TRACKED_CACHE_TS) < 60:
            return self._EM_TRACKED_CACHE
        boards = self._em_boards("m:90+t:3") + self._em_boards("m:90+t:2")
        used = set()
        result: list[dict] = []
        leader_names: set = set()
        for group in self._EM_SECTOR_GROUPS:
            best = None
            for alias in group:
                cands = [b for b in boards if (b.get("f14") or "").strip()
                         and (b.get("f14") or "").strip() not in used
                         and alias in (b.get("f14") or "")]
                if not cands:
                    continue
                if len(alias) <= 2:
                    exact = [b for b in cands if (b.get("f14") or "").strip() == alias]
                    if exact:
                        cands = exact
                best = cands[0]
                break
            if not best:
                continue
            name = (best.get("f14") or "").strip()
            name = re.sub(r"[ⅠⅡⅢⅣⅤ]+$", "", name).strip()
            used.add(name)
            leader = (best.get("f128") or "").strip()
            if leader:
                leader_names.add(leader)
            result.append({
                "sector": name, "name": name, "symbol": best.get("f12") or "",
                "price": 0, "change_pct": round(_f(best.get("f3")), 2),
                "amount": _f(best.get("f6")), "change": 0,
                "is_etf": False, "leader_name": leader, "leader_symbol": "", "count": 0,
            })
        if leader_names:
            syms: dict = {}

            def resolve(n: str) -> None:
                hit = self._EM_LEADER_SYMBOL_CACHE.get(n)
                if hit is not None:
                    syms[n] = hit
                    return
                try:
                    import urllib.parse as _p
                    url = ("https://searchapi.eastmoney.com/api/suggest/get?input=%s&type=14"
                           "&token=D43BF722C8E33BDC906FB84D85E326E8&count=5" % _p.quote(n))
                    req = urllib.request.Request(url, headers={**_UA, "Referer": "https://www.eastmoney.com/"})
                    body = urllib.request.urlopen(req, timeout=8).read()
                    data = json.loads(body.decode("utf-8", "ignore"))
                    for it in ((data.get("QuotationCodeTable") or {}).get("Data") or []):
                        code = str(it.get("Code") or "")
                        if len(code) == 6 and code.isdigit():
                            syms[n] = to_standard_symbol(code)
                            break
                except Exception as e:
                    logger.warning(f"em leader symbol {n}: {e}")
                syms.setdefault(n, "")

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                list(ex.map(resolve, list(leader_names)))
            for k, v in syms.items():
                self._EM_LEADER_SYMBOL_CACHE[k] = v
            for r in result:
                r["leader_symbol"] = syms.get(r.get("leader_name") or "", "")
        self._EM_TRACKED_CACHE = result
        self._EM_TRACKED_CACHE_TS = now
        return result

    # ===================== 东财板块资金流（真实主力净流入/流出） =====================
    _EM_FLOW_FIELDS = "f3,f6,f8,f12,f14,f62,f66,f72,f78,f84,f128,f136,f140,f141,f164,f184,f104,f105"

    @staticmethod
    def _em_json(url: str, timeout: float = 8.0) -> dict:
        req = urllib.request.Request(url, headers={**_UA, "Referer": "https://quote.eastmoney.com/"})
        body = urllib.request.urlopen(req, timeout=timeout).read()
        return json.loads(body.decode("utf-8", "ignore"))

    @classmethod
    def _em_clist_all(cls, fs: str, fields: str, pages: int = 6, fid: str = "f3", pz: int = 100) -> list:
        """东财板块列表分页拉全（多镜像主机轮询兜底）。"""
        import urllib.parse as _p
        import time as _t
        out = []
        page = 1
        while page <= pages:
            params = {"pn": page, "pz": pz, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                      "fid": fid, "fs": fs, "fields": fields}
            qs = _p.urlencode(params)
            diff = []
            for off in range(len(SinaSource._EM_HOSTS)):
                host = SinaSource._EM_HOSTS[(SinaSource._EM_HOST_IDX + off) % len(SinaSource._EM_HOSTS)]
                try:
                    data = SinaSource._em_json("https://%s/api/qt/clist/get?%s" % (host, qs))
                    diff = (data.get("data") or {}).get("diff") or []
                    if diff:
                        SinaSource._EM_HOST_IDX = SinaSource._EM_HOSTS.index(host)
                        break
                except Exception:
                    continue
            if not diff:
                break
            out.extend(diff)
            if len(diff) < pz:
                break
            page += 1
        return out

    _EM_FLOW_BOARD_CACHE: dict = {}
    _EM_FLOW_BOARD_TS = 0.0

    def _em_flow_boards(self, fs: str) -> list:
        """行业/概念板块 + 主力净流入额(f62)/占比(f184)/5日(f164)/领涨股(f128,f140,f136)。"""
        import time as _t
        now = _t.time()
        if self._EM_FLOW_BOARD_CACHE.get(fs) and (now - self._EM_FLOW_BOARD_TS) < 90:
            return self._EM_FLOW_BOARD_CACHE[fs]
        pages = 6 if fs.endswith(":t:3") else 2
        rows = self._em_clist_all(fs, self._EM_FLOW_FIELDS, pages=pages, fid="f62")
        self._EM_FLOW_BOARD_CACHE = {fs: rows}
        self._EM_FLOW_BOARD_TS = now
        return rows

    _EM_CONST_CACHE: dict = {}
    _EM_CONST_TS = 0.0

    @classmethod
    def _em_constituents(cls, code: str) -> list:
        """板块成分股（fs=b:BKn）。push2his 可达，含 市值f20/换手f8/主力净额f62/涨跌幅f3。"""
        import time as _t
        import urllib.parse as _p
        now = _t.time()
        if cls._EM_CONST_CACHE.get(code) and (now - cls._EM_CONST_TS) < 300:
            return cls._EM_CONST_CACHE[code]
        params = {"pn": 1, "pz": 500, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                  "fid": "f20", "fs": "b:" + code, "fields": "f3,f8,f12,f14,f20,f62"}
        qs = _p.urlencode(params)
        rows = []
        hosts = ["push2his.eastmoney.com"] + SinaSource._EM_HOSTS
        for host in hosts:
            try:
                data = SinaSource._em_json("https://%s/api/qt/clist/get?%s" % (host, qs))
                rows = (data.get("data") or {}).get("diff") or []
                if rows:
                    break
            except Exception:
                continue
        cls._EM_CONST_CACHE = {code: rows}
        cls._EM_CONST_TS = now
        return rows

    @staticmethod
    def _em_datacenter(report_name: str, filter_str: str, page_size: int = 50,
                       sort_columns: str = None, columns: str = "ALL") -> list:
        """东财数据中心报表 API（龙虎榜/财务报表）。filter 内部中文/引号会被正确转义。"""
        import urllib.parse as _p
        params = {"reportName": report_name, "columns": columns,
                  "filter": filter_str, "pageNumber": 1, "pageSize": page_size}
        if sort_columns:
            params["sortColumns"] = sort_columns
            params["sortTypes"] = "-1"
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get?" + _p.urlencode(params)
        try:
            d = SinaSource._em_json(url, timeout=10)
            return ((d.get("result") or {}).get("data")) or []
        except Exception as e:
            logger.warning("em datacenter %s failed: %s" % (report_name, e))
            return []

    @staticmethod
    def _em_leader_symbol(f140) -> str:
        s = str(f140 or "").strip()
        if s.isdigit() and len(s) == 6:
            return to_standard_symbol(s)
        return ""

    # ---------- 龙虎榜（东财每日明细） ----------
    _EM_DT_CACHE: Optional[list] = None
    _EM_DT_TS = 0.0

    def get_dragon_tiger(self, limit: int = 50) -> list[dict]:
        import time as _t
        from datetime import date as _d, timedelta as _td
        now = _t.time()
        if self._EM_DT_CACHE is not None and (now - self._EM_DT_TS) < 600:
            return self._EM_DT_CACHE[:limit]
        # 龙虎榜当日数据收盘后才发布，取最近一个交易日（优先当天，最多回退3天）
        rows = []
        for back in range(4):
            day = (_d.today() - _td(days=back)).isoformat()
            if _d.fromisoformat(day).weekday() >= 5:
                continue
            rows = self._em_datacenter("RPT_BILLBOARD_DAILYDETAILS", "(TRADE_DATE='%s')" % day, page_size=80)
            if rows:
                break
        out = []
        for r in rows:
            try:
                code = str(r.get("SECURITY_CODE") or "")
                if not (code.isdigit() and len(code) == 6):
                    continue
                net = r.get("TOTAL_NET")
                if net is None:
                    net = r.get("ACTUAL_NET_AMOUNT")
                if net is None:
                    net = r.get("NET_AMOUNT")
                turnover = r.get("TURNOVERRATE")
                if turnover is None:
                    turnover = r.get("TURNOVER_RATE")
                out.append({
                    "symbol": to_standard_symbol(code),
                    "name": r.get("SECURITY_NAME_ABBR") or "",
                    "date": str((r.get("TRADE_DATE") or ""))[:10],
                    "close": round(_f(r.get("CLOSE_PRICE")), 2),
                    "change_pct": round(_f(r.get("CHANGE_RATE")), 2),
                    "turnover_rate": round(_f(turnover), 2),
                    "net_amount": _f(net),
                    "buy_amount": _f(r.get("TOTAL_BUY")),
                    "sell_amount": _f(r.get("TOTAL_SELL")),
                    "reason": (r.get("EXPLANATION") or "").strip(),
                    "rank": r.get("RANK"),
                })
            except Exception:
                continue
        self._EM_DT_CACHE = out
        self._EM_DT_TS = now
        return out[:limit]

    # ---------- 监管异动：重点监控池 + 日内严重异常波动（东财零鉴权） ----------
    _MONITOR_MARKET = {"1": "SH", "0": "SZ", "B": "BJ"}
    _ANOMALY_RULES = {
        1: "主板连续10个交易日内4次同向异常波动",
        2: "创业板连续10个交易日内3次同向异常波动",
        3: "科创板连续10个交易日内3次同向异常波动",
        4: "10日收盘价涨跌幅偏离值累计达+100%",
        5: "10日收盘价涨跌幅偏离值累计达-50%",
        6: "30日收盘价涨跌幅偏离值累计达+200%",
        7: "30日收盘价涨跌幅偏离值累计达-70%",
        8: "北交所连续10个交易日内3次同向异常波动",
        40: "10日收盘价涨跌幅偏离值累计达+150%",
        50: "10日收盘价涨跌幅偏离值累计达-60%",
        60: "30日收盘价涨跌幅偏离值累计达+300%",
        70: "30日收盘价涨跌幅偏离值累计达-75%",
    }
    _ANOMALY_HQ = {"team": "h5", "product": "EastMoney", "client": "WAP",
                   "version": "9001", "name": "WAP", "user": "123"}
    _EM_MONITOR_CACHE: Optional[list] = None
    _EM_MONITOR_TS = 0.0
    _EM_ANOMALY_CACHE: Optional[dict] = None
    _EM_ANOMALY_TS = 0.0

    @staticmethod
    def _em_cn_today() -> str:
        from datetime import datetime, timezone as _tz
        return datetime.now(_tz(timedelta(hours=8))).date().isoformat()

    @staticmethod
    def _em_anomaly_market(code, m, board) -> str:
        c = str(code or "")
        if c.startswith(("4", "8", "92")) or int(_f(board)) == 8:
            return "BJ"
        return "SH" if int(_f(m)) == 1 else "SZ"

    def get_stock_monitor(self) -> list[dict]:
        """东财重点监控池：交易所风险警示 / 重点监控名单，仅保留今天仍在监控窗口内的标的。"""
        import time as _t
        now = _t.time()
        if self._EM_MONITOR_CACHE is not None and (now - self._EM_MONITOR_TS) < 600:
            return self._EM_MONITOR_CACHE
        url = "https://mobappconfig.securities.eastmoney.com/emcfg/stock_monitor.json"
        try:
            req = urllib.request.Request(url, headers={**_UA, "Referer": "https://vipmoney.eastmoney.com/"})
            rows = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")) or []
        except Exception as e:
            logger.warning("em stock monitor failed: %s" % e)
            return []
        today = self._em_cn_today()
        out = []
        for x in rows:
            start = (x.get("VALIDATESTARTDATE") or "").strip()[:10]
            end = (x.get("VALIDATEENDDATE") or "").strip()[:10]
            if not (start and end and start <= today <= end):
                continue
            code = str(x.get("STKCODE") or "").strip()
            mkt = self._MONITOR_MARKET.get(str(x.get("MARKET") or "").upper(), "SZ")
            days_left = 0
            try:
                days_left = (date.fromisoformat(end) - date.fromisoformat(today)).days
            except ValueError:
                pass
            out.append({
                "symbol": ("%s%s" % (mkt, code)) if code else "",
                "code": code,
                "name": (x.get("STKNAME") or "").strip(),
                "market": mkt,
                "start": start, "end": end, "days_left": max(days_left, 0),
            })
        out.sort(key=lambda r: r["days_left"])
        self._EM_MONITOR_CACHE = out
        self._EM_MONITOR_TS = now
        return out

    def get_price_anomaly(self, max_items: int = 50) -> dict:
        """东财日内异动池（交易所"严重异常波动"口径）：list 明细 + count 按标的聚合。"""
        import time as _t
        import urllib.parse as _p
        now = _t.time()
        if self._EM_ANOMALY_CACHE is not None and (now - self._EM_ANOMALY_TS) < 600:
            return self._EM_ANOMALY_CACHE
        base = "https://dycalchis.eastmoney.com/price-anomaly"
        headers = {**_UA, "Referer": "https://vipmoney.eastmoney.com/"}

        def _freq(path, page_size, page_no=1):
            params = dict(self._ANOMALY_HQ)
            params.update({"pageSize": str(page_size), "pageNo": str(page_no)})
            try:
                req = urllib.request.Request("%s/%s?%s" % (base, path, _p.urlencode(params)), headers=headers)
                d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore"))
            except Exception as e:
                logger.warning("em price anomaly %s failed: %s" % (path, e))
                return None
            if not isinstance(d, dict) or d.get("result") != 0:
                logger.warning("em price anomaly %s refused: %s" % (path, d.get("msg") if isinstance(d, dict) else d))
                return None
            return d

        list_d = _freq("list", 200) or {}
        count_d = _freq("count", 50) or {}
        items = []
        for x in list_d.get("data") or []:
            e = x.get("e")
            board = int(_f(x.get("s")))
            key = (e * 10) if (board == 6 and e in (4, 5, 6, 7)) else e
            code = str(x.get("c") or "")
            mkt = self._em_anomaly_market(code, x.get("m"), x.get("s"))
            items.append({
                "symbol": ("%s%s" % (mkt, code)) if code else "",
                "code": code,
                "name": (x.get("n") or "").strip(),
                "market": mkt,
                "change_pct": round(_f(x.get("a")), 2),
                "deviation": round(_f(x.get("x")), 2),
                "days": int(_f(x.get("d"))),
                "threshold": round(_f(x.get("t")), 2),
                "rule_code": key,
                "rule": self._ANOMALY_RULES.get(key, "未知规则"),
            })
        agg = []
        for x in count_d.get("data") or []:
            code = str(x.get("c") or "")
            mkt = self._em_anomaly_market(code, x.get("m"), x.get("s"))
            agg.append({
                "symbol": ("%s%s" % (mkt, code)) if code else "",
                "code": code,
                "name": (x.get("n") or "").strip(),
                "market": mkt,
                "price": round(_f(x.get("p")), 2),
                "change_pct": round(_f(x.get("a")), 2),
                "times": int(_f(x.get("t"))),
                "deviation": round(_f(x.get("x")), 2),
                "days": int(_f(x.get("d"))),
            })
        agg.sort(key=lambda r: -r["times"])
        out = {"date": str(list_d.get("date") or count_d.get("date") or "")[:10],
               "items": items[:max_items], "count": agg[:max_items]}
        self._EM_ANOMALY_CACHE = out
        self._EM_ANOMALY_TS = now
        return out

    # ---------- 投资日历：未来解禁 + 分红除权（东财数据中心） ----------
    _EM_CALENDAR_CACHE: Optional[dict] = None
    _EM_CALENDAR_TS = 0.0

    def get_invest_calendar(self, days_ahead: int = 45) -> dict:
        """未来限售解禁 + 分红除权日程。unlocks: 解禁(市值万/亿) / dividends: 分红除权。"""
        import time as _t
        now = _t.time()
        if self._EM_CALENDAR_CACHE is not None and (now - self._EM_CALENDAR_TS) < 600:
            return self._EM_CALENDAR_CACHE
        today = self._em_cn_today()
        end = (date.today() + timedelta(days=days_ahead)).isoformat()
        unlocks = []
        try:
            rows = self._em_datacenter("RPT_LIFT_STAGE",
                                       "(FREE_DATE>='%s')(FREE_DATE<='%s')" % (today, end),
                                       page_size=100, sort_columns="FREE_DATE")
            for r in rows:
                free_date = (r.get("FREE_DATE") or "").strip()[:10]
                if not (today <= free_date <= end):
                    continue
                code = str(r.get("SECURITY_CODE") or "")
                if not (code.isdigit() and len(code) == 6):
                    continue
                mc = _f(r.get("LIFT_MARKET_CAP"))
                unlocks.append({
                    "symbol": to_standard_symbol(code),
                    "code": code,
                    "name": r.get("SECURITY_NAME_ABBR") or "",
                    "date": free_date,
                    "type": r.get("FREE_SHARES_TYPE") or "",
                    "shares_wan": round(_f(r.get("CURRENT_FREE_SHARES")), 2),
                    "market_cap_wan": round(mc, 2),
                    "market_cap_yi": round(mc / 10000.0, 2),
                    "ratio": round(_f(r.get("FREE_RATIO")) * 100, 2),
                })
        except Exception as e:
            logger.warning("invest calendar unlocks failed: %s" % e)
        dividends = []
        try:
            rows = self._em_datacenter("RPT_SHAREBONUS_DET",
                                       "(EX_DIVIDEND_DATE>='%s')(EX_DIVIDEND_DATE<='%s')" % (today, end),
                                       page_size=100, sort_columns="EX_DIVIDEND_DATE")
            for r in rows:
                ex_date = (r.get("EX_DIVIDEND_DATE") or "").strip()[:10]
                if not (today <= ex_date <= end):
                    continue
                code = str(r.get("SECURITY_CODE") or "")
                if not (code.isdigit() and len(code) == 6):
                    continue
                dividends.append({
                    "symbol": to_standard_symbol(code),
                    "code": code,
                    "name": r.get("SECURITY_NAME_ABBR") or "",
                    "date": ex_date,
                    "plan": r.get("IMPL_PLAN_PROFILE") or "",
                    "bonus": round(_f(r.get("PRETAX_BONUS_RMB")), 4),
                    "progress": r.get("ASSIGN_PROGRESS") or "",
                    "record_date": (r.get("EQUITY_RECORD_DATE") or "").strip()[:10],
                })
        except Exception as e:
            logger.warning("invest calendar dividends failed: %s" % e)
        out = {"date": today, "unlocks": unlocks, "dividends": dividends}
        self._EM_CALENDAR_CACHE = out
        self._EM_CALENDAR_TS = now
        return out

    # ---------- 龙虎榜营业部席位整合（本地游资打标） ----------
    _EM_SEAT_TAGS = [
        ("拉萨天团", ["拉萨"]),
        ("温州帮", ["温州", "乐清"]),
        ("杭州帮", ["杭州"]),
        ("成都帮", ["成都"]),
        ("佛山帮", ["佛山"]),
        ("宁波敢死队", ["宁波解放南路", "宁波彩虹北路"]),
        ("章盟主", ["上海江苏路"]),
        ("赵老哥", ["绍兴"]),
        ("炒股养家", ["宛平南路"]),
        ("小鳄鱼", ["南京太平南路"]),
        ("溧阳路", ["溧阳路"]),
        ("上海超短", ["上海分公司"]),
    ]
    _EM_SEATS_CACHE: Optional[list] = None
    _EM_SEATS_TS = 0.0

    @staticmethod
    def _seat_tag(name: str) -> str:
        n = name or ""
        if "机构专用" in n:
            return "机构专用"
        if "沪股通" in n or "深股通" in n:
            return "北向资金"
        for tag, kws in SinaSource._EM_SEAT_TAGS:
            if any(k in n for k in kws):
                return tag
        return ""

    def get_dragon_tiger_seats(self, trade_date: str = None, limit: int = 300) -> list[dict]:
        """龙虎榜当日营业部席位明细 + 本地游资打标（最近交易日自动回退）。"""
        import time as _t
        now = _t.time()
        if trade_date and self._EM_SEATS_CACHE is not None and (now - self._EM_SEATS_TS) < 600 \
                and self._EM_SEATS_CACHE and self._EM_SEATS_CACHE[0].get("date") == trade_date:
            return self._EM_SEATS_CACHE[:limit]
        rows = []
        day = trade_date
        if not day:
            for back in range(4):
                d = (date.today() - timedelta(days=back)).isoformat()
                if date.fromisoformat(d).weekday() >= 5:
                    continue
                rows = self._em_datacenter("RPT_OPERATEDEPT_TRADE_DETAILSNEW",
                                           "(TRADE_DATE='%s')" % d, page_size=300)
                if rows:
                    day = d
                    break
        else:
            rows = self._em_datacenter("RPT_OPERATEDEPT_TRADE_DETAILSNEW",
                                       "(TRADE_DATE='%s')" % day, page_size=300)
        out = []
        for r in rows:
            code = str(r.get("SECURITY_CODE") or "")
            if not (code.isdigit() and len(code) == 6):
                continue
            name = r.get("OPERATEDEPT_NAME") or ""
            out.append({
                "date": str((r.get("TRADE_DATE") or ""))[:10],
                "symbol": to_standard_symbol(code),
                "code": code,
                "stock_name": r.get("SECURITY_NAME_ABBR") or "",
                "seat": r.get("OPERATEDEPT_CODE") or "",
                "seat_name": name,
                "tag": self._seat_tag(name),
                "buy": round(_f(r.get("ACT_BUY")), 2),
                "sell": round(_f(r.get("ACT_SELL")), 2),
                "net": round(_f(r.get("NET_AMT")), 2),
                "reason": (r.get("EXPLANATION") or "").strip(),
                "d1": round(_f(r.get("D1_CLOSE_ADJCHRATE")), 2) if r.get("D1_CLOSE_ADJCHRATE") is not None else None,
                "d3": round(_f(r.get("D3_CLOSE_ADJCHRATE")), 2) if r.get("D3_CLOSE_ADJCHRATE") is not None else None,
                "d5": round(_f(r.get("D5_CLOSE_ADJCHRATE")), 2) if r.get("D5_CLOSE_ADJCHRATE") is not None else None,
            })
        self._EM_SEATS_CACHE = out
        self._EM_SEATS_TS = now
        return out[:limit]

    # ---------- 板块资金流（真实主力净流入，覆盖旧的“涨跌近似口径”） ----------
    _EM_SECTORFLOW_CACHE: Optional[list] = None
    _EM_SECTORFLOW_TS = 0.0

    def get_sector_money_flow(self) -> list[dict]:
        """板块主力净流入：合并行业+概念板块按 |主力净额| 排序前12，
        并附 涨停家数 / 市值龙头前三 / 人气票（换手最高） / 5日主力净额。"""
        import time as _t
        now = _t.time()
        if self._EM_SECTORFLOW_CACHE and (now - self._EM_SECTORFLOW_TS) < 120:
            return self._EM_SECTORFLOW_CACHE
        try:
            ind = self._em_flow_boards("m:90+t:2")
            con = self._em_flow_boards("m:90+t:3")
        except Exception as e:
            logger.warning("em sector money flow boards failed: %s" % e)
            return []
        boards = sorted(ind + con, key=lambda r: abs(_f(r.get("f62"))), reverse=True)[:12]
        result = []
        seen_names = set()
        for b in boards:
            code = (b.get("f12") or "").strip()
            bname = (b.get("f14") or "").strip()
            if not bname or bname in seen_names:
                continue
            seen_names.add(bname)
            row = {
                "sector_name": bname,
                "symbol": code, "source": "eastmoney",
                "net_inflow": _f(b.get("f62")),
                "net_ratio": round(_f(b.get("f184")), 2),
                "net_5d": _f(b.get("f164")),
                "change_pct": _f(b.get("f3")),
                "amount": _f(b.get("f6")),
                "ex_super_net": _f(b.get("f66")), "big_net": _f(b.get("f72")),
                "mid_net": _f(b.get("f78")), "small_net": _f(b.get("f84")),
                "leader": (b.get("f128") or "").strip(),
                "leader_symbol": self._em_leader_symbol(b.get("f140")),
                "count": int(_f(b.get("f104")) + _f(b.get("f105"))) if b.get("f104") is not None else 0,
            }
            try:
                cons = self._em_constituents(code)
                if cons:
                    row["constituents"] = len(cons)
                    row["limit_up_count"] = sum(1 for c in cons if _f(c.get("f3")) >= 9.8)
                    top = sorted(cons, key=lambda c: -(c.get("f20") or 0))
                    row["mkt_cap_top"] = [{
                        "name": (c.get("f14") or "").strip(),
                        "symbol": to_standard_symbol(str(c.get("f12") or "")) if len(str(c.get("f12") or "")) == 6 else "",
                        "mkt_cap": _f(c.get("f20")), "change_pct": _f(c.get("f3")),
                    } for c in top[:3]]
                    hot = sorted(cons, key=lambda c: -(c.get("f8") or 0))
                    h = hot[0] if hot else None
                    if h:
                        row["hot_pick"] = {
                            "name": (h.get("f14") or "").strip(),
                            "symbol": to_standard_symbol(str(h.get("f12") or "")),
                            "turnover": round(_f(h.get("f8")), 2),
                        }
            except Exception as e:
                logger.warning("constituents enrich %s failed: %s" % (code, e))
            result.append(row)
        self._EM_SECTORFLOW_CACHE = result
        self._EM_SECTORFLOW_TS = now
        return result

    # ---------- 行业/概念 资金流入流出 TOP（真实主力净额） ----------
    def get_sector_flow_top(self, top: int = 5) -> dict:
        out = {"industries": {"in": [], "out": []}, "concepts": {"in": [], "out": []}}
        try:
            ind = self._em_flow_boards("m:90+t:2")
            con = self._em_flow_boards("m:90+t:3")
        except Exception as e:
            logger.warning("em flow top failed: %s" % e)
            return out

        def _fmt(r: dict) -> dict:
            return {
                "name": (r.get("f14") or "").strip(),
                "code": (r.get("f12") or "").strip(),
                "net_inflow": round(_f(r.get("f62")) / 1e8, 2),
                "net_ratio": round(_f(r.get("f184")), 2),
                "amount": round(_f(r.get("f6")) / 1e8, 2),
                "change_pct": _f(r.get("f3")),
                "leader": (r.get("f128") or "").strip(),
                "leader_symbol": self._em_leader_symbol(r.get("f140")),
                "count": int(_f(r.get("f104")) + _f(r.get("f105"))) if r.get("f104") is not None else 0,
            }

        for fs, key in (("m:90+t:2", "industries"), ("m:90+t:3", "concepts")):
            rows = ind if key == "industries" else con

            def _dedup(sorted_rows):
                seen = set()
                out = []
                for r in sorted_rows:
                    nm = (r.get("f14") or "").strip()
                    if not nm or nm in seen:
                        continue
                    seen.add(nm)
                    out.append(r)
                return out

            inflow = _dedup(sorted([r for r in rows if _f(r.get("f62")) > 0],
                                   key=lambda r: _f(r.get("f62")), reverse=True))[:top]
            outflow = _dedup(sorted([r for r in rows if _f(r.get("f62")) < 0],
                                    key=lambda r: _f(r.get("f62"))))[:top]
            out[key]["in"] = [_fmt(r) for r in inflow]
            out[key]["out"] = [_fmt(r) for r in outflow]
        return out

    # ---------- 财务三大报表（东财数据中心，真实） ----------
    _EM_FIN_CACHE: dict = {}
    _EM_FIN_TS = 0.0

    def get_financial(self, symbol: str, limit: int = 8) -> list[dict]:
        import time as _t
        now = _t.time()
        if self._EM_FIN_CACHE.get(symbol) and (now - self._EM_FIN_TS) < 3600:
            return self._EM_FIN_CACHE[symbol][:limit]
        code = symbol[-6:]
        rows = self._em_datacenter("RPT_LICO_FN_CPD", '(SECURITY_CODE="%s")' % code, page_size=20,
                                   sort_columns="REPORTDATE")

        def _g(r, k):
            v = r.get(k)
            return round(_f(v), 2) if v is not None and str(v) not in ("-", "--") else None

        out = []
        for r in rows:
            out.append({
                "report_date": str((r.get("REPORTDATE") or ""))[:10],
                "update_date": str((r.get("UPDATE_DATE") or ""))[:10],
                "notice_date": str((r.get("NOTICE_DATE") or ""))[:10],
                "revenue": _f(r.get("TOTAL_OPERATE_INCOME")),
                "revenue_yoy": _g(r, "YSTZ"),
                "net_profit": _f(r.get("PARENT_NETPROFIT")),
                "net_profit_yoy": _g(r, "SJLTZ"),
                "eps": _g(r, "BASIC_EPS"),
                "deduct_eps": _g(r, "DEDUCT_BASIC_EPS"),
                "roe": _g(r, "WEIGHTAVG_ROE"),
                "bps": _g(r, "BPS"),
                "ocf_per_share": _g(r, "MGJYXJJE"),
                "gross_margin": _g(r, "XSMLL"),
                "revenue_qoq": _g(r, "YSHZ"),
                "net_qoq": _g(r, "SJLHZ"),
                "industry": (r.get("PUBLISHNAME") or "").strip(),
                "assign": (r.get("ASSIGNDSCRPT") or "").strip(),
            })
        self._EM_FIN_CACHE = {symbol: out}
        self._EM_FIN_TS = now
        return out[:limit]

    _EM_RANK_CACHE: dict = {}
    _EM_RANK_TS = 0.0

    def get_industry_ranking(self, symbol: str) -> dict:
        """行业对比/排名：用东财财务报表按行业名拉取全部同行，按净利增速/ROE 排名。"""
        import time as _t
        from datetime import date as _d
        now = _t.time()
        key = symbol + ":" + _d.today().isoformat()
        cached = self._EM_RANK_CACHE.get(key)
        if cached and (now - self._EM_RANK_TS) < 3600:
            return cached
        fin = self.get_financial(symbol, limit=1)
        industry = (fin[0].get("industry") or "") if fin else ""
        empty = {"industry": industry, "available": False, "peers_count": 0}
        if not industry:
            self._EM_RANK_CACHE = {key: empty}
            self._EM_RANK_TS = now
            return empty
        rows = self._em_datacenter("RPT_LICO_FN_CPD", '(PUBLISHNAME="%s")' % industry, page_size=400,
                                   sort_columns="REPORTDATE")
        peers = []
        target = symbol[-6:]
        for r in rows:
            code = str(r.get("SECURITY_CODE") or "")
            if not (code.isdigit() and len(code) == 6):
                continue
            peers.append({
                "code": code, "symbol": to_standard_symbol(code),
                "name": (r.get("SECURITY_NAME_ABBR") or "").strip(),
                "report_date": str((r.get("REPORTDATE") or ""))[:10],
                "revenue_yoy": _f(r.get("YSTZ")),
                "net_profit_yoy": _f(r.get("SJLTZ")),
                "roe": _f(r.get("WEIGHTAVG_ROE")),
                "eps": _f(r.get("BASIC_EPS")),
                "gross_margin": _f(r.get("XSMLL")),
            })
        growth = [p for p in peers if p.get("net_profit_yoy") is not None]
        roe = [p for p in peers if p.get("roe") is not None]
        growth.sort(key=lambda p: -(p["net_profit_yoy"] or 0))
        roe.sort(key=lambda p: -(p["roe"] or 0))
        g_idx = next((i for i, p in enumerate(growth) if p["code"] == target), None)
        r_idx = next((i for i, p in enumerate(roe) if p["code"] == target), None)

        def _median(arr):
            if not arr:
                return None
            vals = sorted(arr)
            n = len(vals)
            if n % 2:
                return round(vals[n // 2], 2)
            return round((vals[n // 2 - 1] + vals[n // 2]) / 2, 2)

        result = {
            "industry": industry, "available": True,
            "peers_count": len(peers),
            "target": {
                "rank_by_growth": (g_idx + 1) if g_idx is not None else None,
                "rank_by_roe": (r_idx + 1) if r_idx is not None else None,
                "total_by_growth": len(growth), "total_by_roe": len(roe),
            },
            "median_growth": _median([p["net_profit_yoy"] for p in peers if p.get("net_profit_yoy") is not None]),
            "median_roe": _median([p["roe"] for p in peers if p.get("roe") is not None]),
            "top_growth": growth[:8],
            "top_roe": roe[:8],
        }
        self._EM_RANK_CACHE = {key: result}
        self._EM_RANK_TS = now
        return result

    _EM_CHAIN_CACHE: dict = {}
    _EM_CHAIN_TS = 0.0

    @staticmethod
    def _em_board_quote(code: str) -> Optional[dict]:
        """板块自身行情+主力净流入（ulist 直取单板块，fs=b:BKn 仅返回成分股）。"""
        import urllib.parse as _pp
        fields = "f2,f3,f4,f6,f12,f14,f62,f66,f72,f78,f84,f104,f105,f128,f136,f140,f141,f184"
        qs = _pp.urlencode({"fltt": 2, "invt": 2, "secids": "90." + code, "fields": fields})
        for host in SinaSource._EM_HOSTS:
            try:
                d = SinaSource._em_json("https://%s/api/qt/ulist.np/get?%s" % (host, qs))
                diff = (d.get("data") or {}).get("diff") or []
                if diff:
                    return diff[0]
            except Exception:
                continue
        return None

    def get_industry_chain(self, symbol: str) -> dict:
        """产业链：行业板块(主力净额/领涨) + 板块成分(市值TOP) + 所属概念板块(涨幅/净额/领涨)。"""
        import time as _t
        now = _t.time()
        if self._EM_CHAIN_CACHE.get(symbol) and (now - self._EM_CHAIN_TS) < 600:
            return self._EM_CHAIN_CACHE[symbol]
        result = {"industry": None, "peers": [], "concepts": []}
        try:
            sector = self.get_stock_sector(symbol)
            # 行业板块代码：EM 个股行情 f198
            board_code = ""
            secid = ("1." if symbol[-6:].startswith("6") else "0.") + symbol[-6:]
            for host in SinaSource._EM_HOSTS:
                try:
                    d = SinaSource._em_json("https://%s/api/qt/stock/get?secid=%s&fltt=2&invt=2&fields=f198" % (host, secid))
                    bc = ((d.get("data") or {}).get("f198") or "")
                    if bc:
                        board_code = bc
                        break
                except Exception:
                    continue
            ind_rows = self._em_flow_boards("m:90+t:2")

            def _find_board(rows, code=None, name=None):
                for b in rows:
                    if code and (b.get("f12") or "") == code:
                        return b
                    if name and (b.get("f14") or "").strip().lower() == (name or "").strip().lower():
                        return b
                return None

            # 板块自身快照：优先 ulist 直取（fs=b:BK 是成分股列表，部分行业/概念不在 flow 列表前200）
            board = None
            if board_code:
                q = self._em_board_quote(board_code)
                if q and (q.get("f12") or "") == board_code:
                    board = q
            if board is None:
                board = (
                    _find_board(ind_rows, code=board_code)
                    or _find_board(ind_rows, name=(sector.get("industry") or "").strip())
                )
            if board:
                result["industry"] = {
                    "code": board.get("f12") or "", "name": (board.get("f14") or "").strip(),
                    "change_pct": _f(board.get("f3")), "net_inflow": round(_f(board.get("f62")) / 1e8, 2),
                    "net_ratio": round(_f(board.get("f184")), 2),
                    "amount": round(_f(board.get("f6")) / 1e8, 2),
                    "leader": (board.get("f128") or "").strip(),
                    "leader_symbol": self._em_leader_symbol(board.get("f140")),
                }
                try:
                    cons = self._em_constituents(board.get("f12") or "")
                    top = sorted(cons, key=lambda c: -(c.get("f20") or 0))[:10]
                    result["peers"] = [{
                        "symbol": to_standard_symbol(str(c.get("f12") or "")),
                        "name": (c.get("f14") or "").strip(),
                        "mkt_cap": round(_f(c.get("f20")) / 1e8, 1),
                        "change_pct": _f(c.get("f3")),
                        "turnover": round(_f(c.get("f8")), 2),
                        "net_inflow": round(_f(c.get("f62")) / 1e8, 2),
                    } for c in top]
                    result["peers"][0]["role"] = "市值龙头"
                    if len(result["peers"]) > 1:
                        result["peers"][1]["role"] = "龙二"
                    if len(result["peers"]) > 2:
                        result["peers"][2]["role"] = "龙三"
                except Exception as e:
                    logger.warning("industry chain peers failed: %s" % e)
            # 概念板块（按名称精确匹配，取涨幅/净额/领涨）
            con_rows = self._em_flow_boards("m:90+t:3")
            names = {c.strip() for c in (sector.get("concepts") or []) if c.strip()}
            con_by_name = {}
            for b in con_rows:
                nm = (b.get("f14") or "").strip()
                if nm in names:
                    con_by_name[nm] = b
            for nm in [n for n in names if n in con_by_name][:12]:
                b = con_by_name[nm]
                result["concepts"].append({
                    "name": nm, "code": b.get("f12") or "",
                    "change_pct": _f(b.get("f3")),
                    "net_inflow": round(_f(b.get("f62")) / 1e8, 2),
                    "amount": round(_f(b.get("f6")) / 1e8, 2),
                    "leader": (b.get("f128") or "").strip(),
                    "leader_symbol": self._em_leader_symbol(b.get("f140")),
                })
        except Exception as e:
            logger.warning("industry chain failed %s: %s" % (symbol, e))
        self._EM_CHAIN_CACHE = {symbol: result}
        self._EM_CHAIN_TS = now
        return result

    # ---------- A股全量名称（腾讯排行，供本地名称库） ----------
    _NAMES_CACHE: Optional[list] = None
    _NAMES_TS = 0.0

    def _all_stock_names(self, force: bool = False) -> list[dict]:
        import time as _t
        now = _t.time()
        if self._NAMES_CACHE and not force and (now - self._NAMES_TS) < 12 * 3600:
            return self._NAMES_CACHE
        rows = []
        try:
            import concurrent.futures
            payload0 = json.loads(_open(
                "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
                "?board_code=aStock&sort_type=price&direct=down&offset=0&count=200",
                {**_UA, "Referer": "https://gu.qq.com"}, timeout=8).decode("utf-8", "ignore"))
            first = (payload0.get("data", {}).get("rank_list") or [])
            total = int((payload0.get("data", {}).get("total") or len(first)) or 0)
            pages = max(1, int(total / 200) + 1)
            parts = [first]
            offsets = [p * 200 for p in range(1, pages)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                fetched = list(ex.map(self._tencent_rank_page, offsets))
            for part in fetched:
                if not part:
                    break
                parts.append(part)
            seen = set()
            out = []
            for r in [x for part in parts for x in part]:
                code = (r.get("code") or "").lower()
                name = (r.get("name") or "").strip()
                if not code or code in seen or not (3 <= len(name) <= 16):
                    continue
                seen.add(code)
                out.append({"symbol": code.upper(), "name": name})
            rows = sorted(out, key=lambda x: x["symbol"])
        except Exception as e:
            logger.warning("all stock names fetch failed: %s" % e)
        self._NAMES_CACHE = rows
        self._NAMES_TS = now
        return rows

    def get_sector_monitor(self) -> list[dict]:
        codes = [s["symbol"].lower() for s in self.SECTOR_MONITOR_MAP]
        try:
            rt = self.get_realtime(codes)
        except Exception as e:
            logger.warning(f"sector monitor realtime failed: {e}")
            rt = {}
        result = []
        for s in self.SECTOR_MONITOR_MAP:
            info = rt.get(s["symbol"], {})
            result.append({
                "sector": s["sector"], "name": s["name"], "symbol": s["symbol"],
                "price": info.get("price", 0), "change_pct": info.get("change_pct", 0),
                "amount": info.get("amount", 0), "change": info.get("change", 0),
                "is_etf": True, "leader_name": "", "leader_symbol": "", "count": 0,
            })
        # 概念/行业监控板块（东方财富板块信源：跨境电商/IT软件/液冷服务器/云游戏/白银/铜/钻石培育/稀土/贵金属/风电/火电/传媒/旅游/航运）
        try:
            result.extend(self._em_sector_groups_rows())
        except Exception as e:
            logger.warning(f"sector monitor concept extend failed: {e}")
        return result


def _f(v) -> float:
    try:
        return float(str(v).strip() or 0)
    except (ValueError, TypeError):
        return 0.0