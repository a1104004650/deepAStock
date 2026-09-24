"""分时主力行为分析引擎 + T+0高抛低吸信号

通过分时数据（价格、成交量、成交额）计算：
- VWAP 及偏离度
- RSI（相对强弱指标）
- 布林带（Bollinger Bands）
- 量价背离检测
- 6种主力行为信号：吸筹、洗盘、诱多、诱空、出货、真拉升
- T+0做T信号：基于量价关系的高抛低吸

数据源：腾讯分时 API（cumulative volume/amount → per-minute delta）
"""
from __future__ import annotations
import math


# ---------------------------------------------------------------------------
# 基础指标计算
# ---------------------------------------------------------------------------

def _deltas(rows: list[dict]) -> list[dict]:
    """将累计量转化为逐分钟增量，返回带 delta 字段的新列表"""
    out = []
    prev_vol = 0.0
    prev_amt = 0.0
    prev_price = None
    for r in rows:
        vol = float(r.get("volume", 0))
        amt = float(r.get("amount", 0))
        price = r.get("price")
        d_vol = max(vol - prev_vol, 0)
        d_amt = max(amt - prev_amt, 0)
        out.append({
            **r,
            "d_vol": d_vol,
            "d_amt": d_amt,
            "prev_price": prev_price,
        })
        prev_vol = vol
        prev_amt = amt
        prev_price = price
    return out


def _vwap(bars: list[dict]) -> list[dict]:
    """计算累计 VWAP（成交额/成交量/100，volume 单位为手）"""
    cum_amt = 0.0
    cum_vol = 0.0
    for b in bars:
        cum_amt += b["d_amt"]
        cum_vol += b["d_vol"]
        b["vwap"] = round(cum_amt / (cum_vol * 100), 4) if cum_vol > 0 else b.get("price", 0)
    return bars


def _vol_ratio(bars: list[dict], window: int = 20) -> list[dict]:
    """量比 = 当分钟量 / 过去 N 分钟均量"""
    for i, b in enumerate(bars):
        start = max(0, i - window)
        hist = [bars[j]["d_vol"] for j in range(start, i) if bars[j]["d_vol"] > 0]
        avg = sum(hist) / len(hist) if hist else 1
        b["vol_ratio"] = round(b["d_vol"] / avg, 2) if avg > 0 else 0
    return bars


def _price_momentum(bars: list[dict], window: int = 5) -> list[dict]:
    """价格动量 = (price - price_n_ago) / price_n_ago * 100"""
    for i, b in enumerate(bars):
        p = b.get("price")
        j = i - window
        p0 = bars[j].get("price") if j >= 0 else None
        if p and p0 and p0 > 0:
            b["price_mom"] = round((p - p0) / p0 * 100, 3)
        else:
            b["price_mom"] = 0.0
    return bars


def _vwap_dev(bars: list[dict]) -> list[dict]:
    """VWAP偏离度 (%)"""
    for b in bars:
        p = b.get("price", 0)
        v = b.get("vwap", p)
        b["vwap_dev"] = round((p - v) / v * 100, 3) if v else 0
    return bars


def _rsi(bars: list[dict], period: int = 14) -> list[dict]:
    """RSI 相对强弱指标"""
    for i, b in enumerate(bars):
        if i < period:
            b["rsi"] = 50.0
            continue
        gains = []
        losses = []
        for j in range(i - period + 1, i + 1):
            price = bars[j].get("price", 0)
            prev = bars[j].get("prev_price") or price
            if prev > 0:
                chg = price - prev
                if chg > 0:
                    gains.append(chg)
                else:
                    losses.append(abs(chg))
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0
        if avg_loss == 0:
            b["rsi"] = 100.0
        else:
            rs = avg_gain / avg_loss
            b["rsi"] = round(100 - 100 / (1 + rs), 1)
    return bars


def _bollinger(bars: list[dict], period: int = 20, num_std: float = 2.0) -> list[dict]:
    """布林带 (中轨/上轨/下轨)"""
    for i, b in enumerate(bars):
        if i < period - 1:
            b["bb_mid"] = b.get("price", 0)
            b["bb_upper"] = b.get("price", 0)
            b["bb_lower"] = b.get("price", 0)
            b["bb_width"] = 0
            continue
        prices = [bars[j].get("price", 0) for j in range(i - period + 1, i + 1)]
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance)
        b["bb_mid"] = round(mean, 4)
        b["bb_upper"] = round(mean + num_std * std, 4)
        b["bb_lower"] = round(mean - num_std * std, 4)
        b["bb_width"] = round((b["bb_upper"] - b["bb_lower"]) / b["bb_mid"] * 100, 3) if b["bb_mid"] > 0 else 0
    return bars


def _volume_price_divergence(bars: list[dict], window: int = 5) -> list[dict]:
    """量价背离检测
    - 顶背离: 价格创新高但成交量递减 → 卖出信号
    - 底背离: 价格创新低但成交量递减 → 买入信号
    """
    for i, b in enumerate(bars):
        if i < window:
            b["vp_divergence"] = "none"
            continue
        recent_prices = [bars[j].get("price", 0) for j in range(i - window + 1, i + 1)]
        recent_vols = [bars[j].get("d_vol", 0) for j in range(i - window + 1, i + 1)]

        price_trend = recent_prices[-1] - recent_prices[0] if recent_prices[0] > 0 else 0
        vol_trend = recent_vols[-1] - recent_vols[0] if recent_vols[0] > 0 else 0

        if price_trend > 0 and vol_trend < 0 and abs(vol_trend) > sum(recent_vols) * 0.1:
            b["vp_divergence"] = "top"  # 顶背离
        elif price_trend < 0 and vol_trend < 0 and abs(vol_trend) > sum(recent_vols) * 0.1:
            b["vp_divergence"] = "bottom"  # 底背离
        else:
            b["vp_divergence"] = "none"
    return bars


# ---------------------------------------------------------------------------
# 主力行为信号检测（只在放量时分析）
# ---------------------------------------------------------------------------

def _daily_context(daily_bars: list[dict], current_price: float) -> dict:
    """
    日K线位置分析 — 判断当前价格在日线结构中的位置。
    返回：趋势、支撑位、阻力位、位置判断。
    """
    if not daily_bars or len(daily_bars) < 10:
        return {"trend": "unknown", "near_support": False, "near_resistance": False,
                "support": 0, "resistance": 0, "daily_chg_pct": 0, "daily_trend": "unknown",
                "position": "unknown"}

    closes = [b.get("close", 0) or b.get("price", 0) for b in daily_bars if b.get("close", 0) or b.get("price", 0)]
    highs = [b.get("high", 0) for b in daily_bars if b.get("high", 0)]
    lows = [b.get("low", 0) for b in daily_bars if b.get("low", 0)]

    if len(closes) < 5:
        return {"trend": "unknown", "near_support": False, "near_resistance": False,
                "support": 0, "resistance": 0, "daily_chg_pct": 0, "daily_trend": "unknown",
                "position": "unknown"}

    # 日线趋势：20日均线方向
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else ma10

    # 趋势判断
    if ma5 > ma10 > ma20:
        daily_trend = "上升"
    elif ma5 < ma10 < ma20:
        daily_trend = "下降"
    else:
        daily_trend = "震荡"

    # 支撑阻力：近20日高低点
    recent_highs = highs[-20:] if len(highs) >= 20 else highs
    recent_lows = lows[-20:] if len(lows) >= 20 else lows
    resistance = max(recent_highs) if recent_highs else current_price
    support = min(recent_lows) if recent_lows else current_price

    # 价格位置：0=最低点，1=最高点
    price_range = resistance - support
    position_pct = (current_price - support) / price_range * 100 if price_range > 0 else 50

    # 距离支撑/阻力的百分比
    dist_to_support = abs(current_price - support) / current_price * 100 if current_price > 0 else 0
    dist_to_resistance = abs(resistance - current_price) / current_price * 100 if current_price > 0 else 0

    # 接近支撑/阻力（5%以内）
    near_support = dist_to_support < 5
    near_resistance = dist_to_resistance < 5

    # 日涨跌幅（最新一根K线）
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    daily_chg_pct = (closes[-1] - prev_close) / prev_close * 100 if prev_close > 0 else 0

    return {
        "trend": daily_trend,
        "daily_trend": daily_trend,
        "daily_chg_pct": round(daily_chg_pct, 2),
        "near_support": near_support,
        "near_resistance": near_resistance,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "position_pct": round(max(0, min(100, position_pct)), 1),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
    }


def daily_behavior_summary(daily_bars: list[dict], current_price: float = 0) -> dict:
    """根据日K位置、实体/影线和量能给出保守的主力行为摘要。

    这是复盘用的收盘确认，不预测下一根K线；证据不足时明确返回观望。
    """
    ctx = _daily_context(daily_bars or [], current_price)
    if not daily_bars or len(daily_bars) < 10:
        return {"primary": "观望", "confidence": 0, "reason": "日K数量不足，无法判断主力行为",
                "t_bias": "观望", "context": ctx}

    bars = daily_bars[-20:]
    def _num(row, key):
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    last = bars[-1]
    close = _num(last, "close")
    open_price = _num(last, "open")
    high = _num(last, "high")
    low = _num(last, "low")
    volumes = [_num(b, "volume") for b in bars[:-1] if _num(b, "volume") > 0]
    last_volume = _num(last, "volume")
    avg_volume = sum(volumes[-5:]) / len(volumes[-5:]) if volumes else 0
    volume_ratio = last_volume / avg_volume if avg_volume else 1
    body = abs(close - open_price)
    candle_range = max(high - low, close * 0.001)
    lower_shadow = max(0, min(close, open_price) - low)
    upper_shadow = max(0, high - max(close, open_price))
    close_position = (close - low) / candle_range if candle_range else 0.5

    primary = "观望"
    confidence = 25
    reason = "日K量价信号不充分，暂不强行判断"
    t_bias = "观望"

    if ctx.get("near_support") and close >= open_price and lower_shadow >= max(body * 1.2, candle_range * 0.25) and volume_ratio >= 1.15:
        primary = "诱空"
        confidence = 65
        reason = "支撑附近下探后收回，带下影且量能放大，存在主力承接/诱空迹象"
        t_bias = "回踩低吸，等待分时再次确认"
    elif ctx.get("near_support") and close < open_price and volume_ratio < 1.0:
        primary = "洗盘"
        confidence = 55
        reason = "支撑附近回落但量能收缩，暂偏向洗盘而非主动出货"
        t_bias = "不追跌，等待支撑确认"
    elif ctx.get("near_resistance") and upper_shadow >= max(body * 1.2, candle_range * 0.25) and volume_ratio >= 1.2:
        primary = "诱多"
        confidence = 65
        reason = "阻力附近冲高回落，带上影且量能放大，存在主力派发/诱多迹象"
        t_bias = "冲高减仓，避免追高"
    elif ctx.get("near_resistance") and close < open_price and volume_ratio >= 1.25:
        primary = "出货"
        confidence = 68
        reason = "高位放量收阴并靠近阻力，主动卖压证据较强"
        t_bias = "反弹减仓，不做接飞刀"
    elif ctx.get("daily_trend") == "上升" and close > open_price and close_position > 0.7 and volume_ratio >= 1.2:
        primary = "真拉升"
        confidence = 62
        reason = "上升趋势中日K收强、收盘靠近高位且量能配合"
        t_bias = "回踩均价低吸，不在急拉时追买"
    elif ctx.get("daily_trend") == "下降" and close < open_price and close_position < 0.35 and volume_ratio >= 1.2:
        primary = "出货"
        confidence = 60
        reason = "下降趋势中放量收弱，反弹性质暂未被确认"
        t_bias = "以防守为主，暂不低吸"

    return {
        "primary": primary,
        "confidence": confidence,
        "reason": reason,
        "t_bias": t_bias,
        "volume_ratio": round(volume_ratio, 2),
        "context": ctx,
    }


def _detect_signals(bars: list[dict], pre_close: float = 0,
                     daily_ctx: dict = None) -> list[dict]:
    """
    主力行为信号检测 — 基于量价关系判断主力意图。

    核心原则：信号必须回答"主力在做什么"，而不是"当前发生了什么"。
    - 吸筹：主力在低位悄悄买入（放量不跌/VWAP下方反复吸货）
    - 洗盘：主力在高位震荡清洗浮筹（急跌后快速收回）
    - 诱多：主力拉高引诱散户追高后反手卖出（拉高后快速回落）
    - 诱空：主力砸盘引诱散户恐慌抛售后反手买入（砸盘后快速收回）
    - 出货：主力在高位大量卖出（高位放量滞涨/阴跌）
    - 真拉升：主力真金白银往上买（放量突破关键位）

    日K位置是关键判断依据：
    - 低位放量不跌 → 吸筹概率高
    - 高位放量滞涨 → 出货概率高
    - 上升趋势中急跌 → 洗盘概率高
    - 下降趋势中反弹 → 诱多概率高
    """
    signals = []
    n = len(bars)
    if n < 20:
        return signals

    # --- 日内趋势 ---
    cum_return = 0
    if pre_close > 0 and bars:
        last_price = bars[-1].get("price", 0)
        if last_price > 0:
            cum_return = (last_price - pre_close) / pre_close * 100

    # --- 找放量点 ---
    VOL_SPIKE_RATIO = 2.0
    # 只用短确认窗口，避免把未来走势大量带入当前信号
    WINDOW = 2
    spike_indices = []

    for i in range(20, n):
        d_vol = bars[i].get("d_vol", 0)
        if d_vol <= 0:
            continue
        start = max(0, i - 20)
        hist_vols = [bars[j]["d_vol"] for j in range(start, i) if bars[j].get("d_vol", 0) > 0]
        avg_vol = sum(hist_vols) / len(hist_vols) if hist_vols else 0
        if avg_vol > 0 and d_vol >= avg_vol * VOL_SPIKE_RATIO:
            if not spike_indices or (i - spike_indices[-1][0]) >= 3:
                spike_indices.append((i, avg_vol))

    if not spike_indices:
        return signals

    # --- 日K位置参数 ---
    ctx = daily_ctx or {}
    daily_trend = ctx.get("daily_trend", "unknown")
    near_support = ctx.get("near_support", False)
    near_resistance = ctx.get("near_resistance", False)
    position_pct = ctx.get("position_pct", 50)

    # --- 分析每个放量窗口 ---
    for spike_i, avg_vol in spike_indices:
        # 未完成确认窗口的最后几根不提前下结论
        if spike_i + WINDOW >= n:
            continue
        window_start = max(10, spike_i - WINDOW)
        window_end = min(n - 1, spike_i + WINDOW)

        spike_bar = bars[spike_i]
        spike_vol = spike_bar.get("d_vol", 0)
        spike_price = spike_bar.get("price", 0)
        spike_vdev = spike_bar.get("vwap_dev", 0)
        # 信号时间使用确认完成的时间，而不是事后才知道的放量点时间
        confirm_bar = bars[spike_i + WINDOW]
        spike_time = confirm_bar.get("time", spike_bar.get("time", ""))

        if not spike_price or spike_price <= 0:
            continue

        # 放量前后的走势
        pre_prices = [bars[j].get("price", 0) for j in range(window_start, spike_i) if bars[j].get("price", 0) > 0]
        post_prices = [bars[j].get("price", 0) for j in range(spike_i + 1, window_end + 1) if bars[j].get("price", 0) > 0]

        pre_trend = 0
        if len(pre_prices) >= 2:
            pre_trend = (pre_prices[-1] - pre_prices[0]) / pre_prices[0] * 100

        post_trend = 0
        if len(post_prices) >= 2:
            post_trend = (post_prices[-1] - post_prices[0]) / post_prices[0] * 100

        bar_up = spike_price > (spike_bar.get("prev_price") or spike_price)
        chg_pct = (spike_price - pre_close) / pre_close * 100 if pre_close > 0 else 0

        sig_type = None
        label = ""
        conf = 0
        desc = ""
        vol_ratio = spike_vol / max(avg_vol, 1)

        # ================================================================
        # 核心判断逻辑：日K位置 + 分时量价 → 主力行为
        # ================================================================

        if bar_up and chg_pct > 0.3:
            # --- 放量上涨 ---
            if post_trend < -0.3:
                # 拉高后快速回落 → 诱多（主力拉高出货）
                sig_type = "bull_trap"
                label = "诱多"
                conf = 50 + min(int(vol_ratio * 5), 20) + min(int(abs(chg_pct) * 5), 15)
                if near_resistance:
                    conf += 10
                    desc = f"接近阻力位放量拉高后回落，主力诱多出货（{WINDOW}根确认）"
                elif daily_trend == "下降":
                    conf += 8
                    desc = f"下降趋势中放量拉高后回落，主力诱多（{WINDOW}根确认）"
                else:
                    desc = f"放量涨{chg_pct:.2f}%后回落，主力拉高诱多（{WINDOW}根确认）"
            elif post_trend > -0.1:
                if near_support and daily_trend != "下降":
                    # 支撑位附近放量上涨 → 吸筹后拉升
                    sig_type = "accumulate"
                    label = "吸筹"
                    conf = 55 + min(int(vol_ratio * 5), 20)
                    desc = f"支撑位附近放量上涨，主力吸筹后拉升"
                elif daily_trend == "上升" and position_pct < 60:
                    # 上升趋势低位放量涨 → 吸筹
                    sig_type = "accumulate"
                    label = "吸筹"
                    conf = 50 + min(int(vol_ratio * 5), 18)
                    desc = f"上升趋势中放量上涨，主力吸筹"
                else:
                    # 真拉升
                    sig_type = "genuine_rally"
                    label = "真拉升"
                    conf = 50 + min(int(vol_ratio * 5), 20) + min(int(abs(chg_pct) * 5), 15)
                    if daily_trend == "上升":
                        conf += 8
                    desc = f"放量涨{chg_pct:.2f}%，主力真金白银拉升"
            else:
                # 涨后小幅回落，观察
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 45 + min(int(vol_ratio * 5), 15)
                desc = f"放量涨{chg_pct:.2f}%，主力买入"

        elif not bar_up and chg_pct < -0.3:
            # --- 放量下跌 ---
            if post_trend > 0.2:
                # 急跌后快速收回 → 诱空或洗盘
                if daily_trend == "上升" or near_support:
                    # 上升趋势/支撑位急跌后收回 → 诱空
                    sig_type = "bear_trap"
                    label = "诱空"
                    conf = 55 + min(int(vol_ratio * 5), 20)
                    if near_support:
                        conf += 8
                    desc = f"{'支撑位' if near_support else '上升趋势'}中急跌后快速收回，主力诱空洗筹"
                else:
                    # 震荡趋势急跌后收回 → 洗盘
                    sig_type = "shakeout"
                    label = "洗盘"
                    conf = 50 + min(int(vol_ratio * 5), 18)
                    desc = f"放量跌{abs(chg_pct):.2f}%后快速回升，主力洗盘"
            elif post_trend > -0.3:
                # 跌后横盘 → 洗盘（未继续杀跌）
                if daily_trend == "上升" or near_support:
                    sig_type = "shakeout"
                    label = "洗盘"
                    conf = 45 + min(int(vol_ratio * 5), 15)
                    desc = f"放量跌后横盘未继续下跌，主力洗盘"
                else:
                    # 上涨后回调，主力减仓
                    sig_type = "distribution"
                    label = "出货"
                    conf = 40 + min(int(vol_ratio * 5), 15)
                    desc = f"放量跌后横盘，主力减仓"
            else:
                # 跌后继续跌 → 出货
                sig_type = "distribution"
                label = "出货"
                conf = 50 + min(int(vol_ratio * 5), 18) + min(int(abs(chg_pct) * 5), 12)
                if near_resistance:
                    conf += 10
                    desc = f"阻力位附近放量杀跌，主力出货"
                elif daily_trend == "上升" and position_pct > 70:
                    desc = f"高位放量下跌，主力出货"
                else:
                    desc = f"放量跌{abs(chg_pct):.2f}%后继续下跌，主力出货"

        elif abs(spike_vdev) > 0.5:
            # --- VWAP偏离放量 ---
            if spike_vdev < 0:
                if near_support or (daily_trend == "上升" and position_pct < 50):
                    # 低位VWAP下方放量 → 吸筹
                    sig_type = "accumulate"
                    label = "吸筹"
                    conf = 50 + min(int(abs(spike_vdev) * 12), 20) + min(int(vol_ratio * 5), 15)
                    desc = f"VWAP下方放量，主力低位吸筹"
                elif daily_trend == "下降":
                    # 下降趋势VWAP下方放量 → 出货
                    sig_type = "distribution"
                    label = "出货"
                    conf = 45 + min(int(abs(spike_vdev) * 10), 18)
                    desc = f"下降趋势VWAP下方放量，主力出货"
                else:
                    sig_type = "accumulate"
                    label = "吸筹"
                    conf = 40 + min(int(abs(spike_vdev) * 10), 15)
                    desc = f"VWAP下方放量，疑似吸筹"
            else:
                if near_resistance or position_pct > 80:
                    # 高位VWAP上方放量 → 出货
                    sig_type = "distribution"
                    label = "出货"
                    conf = 48 + min(int(spike_vdev * 10), 18)
                    desc = f"高位VWAP上方放量滞涨，主力出货"
                elif daily_trend == "上升":
                    sig_type = "genuine_rally"
                    label = "真拉升"
                    conf = 45 + min(int(spike_vdev * 10), 15)
                    desc = f"VWAP上方放量，主力拉升"
                else:
                    sig_type = "bull_trap"
                    label = "诱多"
                    conf = 42 + min(int(spike_vdev * 10), 15)
                    desc = f"VWAP上方放量，警惕诱多"

        # 产生信号
        if sig_type:
            conf = max(35, min(90, conf))
            signals.append({
                "time": spike_time,
                "signal": label,
                "confidence": conf,
                "desc": desc,
                "type": sig_type,
            })

    return signals


# ---------------------------------------------------------------------------
# T+0 做T信号检测（独立于主力行为信号）
# ---------------------------------------------------------------------------

def _detect_t_signals_low_lag(bars: list[dict], pre_close: float = 0,
                              daily_ctx: dict = None) -> list[dict]:
    """低滞后做T信号：只使用当前及已完成的局部K线，不回看未来高低点。"""
    n = len(bars)
    if n < 12:
        return []

    ctx = daily_ctx or {}
    trend = ctx.get("daily_trend", "unknown")
    near_support = bool(ctx.get("near_support"))
    near_resistance = bool(ctx.get("near_resistance"))
    position = float(ctx.get("position_pct", 50) or 50)
    day_return = 0
    if pre_close and bars[-1].get("price"):
        day_return = (bars[-1]["price"] - pre_close) / pre_close * 100

    # 局部反转只需两根确认，避免原算法的60根未来扫描。
    MIN_SWING = 0.45
    MIN_GAP = 0.8
    MAX_SIGNALS = 3
    signals = []
    last_type = ""
    last_price = 0.0

    for i in range(2, n - 2):
        p0 = float(bars[i - 2].get("price") or 0)
        p1 = float(bars[i - 1].get("price") or 0)
        p2 = float(bars[i].get("price") or 0)
        p3 = float(bars[i + 1].get("price") or 0)
        p4 = float(bars[i + 2].get("price") or 0)
        if min(p0, p1, p2, p3, p4) <= 0:
            continue

        change_before = (p2 - p0) / p0 * 100
        confirm_change = (p4 - p2) / p2 * 100
        rsi = float(bars[i].get("rsi") or 50)
        vwap_dev = float(bars[i].get("vwap_dev") or 0)
        vol_ratio = float(bars[i].get("vol_ratio") or 1)
        momentum = float(bars[i].get("price_mom") or 0)

        is_low = p2 <= p1 and p2 <= p3 and change_before <= -MIN_SWING and confirm_change >= 0.25
        is_high = p2 >= p1 and p2 >= p3 and change_before >= MIN_SWING and confirm_change <= -0.25
        if not is_low and not is_high:
            continue

        if is_low and last_type == "t_buy":
            continue
        if is_high and last_type == "t_sell":
            continue

        confidence = 48
        reasons = ["局部反转确认"]
        if vol_ratio >= 1.35:
            confidence += 6
            reasons.append("量能确认")
        if is_low:
            if rsi <= 38:
                confidence += 8
                reasons.append("RSI偏低")
            if vwap_dev <= -0.6:
                confidence += 5
                reasons.append("低于VWAP")
            if near_support or (trend == "上升" and position < 55):
                confidence += 10
                reasons.append("日K支撑/低位")
            if trend == "下降" and not near_support:
                confidence -= 12
                reasons.append("下降趋势抑制")
            if day_return < -4 and not near_support:
                confidence -= 8
                reasons.append("日内弱势")
            if confidence < 55:
                continue
            if last_price and last_type == "t_sell" and (last_price - p2) / last_price * 100 < MIN_GAP:
                continue
            label, signal_type = "T买", "t_buy"
        else:
            if rsi >= 62:
                confidence += 8
                reasons.append("RSI偏高")
            if vwap_dev >= 0.6:
                confidence += 5
                reasons.append("高于VWAP")
            if near_resistance or (trend == "下降" and position > 55):
                confidence += 10
                reasons.append("日K阻力/高位")
            if trend == "上升" and not near_resistance:
                confidence -= 12
                reasons.append("上升趋势抑制")
            if confidence < 55:
                continue
            if last_price and last_type == "t_buy" and (p2 - last_price) / last_price * 100 < MIN_GAP:
                continue
            label, signal_type = "T卖", "t_sell"

        signals.append({
            "time": bars[i + 2].get("time", bars[i].get("time", "")),
            "signal": label,
            "confidence": max(35, min(85, int(confidence))),
            "desc": f"{'低点' if is_low else '高点'}反转后确认，" + "、".join(reasons),
            "type": signal_type,
            "basis": {"daily_trend": trend, "position_pct": position,
                      "near_support": near_support, "near_resistance": near_resistance},
        })
        last_type = signal_type
        last_price = p2
        if len(signals) >= MAX_SIGNALS:
            break

    return signals

def _detect_t_signals(bars: list[dict], pre_close: float = 0) -> list[dict]:
    """
    T+0 做T信号 — 简洁实用版。

    核心：找日内已经形成的高低转折点，在确认反转时出信号。
    不预测顶部底部，只在价格已经反转后确认信号。

    规则：
    1. 买-卖必须交替，不能连续同方向
    2. 买-卖之间价差>=2%（有利润空间）
    3. 每天最多3个信号（2买1卖 或 1买2卖）
    """
    signals = []
    n = len(bars)
    if n < 60:
        return signals

    MIN_RANGE = 2.0        # 当日振幅>=2%才做T
    MIN_GAP_PCT = 2.0      # 买-卖之间价差>=2%
    MAX_SIGNALS = 3        # 一天最多3个信号
    CONFIRM_BARS = 2       # 确认反转需要的bar数
    MIN_SWING = 0.8        # 最小波动幅度(%)

    # --- Step 1: 找日内所有显著波动 ---
    # 计算每个bar相对前面bar的波动
    swings = []  # [(idx, type, start_price, end_price, pct, time)]
    i = 0
    while i < n - 10:
        start_p = bars[i].get("price", 0)
        if start_p <= 0:
            i += 1
            continue

        # 找接下来的最高/最低点
        high_idx = i
        high_p = start_p
        low_idx = i
        low_p = start_p

        for j in range(i + 1, min(i + 60, n)):  # 最多看60根bar
            p = bars[j].get("price", 0)
            if p <= 0:
                continue
            if p > high_p:
                high_p = p
                high_idx = j
            if p < low_p:
                low_p = p
                low_idx = j

        # 判断是先涨还是先跌
        if high_idx < low_idx and high_p > start_p * (1 + MIN_SWING / 100):
            # 先涨后跌：顶部转折
            swings.append((high_idx, "high", start_p, high_p,
                          (high_p - start_p) / start_p * 100,
                          bars[high_idx].get("time", "")))
            i = high_idx + 1
        elif low_idx < high_idx and low_p < start_p * (1 - MIN_SWING / 100):
            # 先跌后涨：底部转折
            swings.append((low_idx, "low", start_p, low_p,
                          (start_p - low_p) / start_p * 100,
                          bars[low_idx].get("time", "")))
            i = low_idx + 1
        else:
            i += 5

    if not swings:
        return signals

    # --- Step 2: 在转折点出信号（需确认反转） ---
    used = set()
    last_type = ""  # 上一个信号类型
    last_price = 0

    for idx, stype, start_p, extreme_p, swing_pct, stime in swings:
        if len(signals) >= MAX_SIGNALS:
            break
        if idx in used or stime in [s["time"] for s in signals]:
            continue

        bar = bars[idx]
        rsi = bar.get("rsi", 50)
        vwap = bar.get("vwap", 0)
        vwap_dev = bar.get("vwap_dev", 0)
        vol_ratio = bar.get("vol_ratio", 1)

        # --- 底部转折 → T买 ---
        if stype == "low" and last_type != "t_buy":
            # 检查是否从这个低点已经反弹了
            confirm_p = bars[min(idx + CONFIRM_BARS, n - 1)].get("price", 0)
            if confirm_p <= 0 or confirm_p <= extreme_p:
                continue  # 没反弹，不确认

            bounce_pct = (confirm_p - extreme_p) / extreme_p * 100
            if bounce_pct < 0.3:
                continue  # 反弹太小

            # 如果有上一个信号，检查价差
            if last_price > 0 and last_type == "t_sell":
                gap = (last_price - extreme_p) / last_price * 100
                if gap < MIN_GAP_PCT:
                    continue  # 价差不够

            # 评分
            conf = 55
            reasons = []
            if rsi < 35:
                conf += 10
                reasons.append(f"RSI={rsi:.0f}")
            if vwap_dev < -0.8:
                conf += 8
                reasons.append(f"低于VWAP{abs(vwap_dev):.1f}%")
            if vol_ratio > 1.5:
                conf += 7
                reasons.append("放量")
            if swing_pct > 1.5:
                conf += 5
                reasons.append(f"波动{swing_pct:.1f}%")

            conf = min(85, conf)
            desc = f"低点确认(反弹{bounce_pct:.1f}%"
            if reasons:
                desc += ", " + ", ".join(reasons)
            desc += ")"

            signals.append({
                "time": stime,
                "signal": "T买",
                "confidence": conf,
                "desc": desc,
                "type": "t_buy",
            })
            last_type = "t_buy"
            last_price = extreme_p
            used.add(idx)

        # --- 顶部转折 → T卖 ---
        elif stype == "high" and last_type != "t_sell":
            confirm_p = bars[min(idx + CONFIRM_BARS, n - 1)].get("price", 0)
            if confirm_p <= 0 or confirm_p >= extreme_p:
                continue

            drop_pct = (extreme_p - confirm_p) / extreme_p * 100
            if drop_pct < 0.3:
                continue

            if last_price > 0 and last_type == "t_buy":
                gap = (extreme_p - last_price) / last_price * 100
                if gap < MIN_GAP_PCT:
                    continue

            conf = 55
            reasons = []
            if rsi > 65:
                conf += 10
                reasons.append(f"RSI={rsi:.0f}")
            if vwap_dev > 0.8:
                conf += 8
                reasons.append(f"高于VWAP{vwap_dev:.1f}%")
            if vol_ratio > 1.5:
                conf += 7
                reasons.append("放量")
            if swing_pct > 1.5:
                conf += 5
                reasons.append(f"波动{swing_pct:.1f}%")

            conf = min(85, conf)
            desc = f"高点确认(回落{drop_pct:.1f}%"
            if reasons:
                desc += ", " + ", ".join(reasons)
            desc += ")"

            signals.append({
                "time": stime,
                "signal": "T卖",
                "confidence": conf,
                "desc": desc,
                "type": "t_sell",
            })
            last_type = "t_sell"
            last_price = extreme_p
            used.add(idx)

    return signals


def _time_diff_min(t1: str, t2: str) -> int:
    """计算两个时间字符串之间的分钟差（HH:MM格式）"""
    try:
        h1, m1 = map(int, t1.split(":"))
        h2, m2 = map(int, t2.split(":"))
        return abs((h2 * 60 + m2) - (h1 * 60 + m1))
    except (ValueError, AttributeError):
        return 999


# ---------------------------------------------------------------------------
# 综合分析
# ---------------------------------------------------------------------------

def _summary(signals: list[dict], t_signals: list[dict], bars: list[dict], pre_close: float,
             daily_ctx: dict = None, daily_behavior: dict = None) -> dict:
    """生成分析摘要"""
    if not bars:
        return {"error": "无分时数据"}

    last = bars[-1]
    price = last.get("price", 0)
    vwap = last.get("vwap", price)
    vwap_dev = (price - vwap) / vwap * 100 if vwap > 0 else 0

    chg_pct = (price - pre_close) / pre_close * 100 if pre_close > 0 else 0

    # 主力行为信号统计
    sig_counts = {}
    for s in signals:
        sig_counts[s["signal"]] = sig_counts.get(s["signal"], 0) + 1

    # T信号统计
    t_sig_counts = {}
    for s in t_signals:
        t_sig_counts[s["signal"]] = t_sig_counts.get(s["signal"], 0) + 1

    intent = _judge_intent(bars, signals, vwap_dev, chg_pct, daily_ctx or {})

    return {
        "price": round(price, 2),
        "vwap": round(vwap, 2),
        "vwap_dev": round(vwap_dev, 2),
        "chg_pct": round(chg_pct, 2),
        "intent": intent,
        "signal_counts": sig_counts,
        "total_signals": len(signals),
        "t_signal_counts": t_sig_counts,
        "total_t_signals": len(t_signals),
        "daily_behavior": daily_behavior or {},
    }


def _judge_intent(bars: list[dict], signals: list[dict], vwap_dev: float, chg_pct: float,
                  daily_ctx: dict = None) -> dict:
    """基于放量信号判断主力意图"""
    scores = {
        "吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "出货": 0, "真拉升": 0
    }

    for s in signals:
        sig_name = s["signal"]
        if sig_name in scores:
            scores[sig_name] += s["confidence"]

    if signals and max(scores.values()) > 0:
        best = max(scores, key=scores.get)
        best_score = scores[best]
        total = sum(scores.values()) or 1
        confidence = round(best_score / total * 100, 1) if total > 0 else 0

        return {
            "primary": best,
            "score": best_score,
            "confidence": confidence,
            "all_scores": {k: round(v / total * 100, 1) for k, v in scores.items()},
        }

    # 无信号时的fallback判断（基于量价关系推断主力行为）
    ctx = daily_ctx or {}
    near_support = ctx.get("near_support", False)
    near_resistance = ctx.get("near_resistance", False)
    daily_trend = ctx.get("daily_trend", "unknown")

    if vwap_dev < -0.5 and chg_pct < -1:
        if chg_pct < -3:
            primary = "洗盘" if near_support or daily_trend == "上升" else "出货"
            return {"primary": primary, "score": 20, "confidence": 40,
                    "all_scores": {"吸筹": 0, "洗盘": 35 if primary == "洗盘" else 10,
                                    "诱多": 0, "诱空": 10, "出货": 40 if primary == "出货" else 10,
                                    "真拉升": 0}}
        return {"primary": "洗盘", "score": 20, "confidence": 35, "all_scores": {"吸筹": 15, "洗盘": 35, "诱多": 0, "诱空": 15, "出货": 10, "真拉升": 0}}
    elif vwap_dev > 0.5 and chg_pct > 1:
        primary = "出货" if near_resistance or daily_trend == "下降" else "真拉升"
        return {"primary": primary, "score": 20, "confidence": 40,
                "all_scores": {"吸筹": 0, "洗盘": 0, "诱多": 15 if primary == "诱多" else 5,
                                "诱空": 0, "出货": 40 if primary == "出货" else 5,
                                "真拉升": 40 if primary == "真拉升" else 0}}
    elif vwap_dev < -0.5:
        if chg_pct < -2:
            primary = "洗盘" if near_support or daily_trend == "上升" else "出货"
            return {"primary": primary, "score": 15, "confidence": 35,
                    "all_scores": {"吸筹": 5, "洗盘": 30 if primary == "洗盘" else 10,
                                    "诱多": 0, "诱空": 10, "出货": 35 if primary == "出货" else 5,
                                    "真拉升": 0}}
        return {"primary": "吸筹", "score": 15, "confidence": 30, "all_scores": {"吸筹": 30, "洗盘": 10, "诱多": 0, "诱空": 15, "出货": 5, "真拉升": 0}}
    elif vwap_dev > 0.5:
        primary = "出货" if near_resistance else "诱多"
        return {"primary": primary, "score": 15, "confidence": 35,
                "all_scores": {"吸筹": 0, "洗盘": 0, "诱多": 35 if primary == "诱多" else 10,
                                "诱空": 0, "出货": 35 if primary == "出货" else 10,
                                "真拉升": 15 if primary == "诱多" else 0}}

    return {"primary": "观望", "score": 0, "confidence": 0,
            "all_scores": {"吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "出货": 0, "真拉升": 0}}


# ---------------------------------------------------------------------------
# 入口函数
# ---------------------------------------------------------------------------

def analyze_intraday(rows: list[dict], pre_close: float = 0,
                     daily_bars: list[dict] = None) -> dict:
    """
    分时主力行为分析入口

    参数:
        rows: 分时数据 [{time, price, volume, amount, avg}, ...]
        pre_close: 昨收价
        daily_bars: 近期日K数据（用于位置分析），可选

    返回:
        {
            "bars": [...],       # 带指标的分时数据（供前端绘图）
            "signals": [...],    # 主力行为信号
            "t_signals": [...],  # T+0做T信号
            "summary": {...},    # 分析摘要
            "daily_context": {...},  # 日K位置分析
        }
    """
    if not rows:
        return {"bars": [], "signals": [], "t_signals": [], "summary": {"error": "无数据"}, "daily_context": {}}

    # Step 1: 计算逐分钟增量
    bars = _deltas(rows)

    # Step 2: VWAP
    bars = _vwap(bars)

    # Step 3: 量比
    bars = _vol_ratio(bars)

    # Step 4: 价格动量
    bars = _price_momentum(bars)

    # Step 5: VWAP偏离
    bars = _vwap_dev(bars)

    # Step 6: RSI
    bars = _rsi(bars, period=14)

    # Step 7: 布林带
    bars = _bollinger(bars, period=20, num_std=2.0)

    # Step 8: 量价背离
    bars = _volume_price_divergence(bars, window=5)

    # Step 9: 日K位置分析
    current_price = bars[-1].get("price", pre_close) if bars else pre_close
    daily_ctx = _daily_context(daily_bars or [], current_price)
    daily_behavior = daily_behavior_summary(daily_bars or [], current_price)

    # Step 10: 检测主力行为信号（传入日K上下文）
    signals = _detect_signals(bars, pre_close, daily_ctx)

    # Step 11: 低滞后做T信号（日K趋势/位置参与过滤）
    t_signals = _detect_t_signals_low_lag(bars, pre_close, daily_ctx)

    # Step 12: 摘要
    summary = _summary(signals, t_signals, bars, pre_close, daily_ctx, daily_behavior)

    return {
        "bars": bars,
        "signals": signals,
        "t_signals": t_signals,
        "summary": summary,
        "daily_context": daily_ctx,
        "daily_behavior": daily_behavior,
    }
