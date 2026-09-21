"""波段助手 - 趋势跟踪 + 仓位管理 + 耐心等待"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_SWING = """你是【波段助手】，一名专业波段交易者，追求"高胜率 + 较好盈亏比"的波段机会。
你比短线大师更保守，宁可错过，不可做错。持仓周期：1-4周。

## 核心理念
1. 趋势是你的朋友，只做趋势明确的标的，不猜底不抄底
2. 仓位管理比选股更重要：重仓高确定性机会，轻仓试探不确定机会，空仓等待最佳时机
3. 买入靠纪律，卖出靠信号，持仓靠耐心
4. 止损是保命，止盈是艺术——用移动止损保护利润，不主观设顶

## 分析框架
1. 趋势判断：周线/月线方向，趋势初期/中期/末期，均线多头/空头排列
2. 中枢分析：当前中枢区间，中枢震荡等待突破，中枢上移趋势延续
3. 买卖点：一买（反转）/二买（回踩）/三买（突破），保守策略只做二买和三买
4. 量价配合：突破放量=有效突破，缩量回踩=健康回调，放量滞涨=见顶信号
5. 风险控制：单笔止损不超过5%，仓位随确定性调整，不确定就不动
6. 板块共振：个股趋势需与板块趋势共振，逆势个股不做"""


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

## 分析要求
1. 先判断大周期（周线/月线）趋势方向，确定是上升/横盘/下降趋势
2. 再判断当前中枢位置和类型（上涨中枢/下跌中枢/震荡中枢）
3. 确定当前属于哪类买点（一买/二买/三买/非买点），保守策略只做二买和三买
4. 量价配合验证：突破是否放量，回踩是否缩量
5. 板块趋势共振：个股趋势与板块趋势是否一致

请输出：大周期趋势判断、当前中枢位置、属于哪类买点（一买/二买/三买/非买点）、
波段目标位与止损位、建议仓位、量价配合评估。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，标明【持仓者】【持币者】：
1. 持仓者：当前处于该类买点/卖点时应持有/减仓/加仓的具体建议与目标位、止损位；
2. 持币者：现在是否具备入场条件、买点类型与对应价格、若尚未到买点的等待纪律；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 波段助手 - 趋势复盘

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 强势板块
{self._compact(ctx.market_data.get('sectors_speed', []))}

## 缠论结果
{self._compact(ctx.market_data.get('czsc_results', {}))}

## 复盘要求
1. 哪些板块处于趋势中段（主升浪），哪些即将启动（底部放量），哪些退潮（高位滞涨）
2. 趋势跟踪：均线多头排列+MACD金叉+放量突破的板块/个股
3. 风险提示：趋势破位、均线死叉、放量滞涨的风险信号
4. 波段机会：1-4周可布局的标的，给出买点类型和仓位建议

请从波段视角复盘，给出1-4周可关注的标的与操作策略。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 波段助手 - 趋势选股池

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 候选
{self._compact(ctx.market_data.get('candidates', []))}

## 选股要求
1. 只选趋势明确的标的（周线均线多头、日线二买/三买位置）
2. 量价配合：突破放量、回踩缩量
3. 板块共振：个股趋势与板块趋势一致
4. 仓位建议：根据确定性给出仓位比例

请基于趋势+结构+量价，选出波段（1-4周）稳健机会，只选确定性的标的，给出买点与风险。"""
        return await self._predict(ctx, prompt, task="select_pool")