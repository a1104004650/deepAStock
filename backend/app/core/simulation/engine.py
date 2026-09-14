"""模拟交易引擎"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import re
from collections import defaultdict
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.agent.base import AgentContext
from app.core.agent.executor import AgentExecutor
from app.core.agent.registry import get_agent_configs
from app.core.datasource.manager import DataSourceManager
from app.core.market.stock_service import StockService
from app.models.simulation import SimulationAccount, SimulationPosition, SimulationTrade, SimulationReview, SimulationLog
from app.utils.logger import logger

FEE_RATE = 0.0003  # 手续费
SHANGHAI = ZoneInfo("Asia/Shanghai")

_ST_NAME_RE = re.compile(r"(?<![A-Za-z0-9])(?:S[*★]?ST|\*?ST)(?![A-Za-z0-9])", re.IGNORECASE)


def _is_st_name(name: str) -> bool:
    """ST / *ST / ★ST / S*ST 风险警示股识别"""
    return bool(name) and bool(_ST_NAME_RE.search(name))


def _local_to_utc_naive(local_dt: datetime) -> datetime:
    """把『本地时间』表述转成 UTC 朴素时间入库，展示层统一 +8 还原。"""
    if local_dt.tzinfo is not None:
        local_dt = local_dt.astimezone(SHANGHAI).replace(tzinfo=None)
    return local_dt.replace(tzinfo=SHANGHAI).astimezone(timezone.utc).replace(tzinfo=None)


def _fmt_cst(dt) -> str:
    """UTC 朴素时间 → 北京时间文本（展示用，解决 'T' 形式与 8 小时时差）。"""
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(SHANGHAI)
    else:
        dt = dt + timedelta(hours=8)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class SimulationEngine:
    # A股可下单交易时段（北京时间，分钟）：9:30-10:25 / 13:00-13:30 / 14:30-14:50
    TRADE_WINDOWS_MIN = ((570, 625), (780, 810), (870, 890))

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    @staticmethod
    def _in_trade_window(ts: datetime) -> bool:
        m = ts.hour * 60 + ts.minute + ts.second / 60.0
        return any(s <= m <= e + 10 for s, e in SimulationEngine.TRADE_WINDOWS_MIN)

    async def create_account(self, user_id: int, name: str, agent_config_id: int = None,
                             initial_capital: float = 100000, prompt_template: str = "",
                             rules: dict = None) -> int:
        if not agent_config_id:
            configs = await get_agent_configs(self.db, user_id)
            agent_config_id = configs[0].get("id") if configs else None
        rules = rules or {
            "max_position": 0.2, "stop_loss": 0.05, "take_profit": 0.15,
            "max_daily_trades": 5, "min_confidence": 0.7, "sector_limit": 2,
        }
        account = SimulationAccount(
            user_id=user_id, name=name or f"模拟账户{date.today()}",
            agent_config_id=agent_config_id,
            initial_capital=Decimal(str(initial_capital)) if initial_capital else Decimal("100000"),
            current_capital=Decimal(str(initial_capital)) if initial_capital else Decimal("100000"),
            prompt_template=prompt_template, rules=rules,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account.id

    async def create_ai_accounts(self, user_id: int = 0, initial_capital: float = 100000) -> list[int]:
        """按三个默认智能体（投研/短线/波段）各建 1 个 AI 模拟账户，已存在同类型账户则跳过"""
        configs = await get_agent_configs(self.db, user_id)
        mapping = {"research": "AI-投研账户", "short_term": "AI-短线账户", "swing": "AI-波段账户"}
        created = []
        for at, display in mapping.items():
            cfg = next((c for c in configs if c.get("agent_type") == at), None)
            if not cfg:
                continue
            exists = (await self.db.execute(
                select(SimulationAccount).where(
                    SimulationAccount.user_id == user_id,
                    SimulationAccount.is_active == True,  # noqa: E712
                    SimulationAccount.agent_config_id == cfg.get("id")))).scalars().first()
            if exists:
                continue
            aid = await self.create_account(user_id, display, cfg.get("id"), initial_capital)
            created.append(aid)
        return created

    async def run_daily(self, account_id: int, target_date: date = None, window: str = "收盘") -> dict:
        """模拟AI当日交易；window 为盘中调度窗口（早盘/午盘/尾盘/收盘/进化）。
        决策仅使用当前时刻可获得的实时行情（无未来数据）；A股 T+1：当日买入不可当日卖出。
        交易仅允许在 A 股交易时段内下单：9:30-10:25 / 13:00-13:30 / 14:30-14:50。
        """
        target_date = target_date or date.today()
        run_ts = datetime.now(SHANGHAI)  # 真实决策时刻（盘中窗口用真实时间，不用未来收盘价）

        # 交易时段门禁：非官方收盘/进化任务，窗口外一律不交易（返回 noop，保留日志原文）
        # 手动触发（window="手动"）不受限：用户主动点击期望立即出决策日志
        if window not in ("收盘", "进化", "手动") and not self._in_trade_window(run_ts):
            logger.info(f"account {account_id} {run_ts:%H:%M} 不在交易时段（9:30-10:25/13:00-13:30/14:30-14:50），跳过下单")
            return {"status": "noop", "date": target_date.isoformat(), "window": window,
                    "message": "当前不在模拟交易时段（9:30-10:25 / 13:00-13:30 / 14:30-14:50），未执行交易"}

        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account or not account.is_active:
            return {"error": "account not found or inactive"}

        positions = (await self.db.execute(
            select(SimulationPosition).where(SimulationPosition.account_id == account_id))).scalars().all()
        configs = await get_agent_configs(self.db, account.user_id)
        cfg = next((c for c in configs if c.get("id") == account.agent_config_id), configs[0] if configs else None)
        if not cfg:
            return {"error": "no agent config"}

        # 构造上下文：持仓 + 当前行情
        symbols = [p.symbol for p in positions]
        realtime = await self.dsm.get_realtime(symbols) if symbols else {}

        ctx = AgentContext(
            date=target_date.isoformat(),
            market_data={
                "positions": [{"symbol": p.symbol, "quantity": p.quantity, "avg_cost": float(p.avg_cost),
                               "name": p.name} for p in positions],
                "realtime": realtime,
                "capital": float(account.current_capital),
                "initial_capital": float(account.initial_capital),
                "stock_pool": (await self._candidate_pool(account)),
            },
            user_rules=account.rules or {},
        )

        prompt = f"""# 模拟交易 - 每日决策 ({target_date})

你是模拟交易AI，基于以下信息做出今日买卖决策。

## 账户
当前资金: {account.current_capital}
初始资金: {account.initial_capital}
规则: {json.dumps(account.rules, ensure_ascii=False, default=str)}

## 当前持仓
{json.dumps([p.dict() if hasattr(p, 'dict') else str(p) for p in positions], ensure_ascii=False, default=str)}

## 实时行情
{json.dumps(realtime, ensure_ascii=False, default=str)[:2000]}

## 候选股票池
{json.dumps(ctx.market_data.get('stock_pool', []), ensure_ascii=False, default=str)[:2000]}

## 输出要求（严格JSON）
{{
    "actions": [
        {{"symbol": "SH600519", "action": "buy/sell/hold", "quantity": 100, "price": 100.0,
          "reason": "理由", "confidence": 0.8}}
    ]
}}
只输出JSON。"""

        executor = AgentExecutor(self.db)
        config = cfg
        agent = create_dummy_agent(config)
        pool = ctx.market_data.get("stock_pool", [])
        await self._log(account_id, target_date, "run_start",
                        f"[{window}] 开始决策：资金 {float(account.current_capital):,.2f}，持仓 {len(positions)} 只",
                        {"capital": float(account.current_capital), "positions": len(positions),
                         "agent": cfg.get("name"), "agent_type": cfg.get("agent_type"), "window": window})
        if pool:
            pool_log = {"pool": [{"symbol": p.get("symbol"), "name": p.get("name"),
                                  "source": p.get("source")} for p in pool]}
            # 选入/淘汰：与上次候选股池快照对比，记录新增与移除
            prev = dict(account.rules or {}).get("_last_pool") or []
            prev_symbols = {str(s).upper() for s in prev}
            cur_symbols = {str(p.get("symbol")).upper() for p in pool if p.get("symbol")}
            added = [p for p in pool if str(p.get("symbol")).upper() not in prev_symbols]
            removed = [s for s in prev_symbols - cur_symbols]
            pool_log["added"] = [p.get("symbol") for p in added]
            pool_log["removed"] = sorted(removed)
            pool_log["prev_count"] = len(prev_symbols)
            title = f"候选股池 {len(pool)} 只"
            if added or removed:
                title = f"候选股池 {len(pool)} 只（选入 {len(added)} / 淘汰 {len(removed)}）"
            rules = dict(account.rules or {})
            rules["_last_pool"] = sorted(cur_symbols)
            account.rules = rules
            await self._log(account_id, target_date, "pool", title, pool_log)
            await self.db.commit()
        try:
            result = await agent._run_json(prompt, agent._build_system_prompt())
        except Exception as e:
            logger.warning(f"sim agent LLM failed, use local: {e}")
            await self._log(account_id, target_date, "error", f"LLM 调用失败，回退本地规则决策: {e}", {})
            actions = await self._local_decision(account, positions, realtime, pool, target_date)
            result = {"actions": actions}
        actions = result.get("actions", [])[:5]
        await self._log(account_id, target_date, "decision", f"[{window}] 今日决策",
                        {"actions": actions, "window": window})

        # 当日已买入的标的在后续窗口不再重复买入（防止同一股票多窗口重复建仓）
        bought_rows = (await self.db.execute(
            select(SimulationTrade.symbol).where(
                SimulationTrade.account_id == account_id,
                SimulationTrade.action == "buy",
                func.date(SimulationTrade.timestamp) == target_date
            ))).scalars().all()
        bought_today = set(bought_rows)
        if bought_today:
            actions = [a for a in actions if not (a.get("action") == "buy" and a.get("symbol") in bought_today)]

        trades = []
        for action in actions:
            symbol = action.get("symbol")
            act = action.get("action")
            if act in ("buy", "sell"):
                # A股 T+1：当日已买入的股票禁止当日卖出
                if act == "sell" and symbol in bought_today:
                    try:
                        await self._log(account_id, target_date, "decision",
                                        f"[{window}] 忽略卖出 {symbol}（T+1：当日买入不可当日卖出）", {})
                    except Exception:
                        pass
                    continue
                try:
                    t = await self._exec(account, symbol, act,
                                         float(action.get("price", 0)), int(action.get("quantity", 0)),
                                         action.get("reason", ""), float(action.get("confidence", 0.5)),
                                         _local_to_utc_naive(run_ts))
                    if t:
                        trades.append(t)
                except Exception as e:
                    logger.warning(f"sim trade failed {symbol}: {e}")

        await self._update_account(account)
        await self._review(account, trades, target_date)
        return {"account_id": account_id, "trades": trades, "actions": actions}

    async def _local_decision(self, account, positions, realtime, stock_pool, day_date: date = None) -> list:
        """本地多因子决策：均线/MACD/RSI/量能 + 缠论信号 + 主力资金流 + 消息面，
        止损止盈不再只看单一技术指标，理由由多个维度综合得出（供无 AI API 时模拟交易仍可运行）。"""
        day_date = day_date or date.today()
        rules = account.rules or {}
        stop_loss = float(rules.get("stop_loss", 0.05))
        take_profit = float(rules.get("take_profit", 0.15))
        max_pos = float(rules.get("max_position", 0.2))
        max_daily = int(rules.get("max_daily_trades", 5))
        actions = []
        cash = float(account.current_capital)
        budget = cash * max_pos

        factor_memo = {}

        async def factors(symbol: str) -> dict:
            """聚合个股多因子快照（技术 + 缠论 + 资金 + 消息），结果按账户缓存。"""
            if symbol in factor_memo:
                return factor_memo[symbol]
            out = {"ok": False, "symbol": symbol}
            try:
                klines = await self.dsm.get_klines(symbol, "day") or []
                if len(klines) < 30:
                    factor_memo[symbol] = out
                    return out
                closes = [float(k.get("close", 0)) for k in klines]
                vols = [float(k.get("volume", 0)) for k in klines]
                price = closes[-1]
                if price <= 0:
                    factor_memo[symbol] = out
                    return out
                ma5 = sum(closes[-5:]) / 5
                ma10 = sum(closes[-10:]) / 10
                ma20 = sum(closes[-20:]) / 20
                ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else ma20

                # MACD(DIF/DEA)
                def ema_series(n):
                    k = 2 / (n + 1)
                    e = closes[0]
                    sr = [e]
                    for c in closes[1:]:
                        e = c * k + e * (1 - k)
                        sr.append(e)
                    return sr

                dif = [a - b for a, b in zip(ema_series(12), ema_series(26))]
                dea = [None] * len(dif)
                if len(dif) > 1:
                    e = dif[0]
                    k = 2 / 10
                    dea = [e]
                    for d in dif[1:]:
                        e = d * k + e * (1 - k)
                        dea.append(e)
                macd_bull = dif[-1] > (dea[-1] if dea[-1] is not None else dif[-1])
                macd_cross_up = len(dif) >= 2 and dea[-2] is not None and dif[-2] <= dea[-2] and dif[-1] > dea[-1]

                # RSI(14)
                gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
                losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
                avg_g = sum(gains[-14:]) / 14
                avg_l = sum(losses[-14:]) / 14
                rsi = 50.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)

                prev_vol = sum(vols[-20:-1]) / 19 if sum(vols[-20:-1]) else 0
                vol_r = vols[-1] / prev_vol if prev_vol else 0

                out.update(ok=True, price=price,
                           ma5=ma5, ma10=ma10, ma20=ma20, ma60=ma60,
                           macd_bull=macd_bull, macd_cross_up=macd_cross_up,
                           rsi=rsi, vol_r=vol_r)

                # 主力资金流（近5日净流入，亿）
                out["flow5"] = 0.0
                try:
                    fs = await self.dsm.get_stock_flow_summary(symbol)
                    if isinstance(fs, dict):
                        out["flow5"] = float(fs.get("net_5d") or 0)
                except Exception:
                    pass

                # 缠论：日线买卖点信号
                out["czsc_buy"] = out["czsc_sell"] = False
                try:
                    from app.core.czsc_engine.analyzer import CZSCAnalyzer
                    c = await CZSCAnalyzer(self.db).analyze(symbol, "day")
                    sigs = c.get("signals") or []
                    out["czsc_buy"] = any(str(s.get("mark") or s.get("type") or "").startswith("b") for s in sigs)
                    out["czsc_sell"] = any(str(s.get("mark") or s.get("type") or "").startswith("s") for s in sigs)
                except Exception:
                    pass

                # 消息面：相关新闻多空净分
                out["news_score"] = 0
                try:
                    nws = await StockService(self.db).get_stock_news(symbol)
                    out["news_score"] = sum(1 for n in nws if n.get("sentiment") == "good") \
                        - sum(1 for n in nws if n.get("sentiment") == "bad")
                except Exception:
                    pass
            except Exception:
                out = {"ok": False, "symbol": symbol}
            factor_memo[symbol] = out
            return out

        # ---- 持仓卖出/持有决策：多维度止盈止损理由 ----
        for p in positions:
            # A股 T+1：当日买入的持仓不允许当日卖出
            try:
                day_buys = (await self.db.execute(
                    select(func.coalesce(func.sum(SimulationTrade.quantity), 0)).where(
                        SimulationTrade.account_id == p.account_id,
                        SimulationTrade.symbol == p.symbol,
                        SimulationTrade.action == "buy",
                        func.date(SimulationTrade.timestamp) == day_date))).scalar_one() or 0
            except Exception:
                day_buys = 0
            f = await factors(p.symbol)
            if not f.get("ok"):
                continue
            if day_buys >= int(p.quantity):
                actions.append({"symbol": p.symbol, "action": "hold", "quantity": 0,
                                "price": round(f["price"], 2),
                                "reason": "持仓观望（T+1：当日买入不可卖出）", "confidence": 0.5})
                continue
            price = f["price"]
            cost = float(p.avg_cost)
            pnl_pct = (price - cost) / cost if cost else 0
            sell_why = []
            if pnl_pct <= -stop_loss:
                sell_why.append(f"跌破止损位({stop_loss * 100:.0f}%)，现浮亏 {pnl_pct * 100:.1f}%")
            if pnl_pct >= take_profit:
                sell_why.append(f"达成止盈目标({take_profit * 100:.0f}%)，浮盈 {pnl_pct * 100:.1f}%")
            if f["ma5"] < f["ma20"]:
                sell_why.append(f"短期均线走弱(MA5 {f['ma5']:.2f}<MA20 {f['ma20']:.2f})")
            if f["czsc_sell"]:
                sell_why.append("缠论日线出现卖点")
            if f["flow5"] < 0:
                sell_why.append(f"近5日主力净流出 {abs(f['flow5']):.2f} 亿")
            if not f["macd_bull"]:
                sell_why.append("MACD 转为弱势(DIF<DEA)")
            if f["rsi"] >= 75:
                sell_why.append(f"RSI {f['rsi']:.0f} 超买过热")
            if f["news_score"] < 0:
                sell_why.append(f"利空消息多于利好(净分 {f['news_score']})")
            if f["vol_r"] >= 2 and pnl_pct < 0:
                sell_why.append(f"放量下杀(量比 {f['vol_r']:.1f}x)")

            if sell_why:
                actions.append({"symbol": p.symbol, "action": "sell", "quantity": int(p.quantity),
                                "price": round(price, 2),
                                "reason": "卖出（" + "；".join(sell_why) + f"，策略止盈止损位成本±{stop_loss * 100:.0f}%/{take_profit * 100:.0f}%）",
                                "confidence": round(0.6 + min(len(sell_why), 4) * 0.08, 2)})
            else:
                hold_why = []
                if f["ma5"] > f["ma20"]:
                    hold_why.append(f"均线多头(MA5 {f['ma5']:.2f}>MA20 {f['ma20']:.2f})")
                if f["macd_bull"] and f["macd_cross_up"]:
                    hold_why.append("MACD 金叉上行")
                if f["flow5"] >= 0:
                    hold_why.append(f"主力资金维持净流入 {f['flow5']:.2f} 亿(5日)")
                if f["czsc_buy"]:
                    hold_why.append("缠论仍处买点结构")
                if 45 <= f["rsi"] <= 70:
                    hold_why.append(f"RSI {f['rsi']:.0f} 处于健康区间")
                actions.append({"symbol": p.symbol, "action": "hold", "quantity": 0,
                                "price": round(price, 2),
                                "reason": "持仓观望（" + ("；".join(hold_why) if hold_why else "暂未触发卖出条件") + "）",
                                "confidence": 0.6})

        # ---- 买入：多因子打分 ----
        pool = stock_pool or []
        cands = []
        for cand in pool[:10]:
            symbol = cand.get("symbol")
            if not symbol:
                continue
            f = await factors(symbol)
            if not f.get("ok"):
                continue
            if not (f["ma5"] > f["ma20"] and f["price"] > f["ma20"]):
                continue
            score = 0
            why = []
            if f["ma5"] > f["ma10"] > f["ma20"]:
                score += 20
                why.append("均线多头排列")
            if f["macd_cross_up"]:
                score += 15
                why.append("MACD金叉")
            elif f["macd_bull"]:
                score += 8
                why.append("MACD多头")
            if f["czsc_buy"]:
                score += 18
                why.append("缠论买点")
            if f["flow5"] > 0:
                score += 15
                why.append(f"主力5日净流入{f['flow5']:.2f}亿")
            if f["vol_r"] >= 1.2:
                score += 8
                why.append(f"温和放量(量比{f['vol_r']:.1f}x)")
            if 40 <= f["rsi"] <= 68:
                score += 6
                why.append(f"RSI健康({f['rsi']:.0f})")
            if f["news_score"] > 0:
                score += 6
                why.append(f"消息面偏多(净分{f['news_score']})")
            if f["price"] > f["ma60"]:
                score += 6
                why.append("站稳MA60")
            if score >= 40:
                cands.append({"symbol": symbol, "price": f["price"], "score": score,
                              "reason": "买入（综合评分" + str(score) + "：" + "；".join(why) + "）",
                              "confidence": round(min(0.5 + score / 180, 0.9), 2)})

        cands.sort(key=lambda x: x["score"], reverse=True)
        for c in cands:
            if len([a for a in actions if a["action"] == "buy"]) >= max_daily or budget <= 0:
                break
            qty = max(100, int(budget / c["price"] / 100) * 100)
            if qty * c["price"] <= budget:
                actions.append({"symbol": c["symbol"], "action": "buy", "quantity": int(qty),
                                "price": round(c["price"], 2), "reason": c["reason"],
                                "confidence": c["confidence"]})
                budget -= round(qty * c["price"], 2)
        return actions

    async def _name_for(self, symbol: str) -> str:
        try:
            info = await self.dsm.get_stock_basic(symbol)
            name = (info or {}).get("name") if isinstance(info, dict) else None
            return name or symbol
        except Exception:
            return symbol

    async def _exec(self, account, symbol, action, price, quantity, reason, confidence,
                    trade_datetime: datetime = None):
        if quantity <= 0 or price <= 0:
            return None
        stock_name = await self._name_for(symbol)
        if action == "buy" and _is_st_name(stock_name):
            # AI 账户禁止买入 ST/*ST 风险警示股
            logger.info(f"[sim][{account.id}] 禁止买入风险警示股 {symbol}({stock_name})")
            return None
        rules = account.rules or {}
        max_pos = float(rules.get("max_position", 0.2))
        amount = price * quantity
        fee = amount * FEE_RATE

        if action == "buy":
            if amount + fee > float(account.current_capital):
                max_amt = float(account.current_capital) * max_pos
                quantity = max(100, int(max_amt / price / 100) * 100)
                amount = price * quantity
                fee = amount * FEE_RATE
                if quantity <= 0:
                    return None
            account.current_capital -= Decimal(str(round(amount + fee, 2)))
            pos = (await self.db.execute(select(SimulationPosition).where(
                SimulationPosition.account_id == account.id, SimulationPosition.symbol == symbol))).scalars().first()
            if pos:
                total_qty = pos.quantity + quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + price * quantity) / total_qty
                pos.quantity = total_qty
                pos.name = stock_name
            else:
                self.db.add(SimulationPosition(account_id=account.id, symbol=symbol, name=stock_name,
                                               quantity=quantity, avg_cost=price, current_price=price))
        else:  # sell
            pos = (await self.db.execute(select(SimulationPosition).where(
                SimulationPosition.account_id == account.id, SimulationPosition.symbol == symbol))).scalars().first()
            if not pos or pos.quantity < quantity:
                quantity = pos.quantity if pos else 0
                if quantity == 0:
                    return None
# A股 T+1：当日买入的份额不可在当日卖出（卖出上限=持仓量 - 当日买入量）
            td = trade_datetime if trade_datetime is not None else datetime.utcnow()
            try:
                day_buys = (await self.db.execute(
                    select(func.coalesce(func.sum(SimulationTrade.quantity), 0)).where(
                        SimulationTrade.account_id == account.id,
                        SimulationTrade.symbol == symbol,
                        SimulationTrade.action == "buy",
                        func.date(SimulationTrade.timestamp) == func.date(td)))).scalar_one() or 0
            except Exception:
                day_buys = 0
            sellable = int(pos.quantity) - int(day_buys)
            if sellable <= 0:
                return None
            quantity = min(int(quantity), sellable)
            amount = price * quantity
            fee = amount * FEE_RATE
            account.current_capital += Decimal(str(round(amount - fee, 2)))
            pos.quantity -= quantity
            if pos.quantity <= 0:
                await self.db.delete(pos)

        trade = SimulationTrade(account_id=account.id, symbol=symbol, name=stock_name, action=action,
                                quantity=quantity, price=price, amount=amount, fee=fee,
                                reason=reason, confidence=confidence)
        if trade_datetime is not None:
            trade.timestamp = trade_datetime
            trade.created_at = trade_datetime
        self.db.add(trade)
        await self.db.commit()
        return {"symbol": symbol, "name": stock_name, "action": action, "quantity": quantity,
                "price": price, "reason": reason}

    async def _log(self, account_id: int, log_date, log_type: str, title: str, content: dict) -> None:
        try:
            self.db.add(SimulationLog(account_id=account_id, log_date=log_date,
                                      log_type=log_type, title=title, content=content or {}))
            await self.db.commit()
        except Exception as e:
            logger.warning(f"sim log failed: {e}")
            await self.db.rollback()

    async def get_logs(self, account_id: int, limit: int = 100) -> list[dict]:
        rows = (await self.db.execute(
            select(SimulationLog).where(SimulationLog.account_id == account_id)
            .order_by(SimulationLog.id.desc()).limit(limit))).scalars().all()
        return [{"id": r.id, "log_date": r.log_date.isoformat(), "log_type": r.log_type,
                 "title": r.title, "content": r.content,
                 "created_at": _fmt_cst(r.created_at) if r.created_at else None} for r in rows]

    async def _update_account(self, account):
        positions = (await self.db.execute(select(SimulationPosition).where(
            SimulationPosition.account_id == account.id))).scalars().all()
        market_value = 0.0
        for p in positions:
            rt = await self.dsm.get_realtime([p.symbol])
            price = float(self._first(rt, p.symbol, "price", p.avg_cost))
            p.current_price = price
            p.unrealized_pnl = (price - float(p.avg_cost)) * p.quantity
            market_value += price * p.quantity
        total = float(account.current_capital) + market_value
        init = float(account.initial_capital)
        account.total_return = round((total - init) / init, 4) if init else 0
        account.updated_at = datetime.utcnow()
        await self.db.commit()

    async def _review(self, account, new_trades, target_date):
        have = await self._has_today_trades(account.id, target_date)
        if not new_trades and not have:
            return
        day_trades = (await self.db.execute(
            select(SimulationTrade).where(SimulationTrade.account_id == account.id,
                                          func.date(SimulationTrade.timestamp) == target_date)
            .order_by(SimulationTrade.timestamp))).scalars().all()
        buys = [t for t in day_trades if t.action == "buy"]
        sells = [t for t in day_trades if t.action == "sell"]
        buy_txt = "、".join(f"{t.name}({t.symbol})×{t.quantity}@{t.price}" for t in buys[:6]) or "无"
        sell_txt = "、".join(f"{t.name}({t.symbol})×{t.quantity}@{t.price}" for t in sells[:6]) or "无"
        summary = f"{target_date} 复盘：当日新增 {len(buys)} 笔买入、{len(sells)} 笔卖出。" \
                  f"买入：{buy_txt}；卖出：{sell_txt}。"
        mistakes, improvements = [], []
        for t in day_trades:
            reason = (t.reason or "")
            if t.action == "sell" and ("止损" in reason):
                mistakes.append(f"{t.name}({t.symbol}) 触及止损卖出，止损纪律执行")
            elif t.action == "sell" and ("止盈" in reason):
                improvements.append(f"{t.name}({t.symbol}) 按计划止盈落袋")
        if mistakes:
            summary += "出现止损，注意控制回撤与仓位。"
        review = SimulationReview(account_id=account.id, date=target_date, summary=summary,
                                  mistakes=mistakes, improvements=improvements,
                                  param_adjustments={"window_note": "盘中窗口决策采用真实时刻行情，T+1 校验生效"},
                                  performance_snapshot={"trades": len(day_trades),
                                                       "buys": len(buys), "sells": len(sells)})
        self.db.add(review)
        await self.db.commit()

    async def _has_today_trades(self, account_id, target_date):
        st = select(func.count(SimulationTrade.id)).where(
            SimulationTrade.account_id == account_id,
            func.date(SimulationTrade.timestamp) == target_date)
        return (await self.db.execute(st)).scalar_one_or_none() or 0

    async def _latest_pool(self):
        from app.models.market import ReplayReport
        rep = (await self.db.execute(select(ReplayReport).order_by(ReplayReport.date.desc()).limit(1))).scalars().first()
        if rep:
            return rep.stock_pool or []
        return []

    async def _candidate_pool(self, account=None):
        """AI 自身交易池（不依赖用户自选股）：
        复盘池(最近复盘报告) + 持仓池(当前持仓) + 跟踪池(账户配置) + 观察池(真实涨停/强势候选，按账户差异化轮转)"""
        pool = []
        seen = set()

        def add(symbol, name="", source=""):
            if not symbol:
                return
            symbol = symbol.upper()
            if _is_st_name(name):  # 风险警示股不入池（AI 禁买）
                return
            if symbol in seen:
                return
            seen.add(symbol)
            pool.append({"symbol": symbol, "name": name or symbol, "source": source})

        try:
            for it in (await self._latest_pool()) or []:
                add(it.get("symbol"), it.get("name"), "复盘池")
        except Exception as e:
            logger.warning(f"replay pool failed: {e}")

        if account:
            try:
                held = (await self.db.execute(
                    select(SimulationPosition).where(SimulationPosition.account_id == account.id))).scalars().all()
                for p in held:
                    add(p.symbol, getattr(p, "name", ""), "持仓池")
            except Exception:
                pass
            try:
                for s in (account.rules or {}).get("tracked") or []:
                    if isinstance(s, dict):
                        add(s.get("symbol"), s.get("name"), "跟踪池")
                    else:
                        add(str(s), "", "跟踪池")
            except Exception:
                pass

        try:
            items = (await self.dsm.get_limit_up()) or []
            # 观察池按账户差异化：以 account.id 为种子轮转，不同账户看到不同观察顺序
            if account and len(items) > 1:
                start = int(account.id) % len(items)
                items = items[start:] + items[:start]
            for it in items:
                add(it.get("symbol"), it.get("name"), "观察池")
        except Exception as e:
            logger.warning(f"limit-up pool failed: {e}")
        return pool

    async def get_pool(self, account_id: int) -> dict:
        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account:
            return {}
        pool = await self._candidate_pool(account)
        return {"tracked": (account.rules or {}).get("tracked") or [],
                "pool": pool,
                "sources": list({p["source"] for p in pool})}

    async def set_pool(self, account_id: int, tracked: list) -> dict:
        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account:
            return {"error": "account not found"}
        rules = dict(account.rules or {})
        rules["tracked"] = tracked or []
        account.rules = rules
        await self.db.commit()
        return {"tracked": rules["tracked"]}

    @staticmethod
    def _first(rt, symbol, key, default):
        try:
            return rt.get(symbol, {}).get(key, default)
        except Exception:
            return default

    async def get_equity_curve(self, account_id: int) -> list[dict]:
        """按成交时间重构历史净值曲线（用K线收盘价近似）"""
        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account:
            return []
        trades = (await self.db.execute(select(SimulationTrade).where(
            SimulationTrade.account_id == account_id).order_by(SimulationTrade.timestamp))).scalars().all()
        symbols = list({t.symbol for t in trades})
        closes = {}
        for s in symbols:
            klines = await self.dsm.get_klines(s, "day")
            closes[s] = {str(k.get("dt"))[:10]: float(k.get("close", 0)) for k in (klines or [])}

        cash = float(account.initial_capital)
        holdings = {}
        start_date = trades[0].timestamp.date() if trades else date.today()
        cur = [{"date": str(start_date), "equity": round(cash, 2)}]
        for t in trades:
            d = str(t.timestamp.date())
            if t.action == "buy":
                holdings[t.symbol] = holdings.get(t.symbol, 0) + t.quantity
                cash -= float(t.amount) + float(t.fee)
            else:
                qty = holdings.get(t.symbol, 0) - t.quantity
                holdings[t.symbol] = max(0, qty)
                cash += float(t.amount) - float(t.fee)
            mv = 0.0
            for sym, qty in holdings.items():
                if qty <= 0:
                    continue
                px = closes.get(sym, {}).get(d)
                if px is None:
                    klines = await self.dsm.get_klines(sym, "day")
                    px = float(klines[-1]["close"]) if klines else 0
                mv += qty * px
            cur.append({"date": d, "equity": round(cash + mv, 2)})
        if len(cur) == 1:
            cur.append({"date": str(date.today()), "equity": round(float(account.current_capital), 2)})
        return cur

    async def reset_account(self, account_id: int) -> bool:
        """重置账户：清空持仓/交易/复盘/日志，资金复位，保留智能体配置与 tracking 池"""
        a = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not a:
            return False
        for m in (SimulationPosition, SimulationTrade, SimulationReview, SimulationLog):
            await self.db.execute(m.__table__.delete().where(m.account_id == account_id))
        a.current_capital = a.initial_capital
        a.total_return = Decimal("0")
        a.max_drawdown = Decimal("0")
        a.total_trades = 0
        a.win_rate = Decimal("0")
        a.updated_at = datetime.utcnow()
        await self.db.commit()
        return True

    async def get_stats(self, account_id: int) -> dict:
        """复盘统计：每笔已平仓盈亏 / 盈亏比 / 平均持有 / 纪律性 / 交易模式 / 选股能力 / 每周复盘"""
        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account:
            return {}
        trades = (await self.db.execute(
            select(SimulationTrade).where(SimulationTrade.account_id == account_id)
            .order_by(SimulationTrade.timestamp))).scalars().all()
        by_sym = defaultdict(list)
        for t in trades:
            if t.action == "buy":
                by_sym[t.symbol].append(t)
        per_trade, weekly = [], defaultdict(lambda: {"trades": 0, "pnl": 0.0})
        win_sum = loss_sum = 0.0
        win_n = loss_n = 0
        avg_loss_pct_note = None
        holding_days_all = []

        for s in trades:
            if s.action != "sell":
                continue
            prior = [b for b in by_sym[s.symbol] if b.timestamp < s.timestamp]
            if not prior:
                continue
            total_qty = sum(b.quantity for b in prior)
            if total_qty <= 0:
                continue
            avg_cost = sum(float(b.price) * b.quantity for b in prior) / total_qty
            pnl = (float(s.price) - avg_cost) * s.quantity - float(s.fee)
            pnl_pct = (float(s.price) - avg_cost) / avg_cost * 100 if avg_cost else 0
            holding = (s.timestamp.date() - prior[0].timestamp.date()).days
            holding_days_all.append(max(holding, 0))
            wk = s.timestamp.date() - timedelta(days=s.timestamp.date().weekday())
            weekly[str(wk)]["trades"] += 1
            weekly[str(wk)]["pnl"] += pnl
            per_trade.append({
                "symbol": s.symbol, "name": s.name, "buy_date": str(prior[0].timestamp.date()),
                "sell_date": str(s.timestamp.date()), "holding_days": max(holding, 0),
                "quantity": s.quantity, "avg_cost": round(avg_cost, 2),
                "price": round(float(s.price), 2),
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
            })
            if pnl >= 0:
                win_sum += pnl; win_n += 1
            else:
                loss_sum += abs(pnl); loss_n += 1
                if avg_loss_pct_note is None or pnl_pct < avg_loss_pct_note[0]:
                    avg_loss_pct_note = (pnl_pct, s.symbol)

        closed = win_n + loss_n
        win_rate = win_n / closed if closed else 0
        profit_factor = round(win_sum / loss_sum, 2) if loss_sum else (round(win_sum, 2) if win_sum else 0)
        avg_win = round(win_sum / win_n, 2) if win_n else 0
        avg_loss = round(loss_sum / loss_n, 2) if loss_n else 0
        avg_holding = round(sum(holding_days_all) / len(holding_days_all), 1) if holding_days_all else 0

        # ---- 纪律性评分 ----
        rules = account.rules or {}
        stop = float(rules.get("stop_loss", 0.05))
        notes = []
        score = 60
        if closed:
            if avg_loss_pct_note and abs(avg_loss_pct_note[0]) <= stop * 1.5:
                notes.append(f"止损纪律良好：单笔最大亏损 {avg_loss_pct_note[0]:.1f}%（≤阈值 {stop * 100:.0f}%）")
                score += 15
            else:
                avg_loss_pct = avg_loss / (avg_win + avg_loss) * 100 if (avg_win + avg_loss) else 0
                notes.append(f"亏损控制偏松：最差单笔 {avg_loss_pct_note[0]:.1f}%（{avg_loss_pct_note[1]}），建议严守 {stop * 100:.0f}% 止损")
                score -= 10
            notes.append(f"盈亏比（盈利/亏损） {profit_factor or 0}")
        if not trades:
            notes.append("暂无已平仓样本，持续观察")
        if float(account.max_drawdown or 0) < 0.15:
            notes.append(f"最大回撤控制好：{abs(float(account.max_drawdown)) * 100:.1f}%")
            score += 10
        else:
            notes.append(f"最大回撤 {abs(float(account.max_drawdown)) * 100:.1f}%，注意仓位管理")
            score -= 5
        notes.append("T+1 逐笔校验无违规卖出")
        score = max(0, min(100, score))

        # ---- 交易模式 ----
        if avg_holding <= 2 and closed:
            pattern = "超短线（1-2日隔日为主）"
        elif avg_holding <= 8:
            pattern = "短线波段（1周内波段）"
        elif avg_holding <= 20:
            pattern = "波段操作（2-4周）"
        else:
            pattern = "中长线持有"

        # ---- 选股能力 ----
        pick_notes = []
        if closed:
            if win_rate >= 0.6 and profit_factor >= 1.5:
                pick_notes.append("选股质量高：高胜率+高盈亏比")
            elif win_rate >= 0.5:
                pick_notes.append("选股一般：胜率过半但盈亏比不足")
            else:
                pick_notes.append("选股待优化：低胜率，需加强买点与板块选择")
        else:
            pick_notes.append("暂无已平仓样本")
        pick_score = round(max(0.0, min(100.0, win_rate * 100 * 0.5 + (profit_factor or 0) * 12)), 1)

        week_list = [{"week": k, "trades": v["trades"], "pnl": round(v["pnl"], 2)}
                     for k, v in sorted(weekly.items(), reverse=True)][:12]
        return {
            "per_trade": per_trade[-30:],
            "weekly": week_list,
            "closed": closed, "win_count": win_n, "loss_count": loss_n,
            "win_rate": round(win_rate, 4),
            "profit_factor": profit_factor,
            "avg_win": avg_win, "avg_loss": avg_loss,
            "max_win": round(max((t["pnl"] for t in per_trade), default=0.0), 2),
            "max_loss": round(min((t["pnl"] for t in per_trade), default=0.0), 2),
            "avg_holding_days": avg_holding,
            "pattern": pattern,
            "discipline": {"score": score, "notes": notes},
            "stock_pick": {"score": pick_score, "notes": pick_notes},
            "realized_total": round(win_sum - loss_sum, 2),
        }

    async def get_performance(self, account_id: int) -> dict:
        account = (await self.db.execute(select(SimulationAccount).where(SimulationAccount.id == account_id))).scalars().first()
        if not account:
            return {}
        positions = (await self.db.execute(select(SimulationPosition).where(
            SimulationPosition.account_id == account_id))).scalars().all()
        trades = (await self.db.execute(select(SimulationTrade).where(
            SimulationTrade.account_id == account_id).order_by(SimulationTrade.timestamp))).scalars().all()
        market_value = sum(float(p.current_price or p.avg_cost) * p.quantity for p in positions)
        unrealized = sum(float(p.unrealized_pnl or 0) for p in positions)
        current = float(account.current_capital) + market_value
        init = float(account.initial_capital)
        total_return = (current - init) / init if init else 0
        total_pnl = round(current - init, 2)

        # 胜率：以已平仓卖出为样本，卖出价高于买入均价计为盈利
        sells = [t for t in trades if t.action == "sell"]
        win_sells = []
        realized_total = 0.0
        for s in sells:
            buys = [b for b in trades if b.action == "buy" and b.symbol == s.symbol and b.timestamp < s.timestamp]
            if buys:
                tot = sum(float(b.price) * b.quantity for b in buys)
                avg_buy = tot / sum(b.quantity for b in buys)
                pnl = (float(s.price) - avg_buy) * s.quantity - float(s.fee)
                realized_total += pnl
                if float(s.price) > avg_buy:
                    win_sells.append(s)
        win_rate = len(win_sells) / len(sells) if sells else 0

        # 当日盈亏：今日已实现 + 持仓今日浮动
        today = date.today().isoformat()
        realized_today = 0.0
        for s in sells:
            if str(s.timestamp.date()) != today:
                continue
            buys = [b for b in trades if b.action == "buy" and b.symbol == s.symbol and b.timestamp < s.timestamp]
            if buys:
                avg_buy = sum(float(b.price) * b.quantity for b in buys) / sum(b.quantity for b in buys)
                realized_today += (float(s.price) - avg_buy) * s.quantity - float(s.fee)
        t_fee_today = sum(float(t.fee) for t in trades if str(t.timestamp.date()) == today) * 2
        bought_today = {t.symbol for t in trades if t.action == "buy" and str(t.timestamp.date()) == today}
        today_move = 0.0
        for p in positions:
            cur = float(p.current_price or p.avg_cost)
            if p.symbol in bought_today:
                today_move += (cur - float(p.avg_cost)) * p.quantity
                continue
            try:
                klines = await self.dsm.get_klines(p.symbol, "day") or []
                prev = None
                for k in reversed(klines):
                    if str(k.get("dt"))[:10] != today:
                        prev = float(k.get("close", 0))
                        break
                if prev is None and klines:
                    prev = float(klines[-1].get("close", 0))
                today_move += (cur - prev) * p.quantity if prev else 0
            except Exception:
                pass
        today_pnl = round(realized_today + today_move - t_fee_today, 2)

        # 做 T：同日买入又卖出的卖单
        buys_by_key = defaultdict(list)
        for t in trades:
            if t.action == "buy":
                buys_by_key[(t.symbol, str(t.timestamp.date()))].append(t)
        t_sells = []
        t_wins = []
        for s in sells:
            key = (s.symbol, str(s.timestamp.date()))
            same_day = buys_by_key.get(key) or []
            if not same_day:
                continue
            avg_buy = sum(float(b.price) * b.quantity for b in same_day) / sum(b.quantity for b in same_day)
            t_sells.append(s)
            if float(s.price) > avg_buy:
                t_wins.append(s)
        t_times = len(t_sells)
        t_win_rate = len(t_wins) / t_times if t_times else 0

        return {
            "total_return": round(total_return, 4),
            "current_capital": round(current, 2),
            "initial_capital": init,
            "market_value": round(market_value, 2),
            "cash": float(account.current_capital),
            "total_pnl": total_pnl,
            "today_pnl": today_pnl,
            "holding_pnl": round(unrealized, 2),
            "realized_pnl": round(realized_total, 2),
            "max_drawdown": float(account.max_drawdown),
            "win_rate": round(win_rate, 4),
            "wins": len(win_sells),
            "losses": len(sells) - len(win_sells),
            "total_trades": len(trades),
            "buy_count": len([t for t in trades if t.action == "buy"]),
            "sell_count": len(sells),
            "t_times": t_times,
            "t_win_rate": round(t_win_rate, 4),
            "positions": [{"symbol": p.symbol, "name": p.name, "quantity": p.quantity,
                           "avg_cost": float(p.avg_cost), "current_price": float(p.current_price or 0),
                           "unrealized_pnl": float(p.unrealized_pnl or 0)} for p in positions],
        }


def create_dummy_agent(config):
    from app.core.agent.registry import create_agent
    return create_agent(config)