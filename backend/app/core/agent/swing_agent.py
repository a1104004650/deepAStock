"""波段助手 - 趋势 + 中枢 + 保守"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_SWING = """你是【波段助手】，一名专业波段交易者，追求"高胜率 + 较好盈亏比"的波段机会。
你比短线大师更保守，宁可错过，不可做错。持仓周期：1-4周。

分析维度：
1. 趋势判断：周线/月线方向，趋势初期/中期/末期
2. 中枢分析：当前中枢区间，中枢震荡等待突破，中枢上移趋势延续
3. 买卖点：一买（反转）/二买（回踩）/三买（突破），保守策略只做二买和三买
4. 风险控制：单笔止损不超过5%，仓位随确定性调整，不确定就不动"""


class SwingAgent(BaseAgent):
    agent_type = "swing"
    default_model = "deepseek-chat"
    default_prompt = PROMPT_SWING

    async def analyze_stock(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 波段助手 - 趋势 + 中枢 + 耐心

标的: {ctx.symbol}

## 缠论多周期
{self._compact(ctx.czsc_result)}

## 资金流
{self._compact(ctx.money_flow)}

## 板块信息
{self._compact(ctx.sector_info)}

请输出：大周期趋势判断、当前中枢位置、属于哪类买点（一买/二买/三买/非买点）、
波段目标位与止损位、建议仓位。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，标明【持仓者】【持币者】：
1. 持仓者：当前处于该类买点/卖点时应持有/减仓/加仓的具体建议与目标位、止损位；
2. 持币者：现在是否具备入场条件、买点类型与对应价格、若尚未到买点的等待纪律；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 波段助手 - 每日复盘

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 强势板块
{self._compact(ctx.market_data.get('sectors_speed', []))}

## 缠论结果
{self._compact(ctx.market_data.get('czsc_results', {}))}

请从波段视角复盘：哪些板块处于趋势中段、哪些即将启动、哪些退潮，给出1-4周可关注的标的。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 波段助手 - 选股池

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 候选
{self._compact(ctx.market_data.get('candidates', []))}

请基于趋势+结构，选出波段（1-4周）稳健机会，只选确定性的标的，给出买点与风险。"""
        return await self._predict(ctx, prompt, task="select_pool")