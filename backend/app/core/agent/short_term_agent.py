"""短线大师 - 游资视角 + 概率事件"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_SHORT_TERM = """你是【短线大师】，一名顶级游资操盘手，从短线概率角度分析个股的明日走势。
核心目标："越确定的事情，明日上涨概率越大"。

分析维度：
1. K线形态：放量突破、缩量回踩、首板、二波、反包等概率形态
2. 量价关系：量是价的先行指标，放量上涨=资金认可，缩量回调=洗盘，放量下跌=出货
3. 主力意图：通过盘口/分时判断吸筹/拉升/洗盘/出货
4. 板块联动：个股是龙头/中军/跟风，板块情绪周期（启动/发酵/高潮/退潮）
5. 明日信号：明确入场条件、观望条件、防守位置（止损价）

特别注意：
- 不确定就输出"观望"，宁缺毋滥
- 必须给出明确的入场条件与防守位置"""


class ShortTermAgent(BaseAgent):
    agent_type = "short_term"
    default_model = "deepseek-chat"
    default_prompt = PROMPT_SHORT_TERM

    async def analyze_stock(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 游资思维 + 概率博弈

标的: {ctx.symbol}

## 缠论/技术分析
{self._compact(ctx.czsc_result)}

## 资金流
{self._compact(ctx.money_flow)}

## 板块信息
{self._compact(ctx.sector_info)}

## 技术形态
{self._compact(ctx.market_data.get('forms', []))}

## 涨停梯队
{self._compact(ctx.market_data.get('limit_ladder', {}))}

请输出：明日走势判断（支撑/压力位）、K线形态概率分析、主力意图判断、
买入信号触发条件（明确价格）、观望条件、防守位置（止损价）。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，标明【持仓者】【持币者】：
1. 持仓者：明日是否持有/减仓/清仓，关键防守价位（止损价），上涨可减或加的价位；
2. 持币者：明日是否可买、入场条件与触发价、若不满足条件的观望纪律；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 每日复盘

日期: {ctx.date}

## 涨停梯队
{self._compact(ctx.market_data.get('limit_ladder', {}))}

## 涨停股
{self._compact(ctx.market_data.get('limit_up', [])[:15])}

## 板块轮动
{self._compact(ctx.market_data.get('sector_flow', []))}

## 涨跌家数
{self._compact(ctx.market_data.get('distribution', {}))}

请复盘今日短线生态（情绪周期、龙头空间、赚钱效应），给出明日操作策略与重点个股。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 选股池

日期: {ctx.date}

## 涨停梯队
{self._compact(ctx.market_data.get('limit_ladder', {}))}

## 候选
{self._compact(ctx.market_data.get('candidates', []))}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

请基于形态+量价+板块联动，选出短线（1-3日）值得关注的标的，给出明确买入条件与止损。"""
        return await self._predict(ctx, prompt, task="select_pool")