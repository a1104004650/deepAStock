"""智能体基类与统一输出模型"""
from datetime import date
import json
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.core.agent.llm_client import LLMClient, LLMNotConfigured
from app.utils.logger import logger


class AgentContext(BaseModel):
    """智能体运行上下文"""
    date: str = Field(default_factory=lambda: date.today().isoformat())
    symbol: Optional[str] = None
    market_data: Any = {}
    financial_data: Any = {}
    czsc_result: Any = {}
    money_flow: Any = {}
    sector_info: Any = {}
    sentiment: Any = {}
    news: Any = []
    historical_trades: Any = []
    user_rules: Any = {}


class AgentResult(BaseModel):
    agent_type: str
    summary: str = ""
    signals: list = []
    watch_list: list = []
    risk_level: str = "low"
    confidence: float = 0.5
    reasoning: str = ""
    raw_output: str = ""
    score: float | None = None
    recommendation: str = ""
    evidence: list = []
    risks: list = []


class BaseAgent:
    agent_type: str = "custom"
    default_model: str = "deepseek-chat"
    default_prompt: str = "你是一个专业的股票分析助手。"

    def __init__(self, config: dict):
        self.config = config or {}
        self.llm = LLMClient(
            api_base=self.config.get("api_base"),
            api_key=self.config.get("api_key"),
            model=self.config.get("model_name", self.default_model),
            temperature=float(self.config.get("temperature", 0.3) or 0.3),
            max_tokens=int(self.config.get("max_tokens", 4000) or 4000),
            provider=self.config.get("provider", ""),
        )

    async def _run(self, prompt: str, system_prompt: str = "") -> str:
        return await self.llm.complete(prompt, system_prompt)

    async def _run_json(self, prompt: str, system_prompt: str = "") -> dict:
        return await self.llm.complete_json(prompt, system_prompt)

    def _build_system_prompt(self) -> str:
        base = self.config.get("system_prompt") or self.default_prompt
        rules = self.config.get("rules", {}) or {}
        return f"""{base}

# 输出原则
1. 永远基于提供的数据说话，不凭空猜测
2. 给出明确信号（买/卖/观望），不要模棱两可
3. 每个结论都要有依据
4. 风险永远放在第一位

# 输出格式（严格JSON，不要多余文字）
{{
    "summary": "一段话总结",
    "signals": [{{"type": "buy/sell/watch", "condition": "触发条件", "price": 0}}],
    "watch_list": [{{"symbol": "...", "reason": "...", "entry": 0, "stop_loss": 0}}],
    "risk_level": "low/medium/high",
    "confidence": 0.0-1.0,
    "reasoning": "推理过程"
}}"""

    @staticmethod
    def _compact(data) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, default=str)[:4000]
        except Exception:
            return str(data)

    async def _predict(self, ctx: AgentContext, prompt: str, task: str = "analyze_stock") -> AgentResult:
        try:
            data = await self._run_json(prompt, self._build_system_prompt())
            data = data or {}
            return AgentResult(
                agent_type=self.agent_type,
                summary=data.get("summary", ""),
                signals=data.get("signals", []),
                watch_list=data.get("watch_list", []),
                risk_level=data.get("risk_level", "low"),
                confidence=float(data.get("confidence", 0.5) or 0.5),
                reasoning=data.get("reasoning", ""),
                raw_output=json.dumps(data, ensure_ascii=False, default=str),
                score=float(data["score"]) if data.get("score") is not None else None,
                recommendation=data.get("recommendation", data.get("rating", "")),
                evidence=data.get("evidence", []),
                risks=data.get("risks", data.get("risk_factors", [])),
            )
        except Exception as e:
            logger.warning(f"agent {self.agent_type} predict failed: {e}")
            if isinstance(e, LLMNotConfigured):
                return self._local_analysis(ctx, task)
            return AgentResult(agent_type=self.agent_type,
                               summary=f"AI分析暂不可用（{e}）",
                               reasoning=str(e), confidence=0.2)

    # ---------- 本地启发式分析（无 AI API 时降级，保证平台始终可用） ----------
    def _local_analysis(self, ctx: AgentContext, task: str) -> AgentResult:
        if task == "daily_replay":
            return self._local_replay(ctx)
        return self._local_stock(ctx)

    def _local_stock(self, ctx: AgentContext) -> AgentResult:
        lines = []
        signals = []
        bullish = 0
        bearish = 0
        risk = "low"

        # 1. 基本面
        fin = ctx.financial_data if isinstance(ctx.financial_data, list) else []
        if fin:
            last = fin[0]
            revenue_yoy = last.get("revenue_yoy")
            net_profit_yoy = last.get("net_profit_yoy")
            roe = last.get("roe")
            gross = last.get("gross_margin")
            debt = last.get("debt_ratio")
            rep = last.get("report_date", "")
            parts = [f"最新财报({rep})"]
            if revenue_yoy is not None:
                parts.append(f"营收同比{revenue_yoy:+.1f}%")
                bullish += 1 if revenue_yoy > 0 else 0
                bearish += 1 if revenue_yoy < 0 else 0
            if net_profit_yoy is not None:
                parts.append(f"净利同比{net_profit_yoy:+.1f}%")
                bullish += 1 if net_profit_yoy > 0 else 0
                bearish += 1 if net_profit_yoy < 0 else 0
            if roe is not None:
                parts.append(f"ROE {roe:.2f}%")
                if roe > 10:
                    bullish += 1
            if gross is not None:
                parts.append(f"毛利率{gross:.1f}%")
            if debt is not None:
                parts.append(f"负债率{debt:.1f}%")
                if debt > 70:
                    bearish += 1
                    risk = "high"
            lines.append("，".join(parts))

        # 2. 技术形态
        forms = ctx.market_data.get("forms", [])
        if forms:
            b = [f for f in forms if f.get("level") == "bullish"]
            be = [f for f in forms if f.get("level") == "bearish"]
            bullish += len(b)
            bearish += len(be)
            lines.append(f"技术形态：{len(b)}多头 / {len(be)}空头")
            for f in (b + be)[:4]:
                signals.append({"type": "watch", "condition": f.get("desc", ""), "price": 0})

        # 3. 缠论信号
        cz = ctx.czsc_result if isinstance(ctx.czsc_result, dict) else {}
        fx = cz.get("fx_list", []) if isinstance(cz.get("fx_list"), list) else []
        if len(fx) >= 2:
            recent = fx[-2:]
            direction = "顶分型（偏空）" if recent[-1].get("mark") == "g" else "底分型（偏多）"
            lines.append(f"缠论：最近一笔为{recent[-1].get('type', direction)}（{recent[-1].get('price')}）")
            if recent[-1].get("mark") == "d":
                bullish += 1
            else:
                bearish += 1

        # 4. 资金流
        flow = ctx.money_flow if isinstance(ctx.money_flow, list) else []
        if flow:
            mains = [f.get("main_net", 0) for f in flow[:5]]
            main_sum = sum(mains)
            trend = "资金净流入" if main_sum > 0 else "资金净流出"
            lines.append(f"资金流：主力近5日{trend}（{self._fmt_money(main_sum)}）")
            bullish += 1 if main_sum > 0 else 0
            bearish += 1 if main_sum < 0 else 0

        # 5. 情绪
        sent = ctx.sentiment if isinstance(ctx.sentiment, dict) else {}
        pos = float(sent.get("positive_score", 0) or 0)
        neg = float(sent.get("negative_score", 0) or 0)
        if pos or neg:
            lines.append(f"情绪：正面{pos:.2f} / 负面{neg:.2f}")
            if pos > neg:
                bullish += 1
            elif neg > pos:
                bearish += 1

        net = bullish - bearish
        if net >= 3:
            view, confidence, risk = "偏多", 0.75, "low"
        elif net <= -2:
            view, confidence, risk = "偏空", 0.7, "high"
        elif net >= 1:
            view, confidence, risk = "中性偏多", 0.55, "medium"
        else:
            view, confidence, risk = "中性偏弱", 0.5, "medium"

        watch = []
        if net >= 1:
            watch.append({"symbol": ctx.symbol, "reason": "本地启发式看多", "entry": 0, "stop_loss": 0})

        summary = (f"【本地启发式{view}】（未配置 AI API，系统自动分析生成，仅供参考）\n" + "\n".join(lines))
        return AgentResult(
            agent_type=self.agent_type,
            summary=summary,
            signals=signals,
            watch_list=watch,
            risk_level=risk,
            confidence=confidence,
            reasoning=summary,
        )

    def _local_replay(self, ctx: AgentContext) -> AgentResult:
        md = ctx.market_data or {}
        lines = []
        signals = []

        sector_flow = md.get("sector_flow", []) or []
        if sector_flow:
            top = sorted(sector_flow, key=lambda x: float(x.get("net_inflow", 0) or 0), reverse=True)[:3]
            names = "、".join(str(s.get("name", "?")) for s in top)
            lines.append(f"主力资金流入板块：{names}")
            signals.append({"type": "watch", "condition": f"关注 {names} 板块的持续性", "price": 0})

        limit_up = md.get("limit_up", []) or []
        if limit_up:
            lines.append(f"今日涨停 {len(limit_up)} 只")
        ladder = md.get("limit_ladder", {}) or {}
        floor = ladder.get("ladder", {}) if isinstance(ladder, dict) else {}
        if floor:
            top_days = sorted([int(k) for k in floor.keys()], reverse=True)[:1]
            if top_days:
                lines.append(f"最高连板 {top_days[0]} 板")
                for s in (floor.get(str(top_days[0]), []) or [])[:3]:
                    signals.append({"type": "watch", "condition": f"高标 {s.get('name', s.get('symbol'))} 观察是否打开空间", "price": 0})

        dist = md.get("distribution", {}) or {}
        if dist:
            lines.append(f"涨跌家数：上涨{dist.get('up_count', '-')} / 下跌{dist.get('down_count', '-')}")

        dragon = md.get("dragon_tiger", []) or []
        if dragon:
            lines.append(f"龙虎榜 {len(dragon)} 只上榜")

        summary = "【本地启发式复盘】（未配置 AI API，系统自动生成，仅供参考）\n" + "\n".join(lines) if lines else \
            "【本地启发式复盘】暂无足够市场数据，建议稍后重试。"
        return AgentResult(agent_type=self.agent_type, summary=summary, signals=signals,
                           risk_level="low", confidence=0.5, reasoning=summary)

    @staticmethod
    def _fmt_money(v):
        v = float(v or 0)
        abs_v = abs(v)
        if abs_v >= 1e8:
            return f"{v / 1e8:.2f}亿"
        if abs_v >= 1e4:
            return f"{v / 1e4:.1f}万"
        return f"{v:.0f}"

    async def fallback_result(self, message: str) -> AgentResult:
        return AgentResult(agent_type=self.agent_type, summary=message, reasoning=message, confidence=0.3)
