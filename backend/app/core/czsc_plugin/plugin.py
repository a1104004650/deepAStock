"""官方 czsc 插件（外挂式，可选依赖）

安装 czsc>=1.0 后自动启用：真实分型/笔/中枢（Rust 核心） + 官方原生信号函数 +
多级别分析 + 离线 HTML 缠论图。未安装时上层回退内置简化缠论引擎，不影响主流程。

用法:
    from app.core.czsc_plugin import plugin
    plugin.plugin_status()          # {'available': True, 'version': '1.0.1'}
    plugin.analyze_series(klines, period)   # 返回与内置引擎同构的分析字典
"""
from datetime import datetime

import pandas as pd

from app.utils.logger import logger

try:  # czsc 为可选依赖：未安装时仅记录，不阻断
    import czsc as _czsc
    from czsc import CZSC, Freq, format_standard_kline
    from czsc._native.signals import call_signal
    from czsc.utils.plotting.lightweight import plot_czsc as _plot_czsc

    HAS_CZSC = True
    CZSC_VERSION = getattr(_czsc, "__version__", "?")
except Exception:  # pragma: no cover
    HAS_CZSC = False
    CZSC_VERSION = None
    CZSC = None
    Freq = None
    format_standard_kline = None
    call_signal = None
    _plot_czsc = None

if Freq is not None:
    PERIOD_FREQ = {"month": Freq.Y, "week": Freq.W, "day": Freq.D, "60m": Freq.F60,
                   "m60": Freq.F60, "m30": Freq.F30, "m15": Freq.F15, "m5": Freq.F5}
else:
    PERIOD_FREQ = {}

# 精选原生信号序列（官方 Rust 实现，各周期通用）
SIGNAL_SEQ = [
    "cxt_bi_status_V230101",   # 笔状态/盘背
    "cxt_bi_trend_V230824",    # 笔趋势
    "cxt_second_bs_V230320",   # 二买/二卖
    "cxt_third_bs_V230318",    # 三买/三卖(均线)
    "tas_first_bs_V230217",    # 一买/一卖
    "cxt_bs_V240526",          # 完整买卖点
    "cxt_double_zs_V230311",   # 双中枢
    "tas_macd_bc_V230803",     # MACD 双次类背驰
    "bar_trend_V240209",       # 单K趋势
    "bar_fake_break_V230204",  # 假突破
]


def plugin_status() -> dict:
    return {
        "available": bool(HAS_CZSC),
        "version": CZSC_VERSION,
        "engine": "czsc" if HAS_CZSC else "builtin",
        "signals_enabled": len(SIGNAL_SEQ) if HAS_CZSC else 0,
    }


def _to_freq(period: str):
    if Freq is None:
        return None
    return PERIOD_FREQ.get(period, Freq.D)


def build_bars(klines: list[dict], period: str = "day", symbol: str = ""):
    """把我们的 K线 dict 列表转成 czsc RawBar 列表"""
    if not HAS_CZSC or not klines:
        return []
    freq = _to_freq(period)
    df = pd.DataFrame([
        {"symbol": symbol or "", "dt": pd.to_datetime(k["dt"]), "open": float(k["open"]),
         "high": float(k["high"]), "low": float(k["low"]), "close": float(k["close"]),
         "vol": float(k.get("volume") or k.get("vol") or 0),
         "amount": float(k.get("amount") or 0)} for k in klines
    ])
    return format_standard_kline(df, freq=freq)


def _signal_to_buy_sell(sig) -> str | None:
    txt = sig.to_json()
    if "买" in txt:
        return "buy"
    if "卖" in txt:
        return "sell"
    return None


def _is_top_fractal(mark) -> bool:
    """czsc 版本差异兜底：Mark.G 枚举的 str/repr 在不同版本可能是 'Mark.G'/'顶分型'/'TopG'"""
    s = str(mark)
    return s in ("Mark.G", "顶分型", "TopG") or s.endswith("G") or s.endswith("Top")


def _signal_type_text(txt: str) -> str | None:
    import re
    m = re.findall(r"[一二三][买卖]", txt)
    if m:
        return m[0]
    if "BS1" in txt and ("买" in txt or "卖" in txt):
        return "1买" if "买" in txt and "卖" not in txt else ("1卖" if "卖" in txt else None)
    if "BS2" in txt and ("买" in txt or "卖" in txt):
        return "2买" if "买" in txt and "卖" not in txt else ("2卖" if "卖" in txt else None)
    if "BS3" in txt and ("买" in txt or "卖" in txt):
        return "3买" if "买" in txt and "卖" not in txt else ("3卖" if "卖" in txt else None)
    if "第一类" in txt:
        return "1买" if "买" in txt else "1卖"
    if "第二类" in txt:
        return "2买" if "买" in txt else "2卖"
    if "第三类" in txt:
        return "3买" if "买" in txt else "3卖"
    if "反手" in txt:
        return "反手"
    if "二买" in txt:
        return "2买"
    if "一买" in txt:
        return "1买"
    if "三买" in txt:
        return "3买"
    if "二卖" in txt:
        return "2卖"
    if "一卖" in txt:
        return "1卖"
    if "三卖" in txt:
        return "3卖"
    if "买点" in txt or "买" in txt:
        return "买点"
    if "卖点" in txt or "卖" in txt:
        return "卖点"
    return None


def _signal_type(sig) -> str | None:
    txt = sig.to_json()
    return _signal_type_text(txt)


def _sma(values, period):
    if len(values) < period:
        return None
    return [float(sum(values[max(0, i - period + 1): i + 1]) / min(period, i + 1)) for i in range(len(values))]


def _calc_boll(closes: list, period: int = 20) -> dict:
    if len(closes) < period:
        return {"mid": 0, "upper": 0, "lower": 0, "width": 0, "position": "数据不足", "price": 0}
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


def _yangjia_stage(klines: list, closes: list) -> dict:
    """养家心法情绪阶段：吸筹→洗盘→拉升→出货 四阶段周期循环（去掉恐慌盘/试盘）"""
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
    stage, desc = "吸筹", "多空分歧，伺机低吸"
    subtype = ""

    if position_pct >= 78 and (vol_ratio >= 1.3 or recent_chg <= 0 or chg_20 > 22):
        stage, subtype = "出货", "高位派发"
        desc = "高位放量滞涨或缩量阴跌，主力边拉边派发，追高易接盘，逢高减仓"
    elif chg_20 < -8 and position_pct <= 35 and vol_ratio < 0.9:
        stage, subtype = "吸筹", "恐慌止跌"
        desc = "深度回调后缩量企稳，恐慌抛压出清，主力缓慢吸筹接近尾声"
    elif chg_20 > 12 and position_pct > 60 and vol_ratio >= 1.2:
        stage, subtype = "拉升", "主升加速"
        desc = "放量加速上攻，主力主升拉升，趋势最强，勿轻易下车也不宜追高"
    elif chg_20 > 4 and position_pct > 50 and vol_ratio >= 1.0:
        stage, subtype = "拉升", "放量拉升"
        desc = "放量突破走强，主力拉升脱离成本区，跟风盘积极"
    elif position_pct >= 45 and recent_chg <= 0 and vol_ratio < 1.0:
        stage, subtype = "洗盘", "缩量回调"
        desc = "拉升途中或高位缩量回调，主力洗掉浮筹，缩量过前高代表洗盘洗得好"
    elif position_pct < 45 and chg_20 <= 6:
        stage, subtype = "吸筹", "低位建仓"
        desc = "低位横盘或回落，主力悄然建仓，慢涨慢放量代表吃货动作明显"
    elif chg_20 > 1 and recent_chg > 0:
        stage, subtype = "拉升", "缓步上行"
        desc = "温和放量缓步上移，慢牛爬升，量价配合良好"
    elif vol_ratio >= 1.2 and chg_20 < 0:
        stage, subtype = "吸筹", "放量承接"
        desc = "下跌放量承接，主力低位吸筹，散户割肉盘涌出"
    elif vol_ratio < 1.0:
        stage, subtype = "洗盘", "缩量整理"
        desc = "量能枯竭整理换手，浮筹出清，等待方向选择"
    elif position_pct >= 55:
        stage, subtype = "拉升", "多空分歧"
        desc = "中高位多空分歧，主力活跃度一般，等企稳再上"
    else:
        stage, subtype = "吸筹", "低吸观察"
        desc = "低位多空分歧，量能温和，可逢低分批关注"
    return {"stage": stage, "subtype": subtype,
            "description": desc, "position_pct": round(position_pct, 1),
            "vol_ratio": round(vol_ratio, 2), "chg_20d": round(chg_20, 2)}


def _control_score(klines: list) -> dict:
    """主力控盘度 0-100：筹码集中度(量价) + 振幅收敛度 + 上涨放量/下跌缩量 综合估算"""
    if len(klines) < 25:
        return {"score": 0, "level": "未知", "description": "数据不足"}
    seg = klines[-25:]
    closes = [float(k["close"]) for k in seg]
    highs = [float(k["high"]) for k in seg]
    lows = [float(k["low"]) for k in seg]
    vols = [float(k.get("volume", 0)) for k in seg]
    mean_c = sum(closes) / len(closes)
    std_c = (sum((c - mean_c) ** 2 for c in closes) / len(closes)) ** 0.5
    amp = sum((h - l) / mean_c for h, l in zip(highs, lows)) / len(seg)  # 日均振幅
    up_vol = sum(v for i, v in enumerate(vols) if closes[i] >= closes[i - 1])
    dn_vol = sum(v for i, v in enumerate(vols) if i > 0 and closes[i] < closes[i - 1])
    ratio = (up_vol / dn_vol) if dn_vol else 2.0
    cv = std_c / mean_c if mean_c else 0  # 收盘价离散度
    score = 0.0
    score += max(0, min(30, (2.0 - amp * 100) * 12))          # 振幅收敛 → 筹码锁定（最多30分）
    score += max(0, min(30, (1.5 - cv * 100) * 15))          # 价格平稳 → 主力控盘（最多30分）
    score += max(0, min(25, (ratio - 0.8) * 18))             # 上涨放量/下跌缩量（最多25分）
    score += max(0, min(15, 15 - 3 * (sum(1 for v in vols if v <= 0))))  # 有量能（底分15分）
    score = round(min(100, max(0, score)), 1)
    level = ("重度控盘" if score >= 80 else "高度控盘" if score >= 60 else
             "中度控盘" if score >= 40 else "低度控盘")
    desc = ("筹码高度集中，股价被主力牢牢掌控，极易走出独立行情" if level == "重度控盘" else
            "主力介入较深，回调缩量、走高放量，短中线上行有保障" if level == "高度控盘" else
            "主力有一定参与但未完全控盘，跟随大盘波动为主" if level == "中度控盘" else
            "主力参与度低，筹码分散，多为散户主导交易")
    return {"score": score, "level": level, "description": desc,
            "amp": round(amp * 100, 2), "vol_ratio": round(ratio, 2)}


def _mnemonic_tags(klines: list, fx_list: list = None) -> list[dict]:
    """量价口诀标签：依据用户提供的操作笔记/口诀，仅实现能由 K 线客观计算的部分。
    每条含 label/type(danger看多·success看空·warning风险·info观察)/desc。"""
    if len(klines) < 30:
        return []
    o = [float(k["open"]) for k in klines[-30:]]
    h = [float(k["high"]) for k in klines[-30:]]
    lo = [float(k["low"]) for k in klines[-30:]]
    c = [float(k["close"]) for k in klines[-30:]]
    v = [float(k.get("volume", 0)) for k in klines[-30:]]
    tags = []
    n = len(c)
    ma20_last = _sma(c, 20)[-1] if len(c) >= 20 else 0

    def avg(arr, sl):
        s = arr[len(arr) - sl:]
        return sum(s) / len(s) if s else 0

    def chg(i):
        return (c[i] - c[i - 1]) / c[i - 1] * 100 if i > 0 and c[i - 1] else 0

    body = abs(c[-1] - o[-1])
    day_range = (h[-1] - lo[-1]) or 0.001
    lower_shadow = min(o[-1], c[-1]) - lo[-1]
    upper_shadow = h[-1] - max(o[-1], c[-1])
    base_vol = avg(v, 5)

    # 1) 高量第1天——观（高量=主力异动=拐点）
    if len(v) >= 4 and v[-1] > max(v[-4:-1]) and v[-1] > 0:
        tags.append({"label": "高量·主力异动", "type": "warning",
                     "desc": "当日量大于前三天，主力异动/拐点信号，第1天多看少动"})
    # 2) 高量 2、3 天支撑线上方——阳上阴观（量在价先，看后几日在支撑上方能否守住）
    if len(v) >= 4 and v[-1] > max(v[-4:-1]) and c[-1] > ma20_last:
        tags.append({"label": "高量在支撑上", "type": "info",
                     "desc": "高量且收在 MA20 上方，第2、3天能站稳支撑则以阳上阴视之，破了再减"})
    # 3) 高量破，有灾祸——清/减：收盘跌破近期高量日实体低点
    if len(v) >= 12:
        hv_i, hv = None, 0
        for i in range(max(1, n - 12), n - 1):
            if v[i] > hv:
                hv, hv_i = v[i], i
        if hv_i is not None:
            body_low = min(o[hv_i], c[hv_i])
            if c[-1] < body_low:
                tags.append({"label": "高量破实体·减", "type": "success",
                             "desc": "收盘跌破近期高量日实体低点——高量破，有灾祸，先减仓"})
            elif lo[-1] < body_low:
                tags.append({"label": "高量破探底·观", "type": "info",
                             "desc": "盘中击破近期高量实体低点后收回，次日不破可视为支撑有效"})
    # 4) 上涨梯量——风险（连升3天量且价涨）
    if len(v) >= 4 and v[-1] > v[-2] > v[-3] and c[-1] > c[-2] > c[-3] and c[-1] >= o[-1]:
        tags.append({"label": "上涨梯量·风险", "type": "warning",
                     "desc": "连续三日梯量上攻，短线过热，风险大于机会"})
    # 5) 连续三天高低点下移——下跌趋势
    if len(c) >= 3 and h[-1] < h[-2] < h[-3] and lo[-1] < lo[-2] < lo[-3] and c[-1] < c[-2]:
        tags.append({"label": "高低点下移·跌", "type": "success",
                     "desc": "连续三天高低点同步下移，进入下跌趋势，反弹观望"})
    # 6) 长下影线系列（影线≥实体2倍）
    if lower_shadow >= 2 * body and lower_shadow > 0:
        if c[-1] >= o[-1] and v[-1] < base_vol:
            tags.append({"label": "缩量长下影·观", "type": "info",
                         "desc": "缩量大长腿下探回升，支撑有效可以观察（口诀13）"})
        elif v[-1] > max(v[-4:-1]):
            tags.append({"label": "高量长下影·机", "type": "danger",
                         "desc": "高量长下影，下影实体低点为支撑位，守则留（风险高量下影线=机）"})
        elif c[-1] < o[-1]:
            tags.append({"label": "长下影收阴·风险", "type": "success",
                         "desc": "长下影但仍收阴，次日常有低价，下影线越多越长下跌概率越大"})
        else:
            tags.append({"label": "长下影·观", "type": "info", "desc": "长下影线，观望等确认"})
    # 7) 长上影线（影线≥实体2倍）——过不了压力减
    if upper_shadow >= 2 * body and upper_shadow > 0:
        if c[-1] < o[-1]:
            tags.append({"label": "长上影收阴·减", "type": "success",
                         "desc": "长上影收阴，抛压沉重，上影碰到压力过不去——减"})
        else:
            tags.append({"label": "冲高回落上影", "type": "warning",
                         "desc": "长上影阳线，上方套牢盘重，若后续被阳线实体吞没则看多"})
    # 8) 连红≥4天见绿(放量)——减
    reds = 0
    for i in range(n - 1, max(n - 6, 0), -1):
        if c[i] > c[i - 1] and c[i] >= o[i]:
            reds += 1
        else:
            break
    if reds >= 4 and c[-1] < o[-1] and v[-1] > base_vol:
        tags.append({"label": "连红见绿·减", "type": "success",
                     "desc": "连收4天红后放量见绿，短线获利兑现，减仓为主"})
    # 9) 量大实体小，多数有人跑——减（高位）
    if body / day_range < 0.3 and v[-1] > max(v[-4:-1] if len(v) >= 4 else [0]):
        if c[-1] >= max(c[-16:-1]) * 0.97:
            tags.append({"label": "高位量大实体小·减", "type": "success",
                         "desc": "高位放巨量但实体极小，量大花钱多不办事，主力出货迹象明显"})
        else:
            tags.append({"label": "放量滞涨", "type": "warning",
                         "desc": "放量但实体很小，多空分歧大，警惕诱多"})
    # 10) MA20 上方底分型——上看；MA20 下方顶分型——减仓
    if fx_list:
        last_fx = fx_list[-1]
        if last_fx.get("mark") == "d" and c[-1] > ma20_last and ma20_last:
            tags.append({"label": "支撑上方底分型·上", "type": "danger",
                         "desc": "MA20 支撑线上方出现底分型，企稳偏多（口诀20）"})
        if last_fx.get("mark") == "g" and ma20_last and c[-1] < ma20_last:
            tags.append({"label": "压力下方顶分型·减", "type": "success",
                         "desc": "MA20 下方出现顶分型，反弹乏力，减仓（口诀26）"})
    # 11) 缺口（不灌破，前高早晚都会过 ≈ 跳空缺口不回补看高）
    if len(c) >= 3 and lo[-2] > h[-3] and lo[-1] > h[-3] and c[-2] >= o[-2] and c[-1] >= o[-1]:
        tags.append({"label": "上升缺口未补·看高", "type": "danger",
                     "desc": "向上跳空缺口连续两日未被灌破，缺口不破前高早晚过"})
    elif len(c) >= 3 and h[-2] < lo[-3] and h[-1] < lo[-3] and c[-2] < o[-2] and c[-1] < o[-1]:
        tags.append({"label": "下跌缺口未补·弱", "type": "success",
                     "desc": "向下跳空缺口持续未回补，反弹难过缺口压力"})
    # 12) 下跌趋势第一次高量——诱多，观3天
    declining = len(c) >= 6 and c[-5] < c[-6] and c[-4] < c[-5] and c[-3] < c[-4]
    if declining and v[-1] > max(v[-4:-1]) and chg(n - 1) <= 0:
        tags.append({"label": "下跌首次高量·诱多", "type": "success",
                     "desc": "下跌趋势中首次放量，疑似诱多反弹，观察3天"})
    # 13) 下跌趋势缩量/平量反弹——观
    if declining and c[-1] > c[-2] and v[-1] <= base_vol:
        tags.append({"label": "缩量弱反弹·观", "type": "info",
                     "desc": "下跌趋势中缩量反弹，力度存疑，观望不追"})
    # 14) 上涨趋势高量大长腿——减（顶部区）
    if lower_shadow >= 2 * body and c[-1] >= max(c[-16:-1]) * 0.97:
        tags.append({"label": "高位长下影·减", "type": "success",
                     "desc": "上涨趋势高位出现高量大长腿，变盘风险，减仓防守"})
    return tags


def _stage_sequence(klines: list) -> list:
    """逐K线情绪阶段序列（用于K线图下方阶段色带标注）"""
    out = []
    for i in range(len(klines)):
        if i < 20:
            continue
        seg = klines[:i + 1]
        closes = [float(k["close"]) for k in seg]
        st = _yangjia_stage(seg[-20:], closes[-20:])
        stage = (st or {}).get("stage", "")
        if stage and stage != "unknown":
            out.append({"dt": klines[i]["dt"], "stage": stage})
        else:
            out.append({"dt": klines[i]["dt"], "stage": ""})
    return out


_STAGE_COLORS = {
    "吸筹": "#409eff", "洗盘": "#e6a23c", "拉升": "#ef232a", "出货": "#8b5cf6",
}


def stage_color(stage: str) -> str:
    return _STAGE_COLORS.get(stage, "#c0c4cc")


def analyze_series(klines: list[dict], period: str = "day") -> dict:
    """官方 CZSC 全量分析，输出与内置引擎同构；失败抛异常由上层回退"""
    base = {"symbol": "", "period": period, "fx_list": [], "bi_list": [],
            "zs_list": [], "signals": [], "current_state": {},
            "engine": f"czsc:{CZSC_VERSION}", "analyzed_at": datetime.now().isoformat()}
    if not HAS_CZSC:
        base["engine"] = "builtin"
        raise RuntimeError("czsc unavailable")
    if len(klines) < 60:
        base["error"] = "数据不足"
        return base

    bars = build_bars(klines, period)
    if len(bars) < 60:
        base["error"] = "数据不足"
        return base
    c = CZSC(bars)

    fx_list = []
    for f in c.fx_list:
        is_top = _is_top_fractal(f.mark)
        fx_list.append({
            "dt": str(f.dt)[:10],
            "mark": "g" if is_top else "d",
            "price": round(float(f.fx), 2),
            "type": "顶分型" if is_top else "底分型",
        })
    bi_list = []
    for b in c.bi_list:
        bdir = str(b.direction)
        is_up = bdir in ("Up", "Direction.Up", "向上", "mark Up", "UP") or bdir.endswith("Up")
        bi_list.append({
            "start": str(b.fx_a.dt)[:10], "end": str(b.fx_b.dt)[:10],
            "direction": "up" if is_up else "down",
            "high": round(float(b.high), 2), "low": round(float(b.low), 2),
            "power": round(float(getattr(b, "power", 0) or 0), 2),
        })
    zs_list = []
    for z in c.zs_list:
        zs_list.append({
            "start": str(z.sdt)[:10], "end": str(z.edt)[:10],
            "high": round(float(z.zg), 2), "low": round(float(z.zd), 2),
        })

    raw_signals, signal_events = [], []
    last_dt = str(bars[-1].dt)[:10]
    for name in SIGNAL_SEQ:
        try:
            for sig in call_signal(name, c):
                d = {"k1": str(sig.k1), "k2": str(sig.k2), "k3": str(sig.k3),
                     "v1": str(sig.v1), "v2": str(sig.v2), "v3": str(sig.v3),
                     "key": str(sig.key), "value": sig.to_json()}
                raw_signals.append(d)
                bs = _signal_to_buy_sell(sig)
                if bs:
                    signal_events.append({
                        "time": last_dt, "type": bs,
                        "signal_type": _signal_type(sig),
                        "text": d["value"][:120],
                        "reason": d["value"][:80],
                    })
        except Exception as e:
            logger.warning(f"czsc signal {name} failed: {e}")

    closes = [float(k["close"]) for k in klines]
    ma5 = _sma(closes, 5)
    trend = "consolidate"
    if len(bi_list) >= 2:
        last_dir = bi_list[-1]["direction"]
        prev_dir = bi_list[-2]["direction"]
        if last_dir == prev_dir == "up":
            trend = "up"
        elif last_dir == prev_dir == "down":
            trend = "down"
    boll = _calc_boll(closes)
    yangjia_stage = _yangjia_stage(klines, closes)
    control = _control_score(klines)
    state = {
        "trend": trend,
        "last_bi_direction": bi_list[-1]["direction"] if bi_list else None,
        "bi_count": len(bi_list),
        "zs_count": len(zs_list),
        "last_zs": zs_list[-1] if zs_list else None,
        "price": closes[-1] if closes else None,
        "ma5": round(ma5[-1], 2) if ma5 else None,
        "boll": boll,
        "yangjia_stage": yangjia_stage,
        "stage": yangjia_stage.get("stage"),
        "control": control,
    }
    base.update({
        "fx_list": fx_list[-40:], "bi_list": bi_list[-40:],
        "zs_list": zs_list[-5:], "signals": signal_events[-20:],
        "raw_signals": raw_signals[:40], "current_state": state,
        "stage_points": _stage_sequence(klines),
        "mnemonic_tags": _mnemonic_tags(klines, fx_list[-40:])[:12],
    })
    # 结构化三买三卖（基于笔+中枢，官方分型/笔数据，弥补原生信号不常触发的缺失）
    structural = _detect_three_buy_sell(bi_list[-60:], zs_list)
    if structural:
        base["signals"] = (structural + signal_events)[:40]
    return base


def _detect_three_buy_sell(bi_list: list[dict], zs_list: list[dict]) -> list[dict]:
    """基于官方笔/中枢数据的 1/2/3 买卖点结构检测（与内置引擎同规则）"""
    if len(bi_list) < 5:
        return []
    signals = []
    for i in range(2, len(bi_list)):
        cur, prev, prev2 = bi_list[i], bi_list[i - 1], bi_list[i - 2]
        if not prev or not prev2:
            continue
        if cur["direction"] == "up":
            # 一买：连续下跌笔后底分型反转
            if prev["direction"] == "down" and prev2["direction"] == "down" and cur["high"] > prev2["high"]:
                signals.append({"time": cur["end"], "type": "buy", "signal_type": "1买",
                                "reason": "趋势下跌后底分型反转"})
            for zs in zs_list:
                if prev["low"] <= zs["low"] and cur["high"] > zs["high"] and cur["end"] >= zs["end"]:
                    signals.append({"time": cur["end"], "type": "buy", "signal_type": "2买",
                                    "reason": f"中枢{zs['low']}-{zs['high']}下沿获支撑"})
                    break
            for zs in zs_list:
                if prev["low"] > zs["high"] and cur["high"] > zs["high"] and prev["low"] > zs["high"]:
                    signals.append({"time": cur["end"], "type": "buy", "signal_type": "3买",
                                    "reason": f"回踩不入中枢上沿{zs['high']}"})
                    break
        elif cur["direction"] == "down":
            if prev["direction"] == "up" and prev2["direction"] == "up" and cur["low"] < prev2["low"]:
                signals.append({"time": cur["end"], "type": "sell", "signal_type": "1卖",
                                "reason": "趋势上涨后顶分型反转"})
            for zs in zs_list:
                if prev["high"] >= zs["high"] and cur["low"] < zs["low"] and cur["end"] >= zs["end"]:
                    signals.append({"time": cur["end"], "type": "sell", "signal_type": "2卖",
                                    "reason": f"中枢{zs['low']}-{zs['high']}上沿承压"})
                    break
            for zs in zs_list:
                if prev["high"] < zs["low"] and cur["low"] < zs["low"] and prev["high"] < zs["low"]:
                    signals.append({"time": cur["end"], "type": "sell", "signal_type": "3卖",
                                    "reason": f"反弹不入中枢下沿{zs['low']}"})
                    break
    return [{"time": s["time"], "type": s["type"], "signal_type": s["signal_type"],
             "reason": s["reason"]} for s in signals]


def plot_html(klines: list[dict], period: str = "day", title: str = "") -> str | None:
    """生成自包含离线 HTML 缠论图（可嵌入 iframe / 下载），失败返回 None"""
    if not HAS_CZSC or len(klines) < 60:
        return None
    try:
        bars = build_bars(klines, period)
        if len(bars) < 60:
            return None
        c = CZSC(bars)
        return _plot_czsc(c, output="html", title=title or f"缠论图 {period}")
    except Exception as e:
        logger.warning(f"czsc plot failed: {e}")
        return None


def multi_level_analysis(period_results: dict) -> dict:
    """将多级别插件分析结果做综合：小级别定买卖点、大级别定方向"""
    levels = {}
    day = period_results.get("day") or {}
    week = period_results.get("week") or {}
    t60 = period_results.get("m60") or {}
    levels["week"] = (day.get("current_state") or {}).get("trend", "unknown")
    levels["m60"] = (t60.get("current_state") or {}).get("trend", "unknown")
    levels["day"] = (day.get("current_state") or {}).get("trend", "unknown")
    levels["week"] = (week.get("current_state") or {}).get("trend", "unknown")
    buys = sum(1 for p in period_results.values() if isinstance(p, dict) and p.get("signals")
               and any(s.get("type") == "buy" for s in p["signals"]))
    sells = sum(1 for p in period_results.values() if isinstance(p, dict) and p.get("signals")
                and any(s.get("type") == "sell" for s in p["signals"]))
    if levels.get("week") == "down":
        signal = "avoid"
    elif levels.get("day") == "up" and levels.get("m60") == "up":
        signal = "buy_zone"
    elif levels.get("day") == "down" and levels.get("m60") == "down":
        signal = "watch_sell"
    else:
        signal = "neutral"
    return {
        "levels": levels,
        "buy_signals": buys, "sell_signals": sells,
        "signal": signal,
        "advice": ("观望为主，大级别走弱，注意风险" if signal == "avoid"
                   else "日线与60分钟同步向上，逢低关注买点" if signal == "buy_zone"
                   else "日线与60分钟同步向下，持币等待企稳" if signal == "watch_sell"
                   else "震荡格局，等待方向选择，区间操作为主"),
    }