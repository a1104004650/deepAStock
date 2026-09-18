"""分时主力行为分析引擎

通过分时数据（价格、成交量、成交额）计算：
- VWAP 及偏离度
- 量增量减（逐笔成交增量）
- 量比 / 量能强度
- 5种主力行为信号：吸筹、洗盘、诱多、诱空、真拉升

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


# ---------------------------------------------------------------------------
# 行为信号检测（只在放量时分析）
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
    # 放量定义：当前量 > 前20分钟均量的 2倍
    VOL_SPIKE_RATIO = 2.0  # 放量倍数
    WINDOW = 5  # 前后各分析5分钟

    spike_indices = []  # 放量点索引

    for i in range(20, n):
        d_vol = bars[i].get("d_vol", 0)
        if d_vol <= 0:
            continue

        # 计算前20分钟均量
        start = max(0, i - 20)
        hist_vols = [bars[j]["d_vol"] for j in range(start, i) if bars[j].get("d_vol", 0) > 0]
        avg_vol = sum(hist_vols) / len(hist_vols) if hist_vols else 0

        if avg_vol > 0 and d_vol >= avg_vol * VOL_SPIKE_RATIO:
            # 检查与前一个放量点的距离，至少间隔3分钟
            if not spike_indices or (i - spike_indices[-1]) >= 3:
                spike_indices.append(i)

    # --- Step 2: 分析每个放量窗口 ---
    for spike_i in spike_indices:
        # 分析窗口：spike_i 前后各 WINDOW 分钟
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

        # 计算放量前后的趋势
        pre_prices = [bars[j].get("price", 0) for j in range(window_start, spike_i) if bars[j].get("price", 0) > 0]
        post_prices = [bars[j].get("price", 0) for j in range(spike_i + 1, window_end + 1) if bars[j].get("price", 0) > 0]

        # 放量前趋势
        pre_trend = 0
        if len(pre_prices) >= 2:
            pre_trend = (pre_prices[-1] - pre_prices[0]) / pre_prices[0] * 100

        # 放量后趋势
        post_trend = 0
        if len(post_prices) >= 2:
            post_trend = (post_prices[-1] - post_prices[0]) / post_prices[0] * 100

        # 当前bar涨跌
        bar_up = spike_price > (spike_bar.get("prev_price") or spike_price)

        # 涨跌幅（相对昨收）
        chg_pct = (spike_price - pre_close) / pre_close * 100 if pre_close > 0 else 0

        # --- 判断意图 ---
        sig_type = None
        label = ""
        conf = 0
        desc = ""

        # 涨停判断：接近涨停（涨幅>=9%）一定是真拉升
        is_limit_up = chg_pct >= 9

        # 情况1：放量急涨（涨了+量大）
        if bar_up and chg_pct > 0.3:
            if is_limit_up:
                # 涨停或接近涨停，一定是真拉升
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 85 + min(int(spike_vol / max(avg_vol, 1) * 3), 10)
                desc = f"放量涨停{chg_pct:.2f}%，主力强势拉升"
            elif post_trend > -0.2:
                # 放量后没跌，真拉升
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 50 + min(int(abs(chg_pct) * 10), 30) + min(int(spike_vol / max(avg_vol, 1) * 5), 15)
                desc = f"放量涨{chg_pct:.2f}%，量比{spike_vol/avg_vol:.1f}，后续走势确认拉升"
            else:
                # 放量后跌了，诱多
                sig_type = "bull_trap"
                label = "诱多"
                conf = 40 + min(int(abs(chg_pct) * 8), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量涨{chg_pct:.2f}%后回落，疑似诱多出货"

        # 情况2：放量急跌（跌了+量大）
        elif not bar_up and chg_pct < -0.3:
            if post_trend > -0.3:
                # 跌后企稳，洗盘
                sig_type = "shakeout"
                label = "洗盘"
                conf = 45 + min(int(abs(chg_pct) * 10), 28) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量跌{abs(chg_pct):.2f}%后企稳，疑似洗盘"
            else:
                # 跌后继续跌，诱空
                sig_type = "bear_trap"
                label = "诱空"
                conf = 40 + min(int(abs(chg_pct) * 8), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"放量跌{abs(chg_pct):.2f}%后继续下跌，疑似诱空"

        # 情况3：放量震荡（VWAP偏离大）
        elif abs(spike_vdev) > 0.5:
            if is_limit_up:
                # 涨停+VWAP上方放量，真拉升
                sig_type = "genuine_rally"
                label = "真拉升"
                conf = 80 + min(int(spike_vol / max(avg_vol, 1) * 3), 10)
                desc = f"涨停+VWAP上方放量，主力强势拉升"
            elif spike_vdev < 0:
                # VWAP下方放量，吸筹
                sig_type = "accumulate"
                label = "吸筹"
                conf = 40 + min(int(abs(spike_vdev) * 15), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"VWAP下方{abs(spike_vdev):.2f}%放量，疑似吸筹"
            else:
                # VWAP上方放量（非涨停），可能出货
                sig_type = "bull_trap"
                label = "诱多"
                conf = 38 + min(int(spike_vdev * 12), 22) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"VWAP上方{spike_vdev:.2f}%放量，警惕出货"

        # 情况4：做T机会（跌破VWAP后放量企稳）
        if sig_type is None and spike_vdev < -0.8 and bar_up:
            # 跌破VWAP后放量反弹，T买
            if post_trend > 0:
                sig_type = "t_buy"
                label = "T买"
                conf = 45 + min(int(abs(spike_vdev) * 12), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"跌破VWAP {abs(spike_vdev):.2f}%后放量反弹，可低吸"

        # 情况5：做T机会（突破VWAP后放量回落）
        if sig_type is None and spike_vdev > 0.8 and not bar_up:
            # 突破VWAP后放量回落，T卖
            if post_trend < 0:
                sig_type = "t_sell"
                label = "T卖"
                conf = 45 + min(int(spike_vdev * 12), 25) + min(int(spike_vol / max(avg_vol, 1) * 4), 12)
                desc = f"突破VWAP {spike_vdev:.2f}%后放量回落，可高抛"

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
# 综合分析
# ---------------------------------------------------------------------------

def _summary(signals: list[dict], bars: list[dict], pre_close: float) -> dict:
    """生成分析摘要"""
    if not bars:
        return {"error": "无分时数据"}

    # 当前状态
    last = bars[-1]
    price = last.get("price", 0)
    vwap = last.get("vwap", price)
    vwap_dev = (price - vwap) / vwap * 100 if vwap > 0 else 0

    # 涨跌幅
    chg_pct = (price - pre_close) / pre_close * 100 if pre_close > 0 else 0

    # 信号统计
    sig_counts = {}
    for s in signals:
        sig_counts[s["signal"]] = sig_counts.get(s["signal"], 0) + 1

    # 判断当前主力意图（综合评分）
    intent = _judge_intent(bars, signals, vwap_dev, chg_pct)

    return {
        "price": round(price, 2),
        "vwap": round(vwap, 2),
        "vwap_dev": round(vwap_dev, 2),
        "chg_pct": round(chg_pct, 2),
        "intent": intent,
        "signal_counts": sig_counts,
        "total_signals": len(signals),
    }


def _judge_intent(bars: list[dict], signals: list[dict], vwap_dev: float, chg_pct: float) -> dict:
    """
    基于放量信号判断主力意图。
    只根据放量点产生的信号来判断，不凭空分析。
    """
    scores = {
        "吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "真拉升": 0
    }

    # 1. 根据放量信号评分（每个放量点产生一个信号）
    for s in signals:
        sig_name = s["signal"]
        if sig_name in scores:
            scores[sig_name] += s["confidence"]

    # 2. 如果有信号，根据信号综合判断
    if signals:
        # 取最高分作为意图
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

    # 3. 没有放量信号时，根据当前状态简单判断
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
            "signals": [...],    # 信号列表
            "summary": {...},    # 分析摘要
        }
    """
    if not rows:
        return {"bars": [], "signals": [], "summary": {"error": "无数据"}}

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

    # Step 6: 检测信号
    signals = _detect_signals(bars, pre_close)

    # Step 7: 摘要
    summary = _summary(signals, bars, pre_close)

    return {
        "bars": bars,
        "signals": signals,
        "summary": summary,
    }
