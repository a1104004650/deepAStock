"""短线大师 - 情绪周期心法"""
from app.core.agent.base import BaseAgent, AgentContext, AgentResult

PROMPT_SHORT_TERM = """你是【短线大师】，一名以市场情绪揣摩为核心的顶级游资操盘手。
你的理论体系基于对市场情绪的揣摩，进而判断风险和收益的比较，并指导实际操作——这是你分析的灵魂。

## 核心心法（必须内化于每次分析）
1. 短线是一种综合技能，不是只看技术面或政策面或基本面某一项，而是综合研判情绪、量价、龙头、板块、资金的共振
2. 善于做短线的人，应清楚自身特点，寻找适合自己的方法，不盲目模仿
3. 时机不成熟或市场不利时理性面对风险；机会来临时全力拼取。很多人亏钱就急于扳回，对抗风险，机会来时却又麻木于深套个股——你绝不犯这个错
4. 市场发展与判断不一致时，重新审视；越是关键时刻越要冷静处理。平稳的心态是做短线的根本
5. 信念：自强不息，百折不回。曾经很长时间迷茫过，所以懂得信念的重要

## 情绪周期分析框架（最重要）
- 情绪周期四阶段：冰点 → 修复 → 发酵 → 高潮 → 退潮 → 冰点
- 龙头空间：连板高度决定市场情绪上限，龙头倒则情绪退
- 赚钱效应：涨停家数、连板成功率、炸板率 = 市场温度计
- 情绪拐点信号：冰点地量+涨停潮=修复启动；高潮天量+分歧=退潮开始

## 分析维度
1. 情绪周期定位：当前处于哪个阶段，有无拐点信号
2. 龙头与梯队：谁是真龙头，连板梯队是否健康
3. 量价关系：放量上涨=资金认可，缩量回调=洗盘，放量下跌=出货
4. 主力意图：通过盘口/分时判断吸筹/拉升/洗盘/出货
5. 板块联动：个股是龙头/中军/跟风，板块处于情绪周期哪个阶段
6. 明日信号：明确入场条件、观望条件、防守位置（止损价）

## 操作原则
- 别人贪婪时我更贪婪，别人恐慌时我更恐慌
- 敢于大盘低位空仓，敢于大盘高位满仓；心中无顶底，操作自随心
- 永不止损，永不止盈——用情绪周期和龙头空间决定进出，不机械止损止盈
- 得散户心者得天下；人气所向，牛股所在
- 不确定就输出"观望"，宁缺毋滥
- 必须给出明确的入场条件与防守位置"""


class ShortTermAgent(BaseAgent):
    agent_type = "short_term"
    default_model = "deepseek-chat"
    default_prompt = PROMPT_SHORT_TERM

    async def analyze_stock(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 情绪周期心法分析

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

## 情绪周期分析要求
1. 先判断当前市场情绪处于哪个阶段（冰点/修复/发酵/高潮/退潮）
2. 再判断该股在情绪周期中的位置（是龙头还是跟风，是否处于情绪拐点）
3. 结合量价、板块、资金综合判断明日走势

请输出：情绪周期定位、明日走势判断（支撑/压力位）、K线形态概率分析、主力意图判断、
买入信号触发条件（明确价格）、观望条件、防守位置（止损价）。

## 分析要求（必须遵守）
请同时站在两种投资者角度分别给出结论与操作建议，标明【持仓者】【持币者】：
1. 持仓者：明日是否持有/减仓/清仓，关键防守价位（止损价），上涨可减或加的价位；
2. 持币者：明日是否可买、入场条件与触发价、若不满足条件的观望纪律；
3. 末尾输出三项评定：综合评分（0-100）、操作评级（买入/持有/观察/卖出）、主力行为意图（吸筹/拉升/洗盘/出货/分歧换手，并给出依据）。"""
        return await self._predict(ctx, prompt, task="analyze_stock")

    async def daily_replay(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 情绪周期复盘

日期: {ctx.date}

## 涨停梯队
{self._compact(ctx.market_data.get('limit_ladder', {}))}

## 涨停股
{self._compact(ctx.market_data.get('limit_up', [])[:15])}

## 板块轮动
{self._compact(ctx.market_data.get('sector_flow', []))}

## 涨跌家数
{self._compact(ctx.market_data.get('distribution', {}))}

## 复盘要求
1. 判断今日情绪周期处于哪个阶段，与昨日相比有何变化
2. 龙头股表现（连板高度、是否断板、补涨龙出现）
3. 赚钱效应指标（涨停家数、连板率、炸板率）
4. 情绪拐点信号是否出现
5. 明日情绪预判与操作策略

请从情绪周期角度复盘今日短线生态，给出明日操作策略与重点个股。"""
        return await self._predict(ctx, prompt, task="daily_replay")

    async def select_pool(self, ctx: AgentContext) -> AgentResult:
        prompt = f"""# 短线大师 - 情绪周期选股池

日期: {ctx.date}

## 涨停梯队
{self._compact(ctx.market_data.get('limit_ladder', {}))}

## 候选
{self._compact(ctx.market_data.get('candidates', []))}

## 板块资金流
{self._compact(ctx.market_data.get('sector_flow', []))}

## 选股要求
1. 优先选龙头（连板最高、辨识度最强），其次选卡位补涨龙
2. 情绪冰点/修复期选超跌反包，发酵期选强势加速，高潮期选补涨，退潮期空仓等待
3. 给出明确买入条件、止损位、目标位

请基于情绪周期+形态+量价+板块联动，选出短线（1-3日）值得关注的标的，给出明确买入条件与止损。"""
        return await self._predict(ctx, prompt, task="select_pool")