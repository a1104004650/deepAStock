"""实验室数据模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, Boolean, Numeric, ForeignKey, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.utils import shanghai_now


# ==================== AI炒股比赛 ====================

class LabCompetition(Base):
    """比赛表"""
    __tablename__ = "lab_competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="setup")  # setup/active/paused/finished
    stock_pool: Mapped[dict] = mapped_column(JSON, nullable=True)  # null=不限, ["600519","000858"]
    initial_capital: Mapped[float] = mapped_column(Float, default=100000.0)
    max_position_pct: Mapped[float] = mapped_column(Float, default=0.2)  # 单只最大仓位比例
    max_positions: Mapped[int] = mapped_column(Integer, default=5)  # 最大持仓数
    allow_short: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否允许做空
    trading_fee: Mapped[float] = mapped_column(Float, default=0.0003)  # 手续费率
    auto_trade: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否自动交易
    trade_interval_min: Mapped[int] = mapped_column(Integer, default=30)  # 自动交易间隔(分钟)
    start_date: Mapped[str] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str] = mapped_column(String(10), nullable=True)
    paused_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    total_rounds: Mapped[int] = mapped_column(Integer, default=0)  # 已执行轮次
    risk_rules: Mapped[dict] = mapped_column(JSON, nullable=True)  # {price_limit_pct: 0.10, suspension_check: true, circuit_breaker_pct: 0.05}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now(), onupdate=lambda: shanghai_now())


class LabParticipant(Base):
    """参赛者表"""
    __tablename__ = "lab_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_competitions.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar: Mapped[str] = mapped_column(String(50), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # openai/deepseek/qwen/zhipu/claude/gemini/ollama
    api_base: Mapped[str] = mapped_column(String(200), nullable=True)
    api_key: Mapped[str] = mapped_column(String(200), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    personality: Mapped[str] = mapped_column(String(100), nullable=True)  # 激进/稳健/技术/基本面/逆向
    initial_capital: Mapped[float] = mapped_column(Float, default=100000.0)
    current_capital: Mapped[float] = mapped_column(Float, default=100000.0)
    total_return: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/eliminated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabCompPosition(Base):
    """比赛持仓表"""
    __tablename__ = "lab_comp_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_participants.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabCompTrade(Base):
    """比赛交易表"""
    __tablename__ = "lab_comp_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_participants.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(4), nullable=False)  # buy/sell
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabChatMessage(Base):
    """群聊消息表"""
    __tablename__ = "lab_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_competitions.id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_participants.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")  # text/analysis/alert/system
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabLeaderboard(Base):
    """排行榜快照表"""
    __tablename__ = "lab_leaderboard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_competitions.id"), nullable=False, index=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_participants.id"), nullable=False)
    total_return: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabCompEvent(Base):
    """比赛事件时间线表"""
    __tablename__ = "lab_comp_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_competitions.id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_participants.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 涨停/跌停/止损/止盈/排名变化/重大回撤/比赛开始/比赛结束/停牌
    symbol: Mapped[str] = mapped_column(String(10), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


# ==================== AI投研团队 ====================

class LabResearchTask(Base):
    """研究任务表"""
    __tablename__ = "lab_research_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    stage: Mapped[str] = mapped_column(String(20), default="init")  # init/research/discuss/report/done
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class LabAnalyst(Base):
    """分析师配置表"""
    __tablename__ = "lab_analysts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # value/game/tech/quant/overall
    avatar: Mapped[str] = mapped_column(String(50), nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    api_base: Mapped[str] = mapped_column(String(200), nullable=True)
    api_key: Mapped[str] = mapped_column(String(200), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabAnalystReport(Base):
    """分析师报告表"""
    __tablename__ = "lab_analyst_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_research_tasks.id"), nullable=False, index=True)
    analyst_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_analysts.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)  # research/discuss
    content: Mapped[dict] = mapped_column(JSON, nullable=False)  # {view, score, reasoning, concerns, ...}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())


class LabResearchReport(Base):
    """最终研究报告表"""
    __tablename__ = "lab_research_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("lab_research_tasks.id"), nullable=False, unique=True)
    fundamental_score: Mapped[float] = mapped_column(Float, default=0.0)
    technical_score: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=True)  # strong_buy/buy/neutral/sell/strong_sell
    target_price_low: Mapped[float] = mapped_column(Float, nullable=True)
    target_price_high: Mapped[float] = mapped_column(Float, nullable=True)
    risk_factors: Mapped[dict] = mapped_column(JSON, nullable=True)
    consensus: Mapped[dict] = mapped_column(JSON, nullable=True)
    divergences: Mapped[dict] = mapped_column(JSON, nullable=True)
    full_report: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: shanghai_now())
