"""朴素基线预测（naive baseline）——Kronos 式实验对照契约。

任何花哨模型必须先打败这里的 baseline 才算有效。只依赖免费日线收盘价，
不引入付费源、不调用 LLM。指标：方向准确率 / MAE / RMSE；口径写在返回里。
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _direction(ret: float) -> int:
    if ret > 0:
        return 1
    if ret < 0:
        return -1
    return 0


def walk_forward_naive(closes: List[float], horizon: int = 1) -> Dict:
    """用 t 日信息预测 t+horizon 收益（naive walk-forward，无未来函数）。

    收益定义：r_t = close_{t+h}/close_t - 1（对 h 步滚动）。
    每个 baseline 给出 pred_r，与 actual_r 对比。
    """
    if len(closes) < horizon + 2:
        return {"ok": False, "error": f"K线过少（需要至少 {horizon + 2} 根）", "n": len(closes)}

    # actual returns for evaluation: index i uses closes[i] -> closes[i+h]
    actuals = []
    preds: Dict[str, List[float]] = {
        "random_walk": [],
        "momentum_5": [],
        "mean_reversion_5": [],
        "day_of_week": [],
    }
    # simple day-of-week prior from trailing windows (Monday effect style)
    # use calendar weekday of each bar via index % 7 only as weak prior when no date given
    n = len(closes)
    for i in range(0, n - horizon):
        base = closes[i]
        if base <= 0:
            continue
        actual = _safe_div(closes[i + horizon], base) - 1.0
        actuals.append(actual)

        # 1) random walk: next return = 0
        preds["random_walk"].append(0.0)

        # 2) momentum: use last min(5, i) returns average as forecast
        look = min(5, i)
        if look >= 1:
            rets = [(closes[j] / closes[j - 1]) - 1.0 for j in range(i - look + 1, i + 1)]
            mom = sum(rets) / len(rets)
        else:
            mom = 0.0
        preds["momentum_5"].append(mom * horizon)

        # 3) mean reversion: -k * last return
        if i >= 1 and closes[i - 1] > 0:
            last_r = closes[i] / closes[i - 1] - 1.0
            mr = -0.5 * last_r * horizon
        else:
            mr = 0.0
        preds["mean_reversion_5"].append(mr)

        # 4) day-of-week: average return of same weekday position in history (mod 7)
        # When dates are unknown, mod 7 is a crude weekday proxy — documented as low confidence.
        wd = i % 7
        same = []
        j = i - 7
        while j >= horizon:
            if closes[j] > 0 and j + horizon < n:
                same.append(closes[j + horizon] / closes[j] - 1.0)
            j -= 7
        preds["day_of_week"].append(sum(same) / len(same) if same else 0.0)

    if len(actuals) < 5:
        return {"ok": False, "error": f"可评估样本过少（{len(actuals)}）", "n": n}

    metrics = {}
    for name, p in preds.items():
        # align lengths
        m = min(len(p), len(actuals))
        pp, aa = p[:m], actuals[:m]
        errs = [pp[i] - aa[i] for i in range(m)]
        abs_errs = [abs(e) for e in errs]
        sq_errs = [e * e for e in errs]
        mae = sum(abs_errs) / m
        rmse = math.sqrt(sum(sq_errs) / m)
        # direction accuracy: compare sign of pred vs actual, ignore flat actuals
        hits = total = 0
        for a, b in zip(aa, pp):
            da, db = _direction(a), _direction(b)
            if da == 0:
                continue
            total += 1
            if da == db:
                hits += 1
        dir_acc = _safe_div(hits, total) if total else None
        # naive random-walk has pred=0 always → direction undefined for pred; count as miss on non-flat
        if name == "random_walk":
            dir_acc = _safe_div(hits, total) if total else None
        metrics[name] = {
            "mae": round(mae, 6),
            "rmse": round(rmse, 6),
            "direction_accuracy": round(dir_acc, 4) if dir_acc is not None else None,
            "n_eval": m,
            "n_directional": total,
            "bias": round(sum(errs) / m, 6),
        }

    # ranking: lower mae better; if direction_accuracy present prefer higher among similar mae
    best = min(
        metrics.items(),
        key=lambda kv: (kv[1]["mae"], -(kv[1]["direction_accuracy"] or 0)),
    )[0]

    return {
        "ok": True,
        "horizon": horizon,
        "n_bars": n,
        "n_eval": len(actuals),
        "metrics": metrics,
        "best_baseline": best,
        "baselines": list(preds.keys()),
        "definition": (
            "walk-forward 朴素基线：用 t 日及之前信息预测 t+h 收益 "
            "r = close_{t+h}/close_t - 1；random_walk=0；momentum_5=近5日均收益×h；"
            "mean_reversion_5=-0.5×最新单日收益×h；day_of_week=同星期位置历史均收益（无日期时用 i%7 弱代理，置信度低）。"
        ),
        "metrics_definition": "方向准确率=sign(pred)==sign(actual) 且 actual≠0 的比例；MAE/RMSE 在收益尺度上计算。",
        "confidence": "medium" if n >= 60 else "low",
        "caveat": "day_of_week 无真实交易日历对齐时不可信；direction_accuracy 对 random_walk 恒为 0（预测方向恒为 0）。任何模型须在同口径下 MAE/RMSE 优于本表才算有增量。",
    }


async def run_baseline_forecast(db, symbol: str, period: str = "day",
                                horizon: int = 1, start=None, end=None) -> dict:
    from app.core.market.kline_service import KlineService

    payload = await KlineService(db).get_klines(symbol, period, start, end, with_indicators=False)
    klines = payload.get("data") or []
    closes = []
    for b in klines:
        try:
            c = float(b.get("close"))
        except (TypeError, ValueError):
            continue
        if c > 0:
            closes.append(c)

    result = walk_forward_naive(closes, horizon=max(1, min(int(horizon), 10)))
    result["symbol"] = symbol.upper()
    result["period"] = period
    result["data_source"] = "free_daily_kline"
    if not result.get("ok"):
        result["available"] = False
        result["reason"] = result.get("error") or "数据不足，不伪装中性结果"
    else:
        result["available"] = True
    return result
