"""投研智能体 - 基本面深度研究 + 行业景气 + 价值发现"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_RESEARCH = """你是【投研智能体】，一名专业的主线逻辑研究员，擅长从基本面、行业景气度、资金流向、估值等角度判断个股和板块中长期的配置价值。

## 核心理念
1. 好公司+好价格=好投资，但好公司≠好股票，价格决定安全边际
2. 基本面是地基，技术面是信号，资金面是催化剂——三者共振才有大机会
3. 研究的目的是发现预期差：市场预期 vs 实际价值之间的差距
4. 风险控制第一：再好的逻辑也可能被黑天鹅打碎，仓位管理是生存之本

## 分析框架
1. 基本面：营收/净利润增速、毛利率、ROE、现金流质量、负债率
2. 行业地位：市占率、护城河、行业景气周期、政策/技术催化
3. 资金面：主力净流入趋势、机构持仓变化、北向资金动向
4. 估值：PE/PB 历史分位、PEG、股息率、与同行对比
5. 风险：财务异常、减持、商誉减值、行业下行、政策风险
6. 催化剂：业绩拐点、政策利好、行业事件、技术突破

你的任务：给出一只个股或一个板块的中期（1-3个月）逻辑结论，寻找预期差最大的机会。"""


class ResearchAgent(BaseAgent):
    agent_type = "research"
    default_model = "deepseek-chat"
    default_prompt = PROMPT_RESEARCH

    async def analyze_stock(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 个股深度研究

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

## 研究要求
1. 核心逻辑：这家公司靠什么赚钱，护城河在哪里，未来1-3个月有什么催化剂
2. 估值分析：当前估值在历史什么位置，与同行相比如何，是否存在预期差
3. 行业景气：行业处于什么周期阶段，政策/技术面有什么催化
4. 风险提示：最大的风险是什么，如何控制
5. 目标价推导：基于估值和景气度推导合理价格区间

请输出：公司核心逻辑、行业景气度判断、估值分析、预期差分析、中期（1-3个月）支撑/压力区间、关注信号与风险提示。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，标明【持仓者】【持币者】：
1. 持仓者：继续持有/减仓/加仓/止损 的明确建议、持有逻辑与关键价位、风险点；
2. 持币者：现在能否买入、具体入场条件与价格、买入后须承担的风险；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 主线逻辑复盘

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 涨停/强势股
{self._compact(ctx.market_data.get('limit_up', [])[:15])}

## 复盘要求
1. 今日主线板块是什么，为什么成为主线（政策/业绩/事件驱动）
2. 资金流向特征：主力资金流向哪些板块，为什么
3. 行业轮动方向：哪些板块在启动，哪些在退潮
4. 中期逻辑：哪些板块/个股有中期配置价值，预期差在哪里
5. 明日重点关注：主线板块的龙头标的与催化事件

请复盘今日主线板块、资金流向特征，判断行业轮动方向，给出明日重点关注的板块与龙头标的。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 投研智能体 - 中期选股池

日期: {ctx.date}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 候选数据
{self._compact(ctx.market_data.get('candidates', []))}

## 选股要求
1. 优先选基本面扎实、估值合理、行业景气向上的标的
2. 关注预期差：市场预期低但实际逻辑在改善的标的
3. 催化剂明确：近期有业绩拐点、政策利好、行业事件等催化
4. 风险可控：估值不贵、负债不高、现金流好

请基于基本面+资金+行业景气度+估值，选出3-8只中期（1-3个月）值得关注的核心标的，标注入场逻辑与风险。"""
        return await self._predict(ctx, prompt, task="select_pool")