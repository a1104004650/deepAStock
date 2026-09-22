"""AI炒股比赛引擎 v2 — AI只决策，平台负责风控/撮合/记账

流程：
真实行情 → AI独立生成交易指令 → 平台风控校验 → 模拟撮合 → 更新账户/持仓/排行榜 → AI复盘
"""
import json
import time
import asyncio
import random
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laboratory import (
    LabCompetition, LabParticipant, LabCompPosition,
    LabCompTrade, LabChatMessage, LabLeaderboard, LabCompEvent
)
from app.core.agent.llm_client import LLMClient
from app.core.datasource.manager import DataSourceManager
from app.core.lab.call_logger import record_lab_call
from app.utils.logger import logger
from app.utils import shanghai_now


# ==================== 风控规则 ====================

class OrderValidator:
    """平台风控引擎 — 校验每笔交易指令"""

    @staticmethod
    def validate(
        intent: Dict,
        participant: LabParticipant,
        positions: List[LabCompPosition],
        competition: LabCompetition,
        realtime_prices: Dict[str, Dict],
        today_bought_symbols: set,
    ) -> Tuple[bool, str, Dict]:
        """
        校验一条交易指令，返回 (通过, 原因, 校验后的指令)

        校验规则：
        1. 基本格式校验（symbol/action/quantity）
        2. 股票池限制
        3. 100股整数倍（A股规则）
        4. 停牌检查
        5. 涨跌停检查（±10%主板，±20%创业板/科创板）
        6. T+1：今天买的不能今天卖
        7. 买入资金校验（可用资金够不够）
        8. 单只仓位上限
        9. 最大持仓数
        10. 卖出只能卖持仓中已有的
        11. 卖出数量不能超过持仓
        """
        symbol = intent.get("symbol", "").strip()
        action = intent.get("action", "").strip().lower()
        quantity = intent.get("quantity", 0)
        reason = intent.get("reason", "")

        # 1. 基本格式
        if not symbol or not action:
            return False, "缺少股票代码或交易方向", {}
        if action not in ("buy", "sell"):
            return False, f"无效的交易方向: {action}", {}
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            return False, f"无效的交易数量: {quantity}", {}

        # 获取实时价格
        price_data = realtime_prices.get(symbol)
        if not price_data or not price_data.get("price") or price_data["price"] <= 0:
            return False, f"无法获取 {symbol} 的实时价格", {}
        price = price_data["price"]
        stock_name = price_data.get("name", "")
        change_pct = price_data.get("change_pct", 0)

        # 2. 股票池限制
        if competition.stock_pool and symbol not in competition.stock_pool:
            return False, f"{symbol} 不在比赛股票池中", {}

        # 3. 100股整数倍（A股规则）
        quantity = int(quantity)
        if quantity % 100 != 0:
            quantity = (quantity // 100) * 100
            if quantity <= 0:
                return False, "数量调整后为0", {}

        # 4. 停牌检查（成交量为0视为停牌）
        volume = price_data.get("volume", 0)
        if volume == 0 and action == "buy":
            return False, f"{symbol} 疑似停牌，无法买入", {}

        # 5. 涨跌停检查
        risk_rules = competition.risk_rules or {}
        price_limit_pct = risk_rules.get("price_limit_pct", 0.10)
        if change_pct and abs(change_pct) >= price_limit_pct * 100:
            if action == "buy" and change_pct >= price_limit_pct * 100:
                return False, f"{symbol} 已涨停({change_pct:.1f}%)，无法买入", {}
            if action == "sell" and change_pct <= -price_limit_pct * 100:
                return False, f"{symbol} 已跌停({change_pct:.1f}%)，无法卖出", {}

        amount = quantity * price

        if action == "buy":
            # 7. 资金校验
            trading_fee = competition.trading_fee or 0.0003
            fee = amount * trading_fee
            if amount + fee > participant.current_capital:
                max_amount = participant.current_capital * 0.98
                quantity = int(max_amount / price / 100) * 100
                if quantity <= 0:
                    return False, "可用资金不足", {}
                amount = quantity * price
                fee = amount * trading_fee

            # 8. 单只仓位上限（基于总资产，不是可用资金）
            max_pos_pct = competition.max_position_pct or 0.2
            market_value = sum(p.get("current_price", 0) * p.get("quantity", 0) for p in (positions or []))
            total_assets = participant.current_capital + market_value
            if amount > total_assets * max_pos_pct:
                quantity = int(total_assets * max_pos_pct / price / 100) * 100
                if quantity <= 0:
                    return False, "单只仓位超限", {}
                amount = quantity * price

            # 9. 最大持仓数
            max_positions = competition.max_positions or 5
            current_pos_symbols = {p.symbol for p in positions if p.quantity > 0}
            if symbol not in current_pos_symbols and len(current_pos_symbols) >= max_positions:
                return False, f"已达最大持仓数 {max_positions}", {}

        elif action == "sell":
            # 10. 卖出只能卖已有的
            pos = next((p for p in positions if p.symbol == symbol and p.quantity > 0), None)
            if not pos:
                return False, f"未持有 {symbol}，无法卖出", {}

            # 6. T+1检查：今天买的不能卖
            if symbol in today_bought_symbols:
                return False, f"{symbol} 今日买入，T+1限制不可卖出", {}

            # 11. 卖出数量不能超过持仓
            if quantity > pos.quantity:
                quantity = pos.quantity
                amount = quantity * price

        return True, "通过", {
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "amount": amount,
            "fee": amount * (competition.trading_fee or 0.0003),
            "reason": reason,
            "stock_name": stock_name,
        }


# ==================== 撮合引擎 ====================

class SimulatedMatcher:
    """模拟撮合引擎 — 基于实时价格成交"""

    @staticmethod
    def match(order: Dict) -> Dict:
        """
        撮合一笔订单，返回成交结果

        模拟撮合规则：
        - 以实时价格成交（已由OrderValidator确认价格有效）
        - 计算手续费
        - 买入：资金减少；卖出：资金增加
        """
        return {
            "symbol": order["symbol"],
            "action": order["action"],
            "quantity": order["quantity"],
            "price": order["price"],
            "amount": order["amount"],
            "fee": order["fee"],
            "reason": order.get("reason", ""),
            "stock_name": order.get("stock_name", ""),
            "status": "filled",  # 全额成交
        }


# ==================== 记账引擎 ====================

class AccountingEngine:
    """统一记账引擎 — 资金/持仓/市值/净值/收益率/胜率/最大回撤"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_trade(
        self, participant: LabParticipant, fill: Dict, today_bought_symbols: set
    ) -> None:
        """应用一笔成交，更新持仓和资金"""
        symbol = fill["symbol"]
        action = fill["action"]
        quantity = fill["quantity"]
        price = fill["price"]
        amount = fill["amount"]
        fee = fill["fee"]

        if action == "buy":
            participant.current_capital -= (amount + fee)
            today_bought_symbols.add(symbol)
            await self._update_position_buy(participant.id, symbol, fill.get("stock_name", ""), quantity, price)
        elif action == "sell":
            participant.current_capital += (amount - fee)
            await self._update_position_sell(participant.id, symbol, quantity, price)

        participant.total_trades += 1

    async def compute_account_stats(
        self, participant: LabParticipant, competition_id: int
    ) -> None:
        """计算参赛者账户统计"""
        positions = await self._get_positions(participant.id)
        market_value = sum(p.current_price * p.quantity for p in positions)
        total_assets = participant.current_capital + market_value

        participant.total_return = (total_assets - participant.initial_capital) / participant.initial_capital

        # 计算最大回撤（基于已有的total_return）
        # 简化计算：如果有持仓亏损超过历史最大回撤，更新
        for pos in positions:
            pos.unrealized_pnl = (pos.current_price - pos.avg_cost) * pos.quantity

        await self.db.commit()

    async def update_leaderboard(self, competition_id: int) -> None:
        """更新排行榜快照"""
        result = await self.db.execute(
            select(LabParticipant).where(
                LabParticipant.competition_id == competition_id,
                LabParticipant.status == "active"
            )
        )
        participants = list(result.scalars().all())
        participants.sort(key=lambda p: p.total_return, reverse=True)

        today = shanghai_now().date().isoformat()
        await self.db.execute(
            delete(LabLeaderboard).where(
                LabLeaderboard.competition_id == competition_id,
                LabLeaderboard.snapshot_date == today,
            )
        )

        for rank, p in enumerate(participants, 1):
            lb = LabLeaderboard(
                competition_id=competition_id,
                snapshot_date=today,
                participant_id=p.id,
                total_return=p.total_return,
                win_rate=p.win_rate,
                max_drawdown=p.max_drawdown,
                total_trades=p.total_trades,
                rank=rank,
            )
            self.db.add(lb)

        await self.db.commit()

    async def _update_position_buy(
        self, participant_id: int, symbol: str, name: str, qty: int, price: float
    ):
        """买入更新持仓"""
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.symbol == symbol
            )
        )
        pos = result.scalars().first()

        if pos:
            total_cost = pos.avg_cost * pos.quantity + price * qty
            pos.quantity += qty
            pos.avg_cost = total_cost / pos.quantity
            pos.current_price = price
            pos.unrealized_pnl = (price - pos.avg_cost) * pos.quantity
        else:
            pos = LabCompPosition(
                participant_id=participant_id,
                symbol=symbol,
                name=name,
                quantity=qty,
                avg_cost=price,
                current_price=price,
                unrealized_pnl=0,
            )
            self.db.add(pos)

    async def _update_position_sell(
        self, participant_id: int, symbol: str, qty: int, price: float
    ):
        """卖出更新持仓"""
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.symbol == symbol
            )
        )
        pos = result.scalars().first()
        if pos:
            pos.quantity -= qty
            pos.current_price = price
            pos.unrealized_pnl = (price - pos.avg_cost) * pos.quantity
            if pos.quantity <= 0:
                await self.db.delete(pos)

    async def _get_positions(self, participant_id: int) -> List[LabCompPosition]:
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.quantity > 0
            )
        )
        return list(result.scalars().all())


# ==================== AI自主运行引擎 ====================

class AutoRunEngine:
    """管理所有比赛AI自主运行的引擎（进程级单例）"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks = {}
            cls._instance._status = {}
        return cls._instance

    @property
    def running_competitions(self) -> List[int]:
        return list(self._tasks.keys())

    def get_status(self, comp_id: int) -> Optional[Dict]:
        return self._status.get(comp_id)

    def is_running(self, comp_id: int) -> bool:
        return comp_id in self._tasks

    async def start(self, comp_id: int, db_factory):
        if comp_id in self._tasks:
            return {"ok": False, "error": "已在运行中"}
        task = asyncio.create_task(self._run_loop(comp_id, db_factory))
        self._tasks[comp_id] = task
        self._status[comp_id] = {
            "round": 0, "phase": "idle",
            "started_at": shanghai_now().isoformat(),
            "participants": [],
        }
        logger.info(f"[AutoRun] 启动比赛 {comp_id}")
        return {"ok": True}

    async def stop(self, comp_id: int):
        task = self._tasks.pop(comp_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._status.pop(comp_id, None)
        logger.info(f"[AutoRun] 停止比赛 {comp_id}")
        return {"ok": True}

    async def _run_loop(self, comp_id: int, db_factory):
        """主循环：讨论 → 撮合 → 记账 → 排行榜 → 反馈"""
        try:
            while True:
                try:
                    async with db_factory() as db:
                        result = await db.execute(
                            select(LabCompetition).where(LabCompetition.id == comp_id)
                        )
                        comp = result.scalars().first()
                        if not comp or comp.status != "active":
                            logger.info(f"[AutoRun] 比赛 {comp_id} 已结束或不存在，停止")
                            break

                        pr = await db.execute(
                            select(LabParticipant).where(
                                LabParticipant.competition_id == comp_id,
                                LabParticipant.status == "active"
                            )
                        )
                        participants = list(pr.scalars().all())
                        if not participants:
                            await asyncio.sleep(60)
                            continue

                        self._status[comp_id]["round"] += 1
                        round_num = self._status[comp_id]["round"]
                        self._status[comp_id]["phase"] = "analyzing"
                        self._status[comp_id]["participants"] = [
                            {"name": p.name, "avatar": p.avatar, "phase": "waiting", "trades_this_round": 0}
                            for p in participants
                        ]

                        engine = CompetitionEngine(db)

                        # ======== 阶段1: AI思考与分析（不是闲聊） ========
                        topic = await engine._generate_discussion_topic(comp_id, round_num, participants)
                        # 每轮只随机选2个AI发言，节省token，聚焦思考
                        speakers = random.sample(participants, min(2, len(participants)))

                        for p in speakers:
                            if comp_id not in self._tasks:
                                break

                            p_idx = next(j for j, pp in enumerate(participants) if pp.id == p.id)
                            p_status = self._status[comp_id]["participants"][p_idx]
                            p_status["phase"] = "analyzing"

                            try:
                                recent_chat = await engine._get_recent_chat(comp_id, limit=10)
                                positions = await engine._get_positions(p.id)
                                pool = await engine._build_candidate_pool(comp, p.id)
                                context = await engine._build_trading_context(p, positions, pool, comp)
                                remark = await engine._ai_discuss(p, topic, recent_chat, context)
                                if remark:
                                    await engine._post_chat(comp_id, p, remark, "discussion")
                                    p_status["phase"] = "done"
                            except Exception as e:
                                logger.error(f"[AutoRun] AI分析出错 {p.name}: {e}")
                                p_status["phase"] = "error"

                            if p != speakers[-1]:
                                await asyncio.sleep(random.uniform(2, 4))

                        # ======== 阶段2: AI出指令 → 平台撮合 → 记账 ========
                        self._status[comp_id]["phase"] = "trading"

                        pr2 = await db.execute(
                            select(LabParticipant).where(
                                LabParticipant.competition_id == comp_id,
                                LabParticipant.status == "active"
                            )
                        )
                        participants = list(pr2.scalars().all())

                        # 构建统一行情快照（所有选手共享同一批行情数据）
                        all_symbols = set()
                        for p in participants:
                            pool = await engine._build_candidate_pool(comp, p.id)
                            all_symbols.update(pool[:10])
                            positions = await engine._get_positions(p.id)
                            all_symbols.update(pos.symbol for pos in positions)

                        realtime_prices = await engine._fetch_realtime_batch(list(all_symbols))
                        logger.info(f"[AutoRun] 比赛 {comp_id} 第 {round_num} 轮行情快照: {len(realtime_prices)} 只股票")

                        round_results = []

                        for i, p in enumerate(participants):
                            if comp_id not in self._tasks:
                                break

                            p_idx = next(j for j, pp in enumerate(participants) if pp.id == p.id)
                            p_status = self._status[comp_id]["participants"][p_idx]
                            p_status["phase"] = "trading"

                            try:
                                # 1. 获取账户状态
                                positions = await engine._get_positions(p.id)
                                today_bought = set()  # T+1: 今日买入的股票

                                # 从今日交易记录中提取已买入的股票
                                today_trades = await engine._get_today_trades(p.id)
                                for t in today_trades:
                                    if t.action == "buy":
                                        today_bought.add(t.symbol)

                                # 2. 构建上下文，让AI出指令
                                pool = await engine._build_candidate_pool(comp, p.id)
                                context = await engine._build_trading_context(p, positions, pool, comp)
                                context["recent_chat"] = await engine._get_recent_chat(comp_id, limit=15)
                                context["leaderboard"] = await engine._get_leaderboard(comp_id)
                                context["topic"] = topic
                                # 反馈上一轮的实际执行结果
                                if round_num > 1:
                                    context["last_round_feedback"] = await engine._get_last_round_feedback(p.id)

                                # 3. AI只出指令（不校验，不计算可行性）
                                ai_result = await engine._ai_generate_intents(p, context, round_num)
                                intents = ai_result.get("intents", [])

                                # 4. 平台逐条校验 + 撮合 + 记账
                                accounting = AccountingEngine(db)
                                fills = []
                                for intent in intents:
                                    ok, reason, order = OrderValidator.validate(
                                        intent, p, positions, comp, realtime_prices, today_bought
                                    )
                                    if not ok:
                                        logger.info(f"[风控拒绝] {p.name}: {reason}")
                                        continue

                                    fill = SimulatedMatcher.match(order)
                                    await accounting.apply_trade(p, fill, today_bought)
                                    fills.append(fill)

                                    # 记录成交
                                    trade = LabCompTrade(
                                        participant_id=p.id,
                                        symbol=fill["symbol"],
                                        name=fill.get("stock_name", ""),
                                        action=fill["action"],
                                        quantity=fill["quantity"],
                                        price=fill["price"],
                                        amount=fill["amount"],
                                        fee=fill["fee"],
                                        reason=fill.get("reason", ""),
                                    )
                                    db.add(trade)

                                # 5. 重新计算账户净值
                                await accounting.compute_account_stats(p, comp_id)

                                # 6. AI复盘发言
                                await engine._smart_chat_post(p, ai_result, fills, round_num)

                                p_status["phase"] = "done"
                                p_status["trades_this_round"] = len(fills)

                                round_results.append({
                                    "name": p.name,
                                    "intents": len(intents),
                                    "fills": len(fills),
                                    "return": round(p.total_return * 100, 2),
                                })

                            except Exception as e:
                                logger.error(f"[AutoRun] 交易出错 {p.name}: {e}", exc_info=True)
                                p_status["phase"] = "error"

                            if i < len(participants) - 1:
                                await asyncio.sleep(random.uniform(3, 8))

                        # 7. 更新排行榜
                        accounting = AccountingEngine(db)
                        await accounting.update_leaderboard(comp_id)

                        # 8. 事件检测 + 事件触发AI讨论
                        events = await engine.detect_and_record_events(comp_id, participants, round_num)
                        if events:
                            await engine.generate_event_chat(comp_id, events, participants)

                        # 9. 更新总轮数
                        comp.total_rounds = self._status[comp_id]["round"]
                        await db.commit()

                        self._status[comp_id]["phase"] = "idle"
                        logger.info(f"[AutoRun] 比赛 {comp_id} 第 {round_num} 轮完成: {round_results}")

                except Exception as e:
                    logger.error(f"[AutoRun] 比赛 {comp_id} 本轮执行出错，将重试: {e}", exc_info=True)
                    # 本轮出错，不停止，等下一轮重试

                # 等待下一轮
                wait_time = random.uniform(120, 300)
                await asyncio.sleep(wait_time)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[AutoRun] 比赛 {comp_id} 主循环异常: {e}", exc_info=True)
        finally:
            self._tasks.pop(comp_id, None)
            self._status.pop(comp_id, None)


# ==================== 比赛引擎 ====================

class CompetitionEngine:
    """比赛引擎: AI决策 + 数据获取 + 群聊"""

    TRADING_SESSIONS = [("09:30", "11:30"), ("13:00", "15:00")]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    # ==================== 数据获取 ====================

    async def _get_positions(self, participant_id: int) -> List[LabCompPosition]:
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.quantity > 0
            )
        )
        return list(result.scalars().all())

    async def _get_recent_chat(self, comp_id: int, limit: int = 10) -> List[Dict]:
        result = await self.db.execute(
            select(LabChatMessage)
            .where(LabChatMessage.competition_id == comp_id)
            .order_by(LabChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()

        pr = await self.db.execute(
            select(LabParticipant).where(LabParticipant.competition_id == comp_id)
        )
        p_map = {p.id: p.name for p in pr.scalars().all()}

        return [
            {"speaker": p_map.get(m.participant_id, "系统"), "content": m.content}
            for m in messages
        ]

    async def _get_leaderboard(self, comp_id: int) -> List[Dict]:
        result = await self.db.execute(
            select(LabParticipant).where(
                LabParticipant.competition_id == comp_id,
                LabParticipant.status == "active"
            ).order_by(LabParticipant.total_return.desc())
        )
        participants = list(result.scalars().all())
        return [
            {"rank": i + 1, "name": p.name, "return": round(p.total_return * 100, 2), "trades": p.total_trades}
            for i, p in enumerate(participants[:5])
        ]

    async def _get_today_trades(self, participant_id: int) -> List[LabCompTrade]:
        """获取今日交易记录（用于T+1检查）"""
        today = shanghai_now().date().isoformat()
        result = await self.db.execute(
            select(LabCompTrade).where(
                LabCompTrade.participant_id == participant_id,
            ).order_by(LabCompTrade.created_at.desc())
        )
        trades = result.scalars().all()
        return [t for t in trades if t.created_at and t.created_at.date().isoformat() == today]

    async def _get_last_round_feedback(self, participant_id: int) -> str:
        """获取上一轮的执行结果反馈给AI"""
        result = await self.db.execute(
            select(LabCompTrade)
            .where(LabCompTrade.participant_id == participant_id)
            .order_by(LabCompTrade.created_at.desc())
            .limit(5)
        )
        trades = result.scalars().all()
        if not trades:
            return "上一轮没有执行任何交易。"

        lines = []
        for t in trades:
            direction = "买入" if t.action == "buy" else "卖出"
            lines.append(f"  {direction}{t.symbol} {t.quantity}股@{t.price:.2f}，手续费{t.fee:.1f}元")
        return "上一轮成交结果:\n" + "\n".join(lines)

    async def _build_candidate_pool(
        self, competition: LabCompetition, participant_id: int
    ) -> List[str]:
        if competition.stock_pool:
            base_pool = competition.stock_pool
        else:
            try:
                pool_data = await self.dsm.get_sector_flow_top()
                base_pool = [s.get("symbol", "") for s in (pool_data or [])[:30]]
            except Exception:
                base_pool = []

        if not base_pool:
            base_pool = ["SH600519", "SZ000858", "SH601318", "SZ002594", "SH600036",
                         "SZ000333", "SH601888", "SZ002415", "SH600887", "SZ300750"]

        offset = participant_id % max(len(base_pool), 1)
        rotated = base_pool[offset:] + base_pool[:offset]
        return rotated[:20]

    async def _build_trading_context(
        self, participant: LabParticipant,
        positions: List[LabCompPosition],
        pool: List[str],
        competition: LabCompetition,
    ) -> Dict[str, Any]:
        quotes = {}
        for symbol in pool[:10]:
            try:
                q = await self.dsm.get_realtime([symbol])
                if q and symbol in q:
                    quotes[symbol] = q[symbol]
            except Exception:
                pass

        pos_symbols = [p.symbol for p in positions]
        if pos_symbols:
            pos_quotes = await self.dsm.get_realtime(pos_symbols)
        else:
            pos_quotes = {}

        for pos in positions:
            if pos.symbol in (pos_quotes or {}):
                pos.current_price = pos_quotes[pos.symbol].get("price", pos.current_price)
                pos.unrealized_pnl = (pos.current_price - pos.avg_cost) * pos.quantity

        return {
            "date": shanghai_now().date().isoformat(),
            "time": shanghai_now().strftime("%H:%M"),
            "capital": participant.current_capital,
            "initial_capital": participant.initial_capital,
            "total_return": participant.total_return,
            "total_trades": participant.total_trades,
            "positions": [
                {
                    "symbol": p.symbol, "name": p.name,
                    "quantity": p.quantity, "avg_cost": round(p.avg_cost, 2),
                    "current_price": round(p.current_price, 2),
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                }
                for p in positions
            ],
            "candidates": [
                {
                    "symbol": s, "name": quotes.get(s, {}).get("name", ""),
                    "price": quotes.get(s, {}).get("price", 0),
                    "change_pct": quotes.get(s, {}).get("change_pct", 0),
                    "volume": quotes.get(s, {}).get("volume", 0),
                }
                for s in pool[:10] if s in (quotes or {})
            ],
            "stock_pool_limit": competition.stock_pool is not None,
        }

    async def _fetch_realtime_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """批量获取实时行情"""
        result = {}
        for i in range(0, len(symbols), 10):
            batch = symbols[i:i+10]
            try:
                q = await self.dsm.get_realtime(batch)
                if q:
                    result.update(q)
            except Exception:
                pass
        return result

    # ==================== AI生成交易指令（只出意图） ====================

    async def _ai_generate_intents(
        self, participant: LabParticipant, context: Dict[str, Any], round_num: int
    ) -> List[Dict]:
        """
        AI只生成交易意图(intents)，不负责可行性验证。
        平台会负责：风控校验、资金计算、T+1检查、撮合。

        返回: [{"symbol": "600519", "action": "buy", "quantity": 600, "reason": "..."}]
        """
        system_prompt = participant.system_prompt or self._default_system_prompt()

        # 构建聊天上下文
        chat_context = ""
        if context.get("recent_chat"):
            chat_lines = []
            for msg in context["recent_chat"][-8:]:
                chat_lines.append(f"  {msg['speaker']}: {msg['content'][:200]}")
            chat_context = "\n最近群聊:\n" + "\n".join(chat_lines)

        # 排行榜上下文
        lb_context = ""
        if context.get("leaderboard"):
            lb_lines = []
            for item in context["leaderboard"][:5]:
                lb_lines.append(f"  #{item['rank']} {item['name']}: {item['return']:+.2f}% (交易{item['trades']}次)")
            lb_context = "\n当前排名:\n" + "\n".join(lb_lines)

        # 持仓详情
        pos_detail = ""
        for p in context.get("positions", []):
            pnl_pct = (p["current_price"] - p["avg_cost"]) / p["avg_cost"] * 100 if p["avg_cost"] > 0 else 0
            pos_detail += f"  {p['symbol']} {p['name'] or ''} {p['quantity']}股 成本{p['avg_cost']:.2f} 现价{p['current_price']:.2f} {'盈利' if p['unrealized_pnl'] >= 0 else '亏损'}{abs(pnl_pct):.1f}%\n"

        # 上一轮反馈
        feedback = context.get("last_round_feedback", "")

        topic = context.get("topic", "")

        prompt = f"""你正在一场AI炒股竞赛中，第 {round_num} 轮。

你的账户:
  可用资金: {context['capital']:.0f}元
  总收益: {context['total_return'] * 100:.2f}%
  总交易次数: {context['total_trades']}
  持仓: {'空仓' if not pos_detail else chr(10) + pos_detail}

市场数据:
{json.dumps(context['candidates'], ensure_ascii=False, indent=2)}
{chat_context}
{lb_context}
{chr(10) + feedback if feedback else ''}

{'本轮讨论话题: ' + topic if topic else ''}

现在轮到你做交易决策。

**重要：你只负责提出交易意图，平台会负责风控校验和实际撮合。**
- 你可以提出买入任意数量（平台会根据你的资金自动调整到可行的数量）
- 你可以提出卖出任意数量（平台会检查T+1和持仓限制）
- 不需要你计算资金够不够、手续费多少，平台全权处理

思考:
1. 基于市场数据，你认为接下来应该怎么操作？
2. 你的对手在做什么？从讨论中能得到什么信息？
3. 你愿意承担多大风险？

返回JSON:
{{
  "intents": [
    {{"symbol": "600519", "action": "buy", "quantity": 600, "reason": "你为什么想买这个"}}
  ],
  "analysis": "你的市场分析和交易逻辑（50-200字）",
  "summary": "一句话总结"
}}

规则:
- 只能操作候选池里的股票
- 如果你决定空仓不动，intents为空数组
- 你的分析要展现你对市场的独特理解"""

        start = time.time()
        try:
            llm = LLMClient(
                provider=participant.provider,
                api_base=participant.api_base,
                api_key=participant.api_key,
                model=participant.model_name,
            )
            result = await llm.complete_json(prompt, system_prompt)
            duration_ms = int((time.time() - start) * 1000)

            await record_lab_call(
                self.db, "lab_competition", participant.id, "trading_decision",
                participant.provider, participant.model_name or "",
                prompt=prompt, result=result or {}, duration_ms=duration_ms,
            )

            if result and "intents" in result:
                return result  # 返回完整结果，包含intents/analysis/summary
            elif result and "actions" in result:
                # 兼容旧格式
                return {"intents": result["actions"], "analysis": "", "summary": ""}
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await record_lab_call(
                self.db, "lab_competition", participant.id, "trading_decision",
                participant.provider, participant.model_name or "",
                prompt=prompt, status="failed", error=str(e), duration_ms=duration_ms,
            )
            logger.warning(f"AI intent generation failed for {participant.name}: {e}")

        return []

    # ==================== 手动触发（兼容旧接口） ====================

    async def run_participant_trading(
        self, participant_id: int, force: bool = False
    ) -> Dict[str, Any]:
        """为单个参赛者执行一轮交易（兼容旧的手动触发接口）"""
        result = await self.db.execute(
            select(LabParticipant).where(LabParticipant.id == participant_id)
        )
        participant = result.scalars().first()
        if not participant:
            return {"success": False, "error": "参赛者不存在"}
        if participant.status != "active":
            return {"success": False, "error": "参赛者已淘汰"}

        competition = await self._get_competition(participant.competition_id)
        if not competition or competition.status != "active":
            return {"success": False, "error": "比赛未在进行中"}
        if not force and not self._is_trading_time():
            return {"success": False, "error": "非交易时段（使用 force=True 可跳过）"}

        positions = await self._get_positions(participant_id)
        pool = await self._build_candidate_pool(competition, participant_id)
        context = await self._build_trading_context(participant, positions, pool, competition)

        # 获取今日已买入的股票（T+1）
        today_bought = set()
        today_trades = await self._get_today_trades(participant_id)
        for t in today_trades:
            if t.action == "buy":
                today_bought.add(t.symbol)

        # AI出指令
        ai_result = await self._ai_generate_intents(participant, context, 1)
        intents = ai_result.get("intents", [])

        # 批量获取行情
        all_symbols = set()
        for intent in intents:
            all_symbols.add(intent.get("symbol", ""))
        for pos in positions:
            all_symbols.add(pos.symbol)
        realtime_prices = await self._fetch_realtime_batch(list(all_symbols))

        # 校验 + 撮合 + 记账
        accounting = AccountingEngine(self.db)
        fills = []
        for intent in intents:
            ok, reason, order = OrderValidator.validate(
                intent, participant, positions, competition, realtime_prices, today_bought
            )
            if not ok:
                continue
            fill = SimulatedMatcher.match(order)
            await accounting.apply_trade(participant, fill, today_bought)
            fills.append(fill)

            trade = LabCompTrade(
                participant_id=participant_id,
                symbol=fill["symbol"],
                name=fill.get("stock_name", ""),
                action=fill["action"],
                quantity=fill["quantity"],
                price=fill["price"],
                amount=fill["amount"],
                fee=fill["fee"],
                reason=fill.get("reason", ""),
            )
            self.db.add(trade)

        await accounting.compute_account_stats(participant, participant.competition_id)
        await self._smart_chat_post(participant, ai_result, fills, 1)

        return {
            "success": True,
            "trades": len(fills),
            "intents": len(intents),
            "rejected": len(intents) - len(fills),
        }

    async def run_chat_only(self, participant_id: int) -> Dict[str, Any]:
        """仅让AI发表市场分析（不交易）"""
        result = await self.db.execute(
            select(LabParticipant).where(LabParticipant.id == participant_id)
        )
        participant = result.scalars().first()
        if not participant or participant.status != "active":
            return {"success": False, "error": "参赛者不存在或已淘汰"}

        competition = await self._get_competition(participant.competition_id)
        if not competition or competition.status != "active":
            return {"success": False, "error": "比赛未在进行中"}

        positions = await self._get_positions(participant_id)
        pool = await self._build_candidate_pool(competition, participant_id)
        context = await self._build_trading_context(participant, positions, pool, competition)

        # 生成分析（不生成交易指令）
        intents = await self._ai_generate_intents(participant, context, 1)
        await self._chat_post(participant, intents, [])

        return {"success": True, "trades": 0}

    # ==================== AI发言 ====================

    async def _ai_discuss(
        self, participant: LabParticipant, topic: str,
        recent_chat: List[Dict], context: Dict[str, Any],
    ) -> Optional[str]:
        system_prompt = (participant.system_prompt or self._default_system_prompt()).replace(
            "用JSON格式回复。", ""
        ) + "\n\n重要：请用纯文本回复，不要用JSON格式。直接说内容。"

        # 只看别人说的话，过滤掉自己的
        others_chat = ""
        for msg in recent_chat:
            if msg['speaker'] != participant.name:
                others_chat += f"  {msg['speaker']}: {msg['content'][:150]}\n"

        pos_info = "空仓" if not context.get("positions") else json.dumps(
            context["positions"][:3], ensure_ascii=False
        )

        prompt = f"""话题: {topic}

你的持仓: {pos_info}
你的资金: {context['capital']:.0f}元
你的收益: {context['total_return'] * 100:.2f}%

其他选手发言:
{others_chat if others_chat else '（暂时没有其他人的发言）'}

你想说什么就说什么，比如：
- 对盘面的观察
- 对别人观点的看法
- 自己的操作计划
- 或者什么都不说也可以

只输出你想说的话，5-200字，不要客套。"""

        try:
            llm = LLMClient(
                provider=participant.provider,
                api_base=participant.api_base,
                api_key=participant.api_key,
                model=participant.model_name,
            )
            result = await llm.complete(prompt, system_prompt)
            if result and len(result.strip()) >= 5:
                return result.strip()[:200]
        except Exception as e:
            logger.warning(f"AI discuss failed for {participant.name}: {e}")

        return None

    # ==================== 群聊 ====================

    async def _generate_discussion_topic(
        self, comp_id: int, round_num: int, participants: list
    ) -> str:
        try:
            pool_data = await self.dsm.get_sector_flow_top()
            hot_stocks = [s.get("name", s.get("symbol", "")) for s in (pool_data or [])[:5]]
        except Exception:
            hot_stocks = ["大盘走势", "板块轮动", "短线机会"]

        try:
            overview = await self.dsm.get_market_overview()
            sh_change = overview.get("sh_change_pct", 0) if overview else 0
            market_mood = "上涨" if sh_change > 0.5 else ("下跌" if sh_change < -0.5 else "震荡")
        except Exception:
            market_mood = "震荡"

        topics = [
            f"盘面分析：今日{market_mood}，{hot_stocks[0] if hot_stocks else '主线板块'}如何看？",
            f"策略复盘：当前持仓表现如何？下一步怎么调整？",
            f"风控思考：市场{market_mood}，仓位和止损怎么控制？",
            f"机会扫描：{hot_stocks[0] if hot_stocks else '热点题材'}还有参与价值吗？",
            f"情绪判断：市场情绪{market_mood}，短线节奏怎么把握？",
            f"持仓检视：当前组合是否需要优化？理由是什么？",
        ]
        idx = (round_num - 1) % len(topics)
        return topics[idx]

    async def _post_chat(self, comp_id: int, participant: LabParticipant, content: str, msg_type: str = "discussion"):
        msg = LabChatMessage(
            competition_id=comp_id,
            participant_id=participant.id,
            content=content,
            message_type=msg_type,
        )
        self.db.add(msg)
        await self.db.commit()

    async def _smart_chat_post(
        self, participant: LabParticipant, ai_result: Dict, fills: List[Dict], round_num: int
    ):
        """AI复盘发言：基于实际执行结果和AI分析"""
        # 优先使用AI自己的分析
        ai_analysis = ai_result.get("analysis", "")
        ai_summary = ai_result.get("summary", "")

        trade_summary = ""
        for f in fills:
            direction = "买入" if f["action"] == "buy" else "卖出"
            trade_summary += f"{direction}{f['symbol']} {f['quantity']}股@{f['price']:.2f}。"

        if ai_analysis:
            # 有AI分析就用AI分析，附带成交结果
            if fills:
                content = f"{ai_analysis}\n\n实际成交: {trade_summary}"
            else:
                content = f"{ai_analysis}\n\n本轮无成交。"
        elif fills:
            content = f"执行了{len(fills)}笔交易。{trade_summary}"
        else:
            content = "本轮没有合适的交易机会，选择观望。"

        msg = LabChatMessage(
            competition_id=participant.competition_id,
            participant_id=participant.id,
            content=content,
            message_type="analysis",
        )
        self.db.add(msg)
        await self.db.commit()

    async def _chat_post(self, participant: LabParticipant, intents: List[Dict], fills: List[Dict]):
        """基础发言"""
        trade_summary = ""
        for f in fills:
            direction = "买入" if f["action"] == "buy" else "卖出"
            trade_summary += f"{direction}{f['symbol']} {f['quantity']}股@{f['price']:.2f}。"

        content = ""
        if fills:
            content = f"执行了{len(fills)}笔交易。{trade_summary}"
        else:
            content = "本轮观望。"

        msg = LabChatMessage(
            competition_id=participant.competition_id,
            participant_id=participant.id,
            content=content,
            message_type="analysis",
        )
        self.db.add(msg)
        await self.db.commit()

    async def post_system_message(self, competition_id: int, content: str):
        msg = LabChatMessage(
            competition_id=competition_id,
            participant_id=None,
            content=content,
            message_type="system",
        )
        self.db.add(msg)
        await self.db.commit()

    # ==================== 事件系统 ====================

    async def detect_and_record_events(
        self, comp_id: int, participants: List[LabParticipant], round_num: int
    ) -> List[Dict]:
        """检测一轮交易后的事件：涨停/跌停/止损/排名变化/重大回撤"""
        events = []
        prev_leaderboard = await self._get_leaderboard(comp_id)

        for p in participants:
            positions = await self._get_positions(p.id)
            for pos in positions:
                # 涨停/跌停/止损检测 — 用当日涨跌幅而非浮盈
                if pos.current_price > 0 and pos.open_price > 0:
                    day_change = (pos.current_price - pos.open_price) / pos.open_price * 100
                    if day_change >= 9.5:
                        event = await self._record_event(
                            comp_id, p.id, "limit_up", pos.symbol,
                            f"{p.name} 持仓 {pos.symbol} 涨停！当日涨 {day_change:.1f}%",
                            {"symbol": pos.symbol, "change_pct": round(day_change, 2), "name": pos.name}
                        )
                        events.append(event)
                    elif day_change <= -9.5:
                        event = await self._record_event(
                            comp_id, p.id, "limit_down", pos.symbol,
                            f"{p.name} 持仓 {pos.symbol} 跌停！当日跌 {day_change:.1f}%",
                            {"symbol": pos.symbol, "change_pct": round(day_change, 2), "name": pos.name}
                        )
                        events.append(event)
                    elif day_change <= -8:
                        # 止损检测（当日亏损超过8%，且未触发跌停）
                        event = await self._record_event(
                            comp_id, p.id, "stop_loss", pos.symbol,
                            f"{p.name} 持仓 {pos.symbol} 触发止损线！当日跌 {day_change:.1f}%",
                            {"symbol": pos.symbol, "change_pct": round(day_change, 2), "name": pos.name}
                        )
                        events.append(event)

            # 重大回撤检测
            if p.total_return <= -0.10:
                event = await self._record_event(
                    comp_id, p.id, "major_drawdown", None,
                    f"{p.name} 总资产回撤达 {p.total_return*100:.1f}%！",
                    {"total_return": round(p.total_return * 100, 2)}
                )
                events.append(event)

        # 排名变化检测
        if prev_leaderboard:
            prev_ranks = {item["name"]: item["rank"] for item in prev_leaderboard}
            current_ranks = {p.name: i+1 for i, p in enumerate(
                sorted(participants, key=lambda x: x.total_return, reverse=True)
            )}
            for name, current_rank in current_ranks.items():
                prev_rank = prev_ranks.get(name)
                if prev_rank and prev_rank - current_rank >= 2:
                    event = await self._record_event(
                        comp_id, None, "rank_change", None,
                        f"{name} 排名上升 {prev_rank - current_rank} 位，当前第 {current_rank} 名",
                        {"from_rank": prev_rank, "to_rank": current_rank}
                    )
                    events.append(event)

        return events

    async def _record_event(
        self, comp_id: int, participant_id: Optional[int],
        event_type: str, symbol: Optional[str], title: str,
        detail: Optional[Dict] = None
    ) -> Dict:
        """记录一条事件"""
        event = LabCompEvent(
            competition_id=comp_id,
            participant_id=participant_id,
            event_type=event_type,
            symbol=symbol,
            title=title,
            detail=detail or {},
        )
        self.db.add(event)
        await self.db.commit()
        return {"type": event_type, "title": title, "detail": detail}

    async def generate_event_chat(
        self, comp_id: int, events: List[Dict], participants: List[LabParticipant]
    ):
        """根据事件生成AI讨论"""
        if not events:
            return

        for event in events[:2]:  # 每轮最多触发2个事件讨论
            event_title = event["title"]
            # 随机选1-2个AI对事件发表看法
            responders = random.sample(participants, min(2, len(participants)))
            for p in responders:
                try:
                    system_prompt = (p.system_prompt or self._default_system_prompt()).replace(
                        "用JSON格式回复。", ""
                    ) + "\n\n重要：请用纯文本回复，不要用JSON格式，不要包含任何JSON结构。直接说人话。"
                    prompt = f"""比赛刚刚发生了这个事件：
{event_title}

你想说什么就说什么，5-200字。"""
                    llm = LLMClient(
                        provider=p.provider,
                        api_base=p.api_base,
                        api_key=p.api_key,
                        model=p.model_name,
                    )
                    result = await llm.complete(prompt, system_prompt)
                    if result and len(result.strip()) >= 5:
                        await self._post_chat(comp_id, p, result.strip()[:200], "event")
                except Exception as e:
                    logger.warning(f"Event chat failed for {p.name}: {e}")

    # ==================== AI讨论回应 ====================

    async def _ai_discuss_reply(
        self, participant: LabParticipant, topic: str,
        discussion: List[Dict], context: Dict[str, Any],
        other_remark: str,
    ) -> Optional[str]:
        """AI讨论回应：参考别人的观点"""
        system_prompt = (participant.system_prompt or self._default_system_prompt()).replace(
            "用JSON格式回复。", ""
        ) + "\n\n重要：请用纯文本回复，不要用JSON格式。直接说内容。"

        pos_info = "空仓" if not context.get("positions") else json.dumps(
            context["positions"][:3], ensure_ascii=False
        )

        prompt = f"""话题: {topic}

有人说了：{other_remark}

你的持仓: {pos_info}
你的资金: {context['capital']:.0f}元
你的收益: {context['total_return'] * 100:.2f}%

你想说什么就说什么，5-200字，不要客套。"""
        try:
            llm = LLMClient(
                provider=participant.provider,
                api_base=participant.api_base,
                api_key=participant.api_key,
                model=participant.model_name,
            )
            result = await llm.complete(prompt, system_prompt)
            if result and len(result.strip()) >= 5:
                return result.strip()[:200]
        except Exception as e:
            logger.warning(f"AI debate failed for {participant.name}: {e}")
        return None

    # ==================== 工具方法 ====================

    async def _get_competition(self, comp_id: int) -> Optional[LabCompetition]:
        result = await self.db.execute(
            select(LabCompetition).where(LabCompetition.id == comp_id)
        )
        return result.scalars().first()

    def _is_trading_time(self) -> bool:
        now = shanghai_now()
        if now.weekday() >= 5:
            return False
        current_time = now.strftime("%H:%M")
        for start, end in self.TRADING_SESSIONS:
            if start <= current_time <= end:
                return True
        return False

    def _default_system_prompt(self) -> str:
        return """你是一个参加A股实盘模拟竞赛的AI交易员。

你的唯一目标：赢下这场比赛，收益率超过其他选手。

你是独立思考的交易者。你有自己的投资哲学、分析框架和风险偏好。你可以是价值投资者、技术派、趋势跟踪者、逆势交易者、短线客——随便你，但你要有一套自己的逻辑，并且能清晰地阐述你的决策理由。

不要依赖任何预设规则。你的每一个买卖决策都必须基于你对市场的独立判断。如果你认为应该空仓，那就空仓。如果你认为应该满仓搏一把，那就说出你的理由。

市场不会等你，你需要在信息不完整的情况下做出决策。

**重要：你只需要提出交易意图（想买/卖什么、多少股），平台会负责：**
- 资金够不够（不够会自动调整数量）
- T+1限制（今天买的明天才能卖）
- 仓位限制（单只不超过总资金20%）
- 手续费计算
- 实际撮合成交

所以你不需要操心"我钱够不够"这种问题，大胆说出你想做什么。

A股基本约束（不是策略，是物理限制）:
- 买入必须100股的整数倍
- 你只能卖出手里已有的股票
- 你只能买入候选池里的股票
- T+1，今天买的明天才能卖

用JSON格式回复。"""
