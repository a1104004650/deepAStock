"""AI投研团队引擎"""
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.laboratory import (
    LabResearchTask, LabAnalyst, LabAnalystReport, LabResearchReport
)
from app.core.agent.llm_client import LLMClient
from app.core.datasource.manager import DataSourceManager
from app.core.lab.call_logger import record_lab_call
from app.utils.logger import logger
from app.utils import shanghai_now


class ResearchTeamEngine:
    """投研团队引擎: 多AI协作分析"""

    ANALYST_PROMPTS = {
        "value": """你是巴菲特风格的价值投资大师。你的分析框架:
1. 护城河: 品牌、网络效应、转换成本、规模优势、特许经营权
2. 估值: PE、PB、DCF内在价值、安全边际
3. 管理层: 过往业绩、资本配置能力、诚信度
4. 长期价值: 行业趋势、增长空间、可持续性

你的原则:
- 只投资你理解的生意
- 寻找有持久竞争优势的公司
- 在价格低于内在价值时买入
- 长期持有, 复利增长
- 别人贪婪时恐惧, 别人恐惧时贪婪

请用JSON格式返回分析结果。""",

        "game": """你是游资短线交易高手。你的分析框架:
1. 资金动向: 龙虎榜、主力净流入、大单异动
2. 情绪面: 涨停板情绪、连板高度、炸板率
3. 题材: 当前热点题材、政策催化
4. 技术: 强势股形态、突破位、量价配合

你的原则:
- 追强不追高, 找龙头不找杂毛
- 情绪周期是核心, 冰点买入沸点卖出
- 严格止损, 不扛单
- 快进快出, 不恋战
- 只做确定性最高的那一笔

请用JSON格式返回分析结果。""",

        "tech": """你是技术分析专家。你的分析框架:
1. 趋势: 均线系统(MA5/10/20/60/120/250), 趋势方向
2. 形态: 头肩顶底、三角形、旗形、楔形
3. 指标: MACD金叉死叉、RSI超买超卖、KDJ、布林带
4. 量价: 成交量验证、量价背离、放量突破

你的原则:
- 趋势是你的朋友, 顺势而为
- 关键支撑位和压力位是核心
- 多指标共振提高胜率
- 量价配合验证趋势强度
- 严格按信号交易, 不主观臆断

请用JSON格式返回分析结果。""",

        "quant": """你是量化分析专家。你的分析框架:
1. 因子分析: 估值因子、成长因子、动量因子、质量因子
2. 风险评估: 波动率、VaR、最大回撤、夏普比率
3. 统计分析: 相关性、回归分析、蒙特卡洛模拟
4. 量化信号: 多因子打分、统计套利信号

你的原则:
- 数据驱动, 摒弃主观判断
- 风险控制是第一要务
- 分散投资降低非系统性风险
- 回测验证策略有效性
- 关注风险调整后收益

请用JSON格式返回分析结果。""",

        "overall": """你是首席投资官, 负责综合所有分析师的观点并给出最终建议。

你需要:
1. 阅读各分析师的报告
2. 识别共识点和分歧点
3. 权衡各方观点的合理性
4. 给出综合评分和建议
5. 明确指出关键风险

评分标准(各维度0-10分):
- 基本面: 财务健康、盈利能力、成长性
- 技术面: 趋势方向、形态信号、量价配合
- 情绪面: 市场情绪、资金动向、题材热度

综合建议: 强烈推荐/推荐/中性/谨慎/回避

请用JSON格式返回综合报告。""",
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    async def run_research(self, task_id: int) -> Dict[str, Any]:
        """执行完整研究流程"""
        result = await self.db.execute(
            select(LabResearchTask).where(LabResearchTask.id == task_id)
        )
        task = result.scalars().first()
        if not task:
            return {"success": False, "error": "任务不存在"}

        if task.status == "running":
            return {"success": False, "error": "任务正在执行中"}

        task.status = "running"
        task.stage = "research"
        task.progress = 10
        await self.db.commit()

        try:
            # 获取股票数据
            stock_data = await self._fetch_stock_data(task.symbol)

            # Stage 1: 独立研究
            task.stage = "research"
            task.progress = 20
            await self.db.commit()

            analysts = await self._get_active_analysts()
            research_reports = await self._stage1_research(task, analysts, stock_data)

            # Stage 2: 交叉质询
            task.stage = "discuss"
            task.progress = 50
            await self.db.commit()

            discussion_reports = await self._stage2_discuss(task, analysts, research_reports, stock_data)

            # Stage 3: 综合报告
            task.stage = "report"
            task.progress = 80
            await self.db.commit()

            final_report = await self._stage3_report(task, analysts, research_reports, discussion_reports, stock_data)

            # 完成
            task.status = "completed"
            task.stage = "done"
            task.progress = 100
            task.completed_at = shanghai_now()
            await self.db.commit()

            return {"success": True, "report_id": final_report.id if final_report else None}

        except Exception as e:
            task.status = "failed"
            task.stage = "done"
            await self.db.commit()
            logger.error(f"Research task {task_id} failed: {e}")
            return {"success": False, "error": str(e)}

    async def _fetch_stock_data(self, symbol: str) -> Dict[str, Any]:
        """获取股票基础数据"""
        data = {}

        # 实时行情
        try:
            realtime = await self.dsm.get_realtime([symbol])
            if realtime and symbol in realtime:
                data["realtime"] = realtime[symbol]
        except Exception:
            data["realtime"] = {}

        # K线数据
        try:
            klines = await self.dsm.get_klines(symbol, "day")
            data["klines"] = klines[-20:] if klines else []
        except Exception:
            data["klines"] = []

        # 资金流
        try:
            flow = await self.dsm.get_money_flow(symbol)
            data["money_flow"] = flow
        except Exception:
            data["money_flow"] = {}

        # 板块信息
        try:
            sector = await self.dsm.get_stock_sector(symbol)
            data["sector"] = sector
        except Exception:
            data["sector"] = {}

        return data

    async def _get_active_analysts(self) -> List[LabAnalyst]:
        """获取活跃的分析师"""
        result = await self.db.execute(
            select(LabAnalyst)
            .where(LabAnalyst.is_active == True)
            .order_by(LabAnalyst.sort_order)
        )
        return list(result.scalars().all())

    async def _stage1_research(
        self, task: LabResearchTask,
        analysts: List[LabAnalyst],
        stock_data: Dict
    ) -> Dict[int, Dict]:
        """Stage 1: 各分析师独立研究"""
        reports = {}
        stock_context = self._format_stock_context(task, stock_data)

        for i, analyst in enumerate(analysts):
            try:
                report_content = await self._analyst_analyze(analyst, stock_context, task.symbol)
                report = LabAnalystReport(
                    task_id=task.id,
                    analyst_id=analyst.id,
                    stage="research",
                    content=report_content,
                )
                self.db.add(report)
                reports[analyst.id] = report_content
                task.progress = 20 + int(30 * (i + 1) / len(analysts))
                await self.db.commit()
            except Exception as e:
                logger.warning(f"Analyst {analyst.name} failed: {e}")

        return reports

    async def _stage2_discuss(
        self, task: LabResearchTask,
        analysts: List[LabAnalyst],
        research_reports: Dict[int, Dict],
        stock_data: Dict
    ) -> Dict[int, Dict]:
        """Stage 2: 交叉质询"""
        discussions = {}
        for analyst in analysts:
            if analyst.id not in research_reports:
                continue

            try:
                # 构建其他分析师的报告摘要
                others_summary = []
                for aid, content in research_reports.items():
                    if aid != analyst.id:
                        a_name = next((a.name for a in analysts if a.id == aid), "未知")
                        others_summary.append(f"[{a_name}]: {content.get('view', '')}")

                discussion_context = f"""你之前的分析:
{json.dumps(research_reports[analyst.id], ensure_ascii=False)}

其他分析师的观点:
{chr(10).join(others_summary)}

请对其他分析师的观点进行评论, 指出你同意或不同意的地方, 并说明理由。
返回JSON格式:
{{
  "comments": "你的评论内容",
  "adjusted_view": "是否调整你的观点及原因",
  "key_disagreements": ["分歧点1", "分歧点2"]
}}"""

                system_prompt = analyst.system_prompt or self.ANALYST_PROMPTS.get(analyst.role, "")
                start = time.time()
                try:
                    llm = LLMClient(
                        provider=analyst.provider,
                        api_base=analyst.api_base,
                        api_key=analyst.api_key,
                        model=analyst.model_name,
                    )
                    result = await llm.complete_json(discussion_context, system_prompt)
                    duration_ms = int((time.time() - start) * 1000)

                    await record_lab_call(
                        self.db, "lab_research", analyst.id, "cross_discuss",
                        analyst.provider, analyst.model_name or "",
                        prompt=discussion_context, result=result or {}, duration_ms=duration_ms,
                    )

                    if result:
                        discussions[analyst.id] = result
                        report = LabAnalystReport(
                            task_id=task.id,
                            analyst_id=analyst.id,
                            stage="discuss",
                            content=result,
                        )
                        self.db.add(report)
                        await self.db.commit()
                except Exception as e:
                    duration_ms = int((time.time() - start) * 1000)
                    await record_lab_call(
                        self.db, "lab_research", analyst.id, "cross_discuss",
                        analyst.provider, analyst.model_name or "",
                        prompt=discussion_context, status="failed", error=str(e), duration_ms=duration_ms,
                    )
                    logger.warning(f"Analyst {analyst.name} discuss failed: {e}")

            except Exception as e:
                logger.warning(f"Analyst {analyst.name} discuss failed: {e}")
        return discussions

    async def _stage3_report(
        self, task: LabResearchTask,
        analysts: List[LabAnalyst],
        research_reports: Dict[int, Dict],
        discussion_reports: Dict[int, Dict],
        stock_data: Dict
    ) -> Optional[LabResearchReport]:
        """Stage 3: 生成综合报告"""
        # 收集所有报告
        all_reports = []
        for analyst in analysts:
            if analyst.id in research_reports:
                content = research_reports[analyst.id]
                all_reports.append({
                    "analyst": analyst.name,
                    "role": analyst.role,
                    "view": content.get("view", ""),
                    "score": content.get("score", 5),
                    "reasoning": content.get("reasoning", ""),
                    "concerns": content.get("concerns", []),
                    "discussion": discussion_reports.get(analyst.id, {}),
                })

        # 找综合分析师(overall角色)
        overall_analyst = next((a for a in analysts if a.role == "overall"), None)
        if not overall_analyst:
            overall_analyst = analysts[0] if analysts else None

        if not overall_analyst:
            return None

        stock_context = self._format_stock_context(task, stock_data)
        prompt = f"""请综合以下分析师的原始报告和交叉质询结果，生成最终研究报告。分歧必须来自实际质询内容，不得凭空构造；每条结论必须给出可核验的数据依据（evidence）；必须给出风险反方（bear_case，即反驳多头/看多逻辑的论据）；最后给出结构化最终决策（final_decision）。

股票: {task.symbol} ({task.stock_name or ''})

各分析师报告:
{json.dumps(all_reports, ensure_ascii=False, indent=2)}

市场数据:
{stock_context[:2000]}

请返回JSON格式的综合报告:
{{
  "fundamental_score": 7.5,
  "technical_score": 6.0,
  "sentiment_score": 5.5,
  "overall_score": 6.3,
  "recommendation": "强烈推荐/推荐/中性/谨慎/回避",
  "target_price_low": 100.0,
  "target_price_high": 120.0,
  "risk_factors": ["风险1", "风险2"],
  "consensus": ["共识点1", "共识点2"],
  "divergences": ["分歧点1"],
  "evidence": [{{"point": "结论", "basis": "数据/事实依据", "source": "分析师名或行情字段"}}],
  "bear_case": [{{"argument": "反方论据", "strength": "强/中/弱", "trigger": "何种情况下成立"}}],
  "final_decision": {{
    "action": "买入/加仓/持有/减仓/观望/清仓",
    "horizon": "短线/波段/中期",
    "entry_zone": "建议介入区间或条件",
    "stop_loss": "失效条件/止损位",
    "position_hint": "轻仓/半仓/重仓/空仓",
    "confidence": 0.6,
    "rationale": "一句话决策理由"
  }},
  "full_report": "完整的Markdown格式报告..."
}}"""

        try:
            llm = LLMClient(
                provider=overall_analyst.provider,
                api_base=overall_analyst.api_base,
                api_key=overall_analyst.api_key,
                model=overall_analyst.model_name,
            )

            start = time.time()
            result = await llm.complete_json(
                prompt,
                overall_analyst.system_prompt or self.ANALYST_PROMPTS.get("overall", "")
            )
            duration_ms = int((time.time() - start) * 1000)

            await record_lab_call(
                self.db, "lab_research", overall_analyst.id, "final_report",
                overall_analyst.provider, overall_analyst.model_name or "",
                prompt=prompt, result=result or {}, duration_ms=duration_ms,
            )

            if result:
                report = LabResearchReport(
                    task_id=task.id,
                    fundamental_score=result.get("fundamental_score", 0),
                    technical_score=result.get("technical_score", 0),
                    sentiment_score=result.get("sentiment_score", 0),
                    overall_score=result.get("overall_score", 0),
                    recommendation=result.get("recommendation", "中性"),
                    target_price_low=result.get("target_price_low"),
                    target_price_high=result.get("target_price_high"),
                    risk_factors=result.get("risk_factors", []),
                    consensus=result.get("consensus", []),
                    divergences=result.get("divergences", []),
                    evidence=result.get("evidence", []),
                    bear_case=result.get("bear_case", []),
                    final_decision=result.get("final_decision") or {},
                    full_report=result.get("full_report", ""),
                )
                self.db.add(report)
                await self.db.commit()
                return report

        except Exception as e:
            logger.warning(f"Final report generation failed: {e}")

        return None

    async def _analyst_analyze(
        self, analyst: LabAnalyst, stock_context: str, symbol: str
    ) -> Dict[str, Any]:
        """单个分析师进行分析"""
        system_prompt = analyst.system_prompt or self.ANALYST_PROMPTS.get(analyst.role, "")
        prompt = f"""请分析股票 {symbol}:

{stock_context}

请返回JSON格式分析结果:
{{
  "view": "你的投资观点(一段话)",
  "score": 7.5,
  "reasoning": "详细推理过程",
  "concerns": ["风险点1", "风险点2"],
  "suggestion": "买入/持有/观望/卖出"
}}"""

        start = time.time()
        try:
            llm = LLMClient(
                provider=analyst.provider,
                api_base=analyst.api_base,
                api_key=analyst.api_key,
                model=analyst.model_name,
            )
            result = await llm.complete_json(prompt, system_prompt)
            duration_ms = int((time.time() - start) * 1000)

            await record_lab_call(
                self.db, "lab_research", analyst.id, "analyst_research",
                analyst.provider, analyst.model_name or "",
                prompt=prompt, result=result or {}, duration_ms=duration_ms,
            )

            return result or {"view": "分析失败", "score": 5, "reasoning": "", "concerns": []}
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await record_lab_call(
                self.db, "lab_research", analyst.id, "analyst_research",
                analyst.provider, analyst.model_name or "",
                prompt=prompt, status="failed", error=str(e), duration_ms=duration_ms,
            )
            return {"view": "分析失败", "score": 5, "reasoning": "", "concerns": []}

    def _format_stock_context(self, task: LabResearchTask, stock_data: Dict) -> str:
        """格式化股票数据为文本"""
        lines = [f"股票: {task.symbol} ({task.stock_name or ''})"]

        rt = stock_data.get("realtime", {})
        if rt:
            lines.append(f"现价: {rt.get('price', '-')}, 涨跌: {rt.get('change_pct', '-')}%")
            lines.append(f"成交额: {rt.get('volume', '-')}")
            lines.append(f"换手率: {rt.get('turnover_rate', '-')}%")

        klines = stock_data.get("klines", [])
        if klines:
            recent = klines[-5:]
            lines.append("近5日K线:")
            for k in recent:
                lines.append(f"  {k.get('date', '')}: 开{k.get('open',0):.2f} 高{k.get('high',0):.2f} 低{k.get('low',0):.2f} 收{k.get('close',0):.2f}")

        flow = stock_data.get("money_flow", {})
        if flow:
            lines.append(f"主力净流入: {flow.get('main_net', '-')}")

        sector = stock_data.get("sector", {})
        if sector:
            lines.append(f"板块: {sector.get('industry', '-')}")

        return "\n".join(lines)
