"""通用请求/响应模型"""
from datetime import date as _date
from typing import Any, Optional
from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    trace_id: str = ""


class WatchlistGroupCreate(BaseModel):
    name: str
    icon: Optional[str] = None


class WatchlistGroupUpdate(BaseModel):
    name: str
    icon: Optional[str] = None


class WatchlistItemCreate(BaseModel):
    group_id: int
    symbol: str
    name: Optional[str] = None
    note: Optional[str] = None


class WatchlistBatchDeleteRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class WatchlistNoteUpdate(BaseModel):
    note: str


class AgentConfigCreate(BaseModel):
    agent_type: str = "custom"
    name: str
    system_prompt: Optional[str] = None
    model_name: str = "deepseek-chat"
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4000
    extra_params: dict = {}


class AgentConfigUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    model_name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_active: Optional[bool] = None


class AgentAnalyzeRequest(BaseModel):
    symbol: str
    task: str = "analyze_stock"
    agent_type: Optional[str] = None
    agent_config_id: Optional[int] = None


class SimulationAccountCreate(BaseModel):
    name: Optional[str] = None
    agent_config_id: Optional[int] = None
    initial_capital: float = 100000
    prompt_template: Optional[str] = None
    rules: dict = {}


class SimulationRunRequest(BaseModel):
    date: Optional[_date] = None


class TradeItem(BaseModel):
    symbol: str
    name: Optional[str] = None
    action: str = "buy"
    quantity: float
    price: float
    fee: Optional[float] = 0
    date: Optional[str] = None
    note: Optional[str] = None


class TradeImportRequest(BaseModel):
    trades: list[TradeItem]
    source: str = "manual"


class ReplayTriggerRequest(BaseModel):
    date: Optional[_date] = None