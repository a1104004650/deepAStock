"""技术结构分析：筹码控盘 / 交易趋势阶段 / 支撑压力 / 指标信号

口径（全部由真实日K与真实流通市值推导；缺数据时明确标记不可用，不提供任何模拟或占位数值）：

1. 筹码分布与控盘：
   取近 250 根日K，按当日换手率 t = 成交量(手)×100 / 流通股数 对存量筹码做 (1-t) 等比衰减，
   当日新筹码均匀铺在当日最低价~最高价之间；流通股数 = 腾讯实时流通市值 / 现价。
   集中度 = 90% 筹码价位宽度 (P95-P5) / 现价；筹码峰取密度局部极大；获利盘 = 成本低于现价的筹码占比。
   控盘级别按集中度划分为 无 / 轻度 / 中度 / 高度 四档。

2. 交易趋势阶段（顺序循环，非逐日信号）：
   逢低关注 → 洗拉 → 上涨阶段 → 逢高兑现 → 派落 → 下跌阶段 →（回到逢低关注）
   状态机只允许相邻推进或回退；切换条件必须连续 3 根 K 线确认，且在当前阶段至少停留 5 根 K 线。
   因此阶段不会逐日跳变，同一阶段可稳定持续多个交易日。

3. 支撑位 / 压力位：
   日K分型拐点（中间K线价格为 ±2 根窗口极值）按 ATR(14) 容差聚类；接触点越多、越近越强。
   短期回看 60 根，中期回看 240 根；低于现价的聚类为支撑，高于现价的为压力。

4. 指标信号（16 项）：
   MACD/KDJ/RSI/MA/BOLL 交叉类（金叉=买入、死叉=卖出）、多头/空头排列、红三兵/黑三兵、量多头/量空头。
   每项给出最近一次出现的交易日与距今交易日数（当天=0）。
"""
from __future__ import annotations

from app.utils.indicators import sma, macd, rsi, boll

STAGES = ["逢低关注", "洗拉", "上涨阶段", "逢高兑现", "派落", "下跌阶段"]

_CHIP_WINDOW = 250
_CHIP_BINS = 120
_CONFIRM_DAYS = 3
_MIN_DWELL = 5


# ---------------------------------------------------------------- 基础工具

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _atr(highs, lows, closes, period=14):
    n = len(closes)
    out = [None] * n
    if n < period + 1:
        return out
    trs = [0.0] * n
    for i in range(1, n):
        trs[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    for i in range(period, n):
        out[i] = sum(trs[i - period + 1: i + 1]) / period
    return out


def kdj(klines, n=9):
    """KDJ（随机指标），K/D 以 SMA(alpha=1/3) 平滑，起始 50；返回 (K, D, J)"""
    m = len(klines)
    k_out = [None] * m
    d_out = [None] * m
    j_out = [None] * m
    if m < n:
        return k_out, d_out, j_out
    k_prev, d_prev = 50.0, 50.0
    for i in range(m):
        if i < n - 1:
            continue
        window = klines[i - n + 1: i + 1]
        lo = min(float(r["low"]) for r in window)
        hi = max(float(r["high"]) for r in window)
        c = float(klines[i]["close"])
        rsv = (c - lo) / (hi - lo) * 100 if hi > lo else 50.0
        k = (2 / 3) * k_prev + (1 / 3) * rsv
        d = (2 / 3) * d_prev + (1 / 3) * k
        j = 3 * k - 2 * d
        k_prev, d_prev = k, d
        k_out[i] = round(k, 4)
        d_out[i] = round(d, 4)
        j_out[i] = round(j, 4)
    return k_out, d_out, j_out


# ---------------------------------------------------------------- 筹码与控盘

def chip_analysis(klines, float_shares, price, window=_CHIP_WINDOW, bins=_CHIP_BINS):
    """真实换手衰减筹码分布 → 集中度 / 控盘四档 / 筹码峰 / 获利盘"""
    if not klines or len(klines) < 30:
        return {"available": False, "reason": "日K不足30根，无法推算筹码分布"}
    if not float_shares or float_shares <= 0:
        return {"available": False, "reason": "缺流通股数（流通市值/现价），筹码分析不可用"}
    rows = klines[-window:]
    lows = [float(r["low"]) for r in rows]
    highs = [float(r["high"]) for r in rows]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        hi = lo * 1.001
    width = (hi - lo) / bins
    centers = [lo + (i + 0.5) * width for i in range(bins)]
    density = [0.0] * bins

    for idx, r in enumerate(rows):
        t = float(r.get("volume") or 0) * 100.0 / float_shares
        t = _clamp(t, 0.0, 1.0)
        keep = 1.0 - t
        for i in range(bins):
            density[i] *= keep
        bl = float(r["low"])
        bh = float(r["high"])
        if bh <= bl:
            bh = bl * 1.0001
        w = [0.0] * bins
        total_w = 0.0
        for i, c in enumerate(centers):
            if bl <= c <= bh:
                w[i] = 1.0
                total_w += 1.0
        if total_w <= 0:
            nearest = min(range(bins), key=lambda i: abs(centers[i] - (bl + bh) / 2))
            density[nearest] += t
        else:
            share = t / total_w
            for i in range(bins):
                if w[i]:
                    density[i] += share

    total = sum(density)
    if total <= 0:
        return {"available": False, "reason": "K线成交量缺失，无法推算筹码分布"}

    # 加权分位数
    def pct(p):
        target = total * p
        acc = 0.0
        for i, v in enumerate(density):
            acc += v
            if acc >= target:
                return centers[i]
        return centers[-1]

    p5, p95 = pct(0.05), pct(0.95)
    price = price or centers[-1]
    width90 = (p95 - p5) / price if price else None
    mean = sum(c * v for c, v in zip(centers, density)) / total
    variance = sum((c - mean) ** 2 * v for c, v in zip(centers, density)) / total
    std = variance ** 0.5
    winner = sum(v for c, v in zip(centers, density) if c <= price) / total

    # 筹码峰：密度局部极大（至少间隔3格合并），取占比最高的前3
    peaks = []
    for i in range(1, bins - 1):
        if density[i] >= density[i - 1] and density[i] >= density[i + 1] and density[i] > 0:
            peaks.append(i)
    merged = []
    for i in peaks:
        if merged and i - merged[-1] <= 3:
            if density[i] > density[merged[-1]]:
                merged[-1] = i
        else:
            merged.append(i)
    merged.sort(key=lambda i: -density[i])
    peak_list = [
        {"price": round(centers[i], 3), "share": round(density[i] / total * 100, 1)}
        for i in merged[:3]
    ]

    # 四档：按 90% 筹码宽度（占现价比例）
    if width90 is None:
        return {"available": False, "reason": "现价缺失，无法计算集中度"}
    if width90 <= 0.18:
        level = "高度"
        desc = "筹码高度集中，主力持仓成本接近，控盘能力强"
    elif width90 <= 0.32:
        level = "中度"
        desc = "筹码较集中，主力有一定控盘能力"
    elif width90 <= 0.48:
        level = "轻度"
        desc = "筹码较分散，控盘度有限，多为跟风资金"
    else:
        level = "无"
        desc = "筹码分散，无明显控盘特征"
    score = round(_clamp((0.50 - width90) / (0.50 - 0.10) * 100, 0, 100))

    return {
        "available": True,
        "level": level,
        "score": score,
        "width90": round(width90, 4),
        "concentration": round(width90 * 100, 1),
        "winner_rate": round(winner * 100, 1),
        "std": round(std, 3),
        "peaks": peak_list,
        "description": desc,
        "bars_used": len(rows),
    }


# ---------------------------------------------------------------- 支撑压力

def _fractal_pivots(klines):
    n = len(klines)
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    dates = [str(k.get("dt") or k.get("date") or "")[:10] for k in klines]
    pivots = []
    for i in range(2, n - 2):
        wh = highs[i - 2: i + 3]
        if highs[i] == max(wh) and (highs[i] > highs[i - 2] or highs[i] > highs[i + 2]):
            pivots.append({"i": i, "price": highs[i], "date": dates[i], "kind": "high"})
        wl = lows[i - 2: i + 3]
        if lows[i] == min(wl) and (lows[i] < lows[i - 2] or lows[i] < lows[i + 2]):
            pivots.append({"i": i, "price": lows[i], "date": dates[i], "kind": "low"})
    return pivots, highs, lows, dates


def _cluster(pivots, tol):
    if not pivots:
        return []
    ordered = sorted(pivots, key=lambda p: p["price"])
    clusters = []
    for p in ordered:
        if clusters:
            center = sum(x["price"] for x in clusters[-1]) / len(clusters[-1])
            if abs(p["price"] - center) <= tol:
                clusters[-1].append(p)
                continue
        clusters.append([p])
    out = []
    for members in clusters:
        center = sum(x["price"] for x in members) / len(members)
        out.append({
            "price": center,
            "touches": len(members),
            "last_date": max(x["date"] for x in members),
            "first_date": min(x["date"] for x in members),
        })
    return out


def detect_levels(klines, price):
    """日K分型接触点聚类 → 短期(60根)/中期(240根) 支撑与压力"""
    if not klines or len(klines) < 30:
        return {"available": False, "reason": "日K不足30根"}
    pivots, highs, lows, dates = _fractal_pivots(klines)
    if not pivots:
        return {"available": False, "reason": "未识别出有效分型拐点"}
    n = len(klines)
    atr = _atr(highs, lows, [float(k["close"]) for k in klines])
    last_atr = next((a for a in reversed(atr) if a), None)
    tol = max(last_atr or 0.0, price * 0.01)

    def side_levels(window_start, kind):
        win = [p for p in pivots if p["i"] >= window_start]
        clusters = _cluster(win, tol)
        supports = sorted(
            [c for c in clusters if c["price"] < price],
            key=lambda c: (-c["touches"], abs(c["price"] - price)))
        resistances = sorted(
            [c for c in clusters if c["price"] >= price],
            key=lambda c: (-c["touches"], abs(c["price"] - price)))
        fmt = lambda c: {"price": round(c["price"], 3), "touches": c["touches"],
                         "last_date": c["last_date"]}
        return {"support": [fmt(c) for c in supports[:2]],
                "resistance": [fmt(c) for c in resistances[:2]]}

    return {
        "available": True,
        "price": price,
        "tolerance": round(tol, 3),
        "short": side_levels(max(0, n - 60), "short"),
        "mid": side_levels(max(0, n - 240), "mid"),
        "short_window": min(n, 60),
        "mid_window": min(n, 240),
    }


# ---------------------------------------------------------------- 指标信号

def _cross_events(a, b, rising, n):
    events = []
    for i in range(1, n):
        if a[i] is None or b[i] is None or a[i - 1] is None or b[i - 1] is None:
            continue
        if rising and a[i - 1] <= b[i - 1] and a[i] > b[i]:
            events.append(i)
        elif not rising and a[i - 1] >= b[i - 1] and a[i] < b[i]:
            events.append(i)
    return events


def detect_signals(klines):
    """16 项指标信号：每项给出最近出现交易日、距今交易日数与当前状态"""
    n = len(klines)
    if n < 60:
        return []
    dates = [str(k.get("dt") or k.get("date") or "")[:10] for k in klines]
    closes = [float(k["close"]) for k in klines]
    volumes = [float(k.get("volume") or 0) for k in klines]

    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    dif, dea, _ = macd(closes)
    r6, r12 = rsi(closes, 6), rsi(closes, 12)
    kk, dd, _ = kdj(klines)
    bmid, bup, blo = boll(closes)
    vol5, vol10 = sma(volumes, 5), sma(volumes, 10)

    signals = []

    def state_signal(key, name, side, bools, detail_fn):
        last_true = None
        for i in range(n - 1, -1, -1):
            if bools[i]:
                last_true = i
                break
        currently = bools[-1]
        if currently:
            start = n - 1
            while start > 0 and bools[start - 1]:
                start -= 1
            days_ago = 0
            last_date = dates[-1]
            note = f"生效中·持续{n - start}个交易日"
        elif last_true is not None:
            days_ago = n - 1 - last_true
            last_date = dates[last_true]
            note = f"最近结束于{last_date}"
        else:
            days_ago, last_date = None, None
            note = "窗口内未出现"
        signals.append({
            "key": key, "name": name, "side": side, "kind": "state",
            "last_date": last_date, "days_ago": days_ago,
            "active": days_ago == 0, "now": currently,
            "detail": f"{detail_fn()} · {note}",
        })

    def cross_signal(key, name, side, a, b, rising, state_desc, detail_desc):
        events = _cross_events(a, b, rising, n)
        last = events[-1] if events else None
        now_a = a[-1]
        now_b = b[-1]
        now = now_a is not None and now_b is not None and ((now_a > now_b) if rising else (now_a < now_b))
        signals.append({
            "key": key, "name": name, "side": side, "kind": "cross",
            "last_date": dates[last] if last is not None else None,
            "days_ago": (n - 1 - last) if last is not None else None,
            "active": last is not None and (n - 1 - last) == 0,
            "now": now,
            "detail": f"{state_desc}（当前{'成立' if now else '不成立'}）· {detail_desc}",
        })

    # --- 交叉类（金叉=买入 / 死叉=卖出）
    cross_signal("macd_buy", "MACD买入", "buy", dif, dea, True,
                 "DIF上穿DEA", "金叉为买入触发，当前状态指DIF>DEA")
    cross_signal("macd_sell", "MACD卖出", "sell", dif, dea, False,
                 "DIF下穿DEA", "死叉为卖出触发，当前状态指DIF<DEA")
    cross_signal("kdj_buy", "KDJ买入", "buy", kk, dd, True,
                 "K上穿D", "KDJ金叉，当前状态指K>D")
    cross_signal("kdj_sell", "KDJ卖出", "sell", kk, dd, False,
                 "K下穿D", "KDJ死叉，当前状态指K<D")
    cross_signal("rsi_buy", "RSI买入", "buy", r6, r12, True,
                 "RSI6上穿RSI12", "短周期RSI上穿长周期为买入触发")
    cross_signal("rsi_sell", "RSI卖出", "sell", r6, r12, False,
                 "RSI6下穿RSI12", "短周期RSI下穿长周期为卖出触发")
    cross_signal("ma_buy", "MA买入", "buy", ma5, ma10, True,
                 "MA5上穿MA10", "5日线上穿10日线为买入触发")
    cross_signal("ma_sell", "MA卖出", "sell", ma5, ma10, False,
                 "MA5下穿MA10", "5日线下穿10日线为卖出触发")
    cross_signal("boll_buy", "BOLL买入", "buy", closes, bmid, True,
                 "收盘上穿布林中轨", "收盘价上穿中轨为买入触发")
    cross_signal("boll_sell", "BOLL卖出", "sell", closes, bmid, False,
                 "收盘下穿布林中轨", "收盘价下穿中轨为卖出触发")

    # --- 排列类（状态）
    bull = [i for i in range(n)
            if ma5[i] is not None and ma10[i] is not None and ma20[i] is not None and ma60[i] is not None
            and ma5[i] > ma10[i] > ma20[i] > ma60[i]]
    bear = [i for i in range(n)
            if ma5[i] is not None and ma10[i] is not None and ma20[i] is not None and ma60[i] is not None
            and ma5[i] < ma10[i] < ma20[i] < ma60[i]]
    bull_bools = [False] * n
    bear_bools = [False] * n
    for i in bull:
        bull_bools[i] = True
    for i in bear:
        bear_bools[i] = True
    state_signal("bull_align", "多头排列", "buy", bull_bools,
                 lambda: "MA5>MA10>MA20>MA60")
    state_signal("bear_align", "空头排列", "sell", bear_bools,
                 lambda: "MA5<MA10<MA20<MA60")

    # --- 红三兵 / 黑三兵
    def in_upper(o, h, l, c):
        rng = h - l
        return rng > 0 and (c - l) / rng >= 0.5

    def in_lower(o, h, l, c):
        rng = h - l
        return rng > 0 and (c - l) / rng <= 0.5

    red = [False] * n
    black = [False] * n
    for i in range(2, n):
        ok_r = True
        ok_b = True
        for j in (i - 2, i - 1, i):
            o = float(klines[j]["open"]); c = closes[j]
            h = float(klines[j]["high"]); l = float(klines[j]["low"])
            if not (c > o and in_upper(o, h, l, c)):
                ok_r = False
            if not (c < o and in_lower(o, h, l, c)):
                ok_b = False
        if ok_r and closes[i - 2] < closes[i - 1] < closes[i] and closes[i] > float(klines[i - 2]["open"]):
            red[i] = True
        if ok_b and closes[i - 2] > closes[i - 1] > closes[i] and closes[i] < float(klines[i - 2]["open"]):
            black[i] = True
    state_signal("red_three", "红三兵", "buy", red,
                 lambda: "连续3根阳线收盘抬高且收于当日上半区")
    state_signal("black_three", "黑三兵", "sell", black,
                 lambda: "连续3根阴线收盘走低且收于当日下半区")

    # --- 量能
    vol_bull = [False] * n
    vol_bear = [False] * n
    for i in range(n):
        if vol5[i] is not None and vol10[i] is not None:
            vol_bull[i] = vol5[i] > vol10[i]
            vol_bear[i] = vol5[i] < vol10[i]
    state_signal("vol_bull", "量多头", "buy", vol_bull, lambda: "5日均量>10日均量")
    state_signal("vol_bear", "量空头", "sell", vol_bear, lambda: "5日均量<10日均量")

    return signals


# ---------------------------------------------------------------- 交易趋势阶段

def trend_stage(klines):
    """六阶段顺序循环状态机：相邻切换 + 连续3根确认 + 至少停留5根，杜绝逐日跳变"""
    n = len(klines)
    if n < 60:
        return {"available": False, "reason": f"日K仅{n}根，不足60根"}
    dates = [str(k.get("dt") or k.get("date") or "")[:10] for k in klines]
    closes = [float(k["close"]) for k in klines]
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    r6 = rsi(closes, 6)
    _, bup, blo = boll(closes)

    cond = {}
    for i in range(n):
        c = closes[i]
        up = (ma5[i] is not None and ma10[i] is not None and ma20[i] is not None
              and c > ma5[i] > ma10[i] > ma20[i])
        down = (ma5[i] is not None and ma10[i] is not None and ma20[i] is not None
                and c < ma5[i] < ma10[i] < ma20[i])
        over = (r6[i] is not None and r6[i] >= 70) or (bup[i] is not None and c >= bup[i])
        under = (r6[i] is not None and r6[i] <= 30) or (blo[i] is not None and c <= blo[i])
        strengthen = (ma5[i] is not None and i >= 1 and ma5[i - 1] is not None
                      and c > ma5[i] and ma5[i] > ma5[i - 1])
        weak = ma10[i] is not None and c < ma10[i]
        rebound = ma5[i] is not None and c > ma5[i]
        down20 = ma20[i] is not None and c < ma20[i]
        reclaim10 = ma10[i] is not None and c > ma10[i]
        cond[i] = {"up": up, "down": down, "over": over, "under": under,
                   "strengthen": strengthen, "weak": weak, "rebound": rebound,
                   "down20": down20, "reclaim10": reclaim10}

    FWD = {0: (1, "strengthen"), 1: (2, "up"), 2: (3, "over"),
           3: (4, "weak"), 4: (5, "down"), 5: (0, "rebound")}
    BWD = {0: (5, "down"), 1: (0, "down"), 2: (1, "down20"), 3: (2, "up"),
           4: (3, "reclaim10"), 5: (4, "reclaim10")}

    def confirmed(i, key):
        if i < _CONFIRM_DAYS - 1:
            return False
        return all(cond[j][key] for j in range(i - _CONFIRM_DAYS + 1, i + 1))

    def initial(i):
        if cond[i]["down"]:
            return 5
        if cond[i]["up"]:
            return 2
        if cond[i]["under"]:
            return 0
        if cond[i]["over"]:
            return 3
        return 1

    start = 59  # ma60 自此可用
    stage = initial(start)
    stage_start = start
    changes = []
    for i in range(start + 1, n):
        dwell = i - stage_start
        moved = False
        if dwell >= _MIN_DWELL:
            tgt, key = FWD[stage]
            if confirmed(i, key):
                changes.append({"date": dates[i], "from": STAGES[stage], "to": STAGES[tgt]})
                stage, stage_start = tgt, i
                moved = True
        if not moved and dwell >= _MIN_DWELL:
            back = BWD.get(stage)
            if back:
                tgt, key = back
                if confirmed(i, key):
                    changes.append({"date": dates[i], "from": STAGES[stage], "to": STAGES[tgt]})
                    stage, stage_start = tgt, i
    return {
        "available": True,
        "stage": STAGES[stage],
        "stage_index": stage,
        "since": dates[stage_start],
        "days": n - 1 - stage_start,
        "cycle": STAGES,
        "recent_changes": changes[-6:],
        "confirm_days": _CONFIRM_DAYS,
        "min_dwell": _MIN_DWELL,
        "as_of": dates[-1],
    }


# ---------------------------------------------------------------- 汇总

def build_technical_structure(klines, float_shares=None, price=None):
    if not klines or len(klines) < 60:
        n = len(klines or [])
        return {"available": False, "reason": f"日K仅{n}根，不足60根，技术结构分析不可用"}
    price = price or float(klines[-1]["close"])
    return {
        "available": True,
        "as_of": str(klines[-1].get("dt") or klines[-1].get("date") or "")[:10],
        "price": price,
        "chip": chip_analysis(klines, float_shares, price),
        "trend_stage": trend_stage(klines),
        "levels": detect_levels(klines, price),
        "signals": detect_signals(klines),
        "methodology": [
            "筹码=近250日真实换手衰减分布，集中度=P95-P5价位宽/现价，四档：无>48%>轻度>32%>中度>18%>高度",
            "阶段=六阶段顺序循环状态机，相邻切换、条件连续3根确认、停留≥5根，不会逐日跳变",
            "支撑压力=±2根分型拐点按ATR容差聚类，短期60根/中期240根，接触点越多越强",
            "指标信号=真实日K交叉与形态计算，时间以交易日计",
        ],
    }
