"""CZSC 缠论引擎封装

优先使用官方 czsc 库插件；若未安装则退化为内置简化缠论分析（分型/笔/中枢近似）。
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.market.kline_service import KlineService
from app.utils.indicators import detect_chan_signals, compute_indicators
from app.core.czsc_plugin import plugin as czsc_plugin
from app.utils.logger import logger
from app.utils import shanghai_now

try:
    import czsc  # noqa: F401
    HAS_CZSC = True
except Exception:
    HAS_CZSC = False


class CZSCAnalyzer:
    def __init__(self, db: AsyncSession, signals_config: str = None):
        self.db = db
        self.signals_config = signals_config or "czsc_config/signals_config.yaml"
        self.kline_svc = KlineService(db)

    async def analyze(self, symbol: str, period: str = "day") -> dict:
        kdata = await self.kline_svc.get_klines(symbol, period, with_indicators=True)
        klines = kdata.get("data", [])
        if len(klines) < 60:
            return {"symbol": symbol, "period": period, "error": "数据不足", "fx_list": [],
                    "bi_list": [], "zs_list": [], "signals": [], "current_state": {}}

        # 外挂插件：官方 czsc 库（Rust）可用时优先使用
        if czsc_plugin.HAS_CZSC:
            try:
                res = czsc_plugin.analyze_series(klines, period)
                res["symbol"] = symbol
                return res
            except Exception as e:
                logger.warning(f"czsc plugin fallback builtin for {symbol}: {e}")

        # 简化分型检测：顶分型/底分型
        fx_list = self._detect_fx(klines)
        bi_list = self._detect_bi(fx_list)
        signals = detect_chan_signals(klines)
        three_signals = self._detect_three_buy_sell(bi_list, klines)

        state = self._current_state(klines, bi_list)
        all_signals = signals + three_signals
        all_signals.sort(key=lambda x: x.get("time", ""), reverse=True)

        return {
            "symbol": symbol, "period": period,
            "fx_list": fx_list[-40:],
            "bi_list": bi_list[-40:],
            "zs_list": self._detect_zs(bi_list),
            "signals": all_signals[-20:],
            "current_state": state,
            "engine": "builtin",
            "analyzed_at": datetime.now().isoformat(),
        }

    async def multi_period_analysis(self, symbol: str) -> dict:
        result = {}
        for period in ["week", "day", "m60"]:
            try:
                result[period] = await self.analyze(symbol, period)
            except Exception as e:
                logger.warning(f"multi-period {period} failed: {e}")
                result[period] = None
        if czsc_plugin.HAS_CZSC:
            try:
                summary = czsc_plugin.multi_level_analysis(
                    {p: r for p, r in result.items() if r})
            except Exception as e:
                logger.warning(f"czsc multi synthesis failed: {e}")
                summary = self._synthesize(result)
        else:
            summary = self._synthesize(result)
        return {"detail": result, "synthesis": summary}

    def _synthesize(self, multi: dict) -> dict:
        day_state = (multi.get("day") or {}).get("current_state", {})
        week_state = (multi.get("week") or {}).get("current_state", {})
        trend_day = day_state.get("trend", "unknown")
        trend_week = week_state.get("trend", "unknown")
        if trend_week == "up" and trend_day == "consolidate":
            signal = "buy_zone"
        elif trend_week == "up" and trend_day == "down":
            signal = "watch"
        elif trend_week == "down":
            signal = "avoid"
        else:
            signal = "neutral"
        return {"week_trend": trend_week, "day_trend": trend_day, "signal": signal}

    # ---------- 简化缠论 ----------
    def _detect_fx(self, klines: list[dict]) -> list[dict]:
        fx = []
        for i in range(1, len(klines) - 1):
            h0, h1, h2 = float(klines[i-1]["high"]), float(klines[i]["high"]), float(klines[i+1]["high"])
            l0, l1, l2 = float(klines[i-1]["low"]), float(klines[i]["low"]), float(klines[i+1]["low"])
            if h1 > h0 and h1 > h2 and l1 > l0 and l1 > l2:
                fx.append({"dt": klines[i]["dt"], "mark": "g", "price": round(h1, 2), "type": "顶分型"})
            elif l1 < l0 and l1 < l2 and h1 < h0 and h1 < h2:
                fx.append({"dt": klines[i]["dt"], "mark": "d", "price": round(l1, 2), "type": "底分型"})
        return fx

    def _detect_bi(self, fx_list: list[dict]) -> list[dict]:
        if len(fx_list) < 2:
            return []
        bi = []
        for i in range(len(fx_list) - 1):
            a, b = fx_list[i], fx_list[i + 1]
            direction = "up" if a["mark"] == "d" and b["mark"] == "g" else "down"
            if direction == "up":
                high = b["price"]; low = a["price"]
            else:
                high = a["price"]; low = b["price"]
            bi.append({
                "start": a["dt"], "end": b["dt"],
                "direction": direction, "high": round(high, 2), "low": round(low, 2),
            })
        return bi

    def _detect_zs(self, bi_list: list[dict]) -> list[dict]:
        if len(bi_list) < 3:
            return []
        zs = []
        for i in range(0, len(bi_list) - 2, 3):
            seg = bi_list[i:i+3]
            highs = [b["high"] for b in seg]
            lows = [b["low"] for b in seg]
            zg, zd = min(highs), max(lows)
            if zg >= zd:
                zs.append({"start": seg[0]["start"], "end": seg[-1]["end"],
                           "high": round(zg, 2), "low": round(zd, 2)})
        return zs[-5:]

    def _detect_three_buy_sell(self, bi_list: list[dict], klines: list[dict]) -> list[dict]:
        """三买三卖信号检测"""
        if len(bi_list) < 5 or len(klines) < 20:
            return []
        signals = []
        closes = {k["dt"]: float(k["close"]) for k in klines}
        highs = {k["dt"]: float(k["high"]) for k in klines}
        lows = {k["dt"]: float(k["low"]) for k in klines}
        zs_list = self._detect_zs(bi_list)

        for i in range(2, len(bi_list)):
            cur = bi_list[i]
            prev = bi_list[i - 1]
            prev2 = bi_list[i - 2]
            if cur["direction"] == "up":
                cur_high = cur["high"]
                prev_low = prev["low"]
                prev2_high = prev2["high"]
                # 一买：趋势下跌后的底分型反转（最后一个下跌笔创新低后反弹）
                if (prev["direction"] == "down" and prev2["direction"] == "down"
                    and cur_high > prev2_high):
                    signals.append({"time": cur["end"], "type": "buy", "signal_type": "1买",
                                    "reason": "趋势下跌后底分型反转"})
                # 二买：中枢震荡中的底分型买点
                for zs in zs_list:
                    if (prev["low"] <= zs["low"] and cur_high > zs["high"]
                        and cur["end"] >= zs["end"]):
                        signals.append({"time": cur["end"], "type": "buy", "signal_type": "2买",
                                        "reason": f"中枢{zs['low']}-{zs['high']}下沿获支撑"})
                        break
                # 三买：中枢上方回踩不进入中枢
                for zs in zs_list:
                    if (prev["low"] > zs["high"] and cur_high > zs["high"]
                        and prev["low"] > zs["high"]):
                        signals.append({"time": cur["end"], "type": "buy", "signal_type": "3买",
                                        "reason": f"回踩不入中枢上沿{zs['high']}"})
                        break
            elif cur["direction"] == "down":
                cur_low = cur["low"]
                prev_high = prev["high"]
                prev2_low = prev2["low"]
                # 一卖：趋势上涨后的顶分型反转
                if (prev["direction"] == "up" and prev2["direction"] == "up"
                    and cur_low < prev2_low):
                    signals.append({"time": cur["end"], "type": "sell", "signal_type": "1卖",
                                    "reason": "趋势上涨后顶分型反转"})
                # 二卖：中枢震荡中的顶分型卖点
                for zs in zs_list:
                    if (prev["high"] >= zs["high"] and cur_low < zs["low"]
                        and cur["end"] >= zs["end"]):
                        signals.append({"time": cur["end"], "type": "sell", "signal_type": "2卖",
                                        "reason": f"中枢{zs['low']}-{zs['high']}上沿承压"})
                        break
                # 三卖：中枢下方反弹不进入中枢
                for zs in zs_list:
                    if (prev["high"] < zs["low"] and cur_low < zs["low"]
                        and prev["high"] < zs["low"]):
                        signals.append({"time": cur["end"], "type": "sell", "signal_type": "3卖",
                                        "reason": f"反弹不入中枢下沿{zs['low']}"})
                        break
        return signals

    def _current_state(self, klines: list[dict], bi_list: list[dict]) -> dict:
        closes = [float(k["close"]) for k in klines]
        ma5 = self._sma(closes, 5); ma20 = self._sma(closes, 20); ma60 = self._sma(closes, 60)
        trend = "consolidate"
        if ma5 and ma20 and ma60:
            if ma5[-1] > ma20[-1] > ma60[-1]:
                trend = "up"
            elif ma5[-1] < ma20[-1] < ma60[-1]:
                trend = "down"
        boll = self._calc_boll(closes)
        yangjia_stage = self._yangjia_stage(klines, closes)
        return {
            "trend": trend,
            "last_bi_direction": bi_list[-1]["direction"] if bi_list else None,
            "price": closes[-1] if closes else None,
            "boll": boll,
            "rsi": self._calc_rsi(closes, 14),
            "yangjia_stage": yangjia_stage,
        }

    @staticmethod
    def _calc_rsi(closes: list[float], period: int = 14) -> dict:
        """RSI(14)：多周期读数 + 超买超卖/金叉死叉参考（供布林带区引用）"""
        if len(closes) < period + 1:
            return {"rsi6": 50, "rsi12": 50, "rsi24": 50, "superposition": "中性", "cross": "—"}
        def _rsi(vals: list[float], n: int) -> float:
            if len(vals) < n + 1:
                return 50.0
            gains = losses = 0.0
            for i in range(len(vals) - n, len(vals)):
                chg = vals[i] - vals[i - 1]
                gain = chg if chg > 0 else 0.0
                loss = -chg if chg < 0 else 0.0
                gains += gain
                losses += loss
            avg_g = gains / n
            avg_l = losses / n
            if avg_l == 0:
                return 100.0
            rs = avg_g / avg_l
            return round(100 - 100 / (1 + rs), 2)
        rsi6 = _rsi(closes, 6)
        rsi12 = _rsi(closes, 12)
        rsi24 = _rsi(closes, 24)
        superposition = "中性"
        if rsi6 < 30 and rsi12 < 40:
            superposition = "超卖"
        elif rsi6 > 70 and rsi12 > 60:
            superposition = "超买"
        cross = "—"
        if len(closes) >= 25:
            if rsi6 > rsi12 and closes[-1] > closes[-2]:
                cross = "短线金叉"
            elif rsi6 < rsi12 and closes[-1] < closes[-2]:
                cross = "短线死叉"
        return {"rsi6": rsi6, "rsi12": rsi12, "rsi24": rsi24,
                "superposition": superposition, "cross": cross}

    @staticmethod
    def _calc_boll(closes: list[float], period: int = 20) -> dict:
        if len(closes) < period:
            return {"mid": 0, "upper": 0, "lower": 0, "width": 0}
        recent = closes[-period:]
        mid = sum(recent) / period
        std = (sum((x - mid) ** 2 for x in recent) / period) ** 0.5
        upper = mid + 2 * std
        lower = mid - 2 * std
        width = ((upper - lower) / mid * 100) if mid else 0
        price = closes[-1]
        position = "中轨上方" if price > mid else "中轨下方"
        if price >= upper:
            position = "突破上轨（超买）"
        elif price <= lower:
            position = "跌破下轨（超卖）"
        return {"mid": round(mid, 2), "upper": round(upper, 2), "lower": round(lower, 2),
                "width": round(width, 2), "position": position, "price": price}

    @staticmethod
    def _yangjia_stage(klines: list[dict], closes: list[float]) -> dict:
        """养家心法情绪阶段：吸筹→洗盘→拉升→出货 四阶段周期循环"""
        if len(klines) < 20:
            return {"stage": "unknown", "description": "数据不足"}
        recent = klines[-20:]
        closes_20 = [float(k["close"]) for k in recent]
        highs = [float(k["high"]) for k in recent]
        lows = [float(k["low"]) for k in recent]
        volumes = [float(k.get("volume", 0)) for k in recent]
        cur_close = closes_20[-1]
        high_20 = max(highs)
        low_20 = min(lows)
        price_range = high_20 - low_20 if high_20 > low_20 else 1
        position_pct = (cur_close - low_20) / price_range * 100
        avg_vol = sum(volumes) / len(volumes) if volumes else 1
        recent_vol = volumes[-3:]
        vol_ratio = sum(recent_vol) / (3 * avg_vol) if avg_vol else 1
        recent_chg = (closes_20[-1] - closes_20[-4]) / closes_20[-4] * 100 if closes_20[-4] else 0
        chg_20 = (closes_20[-1] - closes_20[0]) / closes_20[0] * 100 if closes_20[0] else 0
        stage, desc, subtype = "吸筹", "多空分歧，伺机低吸", "低吸观察"

        if position_pct >= 78 and (vol_ratio >= 1.3 or recent_chg <= 0 or chg_20 > 22):
            stage, subtype = "出货", "高位派发"
            desc = "高位放量滞涨或缩量阴跌，主力边拉边派发，追高易接盘，逢高减仓"
        elif chg_20 < -8 and position_pct <= 35 and vol_ratio < 0.9:
            stage, subtype = "吸筹", "恐慌止跌"
            desc = "深度回调后缩量企稳，恐慌抛压出清，主力缓慢吸筹接近尾声"
        elif chg_20 > 12 and position_pct > 60 and vol_ratio >= 1.2:
            stage, subtype = "拉升", "主升加速"
            desc = "放量加速上攻，主力主升拉升，趋势最强"
        elif chg_20 > 4 and position_pct > 50 and vol_ratio >= 1.0:
            stage, subtype = "拉升", "放量拉升"
            desc = "放量突破走强，主力拉升脱离成本区"
        elif position_pct >= 45 and recent_chg <= 0 and vol_ratio < 1.0:
            stage, subtype = "洗盘", "缩量回调"
            desc = "拉升途中或高位缩量回调，主力洗掉浮筹"
        elif position_pct < 45 and chg_20 <= 6:
            stage, subtype = "吸筹", "低位建仓"
            desc = "低位横盘或回落，主力悄然建仓吸筹"
        elif chg_20 > 1 and recent_chg > 0:
            stage, subtype = "拉升", "缓步上行"
            desc = "温和放量缓步上移，慢牛爬升"
        elif vol_ratio >= 1.2 and chg_20 < 0:
            stage, subtype = "吸筹", "放量承接"
            desc = "下跌放量承接，主力低位吸筹"
        elif vol_ratio < 1.0:
            stage, subtype = "洗盘", "缩量整理"
            desc = "量能枯竭整理换手，浮筹出清，等待方向选择"
        elif position_pct >= 55:
            stage, subtype = "拉升", "多空分歧"
            desc = "中高位多空分歧，主力活跃度一般，等企稳再上"
        else:
            stage, subtype = "吸筹", "低吸观察"
            desc = "低位多空分歧，量能温和，可逢低分批关注"
        return {"stage": stage, "subtype": subtype, "description": desc,
                "position_pct": round(position_pct, 1),
                "vol_ratio": round(vol_ratio, 2), "chg_20d": round(chg_20, 2)}

    @staticmethod
    def _sma(values: list[float], period: int):
        if len(values) < period:
            return None
        return [float(sum(values[max(0, i - period + 1): i + 1]) / min(period, i + 1)) for i in range(len(values))]

    async def generate_chart_data(self, symbol: str, period: str = "day") -> dict:
        """生成前端K线图所需数据"""
        analysis = await self.analyze(symbol, period)
        kdata = await self.kline_svc.get_klines(symbol, period, with_indicators=True)
        return {**analysis, "kline": kdata.get("data", [])}