"""投研智能体 - 基本面 + 行业 + 资金"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_RESEARCH = """你是【投研智能体】，一名专业的主线逻辑研究员。
擅长从基本面、行业景气度、资金流向、估值等角度判断个股和板块中长期的配置价值。

分析框架：
1. 基本面：营收/净利润增速、毛利率、ROE、现金流质量、负债率
2. 行业地位：市占率、护城河、行业景气周期、政策/技术催化
3. 资金面：主力净流入趋势、机构持仓
4. 估值：PE/PB 历史分位、股息率
5. 风险：财务异常、减持、商誉、行业下行

你的任务：给出一只个股或一个板块的中期（1-3个月）逻辑结论。"""


class ResearchAgent(BaseAgent):
    agent_type = "research"
    default_model = "deepseek-chat"
    default_prompt = PROMPT_RESEARCH

    async def analyze_stock(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 个股基本面分析

标的: {ctx.symbol}

## 财务数据
{self._compact(ctx.financial_data)}

## 资金流
{self._compact(ctx.money_flow)}

## 所属板块/行业
{self._compact(ctx.sector_info)}

## 情绪数据
{self._compact(ctx.sentiment)}

## 新闻
{self._compact(ctx.news[:8])}

请输出：公司核心逻辑、行业景气度判断、估值分析、中期（1-3个月）支撑/压力区间、关注信号与风险提示。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，眼睛清晰地标志【持仓者】【持币者】：
1. 持仓者（我已持有该股）：继续持有/减仓/加仓/止损 的明确建议、持有逻辑与关键价位、风险点；
2. 持币者（我空仓持有现金）：现在能否买入、具体入场条件与价格、买入后须承担的风险；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 每日复盘

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 涨停/强势股
{self._compact(ctx.market_data.get('limit_up', [])[:15])}

请复盘今日主线板块、资金流向特征，判断行业轮动方向，给出明日重点关注的板块与龙头标的。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 选股池

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 候选数据
{self._compact(ctx.market_data.get('candidates', []))}

请基于基本面+资金+行业景气度，选出3-8只中期值得关注的核心标的，标注入场逻辑与风险。"""
        return await self._predict(ctx, prompt, task="select_pool")