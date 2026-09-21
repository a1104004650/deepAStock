"""分时主力行为分析引擎 + T+0高抛低吸信号

通过分时数据（价格、成交量、成交额）计算：
- VWAP 及偏离度
- RSI（相对强弱指标）
- 布林带（Bollinger Bands）
- 量价背离检测
- 5种主力行为信号：吸筹、洗盘、诱多、诱空、真拉升
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

def _detect_signals(bars: list[dict], pre_close: float = 0) -> list[dict]:
    """
    基于放量的行为信号检测。
    逻辑：先找到放量点，再分析放量前后5分钟的意图。
    只在放量时产生信号，没量不分析。
    """
    signals = []
    n = len(bars)
    if n < 20:
        return signals

    # --- Step 1: 找放量点 ---
    VOL_SPIKE_RATIO = 2.0
    WINDOW = 5

    spike_indices = []  # list of (index, avg_vol)

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

    # --- Step 2: 分析每个放量窗口 ---
    for spike_i, avg_vol in spike_indices:
        window_start = max(10, spike_i - WINDOW)
        window_end = min(n - 1, spike_i + WINDOW)

        spike_bar = bars[spike_i]
        spike_vol = spike_bar.get("d_vol", 0)
        spike_price = spike_bar.get("price", 0)
        spike_vwap = spike_bar.get("vwap", spike_price)
        spike_vdev = spike_bar.get("vwap_dev", 0)
        spike_mom = spike_bar.get("price_mom", 0)
        spike_time = spike_bar.get("time", "")

        if not spike_price or spike_price <= 0:
            continue

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

        is_limit_up = chg_pct >= 9

        # 情况1：放量急涨
        if bar_up and chg_pct > 0.3:
            if is_limit_up:
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 85 + min(int(spike_vol / max(avg_vol, 1) * 3), 10)
                desc = f"放量涨停{chg_pct:.2f}%，主力强势拉升"
            elif post_trend > -0.2:
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 50 + min(int(abs(chg_pct) * 10), 30) + min(int(spike_vol / max(avg_vol, 1) * 5), 15)
                desc = f"放量涨{chg_pct:.2f}%，量比{spike_vol/avg_vol:.1f}，后续走势确认拉升"
            else:
                sig_type = "bull_trap"
                label = "诱多"
                conf = 40 + min(int(abs(chg_pct) * 8), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量涨{chg_pct:.2f}%后回落，疑似诱多出货"

        # 情况2：放量急跌
        elif not bar_up and chg_pct < -0.3:
            if post_trend > -0.3:
                sig_type = "shakeout"
                label = "洗盘"
                conf = 45 + min(int(abs(chg_pct) * 10), 28) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量跌{abs(chg_pct):.2f}%后企稳，疑似洗盘"
            else:
                sig_type = "bear_trap"
                label = "诱空"
                conf = 40 + min(int(abs(chg_pct) * 8), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量跌{abs(chg_pct):.2f}%后继续下跌，疑似诱空"

        # 情况3：放量震荡（VWAP偏离大）
        elif abs(spike_vdev) > 0.5:
            if is_limit_up:
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 80 + min(int(spike_vol / max(avg_vol, 1) * 3), 10)
                desc = f"涨停+VWAP上方放量，主力强势拉升"
            elif spike_vdev < 0:
                sig_type = "accumulate"
                label = "吸筹"
                conf = 40 + min(int(abs(spike_vdev) * 15), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"VWAP下方{abs(spike_vdev):.2f}%放量，疑似吸筹"
            else:
                sig_type = "bull_trap"
                label = "诱多"
                conf = 38 + min(int(spike_vdev * 12), 22) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"VWAP上方{spike_vdev:.2f}%放量，警惕出货"

        # 产生主力行为信号
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
    CONFIRM_BARS = 3       # 确认反转需要的bar数
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

def _summary(signals: list[dict], t_signals: list[dict], bars: list[dict], pre_close: float) -> dict:
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

    intent = _judge_intent(bars, signals, vwap_dev, chg_pct)

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
    }


def _judge_intent(bars: list[dict], signals: list[dict], vwap_dev: float, chg_pct: float) -> dict:
    """基于放量信号判断主力意图"""
    scores = {
        "吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "真拉升": 0
    }

    for s in signals:
        sig_name = s["signal"]
        if sig_name in scores:
            scores[sig_name] += s["confidence"]

    if signals:
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

    if vwap_dev < -0.5 and chg_pct < -1:
        return {"primary": "洗盘", "score": 20, "confidence": 40, "all_scores": {"洗盘": 40, "吸筹": 30, "诱多": 0, "诱空": 20, "真拉升": 10}}
    elif vwap_dev > 0.5 and chg_pct > 1:
        return {"primary": "真拉升", "score": 20, "confidence": 40, "all_scores": {"洗盘": 0, "吸筹": 0, "诱多": 20, "诱空": 0, "真拉升": 40}}
    elif vwap_dev < -0.5:
        return {"primary": "吸筹", "score": 15, "confidence": 35, "all_scores": {"洗盘": 15, "吸筹": 35, "诱多": 0, "诱空": 20, "真拉升": 10}}
    elif vwap_dev > 0.5:
        return {"primary": "诱多", "score": 15, "confidence": 35, "all_scores": {"洗盘": 0, "吸筹": 0, "诱多": 35, "诱空": 0, "真拉升": 20}}

    return {"primary": "观望", "score": 0, "confidence": 0, "all_scores": {"吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "真拉升": 0}}


# ---------------------------------------------------------------------------
# 入口函数
# ---------------------------------------------------------------------------

def analyze_intraday(rows: list[dict], pre_close: float = 0) -> dict:
    """
    分时主力行为分析入口

    参数:
        rows: 分时数据 [{time, price, volume, amount, avg}, ...]
        pre_close: 昨收价

    返回:
        {
            "bars": [...],       # 带指标的分时数据（供前端绘图）
            "signals": [...],    # 主力行为信号
            "t_signals": [...],  # T+0做T信号
            "summary": {...},    # 分析摘要
        }
    """
    if not rows:
        return {"bars": [], "signals": [], "t_signals": [], "summary": {"error": "无数据"}}

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

    # Step 9: 检测主力行为信号
    signals = _detect_signals(bars, pre_close)

    # Step 10: 检测T+0做T信号（独立检测，不依赖主力行为信号）
    t_signals = _detect_t_signals(bars, pre_close)

    # Step 11: 摘要
    summary = _summary(signals, t_signals, bars, pre_close)

    return {
        "bars": bars,
        "signals": signals,
        "t_signals": t_signals,
        "summary": summary,
    }
