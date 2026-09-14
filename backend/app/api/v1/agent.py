"""AI智能体接口"""
import json
import re
import shlex
from datetime import datetime
import asyncio
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db, SessionLocal
from app.core.agent.registry import get_agent_configs, ensure_default_agents, create_agent
from app.core.agent.executor import AgentExecutor
from app.core.agent.base import AgentContext
from app.core.market.stock_service import StockService
from app.models.agent import AgentConfig, AgentRun, StockAiAnalysis
from app.schemas.common import AgentConfigCreate, AgentConfigUpdate, AgentAnalyzeRequest
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/agents", tags=["AI智能体"])


# ========================= curl 一键导入 =========================

def _parse_curl(curl_text: str) -> dict:
    """解析 curl 命令为 LLM 配置字段（base_url/api_key/model/provider）"""
    result = {"api_base": "", "api_key": "", "model_name": "", "provider": "", "headers": {}}
    if not curl_text or not curl_text.strip():
        return result
    try:
        # Normalize line continuations
        text = re.sub(r'\\\s*\n', ' ', curl_text.strip())
        tokens = shlex.split(text)
    except Exception:
        return result

    url = ""
    headers = {}
    body_str = ""
    method = "POST"
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("curl", "--request", "-X"):
            if t in ("--request", "-X"):
                i += 1; method = tokens[i].upper() if i < len(tokens) else "POST"
            i += 1
        elif t in ("--url", ""):
            i += 1; url = tokens[i] if i < len(tokens) else url; i += 1
        elif t in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                k, _, v = tokens[i].partition(":")
                headers[k.strip()] = v.strip().strip("'\"")
            i += 1
        elif t in ("-d", "--data", "--data-raw"):
            i += 1
            body_str = tokens[i] if i < len(tokens) else body_str
            i += 1
        else:
            i += 1

    result["api_base"] = url.rstrip("/")
    result["headers"] = headers

    # Extract api_key from various header styles
    for k, v in headers.items():
        kl = k.lower()
        if kl == "authorization" and v.lower().startswith("bearer "):
            result["api_key"] = v[7:].strip().strip("'\"")
            break
        elif kl in ("x-api-key", "x-goog-api-key", "api-key"):
            result["api_key"] = v.strip().strip("'\"")
            break

    # Extract model from JSON body
    if body_str:
        try:
            body = json.loads(body_str)
            if isinstance(body, dict):
                result["model_name"] = body.get("model", "")
        except Exception:
            pass

    # Infer provider from URL
    url_l = url.lower()
    model_l = result["model_name"].lower()
    if "anthropic" in url_l or "claude" in model_l:
        result["provider"] = "claude"
        # Normalize base URL: strip /v1/messages path
        result["api_base"] = re.sub(r'/v1/messages$', '', url_l)
    elif "openai" in url_l or "gpt" in model_l or "o1-" in model_l or "o3-" in model_l:
        result["provider"] = "openai"
    elif "gemini" in url_l or "generativelanguage" in url_l:
        result["provider"] = "gemini"
    elif "deepseek" in url_l or "deepseek" in model_l:
        result["provider"] = "deepseek"
    elif "dashscope" in url_l or "qwen" in model_l:
        result["provider"] = "qwen"
    elif "bigmodel" in url_l or "glm" in model_l:
        result["provider"] = "zhipu"
    elif "localhost" in url_l and ("11434" in url_l or "ollama" in url_l):
        result["provider"] = "ollama"
    elif "x.ai" in url_l or "grok" in model_l:
        result["provider"] = "grok"
    else:
        result["provider"] = "openai"  # Default to OpenAI-compatible

    # For Anthropic, base URL should end with /v1
    if result["provider"] == "claude" and not result["api_base"].endswith("/v1"):
        result["api_base"] = result["api_base"].rstrip("/") + "/v1"

    return result


@router.post("/parse-curl")
async def parse_curl(req: dict):
    """解析 curl 命令，返回 LLM 配置字段"""
    curl_text = req.get("curl", "")
    return _parse_curl(curl_text)


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


async def _build_stock_context(db: AsyncSession, symbol: str) -> AgentContext:
    from app.core.czsc_engine.analyzer import CZSCAnalyzer
    stock = StockService(db)
    return AgentContext(
        symbol=symbol,
        financial_data=await stock.get_financial(symbol),
        money_flow=await stock.get_money_flow(symbol),
        sector_info=await stock.get_sector(symbol),
        sentiment=await stock.get_sentiment(symbol),
        market_data={"forms": await stock.get_technic_forms(symbol)},
        czsc_result=await CZSCAnalyzer(db).analyze(symbol, "day"),
        news=await stock.get_stock_news(symbol),
    )


@router.get("/")
async def list_agents(db: AsyncSession = Depends(get_db)):
    await ensure_default_agents(db)
    return await get_agent_configs(db)


@router.post("/")
async def create_agent_config(body: AgentConfigCreate, db: AsyncSession = Depends(get_db)):
    cfg = AgentConfig(**body.model_dump(), user_id=0, is_active=True, is_default=False)
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"id": cfg.id, "name": cfg.name, "agent_type": cfg.agent_type}


@router.put("/{agent_id}")
async def update_agent(agent_id: int, body: AgentConfigUpdate, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalars().first()
    if not cfg:
        raise HTTPException(404, "agent not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cfg, k, v)
    cfg.updated_at = None
    await db.commit()
    return {"ok": True}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.id == agent_id))).scalars().first()
    if not cfg:
        raise HTTPException(404, "agent not found")
    if cfg.is_default:
        raise HTTPException(400, "不能删除默认智能体")
    await db.delete(cfg)
    await db.commit()
    return {"ok": True}


@router.post("/analyze/stock")
async def analyze_stock(body: AgentAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    ctx = await _build_stock_context(db, body.symbol)
    executor = AgentExecutor(db)
    result = await executor.run(agent_type=body.agent_type or "research",
                                agent_config_id=body.agent_config_id,
                                task=body.task, context=ctx)
    return result.model_dump()


async def _brainstorm_one(agent_type: str, symbol: str) -> dict:
    """独立数据库会话并行分析，避免共享 async session 并发冲突"""
    async with SessionLocal() as db:
        ctx = await _build_stock_context(db, symbol)
        executor = AgentExecutor(db)
        result = await executor.run(agent_type=agent_type, task="analyze_stock", context=ctx)
        data = result.model_dump()
        data["agent_type"] = agent_type
        return data


async def _load_cached(symbol: str, db: AsyncSession) -> dict | None:
    row = (await db.execute(
        select(StockAiAnalysis).where(
            StockAiAnalysis.symbol == symbol.upper(),
            StockAiAnalysis.trade_date == _today()).order_by(StockAiAnalysis.id.desc()).limit(1)
    )).scalars().first()
    if not row:
        return None
    return {
        "symbol": row.symbol, "cached": True,
        "analyzed_at": row.created_at.isoformat() if row.created_at else None,
        "agents": row.payload.get("agents", []) if isinstance(row.payload, dict) else [],
    }


async def _save_agent_result(symbol: str, agent_type: str, data: dict) -> None:
    """单个智能体结果合并入库：当日明细按 agent_type 更新，不覆盖其他智能体。"""
    async with SessionLocal() as db:
        row = (await db.execute(
            select(StockAiAnalysis).where(
                StockAiAnalysis.symbol == symbol.upper(),
                StockAiAnalysis.trade_date == _today()).order_by(StockAiAnalysis.id.desc()).limit(1)
        )).scalars().first()
        if row is None:
            row = StockAiAnalysis(symbol=symbol.upper(), trade_date=_today(), payload={"agents": []})
            db.add(row)
        agents = row.payload.get("agents", []) if isinstance(row.payload, dict) else []
        agents = [a for a in agents if a.get("agent_type") != agent_type]
        agents.append(data)
        row.payload = {"agents": agents}
        try:
            await db.commit()
        except Exception:
            await db.rollback()


@router.get("/brainstorm/{symbol}")
async def brainstorm_cached(symbol: str, db: AsyncSession = Depends(get_db)):
    """读取当日已保存的个股 AI 分析（不调用 LLM，切换个股后展示缓存）"""
    cached = await _load_cached(symbol, db)
    if cached:
        return cached
    return {"symbol": symbol.upper(), "cached": False, "agents": [], "analyzed_at": None}


@router.post("/brainstorm")
async def brainstorm_stock(body: AgentAnalyzeRequest, force: bool = False, db: AsyncSession = Depends(get_db)):
    """只分析选定的一个智能体（body.agent_type，默认 research），不再三智能体串行。
    当日该智能体已分析则返回缓存（force=True 重新分析）。"""
    atype = body.agent_type or "research"
    if atype not in ("research", "short_term", "swing"):
        raise HTTPException(400, "agent_type 必须是 research/short_term/swing")
    if not force:
        cached = await _load_cached(body.symbol, db)
        cached_agents = (cached or {}).get("agents", []) or []
        if any((a.get("agent_type") == atype) for a in cached_agents):
            return cached
    try:
        data = await _brainstorm_one(atype, body.symbol)
    except Exception as e:
        logger.warning(f"brainstorm {atype} failed: {e}")
        raise HTTPException(502, f"{atype} 分析失败: {e}")
    if (data.get("summary") or "").strip() and float(data.get("confidence") or 0) >= 0.3:
        try:
            await _save_agent_result(body.symbol, atype, data)
        except Exception:
            pass
    return {"symbol": body.symbol.upper(), "cached": False, "agent_type": atype, **data}


@router.post("/brainstorm/{symbol}/{agent_type}")
async def brainstorm_one(symbol: str, agent_type: str):
    """单个智能体分析单个完整请求，避免多智能体串行超时；命中 0.3 置信度则持久化。"""
    if agent_type not in ("research", "short_term", "swing"):
        raise HTTPException(400, "agent_type 必须是 research/short_term/swing")
    try:
        data = await _brainstorm_one(agent_type, symbol)
    except Exception as e:
        logger.warning(f"brainstorm {agent_type} failed: {e}")
        raise HTTPException(502, f"{agent_type} 分析失败: {e}")
    if (data.get("summary") or "").strip() and float(data.get("confidence") or 0) >= 0.3:
        try:
            await _save_agent_result(symbol, agent_type, data)
        except Exception:
            pass
    return {"symbol": symbol.upper(), "cached": False, "agent_type": agent_type, **data}


async def _stream_analyze(agent_type: str, symbol: str):
    """SSE 流式分析：不修改 agent 子类，用 wrapper 拦截 llm.complete 实时转发 tokens。"""
    queue: asyncio.Queue = asyncio.Queue()
    result_holder: list = [None]

    class _StreamWrapper:
        """拦截 llm.complete / complete_json，转成流式 SSE 事件，同时保留原返回供 agent 使用。"""

        def __init__(self, real):
            self._real = real

        async def complete(self, prompt, system_prompt="", response_format="text"):
            full = ""
            try:
                async for tok in self._real.stream_complete(prompt, system_prompt):
                    full += tok
                    await queue.put({"type": "delta", "text": tok})
            except Exception as e:
                await queue.put({"type": "error", "message": str(e)})
                raise
            await queue.put({"type": "_stream_done"})
            return full

        async def complete_json(self, prompt, system_prompt=""):
            raw = await self.complete(prompt, system_prompt)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                import re
                m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
                if m:
                    return json.loads(m.group(1))
                m2 = re.search(r"\{.*\}", raw, re.DOTALL)
                if m2:
                    return json.loads(m2.group(0))
                from app.core.agent.llm_client import LLMError
                raise LLMError(f"LLM返回无法解析为JSON: {raw[:200]}")

        def __getattr__(self, name):
            return getattr(self._real, name)

    async with SessionLocal() as db:
        ctx = await _build_stock_context(db, symbol)
        executor = AgentExecutor(db)
        config = await executor._load_config(None, agent_type)
        agent = create_agent(config)
        agent.llm = _StreamWrapper(agent.llm)

        async def _run():
            try:
                result_holder[0] = await agent.analyze_stock(ctx)
            except Exception as e:
                logger.warning(f"stream brainstorm {agent_type} failed: {e}")
                result_holder[0] = None

        task = asyncio.create_task(_run())

        yield f"data: {json.dumps({'type': 'started'}, ensure_ascii=False)}\n\n"

        while not task.done():
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                continue

        while not queue.empty():
            chunk = await queue.get()
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        await task
        result = result_holder[0]
        if result:
            data = result.model_dump()
            data["agent_type"] = agent_type
            yield f"data: {json.dumps({'type': 'done', 'result': data}, ensure_ascii=False)}\n\n"
            if (data.get("summary") or "").strip() and float(data.get("confidence") or 0) >= 0.3:
                try:
                    await _save_agent_result(symbol, agent_type, data)
                except Exception:
                    pass
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': '分析失败，请稍后重试'}, ensure_ascii=False)}\n\n"


@router.post("/brainstorm/{symbol}/{agent_type}/stream")
async def brainstorm_one_stream(symbol: str, agent_type: str):
    """SSE 流式版单个智能体分析，前端实时看到 AI 生成过程。"""
    if agent_type not in ("research", "short_term", "swing"):
        raise HTTPException(400, "agent_type 必须是 research/short_term/swing")
    return StreamingResponse(
        _stream_analyze(agent_type, symbol),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze/market")
async def analyze_market(agent_type: str = "research", db: AsyncSession = Depends(get_db)):
    from app.core.market.quote_service import MarketService
    market = MarketService(db)
    ctx = AgentContext(
        market_data={"sector_flow": await market.get_sector_money_flow(),
                     "limit_up": await market.get_limit_up()}
    )
    executor = AgentExecutor(db)
    result = await executor.run(agent_type=agent_type, task="daily_replay", context=ctx)
    return result.model_dump()


@router.get("/runs")
async def get_runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AgentRun).order_by(AgentRun.id.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "agent_config_id": r.agent_config_id, "task_type": r.task_type,
             "status": r.status, "duration_ms": r.duration_ms,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.get("/runs/stats")
async def get_runs_stats(days: int = 30, db: AsyncSession = Depends(get_db)):
    """智能体调用次数统计（周维度 / 小时维度），供 Agents.vue 图表."""
    from datetime import timedelta
    rows = (await db.execute(
        select(AgentRun).where(AgentRun.created_at >= datetime.utcnow() - timedelta(days=days))
    )).scalars().all()
    sh = ZoneInfo("Asia/Shanghai")
    by_weekday = {i: 0 for i in range(7)}   # 0=周一..6=周日
    by_hour = {i: 0 for i in range(24)}
    total = 0
    for r in rows:
        if not r.created_at:
            continue
        total += 1
        local = r.created_at.astimezone(sh)
        by_weekday[local.weekday()] = by_weekday.get(local.weekday(), 0) + 1
        by_hour[local.hour] = by_hour.get(local.hour, 0) + 1
    week_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return {
        "total": total,
        "days": days,
        "by_weekday": [{"label": week_labels[i], "count": by_weekday[i]} for i in range(7)],
        "by_hour": [{"label": f"{i:02d}:00", "count": by_hour[i]} for i in range(24)],
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalars().first()
    if not r:
        raise HTTPException(404, "run not found")
    return {"id": r.id, "task_type": r.task_type, "input_data": r.input_data,
            "output_data": r.output_data, "status": r.status, "error_message": r.error_message,
            "duration_ms": r.duration_ms}


@router.get("/{agent_type}/prompts")
async def get_prompt_history(agent_type: str, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    from app.models.agent import AgentPromptLog
    logs = (await db.execute(
        select(AgentPromptLog).where(AgentPromptLog.agent_type == agent_type)
        .order_by(AgentPromptLog.version.desc()).limit(20)
    )).scalars().all()
    return {
        "current_version": cfg.prompt_version,
        "current_prompt": cfg.system_prompt,
        "history": [{"version": l.version, "reason": l.reason, "score": float(l.performance_score) if l.performance_score else None,
                      "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs],
    }


@router.post("/{agent_type}/prompts/update")
async def update_prompt(agent_type: str, body: dict, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    new_prompt = body.get("system_prompt", "")
    reason = body.get("reason", "手动更新")
    if not new_prompt:
        raise HTTPException(400, "system_prompt 不能为空")
    from app.models.agent import AgentPromptLog
    old_version = cfg.prompt_version or 1
    log = AgentPromptLog(agent_config_id=cfg.id, agent_type=agent_type, version=old_version,
                         system_prompt=cfg.system_prompt, reason=f"v{old_version}备份")
    db.add(log)
    cfg.system_prompt = new_prompt
    cfg.prompt_version = old_version + 1
    history = cfg.prompt_history or []
    history.append({"version": cfg.prompt_version, "reason": reason})
    cfg.prompt_history = history[-50:]
    cfg.updated_at = None
    await db.commit()
    return {"ok": True, "version": cfg.prompt_version}


@router.post("/{agent_type}/prompts/rollback")
async def rollback_prompt(agent_type: str, body: dict, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(AgentConfig).where(AgentConfig.agent_type == agent_type, AgentConfig.is_default == True))).scalars().first()
    if not cfg:
        raise HTTPException(404, f"agent {agent_type} not found")
    target_version = body.get("version")
    if not target_version:
        raise HTTPException(400, "需要指定 version")
    from app.models.agent import AgentPromptLog
    log = (await db.execute(
        select(AgentPromptLog).where(AgentPromptLog.agent_type == agent_type, AgentPromptLog.version == target_version)
    )).scalars().first()
    if not log:
        raise HTTPException(404, f"版本 v{target_version} 不存在")
    current_log = AgentPromptLog(agent_config_id=cfg.id, agent_type=agent_type, version=cfg.prompt_version,
                                  system_prompt=cfg.system_prompt, reason=f"回滚前备份v{cfg.prompt_version}")
    db.add(current_log)
    cfg.system_prompt = log.system_prompt
    cfg.prompt_version = (cfg.prompt_version or 1) + 1
    cfg.updated_at = None
    await db.commit()
    return {"ok": True, "version": cfg.prompt_version}


@router.post("/{agent_type}/evaluate")
async def self_evaluate(agent_type: str, symbol: str, db: AsyncSession = Depends(get_db)):
    """手动触发AI自我评估"""
    async with SessionLocal() as eval_db:
        ctx = await _build_stock_context(eval_db, symbol)
        executor = AgentExecutor(eval_db)
        result = await executor.run(agent_type=agent_type, task="analyze_stock", context=ctx)
        data = result.model_dump()
        eval_result = {
            "agent_type": agent_type, "symbol": symbol,
            "score": data.get("score"), "summary": data.get("summary"),
            "evaluated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
    return eval_result