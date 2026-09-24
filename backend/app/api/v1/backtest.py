"""策略回测接口：策略存储在数据库，支持编辑参数 / 新增 / 复制 / 自己写 run(bars, params) 策略代码。"""
import builtins
import asyncio
import json
import math
import re
import time
from types import SimpleNamespace
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.market.kline_service import KlineService
from app.models.strategy import StrategyConfig
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/backtest", tags=["策略回测"])

LEGACY_TEMPLATE = '''# -*- coding: utf-8 -*-
# 策略代码：实现 run(bars, params) 并返回信号列表
#
# bars   : 升序K线列表，每条 = {"dt":"YYYY-MM-DD","open":..,"high":..,"low":..,"close":..,"volume":..}
# params : 界面表单填写的参数（已自动合并 schema 默认值）
# 可用辅助函数：sma(values, n)  /  ema(values, n)
#
# 返回 signals: [{"dt":"2026-01-05","action":"buy"|"sell","fraction":1.0}, ...]
#   buy    在 dt 当日开盘价建仓（fraction = 可用资金占比，默认 1.0）
#   sell   在 dt 当日开盘价减仓（fraction = 持仓占比，默认 1.0）
# 注意：dt 必须是 bars 中的交易日；不要用未来数据；已持仓时 buy 会被忽略，空仓时 sell 会被忽略。

def run(bars, params):
    fast_n = int(params.get("fast", 5))
    slow_n = int(params.get("slow", 20))
    closes = [b["close"] for b in bars]
    fast = sma(closes, fast_n)
    slow = sma(closes, slow_n)
    signals = []
    prev_fast = prev_slow = None
    for i in range(len(bars)):
        f, s = fast[i], slow[i]
        if f is None or s is None:
            prev_fast = prev_slow = None
            continue
        if prev_fast is not None:
            if prev_fast <= prev_slow and f > s:
                signals.append({"dt": bars[i]["dt"], "action": "buy", "fraction": 1.0})
            elif prev_fast >= prev_slow and f < s:
                signals.append({"dt": bars[i]["dt"], "action": "sell", "fraction": 1.0})
        prev_fast, prev_slow = f, s
    return signals
'''

CODE_TEMPLATE = LEGACY_TEMPLATE.replace(
    "# 策略代码：实现 run(bars, params) 并返回信号列表\n",
    "# 策略代码：实现 run(bars, params) 并返回信号列表\n"
    "# 支持两种模式（同一份代码两种模式都可跑）：\n"
    "#   单只股票   bars = 升序K线列表，每条 {\"dt\":\"YYYY-MM-DD\",\"open\":..,\"high\":..,\"low\":..,\"close\":..,\"volume\":..}\n"
    "#   自选组合   bars = {\"SH600519\":[K线...], \"SZ000001\":[K线...]} 多只自己选中的股票\n"
    "#             组合模式下信号必须带 symbol，fraction = 可用资金占比（如 0.3 表示用三成现金建仓）\n",
).replace(
    "# 返回 signals: [{\"dt\":\"2026-01-05\",\"action\":\"buy\"|\"sell\",\"fraction\":1.0}, ...]\n",
    "# 返回 signals: [{\"dt\":\"2026-01-05\",\"symbol\":\"SH600519\"(组合必填),\"action\":\"buy\"|\"sell\",\"fraction\":1.0}, ...]\n",
).replace(
    """def run(bars, params):
    fast_n = int(params.get("fast", 5))
    slow_n = int(params.get("slow", 20))
    closes = [b["close"] for b in bars]
    fast = sma(closes, fast_n)
    slow = sma(closes, slow_n)
    signals = []
    prev_fast = prev_slow = None
    for i in range(len(bars)):
        f, s = fast[i], slow[i]
        if f is None or s is None:
            prev_fast = prev_slow = None
            continue
        if prev_fast is not None:
            if prev_fast <= prev_slow and f > s:
                signals.append({"dt": bars[i]["dt"], "action": "buy", "fraction": 1.0})
            elif prev_fast >= prev_slow and f < s:
                signals.append({"dt": bars[i]["dt"], "action": "sell", "fraction": 1.0})
        prev_fast, prev_slow = f, s
    return signals""",
    """def run(bars, params):
    fast_n = int(params.get("fast", 5))
    slow_n = int(params.get("slow", 20))
    weight = float(params.get("weight", 0.5))
    symbols = list(bars.keys()) if isinstance(bars, dict) else [None]
    signals = []
    for sym in symbols:
        kl = bars[sym] if isinstance(bars, dict) else bars
        closes = [b["close"] for b in kl]
        fast = sma(closes, fast_n)
        slow = sma(closes, slow_n)
        prev_fast = prev_slow = None
        for i in range(len(kl)):
            f, s = fast[i], slow[i]
            if f is None or s is None:
                prev_fast = prev_slow = None
                continue
            if prev_fast is not None:
                if prev_fast <= prev_slow and f > s:
                    sig = {"dt": kl[i]["dt"], "action": "buy",
                           "fraction": weight if sym is not None else 1.0}
                    if sym is not None:
                        sig["symbol"] = sym
                    signals.append(sig)
                elif prev_fast >= prev_slow and f < s:
                    sig = {"dt": kl[i]["dt"], "action": "sell", "fraction": 1.0}
                    if sym is not None:
                        sig["symbol"] = sym
                    signals.append(sig)
            prev_fast, prev_slow = f, s
    return signals""",
)

DEFAULT_SCHEMA = [
    {"key": "fast", "label": "快线周期", "type": "int", "default": 5, "min": 2, "max": 120, "step": 1},
    {"key": "slow", "label": "慢线周期", "type": "int", "default": 20, "min": 5, "max": 250, "step": 1},
    {"key": "weight", "label": "组合建仓比例", "type": "number", "default": 0.5, "min": 0.05, "max": 1, "step": 0.05},
]


def _sma(values: list, window: int) -> list:
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out


def _ema(values: list, window: int) -> list:
    out = []
    k = 2.0 / (window + 1)
    e = None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def _check_future_function(src: str) -> None:
    """检测策略代码中是否使用了未来函数（访问 bars[i+k] 或 closes[i+k]，k>0）。"""
    patterns = [
        r'\w+\[i\s*\+\s*[1-9]\w*\]',   # bars[i+1], closes[i+2] etc.
        r'\w+\[\w+\s*\+\s*[1-9]\w*\]',   # idx + 1 style
        r'future|lookahead|next_bar',       # explicit future keywords
    ]
    for pat in patterns:
        matches = re.findall(pat, src, re.IGNORECASE)
        if matches:
            bad = [m for m in matches if not m.startswith(('prev_', 'pre_'))]
            if bad:
                raise ValueError(
                    f"检测到可能使用了未来函数: {bad[0]}。"
                    "回测策略不允许使用未来数据（不能访问 i 之后的 bar），请检查代码。")


def _compile_strategy(code: str) -> object:
    """编译策略代码并返回 run 函数；出错抛 ValueError（带定位信息）。"""
    import inspect
    ns = {"__name__": "strategy_code", "__builtins__": vars(builtins)}
    ns["sma"] = _sma
    ns["ema"] = _ema
    src = code or CODE_TEMPLATE
    _check_future_function(src)
    try:
        exec(compile(src, "<strategy>", "exec"), ns)
    except Exception as e:
        raise ValueError(f"策略代码编译失败: {e}")
    run_fn = ns.get("run")
    if not callable(run_fn):
        if any(callable(ns.get(name)) for name in ("initialize", "handle_data", "before_trading_start")):
            exec("def run(bars, params):\n    return []\n", ns)
            run_fn = ns["run"]
        else:
            raise ValueError("策略代码必须定义 run(bars, params)，或提供 initialize/handle_data 生命周期函数")
    try:
        sig = inspect.signature(run_fn)
        pos = [p for p in sig.parameters.values()
               if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        if not pos and not any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
            raise ValueError("run() 需要参数 (bars, params)")
        if len(pos) < 2 and not any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()):
            raise ValueError("run(bars, params) 需要两个参数")
    except ValueError as e:
        raise ValueError(str(e))
    return run_fn


def _run_strategy(run_fn, bars, params):
    """兼容传统 run(bars, params) 与生命周期脚本。"""
    ns = getattr(run_fn, "__globals__", {})
    if not any(callable(ns.get(name)) for name in ("initialize", "handle_data", "before_trading_start")):
        return run_fn(bars, params) or []
    rows = bars if isinstance(bars, list) else next(iter(bars.values()), [])
    context = SimpleNamespace(current_dt=None, current_data={}, params=dict(params), orders=[])
    def _symbol(symbol): return str(symbol or (next(iter(bars), "") if isinstance(bars, dict) else ""))
    def order(symbol, amount):
        amount = int(amount)
        context.orders.append({"dt": str(context.current_dt), "symbol": _symbol(symbol), "action": "buy" if amount > 0 else "sell", "quantity": abs(amount), "fraction": 1.0})
    def order_value(symbol, value):
        if isinstance(context.current_data, dict) and "open" in context.current_data:
            data = context.current_data
        else:
            data = context.current_data.get(_symbol(symbol), {}) if isinstance(context.current_data, dict) else context.current_data
        price = float(data.get("open") or data.get("close") or 0)
        if price > 0: order(symbol, int(float(value) / price))
    ns.update({"order": order, "order_target": order, "order_value": order_value, "record": lambda **kwargs: None})
    if callable(ns.get("initialize")): ns["initialize"](context)
    if isinstance(bars, dict):
        dates = sorted({str(row["dt"]) for series in bars.values() for row in series})
        lookup = {sym: {str(row["dt"]): row for row in series} for sym, series in bars.items()}
    else:
        dates = [str(row["dt"]) for row in rows]
        lookup = {"": {str(row["dt"]): row for row in rows}}
    for dt in dates:
        context.current_dt = dt
        context.current_data = ({sym: lookup[sym][dt] for sym in lookup if dt in lookup[sym]} if isinstance(bars, dict) else lookup[""][dt])
        if callable(ns.get("before_trading_start")): ns["before_trading_start"](context)
        if callable(ns.get("handle_data")): ns["handle_data"](context, context.current_data)
    return context.orders


def _to_dict(r: StrategyConfig) -> dict:
    return {
        "id": r.id, "key": r.key, "name": r.name, "description": r.description or "",
        "params_schema": r.params_schema or [], "code": r.code or "",
        "is_builtin": r.is_builtin, "is_active": r.is_active,
        "created_at": str(r.created_at), "updated_at": str(r.updated_at),
    }


def _make_key(name: str, existing: list[str]) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", (name or "").strip()).strip("_")
    base = slug or f"stg_{int(time.time())}"
    key = base
    n = 2
    while key in existing:
        key = f"{base}_{n}"
        n += 1
    return key


async def ensure_default_strategies(db: AsyncSession) -> None:
    """保证内置策略存在（幂等）；旧版模板自动升级为单只/组合双模式。"""
    try:
        row = (await db.execute(
            select(StrategyConfig).where(StrategyConfig.key == "ma_cross"))).scalars().first()
        if row is None:
            db.add(StrategyConfig(
                key="ma_cross", name="均线金叉死叉",
                description="快线上穿慢线（金叉）的当日开盘建仓，下穿（死叉）当日开盘清仓；组合模式按 建仓比例 分配资金，信号带 symbol。",
                params_schema=DEFAULT_SCHEMA, code=CODE_TEMPLATE, is_builtin=True, is_active=True,
            ))
            await db.commit()
        elif (row.code or "").strip() == LEGACY_TEMPLATE.strip():
            row.code = CODE_TEMPLATE
            row.params_schema = DEFAULT_SCHEMA
            await db.commit()

        # RSI 超卖反弹策略
        rsi_key = "rsi_oversold"
        rsi_row = (await db.execute(select(StrategyConfig).where(StrategyConfig.key == rsi_key))).scalars().first()
        if rsi_row is None:
            db.add(StrategyConfig(
                key=rsi_key, name="RSI超卖反弹",
                description="RSI低于阈值时超卖买入，高于阈值时卖出；适合震荡市抄底。",
                params_schema=[
                    {"key": "period", "label": "RSI周期", "type": "int", "default": 14, "min": 5, "max": 50, "step": 1},
                    {"key": "oversold", "label": "超卖线", "type": "int", "default": 30, "min": 10, "max": 45, "step": 1},
                    {"key": "overbought", "label": "超买线", "type": "int", "default": 70, "min": 55, "max": 90, "step": 1},
                ],
                code='''# RSI超卖反弹策略
def run(bars, params):
    period = int(params.get("period", 14))
    oversold = int(params.get("oversold", 30))
    overbought = int(params.get("overbought", 70))
    closes = [b["close"] for b in bars]
    # 计算RSI
    deltas = [closes[i] - closes[i-1] if i > 0 else 0 for i in range(len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = [None] * len(closes)
    avg_loss = [None] * len(closes)
    rsi = [None] * len(closes)
    for i in range(period, len(closes)):
        if avg_gain[i-1] is None:
            avg_gain[i] = sum(gains[i-period:i]) / period
            avg_loss[i] = sum(losses[i-period:i]) / period
        else:
            avg_gain[i] = (avg_gain[i-1] * (period-1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i-1] * (period-1) + losses[i]) / period
        if avg_loss[i] == 0:
            rsi[i] = 100
        else:
            rs = avg_gain[i] / avg_loss[i]
            rsi[i] = 100 - 100 / (1 + rs)
    signals = []
    holding = False
    for i in range(period, len(closes)):
        if rsi[i] is None: continue
        if not holding and rsi[i] < oversold:
            signals.append({"dt": bars[i]["dt"], "action": "buy", "fraction": 1.0})
            holding = True
        elif holding and rsi[i] > overbought:
            signals.append({"dt": bars[i]["dt"], "action": "sell", "fraction": 1.0})
            holding = False
    return signals
''', is_builtin=True, is_active=True,
            ))
            await db.commit()

        # MACD策略
        macd_key = "macd_cross"
        macd_row = (await db.execute(select(StrategyConfig).where(StrategyConfig.key == macd_key))).scalars().first()
        if macd_row is None:
            db.add(StrategyConfig(
                key=macd_key, name="MACD金叉死叉",
                description="DIF上穿DEA买入，下穿卖出；MACD柱由负转正确认趋势。",
                params_schema=[
                    {"key": "fast", "label": "快线EMA", "type": "int", "default": 12, "min": 5, "max": 50, "step": 1},
                    {"key": "slow", "label": "慢线EMA", "type": "int", "default": 26, "min": 10, "max": 100, "step": 1},
                    {"key": "signal", "label": "信号线", "type": "int", "default": 9, "min": 3, "max": 30, "step": 1},
                ],
                code='''# MACD金叉死叉策略
def run(bars, params):
    fast_n = int(params.get("fast", 12))
    slow_n = int(params.get("slow", 26))
    sig_n = int(params.get("signal", 9))
    closes = [b["close"] for b in bars]
    fast_ema = ema(closes, fast_n)
    slow_ema = ema(closes, slow_n)
    dif = [f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)]
    # DEA = EMA(DIF, signal)
    dea = [None] * len(closes)
    k = 2.0 / (sig_n + 1)
    e = None
    for i, d in enumerate(dif):
        if d is None:
            dea[i] = None
            continue
        e = d if e is None else d * k + e * (1 - k)
        dea[i] = e
    signals = []
    holding = False
    for i in range(1, len(closes)):
        if dif[i] is None or dea[i] is None or dif[i-1] is None or dea[i-1] is None:
            continue
        if not holding and dif[i-1] <= dea[i-1] and dif[i] > dea[i]:
            signals.append({"dt": bars[i]["dt"], "action": "buy", "fraction": 1.0})
            holding = True
        elif holding and dif[i-1] >= dea[i-1] and dif[i] < dea[i]:
            signals.append({"dt": bars[i]["dt"], "action": "sell", "fraction": 1.0})
            holding = False
    return signals
''', is_builtin=True, is_active=True,
            ))
            await db.commit()

        # 布林带突破策略
        boll_key = "bollinger_break"
        boll_row = (await db.execute(select(StrategyConfig).where(StrategyConfig.key == boll_key))).scalars().first()
        if boll_row is None:
            db.add(StrategyConfig(
                key=boll_key, name="布林带突破",
                description="价格突破布林带上轨买入，跌破下轨卖出；中轨作为止损线。",
                params_schema=[
                    {"key": "period", "label": "均线周期", "type": "int", "default": 20, "min": 10, "max": 60, "step": 1},
                    {"key": "std_dev", "label": "标准差倍数", "type": "number", "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.1},
                ],
                code='''# 布林带突破策略
def run(bars, params):
    period = int(params.get("period", 20))
    std_mult = float(params.get("std_dev", 2.0))
    closes = [b["close"] for b in bars]
    mid = sma(closes, period)
    signals = []
    holding = False
    for i in range(period, len(closes)):
        if mid[i] is None: continue
        window = closes[i-period+1:i+1]
        std = (sum((x - mid[i])**2 for x in window) / period) ** 0.5
        upper = mid[i] + std_mult * std
        lower = mid[i] - std_mult * std
        if not holding and closes[i] > upper:
            signals.append({"dt": bars[i]["dt"], "action": "buy", "fraction": 1.0})
            holding = True
        elif holding and closes[i] < lower:
            signals.append({"dt": bars[i]["dt"], "action": "sell", "fraction": 1.0})
            holding = False
    return signals
''', is_builtin=True, is_active=True,
            ))
            await db.commit()

    except Exception as e:
        logger.warning(f"seed default strategy failed: {e}")
        await db.rollback()


async def _ensure_seeded(db: AsyncSession) -> None:
    try:
        cnt = (await db.execute(select(StrategyConfig.id).limit(1))).scalars().first()
        if cnt is None:
            await ensure_default_strategies(db)
    except Exception:
        await ensure_default_strategies(db)


class StrategyCreate(BaseModel):
    name: str = Field(..., description="策略名称")
    key: str = Field("", description="策略标识，留空自动生成")
    description: str = ""
    params_schema: list = Field(default_factory=list, description='[{key,label,type,default,min,max,step,options}]')
    code: str = Field("", description="run(bars, params) 策略代码，留空使用模板")


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    params_schema: Optional[list] = None
    code: Optional[str] = None
    is_active: Optional[bool] = None


class BacktestRequest(BaseModel):
    symbol: str = Field("", description="股票代码，如 SH600519（单只模式）")
    symbols: list = Field(default_factory=list, description="自选组合模式：多只股票代码；非空时忽略 symbol")
    strategy: str = Field("", description="策略 key")
    strategy_id: Optional[int] = Field(None, description="策略 id（优先于 key）")
    params: dict = Field(default_factory=dict, description="策略参数（缺失项用默认值）")
    start_date: str = Field("2024-01-01", description="起始日期 YYYY-MM-DD")
    end_date: str = Field("", description="结束日期 YYYY-MM-DD，空=今天")
    initial_capital: float = Field(100000.0, description="初始资金")
    commission: float = Field(0.0003, ge=0, le=0.02, description="手续费率")
    slippage: float = Field(0.001, ge=0, le=0.05, description="滑点比例")
    enforce_price_limit: bool = Field(True, description="执行涨跌停限制")
    benchmark_symbol: str = Field("SH000300", description="业绩比较基准，默认沪深300")


class StrategyTestRequest(BaseModel):
    code: str = Field("", description="策略代码")
    params: dict = Field(default_factory=dict)


class SensitivityRequest(BacktestRequest):
    param_key: str = Field("", description="要扫描的参数 key")
    values: list = Field(default_factory=list, description="参数取值列表；为空则按 schema min/max/step 自动生成")


class WalkForwardRequest(BacktestRequest):
    n_splits: int = Field(4, ge=2, le=12, description="时间留出折数")
    optimize_param: str = Field("", description="可选：在训练段扫描的参数 key（留空则各折使用同一组参数）")
    optimize_values: list = Field(default_factory=list, description="优化参数候选值；为空按 schema 生成")


# ---------------------------------------------------------------- 策略执行引擎

def _default_params(cfg: StrategyConfig) -> dict:
    d = {}
    for s in (cfg.params_schema or []):
        if isinstance(s, dict) and s.get("key"):
            d[s["key"]] = s.get("default")
    return d


def _finish_metrics(equity_curve: list, trades: list, capital: float) -> dict:
    """由权益曲线 + 交易记录汇总指标，单只与组合回测共用。"""
    import math
    capital = float(capital)
    final_equity = equity_curve[-1]["equity"] if equity_curve else capital
    total_return = final_equity / capital - 1 if capital else 0

    max_dd = 0.0
    peak = -float("inf")
    dd_start_idx = 0
    dd_end_idx = 0
    cur_start = 0
    for i, c in enumerate(equity_curve):
        e = c["equity"]
        if e > peak:
            peak = e
            cur_start = i
        if peak > 0:
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
                dd_start_idx = cur_start
                dd_end_idx = i

    # 修复周期必须回到最大回撤开始时的峰值，而不是回到全区间最后形成的峰值。
    drawdown_peak = equity_curve[dd_start_idx]["equity"] if equity_curve else capital
    recovery_idx = len(equity_curve) - 1
    for i in range(dd_end_idx, len(equity_curve)):
        if equity_curve[i]["equity"] >= drawdown_peak:
            recovery_idx = i
            break
    recovery_days = recovery_idx - dd_end_idx

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) <= 0]
    n_bars = len(equity_curve)
    years = n_bars / 244
    ann = (final_equity / capital) ** (1 / years) - 1 if capital > 0 and years > 0 else 0

    # Sharpe ratio (日收益率)
    if n_bars > 1:
        daily_returns = []
        for i in range(1, n_bars):
            prev = equity_curve[i-1]["equity"]
            if prev > 0:
                daily_returns.append(equity_curve[i]["equity"] / prev - 1)
        if daily_returns:
            avg_r = sum(daily_returns) / len(daily_returns)
            std_r = (sum((r - avg_r)**2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe = (avg_r / std_r * math.sqrt(244)) if std_r > 0 else 0
        else:
            sharpe = 0
    else:
        sharpe = 0

    # Sortino ratio (只用下行波动率)
    if n_bars > 1:
        down_returns = [r for r in daily_returns if r < 0]
        if down_returns:
            down_std = (sum(r**2 for r in down_returns) / len(down_returns)) ** 0.5
            sortino = (avg_r / down_std * math.sqrt(244)) if down_std > 0 else 0
        else:
            sortino = 0
    else:
        sortino = 0

    # Calmar ratio
    calmar = ann / max_dd if max_dd > 0 else 0

    # Profit factor = 总盈利 / 总亏损；平均盈利/亏损另行返回。
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # 平均持仓天数
    holding_days = []
    for t in trades:
        try:
            d1 = date.fromisoformat(t["entry_date"])
            d2 = date.fromisoformat(t["exit_date"])
            holding_days.append((d2 - d1).days)
        except:
            pass
    avg_holding = sum(holding_days) / len(holding_days) if holding_days else 0

    # 最大连续盈利/亏损
    max_consec_win = max_consec_loss = cur_win = cur_loss = 0
    for t in trades:
        if t.get("pnl", 0) > 0:
            cur_win += 1
            cur_loss = 0
            max_consec_win = max(max_consec_win, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            max_consec_loss = max(max_consec_loss, cur_loss)

    # 月度收益
    monthly = {}
    for c in equity_curve:
        dt = c["dt"][:7]
        if dt not in monthly:
            monthly[dt] = {"start": c["equity"], "end": c["equity"]}
        monthly[dt]["end"] = c["equity"]
    monthly_returns = []
    prev_end = capital
    for dt in sorted(monthly.keys()):
        m = monthly[dt]
        ret = (m["end"] - prev_end) / prev_end if prev_end > 0 else 0
        monthly_returns.append({"month": dt, "return": round(ret, 4), "equity": round(m["end"], 2)})
        prev_end = m["end"]

    return {
        "initial_capital": round(capital, 2),
        "final_equity": round(final_equity, 2),
        "total_return": round(total_return, 4),
        "annualized_return": round(ann, 4),
        "max_drawdown": round(max_dd, 4),
        "dd_start": equity_curve[dd_start_idx]["dt"] if dd_start_idx < len(equity_curve) else "",
        "dd_end": equity_curve[dd_end_idx]["dt"] if dd_end_idx < len(equity_curve) else "",
        "recovery_days": recovery_days,
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0,
        "trade_count": len(trades),
        "bars": n_bars,
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "calmar": round(calmar, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_holding_days": round(avg_holding, 1),
        "max_consec_win": max_consec_win,
        "max_consec_loss": max_consec_loss,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "monthly_returns": monthly_returns,
    }


def _simulate(bars: list, signals: list, capital: float, commission: float = 0.0003, slippage: float = 0.001, enforce_price_limit: bool = True) -> dict:
    """单只股票模拟：T 日收盘后生成信号，统一在下一交易日开盘成交。"""
    opens = {str(b["dt"]): float(b["open"]) for b in bars}
    closes = {str(b["dt"]): float(b["close"]) for b in bars}
    sigs: dict = {}
    next_date = {str(bars[i]["dt"]): str(bars[i + 1]["dt"]) for i in range(len(bars) - 1)}
    for s in signals or []:
        dt = str(s.get("dt"))
        execution_dt = next_date.get(dt)
        if execution_dt in opens:
            sigs.setdefault(execution_dt, []).append(s)

    cash = float(capital)
    shares = 0.0
    entry_price = 0.0
    entry_date = ""
    trades = []
    equity_curve = []

    for bar_index, b in enumerate(bars):
        dt = str(b["dt"])
        close_px = closes[dt]
        for s in sigs.get(dt, []):
            action = str(s.get("action", "")).lower()
            frac = min(max(float(s.get("fraction", 1.0)), 0.0), 1.0)
            fill = opens[dt] * (1 + slippage if action == "buy" else 1 - slippage)
            if enforce_price_limit and bar_index > 0:
                prev_close = float(bars[bar_index - 1].get("close") or fill)
                if action == "buy" and fill >= prev_close * 1.095:
                    continue
                if action == "sell" and fill <= prev_close * 0.905:
                    continue
            if action == "buy" and shares <= 0 and cash > 0:
                spend = cash * frac
                if spend > fill:
                    shares = int(spend / fill / 100) * 100
                    if shares >= 100:
                        fee = shares * fill * commission
                        cash -= shares * fill + fee
                        entry_price = fill
                        entry_date = dt
            elif action == "sell" and shares > 0:
                n = shares * frac
                proceeds = n * fill
                fee = proceeds * commission
                cash += proceeds - fee
                shares -= n
                pnl = proceeds - n * entry_price
                trades.append({
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 4),
                    "exit_date": dt,
                    "exit_price": round(fill, 4),
                    "shares": round(n, 2),
                    "pnl": round(pnl - fee, 2),
                    "pnl_pct": round(pnl / (n * entry_price), 4) if entry_price else 0,
                })
                if shares <= 0:
                    shares = 0.0
                    entry_price = 0.0
                    entry_date = ""
        equity_curve.append({"dt": dt, "equity": round(cash + shares * close_px, 2)})

    # 期末仍持仓：按最后收盘价平仓估值
    if shares > 0 and entry_price > 0 and bars:
        last_px = closes[str(bars[-1]["dt"])]
        proceeds = shares * last_px
        pnl = proceeds - shares * entry_price
        trades.append({
            "entry_date": entry_date, "entry_price": round(entry_price, 4),
            "exit_date": str(bars[-1]["dt"]), "exit_price": round(last_px, 4),
            "shares": round(shares, 2), "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / (shares * entry_price), 4), "open_position": True,
        })

    return {
        "metrics": _finish_metrics(equity_curve, trades, capital),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def _simulate_portfolio(bars_map: dict, signals: list, capital: float, commission: float = 0.0003, slippage: float = 0.001, enforce_price_limit: bool = True) -> dict:
    """组合模拟：各标的 T 日信号在该标的下一交易日开盘成交。"""
    open_map = {sym: {str(b["dt"]): float(b["open"]) for b in bars} for sym, bars in bars_map.items()}
    close_map = {sym: {str(b["dt"]): float(b["close"]) for b in bars} for sym, bars in bars_map.items()}
    dates = sorted({str(b["dt"]) for bars in bars_map.values() for b in bars})

    # 各标的收盘价按日期前向补齐，用于日度估值
    lasts = {}
    for sym, cm in close_map.items():
        cur = None
        out = {}
        for d in dates:
            if d in cm:
                cur = cm[d]
            out[d] = cur
        lasts[sym] = out

    sigs: dict = {}
    next_dates = {
        sym: {str(bars[i]["dt"]): str(bars[i + 1]["dt"]) for i in range(len(bars) - 1)}
        for sym, bars in bars_map.items()
    }
    previous_closes = {
        sym: {str(bars[i]["dt"]): float(bars[i - 1]["close"]) for i in range(1, len(bars))}
        for sym, bars in bars_map.items()
    }
    for s in signals or []:
        sym = str(s.get("symbol", ""))
        dt = str(s.get("dt"))
        execution_dt = next_dates.get(sym, {}).get(dt)
        if sym in open_map and execution_dt in open_map[sym]:
            sigs.setdefault(execution_dt, []).append(s)

    cash = float(capital)
    positions: dict = {}
    trades = []
    equity_curve = []

    for dt in dates:
        for s in sigs.get(dt, []):
            sym = str(s.get("symbol", ""))
            action = str(s.get("action", "")).lower()
            frac = min(max(float(s.get("fraction", 1.0)), 0.0), 1.0)
            fill = open_map[sym][dt] * (1 + slippage if action == "buy" else 1 - slippage)
            previous_close = previous_closes.get(sym, {}).get(dt)
            if enforce_price_limit and previous_close:
                if action == "buy" and fill >= previous_close * 1.095:
                    continue
                if action == "sell" and fill <= previous_close * 0.905:
                    continue
            pos = positions.get(sym)
            if action == "buy":
                if pos is None and cash > 0:
                    spend = cash * frac
                    if spend > fill:
                        shares = int(spend / fill / 100) * 100
                        if shares >= 100:
                            cash -= shares * fill * (1 + commission)
                            positions[sym] = {"shares": shares, "entry_price": fill, "entry_date": dt}
            elif action == "sell" and pos:
                n = pos["shares"] * frac
                proceeds = n * fill
                fee = proceeds * commission
                cash += proceeds - fee
                pos["shares"] -= n
                pnl = proceeds - n * pos["entry_price"]
                trades.append({
                    "symbol": sym,
                    "entry_date": pos["entry_date"],
                    "entry_price": round(pos["entry_price"], 4),
                    "exit_date": dt,
                    "exit_price": round(fill, 4),
                    "shares": round(n, 2),
                    "pnl": round(pnl - fee, 2),
                    "pnl_pct": round(pnl / (n * pos["entry_price"]), 4) if pos["entry_price"] else 0,
                })
                if pos["shares"] <= 0:
                    del positions[sym]

        eq = cash + sum(p["shares"] * (lasts[sym].get(dt) or p["entry_price"])
                        for sym, p in positions.items())
        equity_curve.append({"dt": dt, "equity": round(eq, 2)})

    # 期末仍持仓：按最后收盘价平仓估值
    last_dt = dates[-1] if dates else ""
    for sym, p in positions.items():
        last_px = lasts[sym].get(last_dt) or p["entry_price"]
        proceeds = p["shares"] * last_px
        pnl = proceeds - p["shares"] * p["entry_price"]
        trades.append({
            "symbol": sym,
            "entry_date": p["entry_date"], "entry_price": round(p["entry_price"], 4),
            "exit_date": last_dt, "exit_price": round(last_px, 4),
            "shares": round(p["shares"], 2), "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / (p["shares"] * p["entry_price"]), 4), "open_position": True,
        })

    return {
        "metrics": _finish_metrics(equity_curve, trades, capital),
        "equity_curve": equity_curve,
        "trades": trades,
    }


async def _resolve_strategy(db: AsyncSession, body: BacktestRequest) -> StrategyConfig:
    await _ensure_seeded(db)
    row = None
    if body.strategy_id:
        row = (await db.execute(select(StrategyConfig).where(StrategyConfig.id == body.strategy_id))).scalars().first()
    elif body.strategy:
        row = (await db.execute(select(StrategyConfig).where(StrategyConfig.key == body.strategy))).scalars().first()
    if row is None:
        raise HTTPException(404, "策略不存在")
    if not row.is_active:
        raise HTTPException(400, f"策略「{row.name}」已停用")
    return row


# ---------------------------------------------------------------- 接口

@router.get("/strategies")
async def list_strategies(db: AsyncSession = Depends(get_db)):
    await _ensure_seeded(db)
    rows = (await db.execute(
        select(StrategyConfig).order_by(StrategyConfig.id))).scalars().all()
    return [_to_dict(r) for r in rows]


@router.post("/strategies")
async def create_strategy(body: StrategyCreate, db: AsyncSession = Depends(get_db)):
    await _ensure_seeded(db)
    existing = list((await db.execute(select(StrategyConfig.key))).scalars())
    key = body.key.strip() or _make_key(body.name, existing)
    if key in existing:
        raise HTTPException(400, f"strategy key「{key}」已存在")
    code = body.code or CODE_TEMPLATE
    try:
        _compile_strategy(code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    row = StrategyConfig(
        key=key, name=body.name, description=body.description,
        params_schema=body.params_schema or DEFAULT_SCHEMA, code=code,
        is_builtin=False, is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_dict(row)


@router.put("/strategies/{sid}")
async def update_strategy(sid: int, body: StrategyUpdate, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StrategyConfig).where(StrategyConfig.id == sid))).scalars().first()
    if not row:
        raise HTTPException(404, "策略不存在")
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.params_schema is not None:
        row.params_schema = body.params_schema
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.code is not None:
        try:
            _compile_strategy(body.code)
        except ValueError as e:
            raise HTTPException(400, str(e))
        row.code = body.code
    await db.commit()
    await db.refresh(row)
    return _to_dict(row)


@router.delete("/strategies/{sid}")
async def delete_strategy(sid: int, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StrategyConfig).where(StrategyConfig.id == sid))).scalars().first()
    if not row:
        raise HTTPException(404, "策略不存在")
    if row.is_builtin:
        row.is_active = False
        await db.commit()
        return {"ok": True, "message": "内置策略已停用"}
    await db.delete(row)
    await db.commit()
    return {"ok": True, "message": "已删除"}


@router.post("/strategies/{sid}/duplicate")
async def duplicate_strategy(sid: int, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(StrategyConfig).where(StrategyConfig.id == sid))).scalars().first()
    if not row:
        raise HTTPException(404, "策略不存在")
    existing = list((await db.execute(select(StrategyConfig.key))).scalars())
    new = StrategyConfig(
        key=_make_key(f"{row.key}_copy", existing),
        name=f"{row.name}（副本）",
        description=row.description,
        params_schema=list(row.params_schema or []),
        code=row.code,
        is_builtin=False, is_active=True,
    )
    db.add(new)
    await db.commit()
    await db.refresh(new)
    return _to_dict(new)


@router.post("/strategies/test")
async def test_strategy(body: StrategyTestRequest):
    """用合成K线快速验证策略代码能否运行、是否产出信号（不发网络请求）。"""
    try:
        run_fn = _compile_strategy(body.code)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    bars = []
    d0 = date(2025, 1, 1)
    for i in range(150):
        price = 100 + 8 * math.sin(i / 9.0) + i * 0.12
        bars.append({
            "dt": (d0 + timedelta(days=i)).isoformat(),
            "open": round(price, 2), "high": round(price + 1, 2),
            "low": round(price - 1, 2), "close": round(price + 0.4, 2),
            "volume": 10000 + i * 60,
        })
    try:
        signals = _run_strategy(run_fn, bars, dict(body.params)) or []
        if not isinstance(signals, list):
            return {"ok": False, "error": "run() 必须返回信号列表"}
        mode = "组合模式" if isinstance(signals, list) and any(s.get("symbol") for s in signals[:50]) else "单只模式"
        first = [{"dt": s.get("dt"), "symbol": s.get("symbol"), "action": s.get("action"),
                  "fraction": s.get("fraction", 1.0)} for s in signals[:8]]
        meta = _simulate(bars, signals, 100000)["metrics"]
        return {"ok": True, "mode": mode, "signals": len(signals), "first": first,
                "preview": {"total_return": meta["total_return"], "trade_count": meta["trade_count"]}}
    except (TypeError, AttributeError) as e:
        # 兼容组合型策略：单只 list 当作一只的 dict 再试一次
        try:
            signals = _run_strategy(run_fn, {"TEST_A": bars, "TEST_B": bars}, dict(body.params)) or []
        except Exception as e2:
            return {"ok": False, "error": f"run() 执行出错: {e2}"}
        if not isinstance(signals, list):
            return {"ok": False, "error": "run() 必须返回信号列表"}
        first = [{"dt": s.get("dt"), "symbol": s.get("symbol"), "action": s.get("action"),
                  "fraction": s.get("fraction", 1.0)} for s in signals[:8]]
        meta = _simulate_portfolio({"TEST_A": bars, "TEST_B": bars}, signals, 100000)["metrics"]
        return {"ok": True, "mode": "组合模式", "signals": len(signals), "first": first,
                "preview": {"total_return": meta["total_return"], "trade_count": meta["trade_count"]}}
    except Exception as e:
        return {"ok": False, "error": f"run() 执行出错: {e}"}


@router.post("/run")
async def run_backtest(body: BacktestRequest, db: AsyncSession = Depends(get_db)):
    cfg = await _resolve_strategy(db, body)

    try:
        start = date.fromisoformat(body.start_date)
    except ValueError:
        raise HTTPException(400, "start_date 格式应为 YYYY-MM-DD")
    end_s = body.end_date or date.today().isoformat()
    try:
        end = date.fromisoformat(end_s)
    except ValueError:
        raise HTTPException(400, "end_date 格式应为 YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "start_date 不能晚于 end_date")
    if body.initial_capital <= 0:
        raise HTTPException(400, "initial_capital 必须大于 0")

    portfolio = [s.strip().upper() for s in (body.symbols or []) if s and s.strip()]
    if not portfolio and not (body.symbol or "").strip():
        raise HTTPException(400, "请提供 symbol（单只模式）或 symbols（自选组合模式）")

    merged = _default_params(cfg)
    merged.update({k: v for k, v in (body.params or {}).items() if v is not None})
    try:
        run_fn = _compile_strategy(cfg.code)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if portfolio:
        if len(portfolio) > 20:
            raise HTTPException(400, "自选组合最多支持 20 只股票")
        async def _fetch_symbol(sym):
            try:
                payload = await KlineService(db).get_klines(sym, "day", start, end)
                klines = (payload or {}).get("data", []) or []
                if not klines:
                    raise ValueError(f"未获取到 {sym} 区间 K 线数据")
                return sym, klines, None
            except Exception as e:
                return sym, [], e

        fetched = await asyncio.gather(*[_fetch_symbol(sym) for sym in portfolio])
        bars_map = {}
        for sym, klines, error in fetched:
            if error:
                logger.warning(f"backtest kline fetch failed for {sym}: {error}")
                raise HTTPException(502, f"{sym} K线获取失败: {error}")
            bars_map[sym] = klines
        try:
            signals = _run_strategy(run_fn, bars_map, merged) or []
        except (TypeError, AttributeError) as e:
            raise HTTPException(400,
                f"策略未兼容组合模式：run 收到的是 {{symbol: 列表}} 字典（错误: {e}）。请修改策略代码支持 dict 入参。")
        except Exception as e:
            raise HTTPException(400, f"策略执行出错: {e}")
        if not isinstance(signals, list):
            raise HTTPException(400, "run() 必须返回信号列表")
        result = _simulate_portfolio(bars_map, signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
        result["symbols"] = portfolio
        result["symbol"] = "+".join(portfolio)
    else:
        try:
            payload = await KlineService(db).get_klines(body.symbol, "day", start, end)
            klines = (payload or {}).get("data", []) or []
        except Exception as e:
            logger.warning(f"backtest kline fetch failed: {e}")
            raise HTTPException(502, f"K线获取失败: {e}")
        if not klines:
            raise HTTPException(404, f"未获取到 {body.symbol} 区间 K 线数据")
        try:
            signals = _run_strategy(run_fn, klines, merged) or []
            if not isinstance(signals, list):
                raise ValueError("run() 必须返回信号列表")
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"策略执行出错: {e}")
        result = _simulate(klines, signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
        sym = body.symbol.upper()
        if not result["trades"]:
            result.setdefault("trades", [])
        for t in result["trades"]:
            t.setdefault("symbol", sym)
        result["symbol"] = sym
        result["symbols"] = [sym]

    result["strategy_id"] = cfg.id
    result["strategy"] = cfg.key
    result["strategy_name"] = cfg.name
    result["params"] = merged
    result["execution"] = {
        "commission": body.commission,
        "slippage": body.slippage,
        "enforce_price_limit": body.enforce_price_limit,
        "signal_time": "close_t",
        "fill_time": "open_t_plus_1",
        "lot_size": 100,
    }
    result["start_date"] = start.isoformat()
    result["end_date"] = end.isoformat()
    curve = result.get("equity_curve") or []
    actual_start = date.fromisoformat(curve[0]["dt"]) if curve else None
    actual_end = date.fromisoformat(curve[-1]["dt"]) if curve else None
    result["data_window"] = {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "actual_start": curve[0]["dt"] if curve else None,
        "actual_end": curve[-1]["dt"] if curve else None,
        "bars": len(curve),
        "complete": bool(actual_start and actual_end and (actual_start - start).days <= 7 and (end - actual_end).days <= 7),
    }

    benchmark_symbol = (body.benchmark_symbol or "SH000300").strip().upper()
    benchmark = {"symbol": benchmark_symbol, "name": "沪深300" if benchmark_symbol == "SH000300" else benchmark_symbol, "available": False, "equity_curve": []}
    try:
        benchmark_payload = await KlineService(db).get_klines(benchmark_symbol, "day", start, end)
        benchmark_bars = (benchmark_payload or {}).get("data", []) or []
        close_by_date = {str(b["dt"]): float(b["close"]) for b in benchmark_bars if b.get("close") is not None}
        common = [(c["dt"], close_by_date[c["dt"]]) for c in curve if c["dt"] in close_by_date]
        if len(common) >= 2:
            base = common[0][1]
            bench_curve = [{"dt": dt, "equity": round(float(body.initial_capital) * close / base, 2)} for dt, close in common]
            bench_metrics = _finish_metrics(bench_curve, [], float(body.initial_capital))
            benchmark.update({
                "available": True,
                "actual_start": common[0][0],
                "actual_end": common[-1][0],
                "bars": len(common),
                "total_return": bench_metrics["total_return"],
                "annualized_return": bench_metrics["annualized_return"],
                "equity_curve": bench_curve,
            })
            result["metrics"]["excess_return"] = round(result["metrics"]["total_return"] - bench_metrics["total_return"], 4)
            result["metrics"]["annualized_excess_return"] = round(result["metrics"]["annualized_return"] - bench_metrics["annualized_return"], 4)
    except Exception as e:
        logger.warning(f"backtest benchmark fetch failed for {benchmark_symbol}: {e}")
    result["benchmark"] = benchmark
    return result


# ---------------------------------------------------------------- 敏感性 / Walk-Forward

def _param_values_from_schema(schema: list, key: str, explicit: list, cap: int = 9) -> list:
    if explicit:
        return [v for v in explicit if v is not None][:cap]
    for s in (schema or []):
        if isinstance(s, dict) and s.get("key") == key:
            lo, hi, step = s.get("min"), s.get("max"), s.get("step") or 1
            if lo is None or hi is None:
                base = s.get("default")
                return [base] if base is not None else []
            vals, cur = [], float(lo)
            while cur <= float(hi) + 1e-9 and len(vals) < cap:
                vals.append(int(cur) if str(s.get("type")) == "int" else round(cur, 6))
                cur += float(step)
            return vals
    return []


async def _load_bars_for_body(db: AsyncSession, body: BacktestRequest, start: date, end: date):
    portfolio = [s.strip().upper() for s in (body.symbols or []) if s and s.strip()]
    if portfolio:
        if len(portfolio) > 20:
            raise HTTPException(400, "自选组合最多支持 20 只股票")
        bars_map = {}
        for sym in portfolio:
            payload = await KlineService(db).get_klines(sym, "day", start, end)
            klines = (payload or {}).get("data", []) or []
            if not klines:
                raise HTTPException(502, f"{sym} K线获取失败或区间无数据")
            bars_map[sym] = klines
        return portfolio, bars_map, None
    if not (body.symbol or "").strip():
        raise HTTPException(400, "请提供 symbol 或 symbols")
    payload = await KlineService(db).get_klines(body.symbol, "day", start, end)
    klines = (payload or {}).get("data", []) or []
    if not klines:
        raise HTTPException(404, f"未获取到 {body.symbol} 区间 K 线数据")
    return [body.symbol.upper()], None, klines


def _run_once(run_fn, portfolio, bars_map, klines, params, body) -> dict:
    target = bars_map if bars_map is not None else klines
    signals = _run_strategy(run_fn, target, params) or []
    if not isinstance(signals, list):
        raise HTTPException(400, "run() 必须返回信号列表")
    if bars_map is not None:
        out = _simulate_portfolio(bars_map, signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
    else:
        out = _simulate(klines, signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
    m = out["metrics"]
    return {
        "total_return": m["total_return"],
        "annualized_return": m["annualized_return"],
        "max_drawdown": m["max_drawdown"],
        "sharpe": m["sharpe"],
        "sortino": m["sortino"],
        "win_rate": m["win_rate"],
        "trade_count": m["trade_count"],
        "profit_factor": m["profit_factor"],
        "bars": m["bars"],
    }


def _parse_body_dates(body: BacktestRequest) -> tuple[date, date]:
    try:
        start = date.fromisoformat(body.start_date)
    except ValueError:
        raise HTTPException(400, "start_date 格式应为 YYYY-MM-DD")
    end_s = body.end_date or date.today().isoformat()
    try:
        end = date.fromisoformat(end_s)
    except ValueError:
        raise HTTPException(400, "end_date 格式应为 YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "start_date 不能晚于 end_date")
    if body.initial_capital <= 0:
        raise HTTPException(400, "initial_capital 必须大于 0")
    return start, end


def _merged_params(cfg: StrategyConfig, body: BacktestRequest) -> dict:
    merged = _default_params(cfg)
    merged.update({k: v for k, v in (body.params or {}).items() if v is not None})
    return merged


@router.post("/sensitivity")
async def run_sensitivity(body: SensitivityRequest, db: AsyncSession = Depends(get_db)):
    """单参数敏感性扫描：固定其余参数，扫描 param_key 取值，报告指标随参数变化。"""
    cfg = await _resolve_strategy(db, body)
    start, end = _parse_body_dates(body)
    if not body.param_key:
        raise HTTPException(400, "请指定 param_key")
    try:
        run_fn = _compile_strategy(cfg.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    base = _merged_params(cfg, body)
    values = _param_values_from_schema(cfg.params_schema, body.param_key, body.values)
    if not values:
        raise HTTPException(400, f"无法为参数「{body.param_key}」生成扫描取值，请显式传 values")
    portfolio, bars_map, klines = await _load_bars_for_body(db, body, start, end)

    rows = []
    for v in values:
        params = dict(base)
        params[body.param_key] = v
        try:
            metrics = _run_once(run_fn, portfolio, bars_map, klines, params, body)
            rows.append({"param_value": v, "params": params, "metrics": metrics, "error": None})
        except HTTPException as e:
            rows.append({"param_value": v, "params": params, "metrics": None, "error": str(e.detail)})
        except Exception as e:
            rows.append({"param_value": v, "params": params, "metrics": None, "error": str(e)})

    ok = [r for r in rows if r["metrics"]]
    base_val = base.get(body.param_key)
    summary = None
    if ok:
        rets = [r["metrics"]["total_return"] for r in ok]
        sharpes = [r["metrics"]["sharpe"] for r in ok]
        mean_r = sum(rets) / len(rets)
        var_r = sum((x - mean_r) ** 2 for x in rets) / len(rets)
        best = max(ok, key=lambda r: r["metrics"]["sharpe"])
        worst = min(ok, key=lambda r: r["metrics"]["sharpe"])
        summary = {
            "param_key": body.param_key,
            "base_value": base_val,
            "n_points": len(ok),
            "return_mean": round(mean_r, 4),
            "return_std": round(var_r ** 0.5, 4),
            "sharpe_mean": round(sum(sharpes) / len(sharpes), 4),
            "sharpe_min": round(min(sharpes), 4),
            "sharpe_max": round(max(sharpes), 4),
            "best_value": best["param_value"],
            "worst_value": worst["param_value"],
            "sensitive": bool((max(sharpes) - min(sharpes)) > 0.5 and var_r ** 0.5 > 0.02),
            "basis": "敏感=Sharpe极差>0.5 且 收益率标准差>0.02；参数敏感说明结果依赖特定取值，需结合 walk-forward 验证稳健性。",
        }
    return {
        "strategy": cfg.key,
        "strategy_name": cfg.name,
        "symbol": body.symbol or "+".join(body.symbols or []),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "param_key": body.param_key,
        "rows": rows,
        "summary": summary,
    }


@router.post("/walk-forward")
async def run_walk_forward(body: WalkForwardRequest, db: AsyncSession = Depends(get_db)):
    """时间留出 walk-forward：按交易日等分 n_splits 段，每段用前一段（或滚动历史）选参，只在留出段计成绩。"""
    cfg = await _resolve_strategy(db, body)
    start, end = _parse_body_dates(body)
    try:
        run_fn = _compile_strategy(cfg.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    base = _merged_params(cfg, body)
    portfolio, bars_map, klines = await _load_bars_for_body(db, body, start, end)

    if bars_map is not None:
        all_dates = sorted({str(b["dt"]) for series in bars_map.values() for b in series})
        date_index = {d: i for i, d in enumerate(all_dates)}
        n_bars = len(all_dates)
    else:
        all_dates = [str(b["dt"]) for b in klines]
        date_index = {d: i for i, d in enumerate(all_dates)}
        n_bars = len(klines)

    if n_bars < body.n_splits * 8:
        raise HTTPException(400, f"区间交易日过少（{n_bars}），无法切成 {body.n_splits} 折（每折至少 8 日）")

    opt_key = (body.optimize_param or "").strip()
    opt_values = _param_values_from_schema(cfg.params_schema, opt_key, body.optimize_values) if opt_key else []
    if opt_key and not opt_values:
        raise HTTPException(400, f"无法为优化参数「{opt_key}」生成候选值")

    fold_size = n_bars // body.n_splits
    folds = []
    for i in range(body.n_splits):
        oos_start_i = i * fold_size
        oos_end_i = n_bars if i == body.n_splits - 1 else (i + 1) * fold_size
        # 训练段 = 该折之前的历史（首折无历史，则用本折内前一半作 warm 训练仅用于选参展示，仍只在后半计成绩）
        if i == 0:
            train_start_i = 0
            train_end_i = max(8, fold_size // 2)
            eval_start_i = train_end_i
        else:
            train_start_i = 0
            train_end_i = oos_start_i
            eval_start_i = oos_start_i
        if eval_start_i >= oos_end_i - 4:
            continue
        folds.append({
            "fold": i + 1,
            "train_start_i": train_start_i,
            "train_end_i": train_end_i,
            "eval_start_i": eval_start_i,
            "eval_end_i": oos_end_i,
        })

    def _slice_bars(sl: slice):
        if bars_map is not None:
            return {s: series[sl] for s, series in bars_map.items()}
        return klines[sl]

    def _slice_signals_to_range(signals: list, lo: date, hi: date) -> list:
        out = []
        for s in signals:
            try:
                d = date.fromisoformat(str(s.get("dt")))
            except Exception:
                continue
            if lo <= d <= hi:
                out.append(s)
        return out

    results = []
    for f in folds:
        train_bars = _slice_bars(slice(f["train_start_i"], f["train_end_i"]))
        eval_bars = _slice_bars(slice(f["eval_start_i"], f["eval_end_i"]))
        if bars_map is None and (len(train_bars) < 8 or len(eval_bars) < 4):
            continue
        if bars_map is not None:
            min_len = min((len(v) for v in eval_bars.values()), default=0)
            train_min = min((len(v) for v in train_bars.values()), default=0)
            if min_len < 4 or train_min < 8:
                continue

        eval_lo = date.fromisoformat(str((eval_bars if bars_map is None else next(iter(eval_bars.values())))[0]["dt"]))
        eval_hi = date.fromisoformat(str((eval_bars if bars_map is None else next(iter(eval_bars.values())))[-1]["dt"]))

        # 选参：在训练段网格扫描 optimize_param（或直接用 base）
        chosen = dict(base)
        train_best_sharpe = None
        if opt_key and opt_values:
            best_sharpe = -float("inf")
            for v in opt_values:
                params = dict(base)
                params[opt_key] = v
                try:
                    train_target = train_bars
                    train_signals = _run_strategy(run_fn, train_target, params) or []
                    if bars_map is not None:
                        tr = _simulate_portfolio(train_bars, train_signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)["metrics"]
                    else:
                        tr = _simulate(train_bars, train_signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)["metrics"]
                except Exception:
                    continue
                if tr["sharpe"] > best_sharpe:
                    best_sharpe = tr["sharpe"]
                    chosen = params
            train_best_sharpe = round(best_sharpe, 4) if best_sharpe > -float("inf") else None

        # OOS：信号在全量上生成（避免截断 warmup），再按留出区间过滤后在留出段模拟
        # 更严谨：只在 eval 段 K 线上跑策略（无未来函数，因策略只看 bars 内历史）
        try:
            eval_signals = _run_strategy(run_fn, eval_bars, chosen) or []
            if bars_map is not None:
                oos = _simulate_portfolio(eval_bars, eval_signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
            else:
                oos = _simulate(eval_bars, eval_signals, float(body.initial_capital), body.commission, body.slippage, body.enforce_price_limit)
            m = oos["metrics"]
            results.append({
                "fold": f["fold"],
                "train_range": [
                    str((train_bars if bars_map is None else next(iter(train_bars.values())))[0]["dt"]),
                    str((train_bars if bars_map is None else next(iter(train_bars.values())))[-1]["dt"]),
                ],
                "oos_range": [eval_lo.isoformat(), eval_hi.isoformat()],
                "chosen_params": {opt_key: chosen.get(opt_key)} if opt_key else {},
                "train_sharpe": train_best_sharpe,
                "oos_total_return": m["total_return"],
                "oos_sharpe": m["sharpe"],
                "oos_max_drawdown": m["max_drawdown"],
                "oos_trade_count": m["trade_count"],
                "oos_win_rate": m["win_rate"],
                "oos_bars": m["bars"],
            })
        except Exception as e:
            results.append({
                "fold": f["fold"],
                "train_range": None,
                "oos_range": [eval_lo.isoformat(), eval_hi.isoformat()],
                "chosen_params": {opt_key: chosen.get(opt_key)} if opt_key else {},
                "train_sharpe": train_best_sharpe,
                "error": str(e),
            })

    ok = [r for r in results if "oos_total_return" in r]
    summary = None
    if ok:
        rets = [r["oos_total_return"] for r in ok]
        sharpes = [r["oos_sharpe"] for r in ok]
        mean_r = sum(rets) / len(rets)
        mean_s = sum(sharpes) / len(sharpes)
        summary = {
            "n_folds": len(ok),
            "oos_return_mean": round(mean_r, 4),
            "oos_return_min": round(min(rets), 4),
            "oos_return_max": round(max(rets), 4),
            "oos_sharpe_mean": round(mean_s, 4),
            "oos_positive_folds": sum(1 for r in rets if r > 0),
            "oos_win_rate_mean": round(sum(r["oos_win_rate"] for r in ok) / len(ok), 4),
            "stable": bool(sum(1 for r in rets if r > 0) >= max(1, len(ok) // 2) and mean_s > 0),
            "basis": "walk-forward：每折只在留出时间段计成绩；若指定 optimize_param，只用该折之前的历史选参。stable=过半折收益为正且平均 Sharpe>0。",
        }

    return {
        "strategy": cfg.key,
        "strategy_name": cfg.name,
        "symbol": body.symbol or "+".join(body.symbols or []),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "n_splits": body.n_splits,
        "optimize_param": opt_key or None,
        "folds": results,
        "summary": summary,
        "methodology": "时间顺序切分交易日，训练段选参、留出段评估，禁止用留出段数据选参；与全样本回测结果对照可识别过拟合。",
    }
