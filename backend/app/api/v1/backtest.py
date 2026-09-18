"""策略回测接口：策略存储在数据库，支持编辑参数 / 新增 / 复制 / 自己写 run(bars, params) 策略代码。"""
import builtins
import json
import math
import re
import time
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
        raise ValueError("策略代码必须定义 run(bars, params) 函数")
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


class StrategyTestRequest(BaseModel):
    code: str = Field("", description="策略代码")
    params: dict = Field(default_factory=dict)


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

    # 修复周期
    recovery_idx = len(equity_curve) - 1
    for i in range(dd_end_idx, len(equity_curve)):
        if equity_curve[i]["equity"] >= peak:
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

    # 盈亏比
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 0
    profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

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


def _simulate(bars: list, signals: list, capital: float) -> dict:
    """单只股票资金模拟：信号当日开盘价成交，buy 只允许空仓建仓，sell 按持仓比例减仓。"""
    opens = {str(b["dt"]): float(b["open"]) for b in bars}
    closes = {str(b["dt"]): float(b["close"]) for b in bars}
    sigs: dict = {}
    for s in signals or []:
        dt = str(s.get("dt"))
        if dt in opens:
            sigs.setdefault(dt, []).append(s)

    cash = float(capital)
    shares = 0.0
    entry_price = 0.0
    entry_date = ""
    trades = []
    equity_curve = []

    for b in bars:
        dt = str(b["dt"])
        close_px = closes[dt]
        for s in sigs.get(dt, []):
            action = str(s.get("action", "")).lower()
            frac = min(max(float(s.get("fraction", 1.0)), 0.0), 1.0)
            fill = opens[dt]
            if action == "buy" and shares <= 0 and cash > 0:
                spend = cash * frac
                if spend > fill:
                    shares = int(spend / fill / 100) * 100
                    if shares >= 100:
                        cash -= shares * fill
                        entry_price = fill
                        entry_date = dt
            elif action == "sell" and shares > 0:
                n = shares * frac
                proceeds = n * fill
                cash += proceeds
                shares -= n
                pnl = proceeds - n * entry_price
                trades.append({
                    "entry_date": entry_date,
                    "entry_price": round(entry_price, 4),
                    "exit_date": dt,
                    "exit_price": round(fill, 4),
                    "shares": round(n, 2),
                    "pnl": round(pnl, 2),
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


def _simulate_portfolio(bars_map: dict, signals: list, capital: float) -> dict:
    """自选组合资金模拟：多只股票按日期对齐，buy 按 fraction 分配可用资金建仓，sell 按持仓比例减仓。"""
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
    for s in signals or []:
        sym = str(s.get("symbol", ""))
        dt = str(s.get("dt"))
        if sym in open_map and dt in open_map[sym]:
            sigs.setdefault(dt, []).append(s)

    cash = float(capital)
    positions: dict = {}
    trades = []
    equity_curve = []

    for dt in dates:
        for s in sigs.get(dt, []):
            sym = str(s.get("symbol", ""))
            action = str(s.get("action", "")).lower()
            frac = min(max(float(s.get("fraction", 1.0)), 0.0), 1.0)
            fill = open_map[sym][dt]
            pos = positions.get(sym)
            if action == "buy":
                if pos is None and cash > 0:
                    spend = cash * frac
                    if spend > fill:
                        shares = int(spend / fill / 100) * 100
                        if shares >= 100:
                            cash -= shares * fill
                            positions[sym] = {"shares": shares, "entry_price": fill, "entry_date": dt}
            elif action == "sell" and pos:
                n = pos["shares"] * frac
                proceeds = n * fill
                cash += proceeds
                pos["shares"] -= n
                pnl = proceeds - n * pos["entry_price"]
                trades.append({
                    "symbol": sym,
                    "entry_date": pos["entry_date"],
                    "entry_price": round(pos["entry_price"], 4),
                    "exit_date": dt,
                    "exit_price": round(fill, 4),
                    "shares": round(n, 2),
                    "pnl": round(pnl, 2),
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
        signals = run_fn(bars, dict(body.params)) or []
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
            signals = run_fn({"TEST_A": bars, "TEST_B": bars}, dict(body.params)) or []
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
        bars_map = {}
        for sym in portfolio:
            try:
                payload = await KlineService(db).get_klines(sym, "day", start, end)
            except Exception as e:
                logger.warning(f"backtest kline fetch failed for {sym}: {e}")
                raise HTTPException(502, f"{sym} K线获取失败: {e}")
            klines = (payload or {}).get("data", []) or []
            if not klines:
                raise HTTPException(404, f"未获取到 {sym} 区间 K 线数据")
            bars_map[sym] = klines
        try:
            signals = run_fn(bars_map, merged) or []
        except (TypeError, AttributeError) as e:
            raise HTTPException(400,
                f"策略未兼容组合模式：run 收到的是 {{symbol: 列表}} 字典（错误: {e}）。请修改策略代码支持 dict 入参。")
        except Exception as e:
            raise HTTPException(400, f"策略执行出错: {e}")
        if not isinstance(signals, list):
            raise HTTPException(400, "run() 必须返回信号列表")
        result = _simulate_portfolio(bars_map, signals, float(body.initial_capital))
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
            signals = run_fn(klines, merged) or []
            if not isinstance(signals, list):
                raise ValueError("run() 必须返回信号列表")
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"策略执行出错: {e}")
        result = _simulate(klines, signals, float(body.initial_capital))
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
    result["start_date"] = start.isoformat()
    result["end_date"] = end.isoformat()
    return result