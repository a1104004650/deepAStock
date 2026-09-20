"""AI炒股比赛引擎"""
import json
import time
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laboratory import (
    LabCompetition, LabParticipant, LabCompPosition,
    LabCompTrade, LabChatMessage, LabLeaderboard
)
from app.core.agent.llm_client import LLMClient
from app.core.datasource.manager import DataSourceManager
from app.core.lab.call_logger import record_lab_call
from app.utils.logger import logger


class CompetitionEngine:
    """比赛引擎: 管理AI参赛者的交易决策和互动"""

    TRADING_FEE = 0.0003  # 默认万三手续费

    TRADING_SESSIONS = [
        ("09:30", "11:30"),
        ("13:00", "15:00"),
    ]

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    # ==================== 交易执行 ====================

    async def run_participant_trading(self, participant_id: int) -> Dict[str, Any]:
        """为单个参赛者执行一轮交易决策"""
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

        if not self._is_trading_time():
            return {"success": False, "error": "非交易时段"}

        # 获取持仓
        positions = await self._get_positions(participant_id)

        # 获取候选股票池
        pool = await self._build_candidate_pool(competition, participant_id)

        # 构建AI决策上下文
        context = await self._build_trading_context(participant, positions, pool, competition)

        # AI决策
        decision = await self._ai_decide(participant, context)

        # 执行交易
        trades = await self._execute_decisions(participant, positions, decision, competition)

        # 更新账户
        await self._update_account(participant, positions)

        # AI群聊发言
        await self._chat_post(participant, decision, trades)

        return {
            "success": True,
            "trades": len(trades),
            "decision": decision.get("summary", ""),
        }

    async def _get_competition(self, comp_id: int) -> Optional[LabCompetition]:
        result = await self.db.execute(
            select(LabCompetition).where(LabCompetition.id == comp_id)
        )
        return result.scalars().first()

    async def _get_positions(self, participant_id: int) -> List[LabCompPosition]:
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.quantity > 0
            )
        )
        return list(result.scalars().all())

    async def _build_candidate_pool(
        self, competition: LabCompetition, participant_id: int
    ) -> List[str]:
        """构建候选股票池, 防扎堆: 按participant_id偏移"""
        if competition.stock_pool:
            base_pool = competition.stock_pool
        else:
            # 从涨停板+板块龙头获取
            pool_data = await self.dsm.get_sector_flow_top()
            base_pool = [s.get("symbol", "") for s in (pool_data or [])[:30]]

        # 按participant_id偏移, 避免所有AI买一样的
        offset = participant_id % max(len(base_pool), 1)
        rotated = base_pool[offset:] + base_pool[:offset]
        return rotated[:20]  # 最多20只候选

    async def _build_trading_context(
        self, participant: LabParticipant,
        positions: List[LabCompPosition],
        pool: List[str],
        competition: LabCompetition,
    ) -> Dict[str, Any]:
        """构建AI决策上下文"""
        # 获取候选股行情
        quotes = {}
        for symbol in pool[:10]:
            try:
                q = await self.dsm.get_realtime([symbol])
                if q and symbol in q:
                    quotes[symbol] = q[symbol]
            except Exception:
                pass

        # 持仓行情
        pos_symbols = [p.symbol for p in positions]
        if pos_symbols:
            pos_quotes = await self.dsm.get_realtime(pos_symbols)
        else:
            pos_quotes = {}

        # 更新持仓现价
        for pos in positions:
            if pos.symbol in (pos_quotes or {}):
                pos.current_price = pos_quotes[pos.symbol].get("price", pos.current_price)
                pos.unrealized_pnl = (pos.current_price - pos.avg_cost) * pos.quantity

        return {
            "date": date.today().isoformat(),
            "capital": participant.current_capital,
            "initial_capital": participant.initial_capital,
            "total_return": participant.total_return,
            "positions": [
                {
                    "symbol": p.symbol, "name": p.name,
                    "quantity": p.quantity, "avg_cost": p.avg_cost,
                    "current_price": p.current_price, "pnl": p.unrealized_pnl,
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

    async def _ai_decide(
        self, participant: LabParticipant, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """AI做出交易决策"""
        system_prompt = participant.system_prompt or self._default_system_prompt()
        prompt = f"""当前市场数据和你的账户状态:

资金: {context['capital']:.0f}元
总收益: {context['total_return']:.2f}%

持仓:
{json.dumps(context['positions'], ensure_ascii=False, indent=2) if context['positions'] else '空仓'}

候选股票:
{json.dumps(context['candidates'], ensure_ascii=False, indent=2)}

请分析并给出交易决策。返回JSON格式:
{{
  "actions": [
    {{"symbol": "600519", "action": "buy", "quantity": 100, "reason": "理由", "confidence": 0.8}}
  ],
  "analysis": "今日市场分析...",
  "summary": "一句话总结"
}}

规则:
- 买入数量必须是100的整数倍
- 单只股票不超过总资金的20%
- 只能交易候选股票池中的股票
- 卖出只能卖持仓中已有的
- 不买ST股票"""

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

            # 记录调用
            await record_lab_call(
                self.db, "lab_competition", participant.id, "trading_decision",
                participant.provider, participant.model_name or "",
                prompt=prompt, result=result or {}, duration_ms=duration_ms,
            )

            if result and "actions" in result:
                return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await record_lab_call(
                self.db, "lab_competition", participant.id, "trading_decision",
                participant.provider, participant.model_name or "",
                prompt=prompt, status="failed", error=str(e), duration_ms=duration_ms,
            )
            logger.warning(f"AI decision failed for participant {participant.id}: {e}")

        # Fallback: 本地简单策略
        return self._local_decision(context)

    def _local_decision(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """本地fallback策略"""
        actions = []
        capital = context["capital"]
        positions = context["positions"]
        candidates = context["candidates"]

        # 卖出: 止损5%或止盈15%
        for pos in positions:
            if pos["avg_cost"] > 0:
                pnl_pct = (pos["current_price"] - pos["avg_cost"]) / pos["avg_cost"]
                if pnl_pct <= -0.05 or pnl_pct >= 0.15:
                    actions.append({
                        "symbol": pos["symbol"],
                        "action": "sell",
                        "quantity": pos["quantity"],
                        "reason": f"止损{pnl_pct:.1%}" if pnl_pct < 0 else f"止盈{pnl_pct:.1%}",
                        "confidence": 0.7,
                    })

        # 买入: 选候选中涨幅最大且未持有的
        held = {p["symbol"] for p in positions}
        for c in candidates:
            if c["symbol"] not in held and c.get("change_pct", 0) > 0:
                buy_amount = min(capital * 0.2, capital * 0.9)
                if buy_amount > c.get("price", 0) * 100:
                    qty = int(buy_amount / c["price"] / 100) * 100
                    if qty >= 100:
                        actions.append({
                            "symbol": c["symbol"],
                            "action": "buy",
                            "quantity": qty,
                            "reason": "本地策略: 涨幅领先",
                            "confidence": 0.5,
                        })
                        capital -= qty * c["price"]
                break

        return {
            "actions": actions,
            "analysis": "本地策略分析",
            "summary": f"本地策略: {len(actions)}个交易决策",
        }

    async def _execute_decisions(
        self, participant: LabParticipant,
        positions: List[LabCompPosition],
        decision: Dict[str, Any],
        competition: LabCompetition,
    ) -> List[LabCompTrade]:
        """执行交易决策"""
        trades = []
        trading_fee = competition.trading_fee or self.TRADING_FEE
        max_pos_pct = competition.max_position_pct or 0.2
        max_positions = competition.max_positions or 5

        for action in decision.get("actions", []):
            symbol = action.get("symbol", "")
            act = action.get("action", "")
            qty = action.get("quantity", 0)
            reason = action.get("reason", "")
            confidence = action.get("confidence", 0.5)

            if not symbol or not act or qty <= 0:
                continue

            # 获取实时价格
            try:
                q = await self.dsm.get_realtime([symbol])
                price = q.get(symbol, {}).get("price", 0) if q else 0
            except Exception:
                continue

            if price <= 0:
                continue

            amount = qty * price
            fee = amount * trading_fee

            if act == "buy":
                if amount + fee > participant.current_capital:
                    continue
                if participant.current_capital * max_pos_pct < amount:
                    continue  # 超过最大仓位限制
                # 检查持仓数量限制
                if len(positions) >= max_positions:
                    continue

                # 执行买入
                participant.current_capital -= (amount + fee)
                await self._add_or_update_position(
                    participant.id, symbol, "", qty, price, "buy"
                )

            elif act == "sell":
                # 查找持仓
                pos = next((p for p in positions if p.symbol == symbol), None)
                if not pos or pos.quantity < qty:
                    continue

                # 执行卖出
                participant.current_capital += (amount - fee)
                await self._add_or_update_position(
                    participant.id, symbol, "", -qty, price, "sell"
                )

            else:
                continue

            # 记录交易
            trade = LabCompTrade(
                participant_id=participant.id,
                symbol=symbol,
                name="",
                action=act,
                quantity=qty,
                price=price,
                amount=amount,
                fee=fee,
                reason=reason,
                confidence=confidence,
            )
            self.db.add(trade)
            trades.append(trade)
            participant.total_trades += 1

        await self.db.commit()
        return trades

    async def _add_or_update_position(
        self, participant_id: int, symbol: str, name: str,
        qty_delta: int, price: float, action: str
    ):
        """更新持仓"""
        result = await self.db.execute(
            select(LabCompPosition).where(
                LabCompPosition.participant_id == participant_id,
                LabCompPosition.symbol == symbol
            )
        )
        pos = result.scalars().first()

        if action == "buy":
            if pos:
                total_cost = pos.avg_cost * pos.quantity + price * qty_delta
                pos.quantity += qty_delta
                pos.avg_cost = total_cost / pos.quantity if pos.quantity > 0 else 0
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.avg_cost) * pos.quantity
            else:
                pos = LabCompPosition(
                    participant_id=participant_id,
                    symbol=symbol,
                    name=name,
                    quantity=qty_delta,
                    avg_cost=price,
                    current_price=price,
                    unrealized_pnl=0,
                )
                self.db.add(pos)
        elif action == "sell":
            if pos:
                pos.quantity += qty_delta  # qty_delta is negative
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.avg_cost) * pos.quantity
                if pos.quantity <= 0:
                    await self.db.delete(pos)

    async def _update_account(self, participant: LabParticipant, positions: List[LabCompPosition]):
        """更新参赛者账户统计"""
        market_value = sum(p.current_price * p.quantity for p in positions)
        total_assets = participant.current_capital + market_value
        participant.total_return = (total_assets - participant.initial_capital) / participant.initial_capital

        # 更新持仓现价
        for pos in positions:
            pos.unrealized_pnl = (pos.current_price - pos.avg_cost) * pos.quantity

        await self.db.commit()

    # ==================== 群聊 ====================

    async def _chat_post(self, participant: LabParticipant, decision: Dict, trades: list):
        """AI在群聊中发言"""
        content = decision.get("analysis", "") or decision.get("summary", "")
        if not content:
            return

        trade_summary = ""
        for t in trades:
            trade_summary += f"{'买入' if t.action == 'buy' else '卖出'}{t.symbol} {t.quantity}股@{t.price:.2f}。"

        msg_content = f"[{participant.name}] {content}"
        if trade_summary:
            msg_content += f"\n交易: {trade_summary}"

        msg = LabChatMessage(
            competition_id=participant.competition_id,
            participant_id=participant.id,
            content=msg_content,
            message_type="analysis",
        )
        self.db.add(msg)
        await self.db.commit()

    async def post_system_message(self, competition_id: int, content: str):
        """系统消息"""
        msg = LabChatMessage(
            competition_id=competition_id,
            participant_id=None,
            content=content,
            message_type="system",
        )
        self.db.add(msg)
        await self.db.commit()

    # ==================== 排行榜 ====================

    async def update_leaderboard(self, competition_id: int):
        """更新排行榜"""
        result = await self.db.execute(
            select(LabParticipant).where(
                LabParticipant.competition_id == competition_id,
                LabParticipant.status == "active"
            )
        )
        participants = list(result.scalars().all())

        # 按收益率排序
        participants.sort(key=lambda p: p.total_return, reverse=True)

        today = date.today().isoformat()
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

    # ==================== 工具方法 ====================

    def _is_trading_time(self) -> bool:
        """判断是否为交易时段"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        for start, end in self.TRADING_SESSIONS:
            if start <= current_time <= end:
                return True
        return False

    def _default_system_prompt(self) -> str:
        return """你是一个A股模拟交易AI选手。你需要根据市场数据做出买卖决策。

交易规则:
- 只在交易日和交易时段操作
- T+1: 今天买的明天才能卖
- 不买ST/*ST股票
- 买入数量必须是100的整数倍
- 单只股票不超过总资金20%

分析框架:
1. 技术面: K线形态、均线系统、MACD、RSI
2. 资金面: 主力资金流向
3. 基本面: 估值、业绩
4. 情绪面: 市场情绪、板块轮动

请用JSON格式回复交易决策。"""
