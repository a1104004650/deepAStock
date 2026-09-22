"""技术指标计算 (纯 Python / NumPy 实现)"""
from typing import Optional
from datetime import datetime
import numpy as np
from app.utils import shanghai_now


def sma(values: list[float], period: int) -> list[Optional[float]]:
    out = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = np.convolve(np.array(values, dtype=float), np.ones(period), mode="valid") / period
    for i, v in enumerate(window):
        out[i + period - 1] = round(float(v), 4)
    return out


def ema(values: list[float], period: int) -> list[Optional[float]]:
    out = [None] * len(values)
    if not values or period <= 0:
        return out
    k = 2 / (period + 1)
    prev = float(values[0])
    out[0] = prev
    for i in range(1, len(values)):
        prev = float(values[i]) * k + prev * (1 - k)
        out[i] = round(prev, 4)
    return out


def macd(values: list[float], fast=12, slow=26, signal=9):
    """返回 (DIF, DEA, HIST), 均以 None 开头"""
    n = len(values)
    dif = [None] * n
    dea = [None] * n
    hist = [None] * n
    if n < slow + signal:
        return dif, dea, hist
    fast_e = ema(values, fast)
    slow_e = ema(values, slow)
    for i in range(n):
        if fast_e[i] is not None and slow_e[i] is not None:
            dif[i] = round(fast_e[i] - slow_e[i], 4)
    # DEA = EMA of DIF
    dif_clean = [d if d is not None else 0.0 for d in dif]
    dea_list = ema(dif_clean, signal)
    for i in range(n):
        if dea_list[i] is not None:
            dea[i] = dea_list[i]
            hist[i] = round((dif[i] if dif[i] is not None else 0.0) - dea_list[i], 4)
    return dif, dea, hist


def rsi(values: list[float], period: int = 14) -> list[Optional[float]]:
    n = len(values)
    out = [None] * n
    if n < period + 1:
        return out
    gains = []
    losses = []
    for i in range(1, n):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = _rsi_from_avgs(avg_g, avg_l)
    for i in range(period, n - 1):
        g = gains[i]
        l = losses[i]
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        out[i + 1] = _rsi_from_avgs(avg_g, avg_l)
    return out


def _rsi_from_avgs(avg_g: float, avg_l: float) -> float:
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 4)


def boll(values: list[float], period: int = 20, k: float = 2.0):
    n = len(values)
    mid = [None] * n
    upper = [None] * n
    lower = [None] * n
    if n < period:
        return mid, upper, lower
    arr = np.array(values, dtype=float)
    for i in range(period - 1, n):
        window = arr[i - period + 1: i + 1]
        m = float(window.mean())
        std = float(window.std())
        mid[i] = round(m, 4)
        upper[i] = round(m + k * std, 4)
        lower[i] = round(m - k * std, 4)
    return mid, upper, lower


def compute_indicators(klines: list[dict], include: list[str] | None = None) -> dict:
    """基于K线列表计算指标，返回可叠加到K线图的数据"""
    if not klines:
        return {}
    closes = [float(k["close"]) for k in klines]
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    volumes = [float(k.get("volume", 0) or 0) for k in klines]

    result = {"klines": klines}

    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)

    result["ma"] = {
        "ma5": _pack(closes, ma5), "ma10": _pack(closes, ma10),
        "ma20": _pack(closes, ma20), "ma60": _pack(closes, ma60),
    }

    dif, dea, hist = macd(closes)
    result["macd"] = {
        "dif": _pack(closes, dif), "dea": _pack(closes, dea), "hist": _pack(closes, hist),
    }

    rsi14 = rsi(closes, 14)
    result["rsi"] = {"rsi14": _pack(closes, rsi14)}

    mid, upper, lower = boll(closes)
    result["boll"] = {
        "mid": _pack(closes, mid), "upper": _pack(closes, upper), "lower": _pack(closes, lower),
    }

    # 成交量均线
    vol_ma5 = sma(volumes, 5)
    vol_ma10 = sma(volumes, 10)
    result["volume"] = _pack_volumes(klines, vol_ma5, vol_ma10)

    # 涨跌
    changes = [0.0]
    prev = closes[0]
    for c in closes[1:]:
        changes.append(round((c - prev) / prev * 100, 2) if prev else 0.0)
        prev = c
    for i, k in enumerate(klines):
        k["change_pct"] = changes[i]

    return result


def _pack(closes, series):
    out = []
    for i, v in enumerate(series):
        if v is not None:
            out.append({"time": _fmt_time(closes, i), "value": v})
    return out


def _pack_volumes(klines, vol_ma5, vol_ma10):
    out = []
    for i, k in enumerate(klines):
        rec = {"time": _fmt_time([k["close"]], i), "value": float(k.get("volume", 0) or 0)}
        if vol_ma5[i] is not None:
            rec["ma5"] = vol_ma5[i]
        if vol_ma10[i] is not None:
            rec["ma10"] = vol_ma10[i]
        out.append(rec)
    return out


def closes_for(k):
    return [k["close"]]


def _fmt_time(closes, i):
    return str(i)


# 简易缠论信号：用MA排列 + 形态实现基础信号（不依赖CZSC库以保持可运行）
def detect_chan_signals(klines: list[dict]) -> list[dict]:
    """缠论简化信号：基于 MACD 与均线排列的基础买卖点判断"""
    signals = []
    if len(klines) < 60:
        return signals
    closes = [float(k["close"]) for k in klines]
    ma5 = sma(closes, 5)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    dif, dea, hist = macd(closes)

    i = len(klines) - 1
    # 金叉/死叉
    for j in range(30, i + 1):
        if ma5[j] and ma20[j] and ma5[j - 1] and ma20[j - 1]:
            if dif[j] and dif[j - 1] and dea[j] and dea[j - 1] and hist[j] and hist[j - 1]:
                # MACD金叉 + MA多头
                if dif[j - 1] <= dea[j - 1] and dif[j] > dea[j] and ma5[j] > ma20[j]:
                    signals.append({"time": klines[j]["dt"], "type": "buy",
                                    "text": "MACD金叉+均线多头"})
                # MACD死叉 + MA空头
                elif dif[j - 1] >= dea[j - 1] and dif[j] < dea[j] and ma5[j] < ma20[j]:
                    signals.append({"time": klines[j]["dt"], "type": "sell",
                                    "text": "MACD死叉+均线空头"})
    return signals[-20:]