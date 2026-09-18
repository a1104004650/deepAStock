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
# 行为信号检测
# ---------------------------------------------------------------------------

def _detect_signals(bars: list[dict], pre_close: float = 0) -> list[dict]:
    """
    自适应阈值分时主力行为检测。
    先统计全市场波动特征，再按相对阈值判定信号。
    同一信号至少间隔 MIN_GAP 分钟。
    """
    signals = []
    n = len(bars)
    if n < 15:
        return signals

    MIN_GAP = 3  # 同一信号至少间隔3分钟

    # --- 自适应阈值：根据当日波动特征动态调整 ---
    abs_vdevs = [abs(b.get("vwap_dev", 0)) for b in bars if b.get("vwap_dev") is not None]
    abs_moms = [abs(b.get("price_mom", 0)) for b in bars if b.get("price_mom") is not None]
    vrs = [b.get("vol_ratio", 1) for b in bars if b.get("vol_ratio") is not None]

    avg_vdev = sum(abs_vdevs) / len(abs_vdevs) if abs_vdevs else 0.2
    avg_mom = sum(abs_moms) / len(abs_moms) if abs_moms else 0.15
    avg_vr = sum(vrs) / len(vrs) if vrs else 1.0

    # 阈值计算：取相对值和绝对值的较大者，但限制上限
    TH_VDEV = max(avg_vdev * 0.8, 0.05)  # 降低倍数，允许更多信号
    TH_MOM = max(avg_mom * 0.8, 0.03)   # 降低倍数
    
    # 量比阈值特殊处理：避免平均量比过高时阈值太离谱
    if avg_vr > 3:
        # 高量比股票（可能是活跃股），用更宽松的阈值
        TH_VR_HIGH = max(avg_vr * 1.2, 2.0)  # 限制上限
        TH_VR_LOW = min(avg_vr * 0.5, 1.0)
    else:
        TH_VR_HIGH = max(avg_vr * 1.5, 1.5)
        TH_VR_LOW = min(avg_vr * 0.6, 0.8)

    last_sig_idx = {}

    for i in range(10, n):
        b = bars[i]
        p = b.get("price", 0)
        if not p or p <= 0:
            continue

        vwap = b.get("vwap", p)
        vr = b.get("vol_ratio", 1)
        mom = b.get("price_mom", 0)
        vdev = b.get("vwap_dev", 0)
        d_vol = b.get("d_vol", 0)

        # --- 辅助变量 ---
        # 近5分钟趋势
        recent_5 = [bars[j]["price"] for j in range(max(0, i - 4), i + 1) if bars[j].get("price")]
        trend_5 = (recent_5[-1] - recent_5[0]) / recent_5[0] * 100 if len(recent_5) >= 2 and recent_5[0] else 0

        # 近3分钟趋势
        recent_3 = [bars[j]["price"] for j in range(max(0, i - 2), i + 1) if bars[j].get("price")]
        trend_3 = (recent_3[-1] - recent_3[0]) / recent_3[0] * 100 if len(recent_3) >= 2 and recent_3[0] else 0

        # 当前bar涨跌
        bar_up = p > (b.get("prev_price") or p)

        # 涨跌幅（相对昨收）
        chg_pct = (p - pre_close) / pre_close * 100 if pre_close > 0 else 0

        # 近10分钟最大量
        recent_vol10 = [bars[j]["d_vol"] for j in range(max(0, i - 9), i + 1)]
        max_vol10 = max(recent_vol10) if recent_vol10 else 1
        avg_vol10 = sum(recent_vol10) / len(recent_vol10) if recent_vol10 else 1

        # 量能活跃度 = 当前量 / 10分钟均量
        vol_active = d_vol / avg_vol10 if avg_vol10 > 0 else 0

        def can_emit(sig_type: str) -> bool:
            last = last_sig_idx.get(sig_type, -999)
            return (i - last) >= MIN_GAP

        def emit(sig_type: str, label: str, conf: int, desc: str):
            if can_emit(sig_type):
                conf = max(30, min(95, conf))
                signals.append({
                    "time": b["time"], "signal": label,
                    "confidence": conf, "desc": desc, "type": sig_type
                })
                last_sig_idx[sig_type] = i

        # ========== 1. 吸筹 ==========
        # 价格在VWAP下方 + 有企稳迹象
        if (vdev < -TH_VDEV * 0.6 and d_vol > 0 and bar_up):
            if i >= 1:
                # 价格企稳或反弹
                if p >= bars[i-1].get("price", p) * 0.999:
                    conf = 30 + int(abs(vdev) / TH_VDEV * 20) + int(min(vr, 2) * 5)
                    emit("accumulate", "吸筹", conf,
                         f"VWAP下方{abs(vdev):.2f}%，量比{vr:.1f}，疑似吸筹")

        # ========== 2. 洗盘 ==========
        # 价格在VWAP下方 + 跌幅收窄
        if (vdev < -TH_VDEV * 0.6 and d_vol > 0):
            if i >= 2:
                # 跌幅收窄或企稳
                if bars[i].get("price", 0) > bars[i - 2].get("price", 0) * 0.996:
                    conf = 30 + int((1 - min(vr, 1)) * 20) + int(abs(vdev) / TH_VDEV * 10)
                    emit("shakeout", "洗盘", conf,
                         f"回调后企稳，VWAP偏离{vdev:.2f}%，疑似洗盘")

        # ========== 3. 诱多 ==========
        # 价格在VWAP上方 + 动量衰减
        if (vdev > TH_VDEV * 0.6 and d_vol > 0 and bar_up):
            if i >= 1:
                prev_mom = bars[i - 1].get("price_mom", 0)
                # 动量减弱
                if mom < prev_mom and prev_mom > 0:
                    conf = 30 + int(vr / max(TH_VR_HIGH, 1) * 20) + int(max(mom, 0) / max(TH_MOM, 0.01) * 10)
                    emit("bull_trap", "诱多", conf,
                         f"冲高后动量衰减，VWAP上方{vdev:.2f}%，警惕诱多")

        # ========== 4. 诱空 ==========
        # 价格在VWAP下方 + 动量企稳
        if (vdev < -TH_VDEV * 0.6 and d_vol > 0 and not bar_up):
            if i >= 1:
                prev_vdev = bars[i - 1].get("vwap_dev", 0)
                # VWAP偏离收窄
                if vdev > prev_vdev:
                    conf = 30 + int((1 - min(vr, 1)) * 20) + int(abs(min(mom, 0)) / max(TH_MOM, 0.01) * 10)
                    emit("bear_trap", "诱空", conf,
                         f"下跌后企稳，VWAP偏离{vdev:.2f}%，疑似诱空")

        # ========== 5. 真拉升 ==========
        # 价格在VWAP上方 + 动量持续
        if (vdev > TH_VDEV * 0.5 and bar_up and d_vol > 0 and p > vwap):
            if i >= 1:
                prev_mom = bars[i - 1].get("price_mom", 0)
                # 动量保持或增强
                if mom >= prev_mom * 0.3:
                    conf = 35 + int(vr / max(TH_VR_HIGH, 1) * 15) + int(max(mom, 0) / max(TH_MOM, 0.01) * 10)
                    emit("genuine_rally", "真拉升", conf,
                         f"VWAP上方{vdev:.2f}%，量比{vr:.1f}，主力拉升")

        # ========== 6. 放量急涨分析 ==========
        # 短时间快速上涨时，分析是真拉升还是诱多
        if (i >= 3 and d_vol > 0 and bar_up):
            p_3ago = bars[i-3].get("price", p)
            if p_3ago and p_3ago > 0:
                sharp_rise = (p - p_3ago) / p_3ago * 100
                vol_3ago = bars[i-3].get("d_vol", 1)
                vol_surge = d_vol / vol_3ago if vol_3ago > 0 else 1
                
                if sharp_rise > 0.3 and vol_surge > 1.5:
                    # 分析意图：真拉升 vs 诱多
                    # 真拉升：动量持续 + VWAP上方 + 量能持续放大
                    # 诱多：动量衰减 + 冲高回落
                    
                    # 检查动量是否持续
                    mom_sustained = mom >= bars[i-1].get("price_mom", 0) * 0.5
                    # 检查是否在VWAP上方
                    above_vwap = p > vwap
                    # 检查量能是否持续放大
                    vol_sustained = bars[i].get("d_vol", 0) > bars[i-1].get("d_vol", 0) * 0.7
                    
                    if mom_sustained and above_vwap and vol_sustained:
                        # 真拉升信号
                        conf = 40 + int(sharp_rise * 25) + int(min(vol_surge, 3) * 10)
                        conf = min(conf, 90)
                        emit("genuine_rally", "真拉升", conf,
                             f"急涨{sharp_rise:.2f}%，量比{vol_surge:.1f}，动量持续，主力拉升")
                    else:
                        # 诱多信号（冲高回落风险）
                        conf = 30 + int(sharp_rise * 15) + int(min(vol_surge, 2) * 8)
                        conf = min(conf, 75)
                        emit("bull_trap", "诱多", conf,
                             f"急涨{sharp_rise:.2f}%后动量衰减，量比{vol_surge:.1f}，警惕诱多")

        # ========== 7. 放量急跌分析 ==========
        # 短时间快速下跌时，分析是洗盘还是诱空
        if (i >= 3 and d_vol > 0 and not bar_up):
            p_3ago = bars[i-3].get("price", p)
            if p_3ago and p_3ago > 0:
                sharp_drop = (p - p_3ago) / p_3ago * 100
                vol_3ago = bars[i-3].get("d_vol", 1)
                vol_surge = d_vol / vol_3ago if vol_3ago > 0 else 1
                
                if sharp_drop < -0.3 and vol_surge > 1.3:
                    # 分析意图：洗盘 vs 诱空
                    # 洗盘：缩量急跌后企稳，主力清洗浮筹
                    # 诱空：放量急跌后企稳，主力诱空吸筹
                    
                    # 检查是否企稳（当前跌幅收窄）
                    stabilizing = bars[i].get("price", 0) > bars[i-1].get("price", 0) * 0.998
                    # 检查量能是否萎缩
                    shrinking_vol = vol_surge < 2.0
                    
                    if stabilizing and shrinking_vol:
                        # 洗盘信号（急跌后企稳，量能萎缩）
                        conf = 35 + int(abs(sharp_drop) * 20) + int((2 - min(vol_surge, 2)) * 10)
                        conf = min(conf, 80)
                        emit("shakeout", "洗盘", conf,
                             f"急跌{abs(sharp_drop):.2f}%后企稳，量比{vol_surge:.1f}，疑似洗盘")
                    else:
                        # 诱空信号（放量急跌，可能诱空）
                        conf = 30 + int(abs(sharp_drop) * 15) + int(min(vol_surge, 2) * 8)
                        conf = min(conf, 75)
                        emit("bear_trap", "诱空", conf,
                             f"急跌{abs(sharp_drop):.2f}%，量比{vol_surge:.1f}，疑似诱空")

        # ========== 8. 做T买入（T+0低吸）==========
        # 核心：价格跌破VWAP一定幅度 + 缩量 + 企稳迹象
        if (vdev < -TH_VDEV * 1.2 and vr < TH_VR_LOW * 1.3 and d_vol > 0 and not bar_up):
            if i >= 2:
                p_i = bars[i].get("price", 0)
                p_i1 = bars[i - 1].get("price", 0)
                # 企稳迹象：跌幅收窄或价格企稳
                if p_i >= p_i1 * 0.998 or (bars[i-1].get("price", 0) - p_i1) > (p_i1 - p_i):
                    conf = 40 + int(abs(vdev) / TH_VDEV * 15) + int((1 - min(vr, 1)) * 15)
                    emit("t_buy", "T买", conf,
                         f"跌破VWAP {abs(vdev):.2f}%后企稳，量比{vr:.2f}，可低吸")

        # ========== 9. 做T卖出（T+0高抛）==========
        # 核心：价格突破VWAP一定幅度 + 放量 + 动量衰减
        if (vdev > TH_VDEV * 1.2 and vr > TH_VR_HIGH * 0.9 and d_vol > 0):
            if i >= 2:
                p_i = bars[i].get("price", 0)
                p_i1 = bars[i - 1].get("price", 0)
                prev_mom = bars[i - 1].get("price_mom", 0)
                # 动量减弱 + 价格开始回落
                if mom < prev_mom and prev_mom > 0 and p_i < p_i1:
                    conf = 40 + int(vdev / TH_VDEV * 15) + int(vr / TH_VR_HIGH * 15)
                    emit("t_sell", "T卖", conf,
                         f"突破VWAP {vdev:.2f}%后动量衰减，量比{vr:.1f}，可高抛")

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
    """综合判断主力意图（基于多维度评分）"""
    # 使用所有信号，但最近的权重更高
    scores = {
        "吸筹": 0, "洗盘": 0, "诱多": 0, "诱空": 0, "真拉升": 0
    }

    # 1. 信号权重（最近10个信号，越近权重越高）
    recent = signals[-10:] if signals else []
    for idx, s in enumerate(recent):
        weight = 1 + (idx / len(recent)) if recent else 1  # 越近权重越高
        sig_name = s["signal"]
        if sig_name in scores:
            scores[sig_name] += s["confidence"] * weight

    # 2. VWAP偏离加权（当前状态）
    if vwap_dev < -0.3:
        scores["吸筹"] += 20
        scores["诱空"] += 15
    elif vwap_dev > 0.3:
        scores["真拉升"] += 18
        scores["诱多"] += 12

    # 3. 涨跌幅加权
    if chg_pct > 2:
        scores["真拉升"] += 15
    elif chg_pct < -2:
        scores["洗盘"] += 15
    elif chg_pct > 0.5:
        scores["真拉升"] += 8
    elif chg_pct < -0.5:
        scores["洗盘"] += 8

    # 4. 量能趋势
    if len(bars) > 10:
        recent_vol = sum(b["d_vol"] for b in bars[-5:]) / 5
        early_vol = sum(b["d_vol"] for b in bars[5:10]) / 5
        if early_vol > 0:
            vol_trend = recent_vol / early_vol
            if vol_trend > 1.5:
                scores["真拉升"] += 12
            elif vol_trend < 0.5:
                scores["洗盘"] += 10
                scores["吸筹"] += 8

    # 5. 价格位置
    if len(bars) > 0:
        last_price = bars[-1].get("price", 0)
        if len(bars) > 20:
            high_20 = max(b.get("price", 0) for b in bars[-20:])
            low_20 = min(b.get("price", 0) for b in bars[-20:])
            if high_20 > low_20:
                pos = (last_price - low_20) / (high_20 - low_20)
                if pos > 0.8:
                    scores["真拉升"] += 8
                elif pos < 0.2:
                    scores["吸筹"] += 8

    # 取最高分
    best = max(scores, key=scores.get)
    best_score = scores[best]
    total = sum(scores.values()) or 1

    # 置信度
    confidence = round(best_score / total * 100, 1) if total > 0 else 0

    # 如果没有任何信号且得分很低，显示"观望"
    if not recent and best_score < 30:
        return {
            "primary": "观望",
            "score": best_score,
            "confidence": confidence,
            "all_scores": {k: round(v / total * 100, 1) for k, v in scores.items()},
        }

    return {
        "primary": best,
        "score": best_score,
        "confidence": confidence,
        "all_scores": {k: round(v / total * 100, 1) for k, v in scores.items()},
    }


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
