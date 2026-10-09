"""Historical condition-event attribution over the locally cached daily panel."""
from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Kline, StockName


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _mean(values: list[float | None], required: int | None = None) -> float | None:
    valid = [v for v in values if v is not None]
    if required is not None and len(valid) != required:
        return None
    return statistics.fmean(valid) if valid else None


def _pct(value: float | None) -> float | None:
    return round(value * 100, 3) if value is not None else None


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - pos) + ordered[high] * (pos - low)


def _bootstrap_ci(values: list[float], iterations: int = 500) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    rng = random.Random(20261009 + len(values))
    means = []
    for _ in range(iterations):
        means.append(sum(rng.choice(values) for _ in values) / len(values))
    return _quantile(means, .025), _quantile(means, .975)


def _cluster_bootstrap_ci(pairs: list[tuple[str, float]], iterations: int = 500) -> tuple[float | None, float | None]:
    """按事件日聚类重抽样：同一天的事件始终同时入样，事件加权均值的 95% CI。"""
    groups: dict[str, list[float]] = defaultdict(list)
    for day, value in pairs:
        groups[day].append(value)
    days = list(groups)
    if len(days) < 2:
        return None, None
    rng = random.Random(20261009 + len(days))
    means = []
    for _ in range(iterations):
        sample: list[float] = []
        for _ in days:
            sample.extend(groups[rng.choice(days)])
        means.append(sum(sample) / len(sample))
    return _quantile(means, .025), _quantile(means, .975)


def _t_stat(values: list[float]) -> float | None:
    """IID t = mean / (sample_std / sqrt(n))。事件间不独立时仅供方向参考。"""
    if len(values) < 3:
        return None
    std = statistics.stdev(values)
    if not std:
        return None
    return statistics.fmean(values) / (std / math.sqrt(len(values)))


def _limit_threshold(symbol: str, name: str = "") -> float:
    digits = "".join(ch for ch in symbol if ch.isdigit())
    upper_name = (name or "").upper()
    if symbol.upper().startswith("BJ") or digits.startswith(("43", "83", "87", "92")):
        return .295
    if digits.startswith(("300", "301", "688")):
        return .195
    if "ST" in upper_name:
        return .047
    return .098


def _board(symbol: str) -> str:
    value = symbol.upper()
    digits = "".join(ch for ch in value if ch.isdigit())
    if value.startswith("BJ") or digits.startswith(("43", "83", "87", "92")):
        return "beijing"
    if value.startswith("SH688"):
        return "star"
    if value.startswith(("SZ300", "SZ301")):
        return "chinext"
    if value.startswith(("SH600", "SH601", "SH603", "SH605")):
        return "main_sh"
    if value.startswith(("SZ000", "SZ001", "SZ002", "SZ003")):
        return "main_sz"
    return "unknown"


def _is_equity(symbol: str) -> bool:
    return _board(symbol) != "unknown"


def _window(rows: list[dict], index: int, lookback: int, include_current: bool = False) -> list[dict]:
    end = index + 1 if include_current else index
    start = end - lookback
    return rows[start:end] if start >= 0 and lookback > 0 else []


def _range(value: float | None, condition: dict, low: float = -math.inf,
           high: float = math.inf) -> bool:
    minimum = float(condition.get("min", low))
    maximum = float(condition.get("max", high))
    return value is not None and minimum <= value <= maximum


def _derived(rows: list[dict], symbol: str, name: str) -> list[dict]:
    threshold = _limit_threshold(symbol, name)
    streak = 0
    closes: list[float] = []
    volumes: list[float] = []
    out = []
    for index, raw in enumerate(rows):
        close = _num(raw.get("close"))
        prev = _num(rows[index - 1].get("close")) if index else None
        change = close / prev - 1 if close and prev else None
        is_limit = change is not None and change >= threshold
        streak = streak + 1 if is_limit else 0
        volume = _num(raw.get("volume"))
        closes.append(close)
        volumes.append(volume)
        ma5 = _mean(closes[-5:], 5)
        prior_volumes = volumes[max(0, index - 5):index]
        vol_ma5 = _mean(prior_volumes, 5)
        out.append({
            **raw, "index": index, "change": change, "amplitude": (
                (_num(raw.get("high")) - _num(raw.get("low"))) / prev
                if prev and _num(raw.get("high")) is not None and _num(raw.get("low")) is not None else None
            ), "limit_threshold": threshold, "is_limit_up": is_limit,
            "limit_streak": streak, "ma5": ma5, "volume_ma5": vol_ma5,
        })
    return out


class EventStudyEngine:
    ENGINE_VERSION = "condition-event-v1"
    SUPPORTED_TYPES = {
        "limit_up_streak", "post_limit_pullback", "turnover_limit_up",
        "change_pct", "volume_ratio", "amplitude", "close_vs_ma5", "return_n",
        "direction_streak", "gap_pct", "intraday_return_pct", "close_location",
        "upper_shadow_pct", "lower_shadow_pct", "breakout_distance", "range_position",
        "drawdown_from_high", "rebound_from_low", "ma_distance", "ma_cross",
        "realized_volatility", "atr_pct", "volume_trend", "volume_contraction_streak",
        "first_limit_in_window", "days_since_limit", "limit_break",
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def capabilities(self) -> dict:
        total_symbols = len((await self.db.execute(
            select(Kline.symbol).where(Kline.period == "day").distinct()
        )).scalars().all())
        turnover_symbols = len((await self.db.execute(
            select(Kline.symbol).where(Kline.period == "day", Kline.turnover.is_not(None)).distinct()
        )).scalars().all())
        dates = (await self.db.execute(
            select(Kline.timestamp).where(Kline.period == "day").order_by(Kline.timestamp)
        )).scalars().all()
        return {
            "engine_version": self.ENGINE_VERSION,
            "daily_symbols": total_symbols, "turnover_symbols": turnover_symbols,
            "first_date": dates[0].date().isoformat() if dates else None,
            "last_date": dates[-1].date().isoformat() if dates else None,
            "fields": {
                "ohlcv": {"available": bool(total_symbols), "source": "local klines cache"},
                "turnover_rate": {"available": bool(turnover_symbols), "coverage_symbols": turnover_symbols,
                                  "reason": "历史换手率仅在K线turnover非空时可用"},
                "exact_limit_price": {"available": False, "reason": "缺少原始前收盘、历史ST与规则版本；涨停采用代码板块阈值近似"},
            },
        }

    async def run(self, request: dict) -> dict:
        start = date.fromisoformat(request["start_date"])
        end = date.fromisoformat(request["end_date"])
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        horizons = sorted(set(int(h) for h in request.get("horizons", [1, 3, 7, 30]) if 1 <= int(h) <= 120))
        if not horizons:
            raise ValueError("至少需要一个有效前瞻交易日")
        rule = request.get("rule") or {}
        conditions = rule.get("conditions") or []
        if not conditions:
            raise ValueError("至少需要一个条件")
        unsupported = [c.get("type") for c in conditions if c.get("type") not in self.SUPPORTED_TYPES]
        if unsupported:
            raise ValueError(f"不支持的条件: {', '.join(str(x) for x in unsupported)}")

        symbols = [str(s).upper() for s in (request.get("universe") or {}).get("symbols", []) if s]
        symbol_query = select(Kline.symbol).where(Kline.period == "day").distinct()
        cached_symbols = sorted(set(str(s).upper() for s in (await self.db.execute(symbol_query)).scalars().all()))
        universe = [s for s in cached_symbols if not symbols or s in symbols]
        universe_spec = request.get("universe") or {}
        if universe_spec.get("equity_only", True):
            universe = [s for s in universe if _is_equity(s)]
        excluded_boards = set(universe_spec.get("exclude_boards") or [])
        universe = [s for s in universe if _board(s) not in excluded_boards]
        max_symbols = max(1, min(int((request.get("universe") or {}).get("max_symbols", 500)), 2000))
        if len(universe) > max_symbols:
            rng = random.Random(20261009)
            universe = sorted(rng.sample(universe, max_symbols))
        if not universe:
            return self._empty(request, horizons, "本地日K缓存没有匹配股票")

        benchmark_symbol = str(request.get("benchmark") or "SH000300").upper()
        query_symbols = sorted(set([*universe, benchmark_symbol]))
        names = dict((await self.db.execute(
            select(StockName.symbol, StockName.name).where(StockName.symbol.in_(query_symbols))
        )).all())
        max_lookback = max([int(c.get("lookback", 0) or 0) for c in conditions] + [120])
        query_start = start - timedelta(days=max_lookback * 2 + 60)
        query_end = end + timedelta(days=max(horizons) * 2 + 30)
        raw_rows = (await self.db.execute(
            select(Kline).where(
                Kline.period == "day", Kline.symbol.in_(query_symbols),
                Kline.timestamp >= datetime.combine(query_start, datetime.min.time()),
                Kline.timestamp <= datetime.combine(query_end, datetime.max.time()),
            ).order_by(Kline.symbol, Kline.timestamp)
        )).scalars().all()
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in raw_rows:
            grouped[row.symbol.upper()].append({
                "date": row.timestamp.date(), "open": _num(row.open), "high": _num(row.high),
                "low": _num(row.low), "close": _num(row.close), "volume": _num(row.volume),
                "turnover": float(row.turnover) if row.turnover is not None else None,
            })

        benchmark_rows = grouped.get(benchmark_symbol, [])
        benchmark_by_date = {r["date"]: r for r in benchmark_rows}
        logic = rule.get("logic", "all")
        occurrence = request.get("occurrence_policy", "entry")
        cooldown = max(0, int(request.get("cooldown_sessions", max(horizons))))
        events, condition_errors = [], []
        excluded_counts = defaultdict(int)
        for symbol in universe:
            if symbol == benchmark_symbol:
                continue
            rows = grouped.get(symbol, [])
            if len(rows) < 2:
                continue
            derived = _derived(rows, symbol, names.get(symbol, symbol))
            last_event_index = -10_000
            was_match = False
            for index, row in enumerate(derived):
                if row["date"] > end:
                    break
                in_window = row["date"] >= start
                if row["date"] < query_start:
                    continue
                if in_window:
                    eligible, reason = self._eligible(universe_spec, symbol, names.get(symbol, symbol), derived, index)
                    if not eligible:
                        excluded_counts[reason] += 1
                        was_match = False
                        continue
                else:
                    eligible, reason = True, ""
                checks, diagnostics = [], []
                for condition in conditions:
                    passed, detail, error = self._evaluate(condition, derived, index)
                    checks.append(passed)
                    diagnostics.append(detail)
                    if error and error not in condition_errors:
                        condition_errors.append(error)
                matched = all(checks) if logic == "all" else any(checks)
                emit = matched
                if occurrence == "entry":
                    emit = matched and not was_match
                elif occurrence == "cooldown":
                    emit = matched and index - last_event_index > cooldown
                if emit and in_window:
                    event = self._event(symbol, names.get(symbol, symbol), derived, index, horizons,
                                        benchmark_by_date, diagnostics, request.get("return_basis", "event_close"))
                    events.append(event)
                    last_event_index = index
                was_match = matched

        stats = self._statistics(events, horizons)
        unique_dates = len({e["event_date"] for e in events})
        complete_symbols = sum(1 for symbol in universe if grouped.get(symbol) and grouped[symbol][0]["date"] <= start)
        return {
            "engine_version": self.ENGINE_VERSION,
            "rule": rule, "scope": {"start_date": start.isoformat(), "end_date": end.isoformat(),
                                      "horizons": horizons, "return_basis": request.get("return_basis", "event_close"),
                                      "occurrence_policy": occurrence, "cooldown_sessions": cooldown},
            "universe": {"requested_mode": "cached", "symbols_scanned": len(universe),
                         "symbols_with_rows": sum(bool(grouped.get(s)) for s in universe),
                         "symbols_covering_start": complete_symbols,
                         "filters": universe_spec, "excluded_event_bars": dict(excluded_counts),
                         "survivorship_caveat": "本地缓存是按需获取的当前股票样本；ST过滤使用当前名称，新股过滤使用缓存观察长度，均非历史时点精确口径"},
            "summary": {"events": len(events), "unique_symbols": len({e["symbol"] for e in events}),
                        "unique_dates": unique_dates, "condition_errors": condition_errors},
            "statistics": stats, "events": events[:1000],
            "data_quality": {
                "exact_limit_up": False,
                "limit_method": "前复权相邻收盘涨幅 + 当前代码板块阈值近似；包含301创业板修正，但无历史ST/上市规则",
                "turnover_available": any(r.get("turnover") is not None for rows in grouped.values() for r in rows),
                "amount_available": False,
                "censored_events": {str(h): sum(e["forward"].get(str(h)) is None for e in events) for h in horizons},
                "warnings": condition_errors,
            },
        }

    @staticmethod
    def _eligible(spec: dict, symbol: str, name: str, rows: list[dict], index: int) -> tuple[bool, str]:
        if spec.get("exclude_current_st", True) and "ST" in (name or "").upper():
            return False, "current_st_name"
        minimum_history = int(spec.get("min_observed_bars", 0) or 0)
        if index < minimum_history:
            return False, "insufficient_observed_history"
        close = rows[index].get("close")
        if close is None or close <= 0:
            return False, "invalid_close"
        if spec.get("min_price") is not None and close < float(spec["min_price"]):
            return False, "price_below_min"
        if spec.get("max_price") is not None and close > float(spec["max_price"]):
            return False, "price_above_max"
        return True, ""

    @staticmethod
    def _evaluate(condition: dict, rows: list[dict], index: int) -> tuple[bool, dict, str | None]:
        kind = condition.get("type")
        row = rows[index]
        if kind == "limit_up_streak":
            minimum, maximum = int(condition.get("min", 1)), int(condition.get("max", 99))
            value = int(row["limit_streak"])
            return minimum <= value <= maximum, {"type": kind, "value": value, "min": minimum, "max": maximum}, None
        if kind == "post_limit_pullback":
            days_min, days_max = int(condition.get("days_min", 2)), int(condition.get("days_max", 5))
            streak_min, streak_max = int(condition.get("streak_min", 1)), int(condition.get("streak_max", 3))
            strict_volume = bool(condition.get("shrinking_volume", True))
            matched = None
            for days in range(days_min, days_max + 1):
                streak_index = index - days
                if streak_index < 0:
                    continue
                streak = rows[streak_index]["limit_streak"]
                adjustment = rows[streak_index + 1:index + 1]
                if not (streak_min <= streak <= streak_max) or any(r["is_limit_up"] for r in adjustment):
                    continue
                volumes = [r["volume"] for r in adjustment]
                if any(v is None for v in volumes) or rows[streak_index].get("volume") is None:
                    volume_ok = False
                elif strict_volume:
                    volume_ok = all(volumes[i] < volumes[i - 1] for i in range(1, len(volumes)))
                else:
                    volume_ok = bool(volumes) and sum(volumes) / len(volumes) < rows[streak_index]["volume"]
                streak_close = rows[streak_index].get("close")
                if streak_close is None:
                    continue
                require_pullback = bool(condition.get("require_pullback", True))
                pullback_ok = rows[index]["close"] < streak_close if require_pullback else True
                max_drawdown = float(condition.get("max_drawdown_pct", 100)) / 100
                drawdown = rows[index]["close"] / streak_close - 1
                if volume_ok and pullback_ok and drawdown >= -max_drawdown:
                    matched = {"days": days, "prior_streak": streak, "drawdown_pct": _pct(drawdown), "volumes": volumes}
                    break
            return matched is not None, {"type": kind, "value": matched}, None
        if kind == "turnover_limit_up":
            if row.get("turnover") is None:
                return False, {"type": kind, "value": None}, "历史换手率字段不可用，换手板条件未执行"
            minimum, maximum = float(condition.get("min", 5)), float(condition.get("max", 100))
            value = row["turnover"]
            return row["is_limit_up"] and minimum <= value <= maximum, {"type": kind, "value": value}, None
        if kind == "change_pct":
            value = _pct(row.get("change"))
            minimum, maximum = float(condition.get("min", -100)), float(condition.get("max", 100))
            return value is not None and minimum <= value <= maximum, {"type": kind, "value": value}, None
        if kind == "volume_ratio":
            lookback = int(condition.get("lookback", 5))
            prior = _window(rows, index, lookback)
            baseline = _mean([r.get("volume") for r in prior], lookback)
            value = row["volume"] / baseline if row.get("volume") is not None and baseline else None
            minimum, maximum = float(condition.get("min", 0)), float(condition.get("max", 100))
            return value is not None and minimum <= value <= maximum, {"type": kind, "value": value, "lookback": lookback}, None
        if kind == "amplitude":
            value = _pct(row.get("amplitude"))
            minimum, maximum = float(condition.get("min", 0)), float(condition.get("max", 100))
            return value is not None and minimum <= value <= maximum, {"type": kind, "value": value}, None
        if kind == "close_vs_ma5":
            value = row["close"] / row["ma5"] - 1 if row.get("ma5") else None
            direction = condition.get("direction", "above")
            passed = value is not None and (value >= 0 if direction == "above" else value <= 0)
            return passed, {"type": kind, "value_pct": _pct(value), "direction": direction}, None
        if kind == "return_n":
            lookback = int(condition.get("lookback", 20))
            prior = rows[index - lookback] if index >= lookback else None
            value = row["close"] / prior["close"] - 1 if prior and row.get("close") and prior.get("close") else None
            value_pct = _pct(value)
            return _range(value_pct, condition), {"type": kind, "value": value_pct, "lookback": lookback}, None
        if kind == "direction_streak":
            direction = condition.get("direction", "up")
            streak = 0
            for cursor in range(index, 0, -1):
                change = rows[cursor].get("change")
                if change is None or (direction == "up" and change <= 0) or (direction == "down" and change >= 0):
                    break
                streak += 1
            return _range(streak, condition, 1, 999), {"type": kind, "value": streak, "direction": direction}, None
        if kind in ("gap_pct", "intraday_return_pct", "close_location", "upper_shadow_pct", "lower_shadow_pct"):
            prev = rows[index - 1].get("close") if index else None
            open_, high, low, close = row.get("open"), row.get("high"), row.get("low"), row.get("close")
            value = None
            if kind == "gap_pct" and prev and open_:
                value = (open_ / prev - 1) * 100
            elif kind == "intraday_return_pct" and open_ and close:
                value = (close / open_ - 1) * 100
            elif kind == "close_location" and None not in (high, low, close) and high > low:
                value = (close - low) / (high - low) * 100
            elif kind == "upper_shadow_pct" and prev and None not in (open_, high, close):
                value = (high - max(open_, close)) / prev * 100
            elif kind == "lower_shadow_pct" and prev and None not in (open_, low, close):
                value = (min(open_, close) - low) / prev * 100
            return _range(value, condition), {"type": kind, "value": value}, None
        if kind in ("breakout_distance", "range_position", "drawdown_from_high", "rebound_from_low"):
            lookback = int(condition.get("lookback", 20))
            prior = _window(rows, index, lookback)
            value = None
            if len(prior) == lookback and row.get("close"):
                highs = [r.get("high") for r in prior]
                lows = [r.get("low") for r in prior]
                closes = [r.get("close") for r in prior]
                if all(v is not None for v in [*highs, *lows, *closes]):
                    if kind == "breakout_distance":
                        reference = max(highs if condition.get("reference", "high") == "high" else closes)
                        value = (row["close"] / reference - 1) * 100 if reference else None
                    elif kind == "range_position":
                        high, low = max(highs), min(lows)
                        value = (row["close"] - low) / (high - low) * 100 if high > low else None
                    elif kind == "drawdown_from_high":
                        peak = max(closes); value = (1 - row["close"] / peak) * 100 if peak else None
                    else:
                        trough = min(closes); value = (row["close"] / trough - 1) * 100 if trough else None
            return _range(value, condition), {"type": kind, "value": value, "lookback": lookback}, None
        if kind == "ma_distance":
            lookback = int(condition.get("lookback", 20))
            window = _window(rows, index, lookback, include_current=True)
            average = _mean([r.get("close") for r in window], lookback)
            value = (row["close"] / average - 1) * 100 if row.get("close") and average else None
            return _range(value, condition), {"type": kind, "value": value, "lookback": lookback}, None
        if kind == "ma_cross":
            short, long = int(condition.get("short", 5)), int(condition.get("long", 20))
            current_long, previous_long = _window(rows, index, long, True), _window(rows, index - 1, long, True)
            current_short, previous_short = _window(rows, index, short, True), _window(rows, index - 1, short, True)
            c_s, c_l = _mean([r.get("close") for r in current_short], short), _mean([r.get("close") for r in current_long], long)
            p_s, p_l = _mean([r.get("close") for r in previous_short], short), _mean([r.get("close") for r in previous_long], long)
            direction = condition.get("direction", "golden")
            passed = None not in (c_s, c_l, p_s, p_l) and ((p_s <= p_l and c_s > c_l) if direction == "golden" else (p_s >= p_l and c_s < c_l))
            return passed, {"type": kind, "short": c_s, "long": c_l, "direction": direction}, None
        if kind in ("realized_volatility", "atr_pct"):
            lookback = int(condition.get("lookback", 20))
            window = _window(rows, index, lookback, True)
            value = None
            if len(window) == lookback and index >= lookback:
                if kind == "realized_volatility":
                    returns = [math.log(rows[i]["close"] / rows[i - 1]["close"]) for i in range(index - lookback + 1, index + 1) if rows[i].get("close") and rows[i - 1].get("close")]
                    value = statistics.stdev(returns) * math.sqrt(252) * 100 if len(returns) == lookback and len(returns) >= 2 else None
                else:
                    ranges = []
                    for i in range(index - lookback + 1, index + 1):
                        high, low, prev = rows[i].get("high"), rows[i].get("low"), rows[i - 1].get("close")
                        if None in (high, low, prev): ranges = []; break
                        ranges.append(max(high - low, abs(high - prev), abs(low - prev)))
                    value = statistics.fmean(ranges) / row["close"] * 100 if len(ranges) == lookback and row.get("close") else None
            return _range(value, condition), {"type": kind, "value": value, "lookback": lookback}, None
        if kind == "volume_trend":
            recent_n, baseline_n = int(condition.get("recent", 3)), int(condition.get("baseline", 20))
            recent = _window(rows, index, recent_n, True)
            baseline_end = index - recent_n + 1
            baseline = rows[baseline_end - baseline_n:baseline_end] if baseline_end >= baseline_n else []
            recent_avg = _mean([r.get("volume") for r in recent], recent_n)
            baseline_avg = _mean([r.get("volume") for r in baseline], baseline_n)
            value = recent_avg / baseline_avg if recent_avg is not None and baseline_avg else None
            return _range(value, condition), {"type": kind, "value": value, "recent": recent_n, "baseline": baseline_n}, None
        if kind == "volume_contraction_streak":
            ratio = float(condition.get("ratio_max", 1.0)); streak = 0
            for cursor in range(index, 0, -1):
                current, previous = rows[cursor].get("volume"), rows[cursor - 1].get("volume")
                if current is None or not previous or current >= previous * ratio: break
                streak += 1
            return _range(streak, condition, 1, 999), {"type": kind, "value": streak, "ratio_max": ratio}, None
        if kind == "first_limit_in_window":
            lookback = int(condition.get("lookback", 20)); prior = _window(rows, index, lookback)
            passed = row["is_limit_up"] and len(prior) == lookback and not any(r["is_limit_up"] for r in prior)
            return passed, {"type": kind, "value": passed, "lookback": lookback}, None
        if kind == "days_since_limit":
            days = None
            for cursor in range(index - 1, -1, -1):
                if rows[cursor]["is_limit_up"]: days = index - cursor; break
            return _range(days, condition, 0, 999), {"type": kind, "value": days}, None
        if kind == "limit_break":
            prev = rows[index - 1].get("close") if index else None
            threshold_price = prev * (1 + row["limit_threshold"]) if prev else None
            gap = float(condition.get("close_gap_bp", 50)) / 10000
            passed = bool(threshold_price and row.get("high") and row.get("close") and row["high"] >= threshold_price and row["close"] < threshold_price * (1 - gap))
            return passed, {"type": kind, "value": passed, "threshold_price": threshold_price}, None
        return False, {"type": kind, "value": None}, f"不支持的条件: {kind}"

    @staticmethod
    def _event(symbol: str, name: str, rows: list[dict], index: int, horizons: list[int],
               benchmark_by_date: dict, diagnostics: list[dict], basis: str) -> dict:
        event_row = rows[index]
        next_open = basis == "next_open"
        if next_open and index + 1 < len(rows):
            entry_index = index + 1
            entry_price = rows[entry_index]["open"]
            entry_date = rows[entry_index]["date"]
        elif next_open:
            entry_index = index + 1
            entry_price = None
            entry_date = None
        else:
            entry_index = index
            entry_price = event_row["close"]
            entry_date = event_row["date"]
        forward, relative = {}, {}
        for horizon in horizons:
            exit_index = index + horizon
            if entry_price and exit_index < len(rows) and exit_index >= entry_index and rows[exit_index].get("close"):
                exit_row = rows[exit_index]
                value = exit_row["close"] / entry_price - 1
                forward[str(horizon)] = _pct(value)
                bench_entry = benchmark_by_date.get(entry_date)
                bench_exit = benchmark_by_date.get(exit_row["date"])
                bench_start = ((bench_entry.get("open") if bench_entry else None) if next_open
                               else (bench_entry.get("close") if bench_entry else None))
                bench_ret = bench_exit["close"] / bench_start - 1 if bench_exit and bench_exit.get("close") and bench_start else None
                relative[str(horizon)] = _pct(value - bench_ret) if bench_ret is not None else None
            else:
                forward[str(horizon)] = None
                relative[str(horizon)] = None
        return {
            "symbol": symbol, "name": name, "event_date": event_row["date"].isoformat(),
            "entry_date": entry_date.isoformat() if entry_date else None, "entry_basis": basis,
            "event_close": round(event_row["close"], 4), "entry_price": round(entry_price, 4) if entry_price else None,
            "limit_streak": event_row["limit_streak"], "change_pct": _pct(event_row.get("change")),
            "volume": event_row["volume"], "turnover": event_row.get("turnover"),
            "diagnostics": diagnostics, "forward": forward, "relative": relative,
        }

    @staticmethod
    def _statistics(events: list[dict], horizons: list[int]) -> list[dict]:
        out = []
        for horizon in horizons:
            key = str(horizon)
            pairs = [(e["event_date"], e["forward"][key] / 100) for e in events if e["forward"].get(key) is not None]
            rel_pairs = [(e["event_date"], e["relative"][key] / 100) for e in events if e["relative"].get(key) is not None]
            values = [v for _, v in pairs]
            relative = [v for _, v in rel_pairs]
            t_value = _t_stat(values)
            t_rel = _t_stat(relative)
            low, high = _bootstrap_ci(values)
            cluster_low, cluster_high = _cluster_bootstrap_ci(pairs)
            # 事件日等权：先对同日事件取均值，再对日期取均值
            by_day: dict[str, list[float]] = defaultdict(list)
            for day, value in pairs:
                by_day[day].append(value)
            day_means = [statistics.fmean(day_by_day) for day_by_day in by_day.values()]
            # 按年份分层：年度事件数 >= 年最小样本的年份参与稳定性统计
            by_year: dict[str, list[float]] = defaultdict(list)
            for day, value in pairs:
                by_year[day[:4]].append(value)
            min_year_samples = 10
            year_rows = [
                {"year": year, "samples": len(year_values), "mean_pct": _pct(statistics.fmean(year_values)),
                 "win_rate_pct": round(sum(v > 0 for v in year_values) / len(year_values) * 100, 1)}
                for year, year_values in sorted(by_year.items()) if len(year_values) >= min_year_samples
            ]
            year_means = [row["mean_pct"] for row in year_rows if row["mean_pct"] is not None]
            out.append({
                "horizon": horizon, "samples": len(values), "coverage_pct": round(len(values) / len(events) * 100, 1) if events else 0,
                "mean_pct": _pct(statistics.fmean(values)) if values else None,
                "median_pct": _pct(statistics.median(values)) if values else None,
                "win_rate_pct": round(sum(v > 0 for v in values) / len(values) * 100, 1) if values else None,
                "std_pct": _pct(statistics.pstdev(values)) if len(values) > 1 else None,
                "p25_pct": _pct(_quantile(values, .25)) if values else None,
                "p75_pct": _pct(_quantile(values, .75)) if values else None,
                "min_pct": _pct(min(values)) if values else None, "max_pct": _pct(max(values)) if values else None,
                "ci95_low_pct": _pct(low), "ci95_high_pct": _pct(high),
                "cluster_ci95_low_pct": _pct(cluster_low), "cluster_ci95_high_pct": _pct(cluster_high),
                "t_stat": round(t_value, 3) if t_value is not None else None,
                "event_weighted": {
                    "label": "事件等权", "n": len(values),
                    "mean_pct": _pct(statistics.fmean(values)) if values else None,
                    "t_stat": round(t_value, 3) if t_value is not None else None,
                },
                "date_weighted": {
                    "label": "事件日等权", "n": len(day_means), "days": len(by_day),
                    "mean_pct": _pct(statistics.fmean(day_means)) if day_means else None,
                    "median_pct": _pct(statistics.median(day_means)) if day_means else None,
                    "t_stat": round(_t_stat(day_means), 3) if _t_stat(day_means) is not None else None,
                },
                "by_year": year_rows,
                "stability": {
                    "years_covered": len(by_year), "years_used": len(year_rows), "min_year_samples": min_year_samples,
                    "positive_years_pct": round(sum(m > 0 for m in year_means) / len(year_means) * 100, 1) if year_means else None,
                    "year_mean_min_pct": min(year_means) if year_means else None,
                    "year_mean_max_pct": max(year_means) if year_means else None,
                },
                "benchmark_excess_mean_pct": _pct(statistics.fmean(relative)) if relative else None,
                "benchmark_t_stat": round(t_rel, 3) if t_rel is not None else None,
                "benchmark_samples": len(relative),
            })
        return out

    def _empty(self, request: dict, horizons: list[int], reason: str) -> dict:
        return {"engine_version": self.ENGINE_VERSION, "rule": request.get("rule") or {}, "scope": request,
                "universe": {"symbols_scanned": 0}, "summary": {"events": 0, "unique_symbols": 0, "unique_dates": 0, "condition_errors": [reason]},
                "statistics": self._statistics([], horizons), "events": [], "data_quality": {"warnings": [reason]}}
