"""定时任务调度 - 用 APScheduler 简化（替代 Celery，免去 Redis 依赖）"""
from datetime import date
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, func
from app.utils.logger import logger

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _job_wrapper(title: str, fn, *args, **kwargs):
    logger.info(f"[定时任务] 开始: {title}")
    try:
        result = await fn(*args, **kwargs)
        logger.info(f"[定时任务] 完成: {title} -> {result}")
        return result
    except Exception as e:
        logger.error(f"[定时任务] 失败: {title}: {e}")


async def _run_all_accounts(db, title: str, window: str = "收盘", skip_has_trades_today: bool = False) -> dict:
    from app.core.simulation.engine import SimulationEngine
    from sqlalchemy import select
    from app.models.simulation import SimulationAccount, SimulationTrade
    accounts = (await db.execute(select(SimulationAccount).where(SimulationAccount.is_active == True))).scalars().all()  # noqa: E712
    engine = SimulationEngine(db)
    done, skipped = [], 0
    today = date.today()
    for acc in accounts:
        try:
            if skip_has_trades_today:
                res = await db.execute(select(SimulationTrade.id).where(
                    SimulationTrade.account_id == acc.id,
                    func.date(SimulationTrade.timestamp) == today))
                if res.first():
                    skipped += 1
                    continue
            r = await engine.run_daily(acc.id, today, window=window)
            done.append({"account_id": acc.id, "trades": len(r.get("trades", [])),
                         "error": r.get("error")})
        except Exception as e:
            logger.error(f"{title} run failed account {acc.id}: {e}")
    return {"done": done, "skipped": skipped, "title": title}


async def _is_trading_day(db) -> bool:
    from datetime import date, timedelta
    today = date.today()
    if today.weekday() >= 5:
        return False
    try:
        from app.core.datasource.manager import DataSourceManager
        dsm = DataSourceManager(db)
        # 以今日是否已有真实K线判定（节假日/停市无当日K线）
        k = await dsm.get_klines("SH000001", "day",
                                 start=today - timedelta(days=1), end=today)
        if not k:
            return False
        last = str((k[-1].get("dt") or ""))[:10]
        return last >= today.isoformat()
    except Exception as e:
        logger.warning(f"trading-day check failed, assume trading day: {e}")
        return True


def setup_scheduler() -> AsyncIOScheduler:
    from app.db.session import SessionLocal

    async def run_replay():
        async with SessionLocal() as db:
            if not await _is_trading_day(db):
                logger.info("非交易日，跳过每日复盘")
                return {"skipped": True, "reason": "非交易日"}
            from app.core.replay.engine import ReplayEngine
            return await ReplayEngine(db).run()

    async def run_auto_trade(window: str):
        # 交易时段：9:30-10:25 / 13:00-13:30 / 14:30-14:50 末点触发（10:25 / 13:30 / 14:50）
        async with SessionLocal() as db:
            if not await _is_trading_day(db):
                logger.info(f"非交易日，跳过[{window}]")
                return {"skipped": True, "reason": "非交易日"}
            return await _run_all_accounts(db, f"盘中模拟交易[{window}]", window)

    async def run_evolution():
        # 20:00 进化：只补跑当天尚未模拟交易的账户，避免重复下单
        async with SessionLocal() as db:
            if not await _is_trading_day(db):
                logger.info("非交易日，跳过进化补跑")
                return {"skipped": True, "reason": "非交易日"}
            return await _run_all_accounts(db, "AI模拟交易/进化", skip_has_trades_today=True)

    async def run_rss_poll():
        from app.core.settings import get_setting
        if get_setting("rsshub_enabled") != "1":
            return {"skipped": True, "reason": "rsshub disabled"}
        async with SessionLocal() as db:
            from app.core.rsshub.service import RssService
            return await RssService(db).poll_sources()

    # 每个交易日的收盘复盘任务（18:00 自动复盘）
    scheduler.add_job(
        lambda: _job_wrapper("每日复盘", run_replay),
        CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone="Asia/Shanghai"),
        id="daily_replay", replace_existing=True,
    )
    # 收盘后自动执行当日模拟交易
    scheduler.add_job(
        lambda: _job_wrapper("模拟交易自动执行", lambda: run_auto_trade("收盘")),
        CronTrigger(day_of_week="mon-fri", hour=15, minute=10, timezone="Asia/Shanghai"),
        id="auto_trade_close", replace_existing=True,
    )
    # 盘中交易窗口末点：10:25(9:30-10:25) / 13:30(13:00-13:30) / 14:50(14:30-14:50)
    for hour, minute, label in [(10, 25, "早盘"), (13, 30, "午盘"), (14, 50, "尾盘")]:
        scheduler.add_job(
            lambda lbl=label: _job_wrapper(f"盘中模拟交易[{lbl}]", lambda lb=lbl: run_auto_trade(lb)),
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone="Asia/Shanghai"),
            id=f"auto_trade_{label}", replace_existing=True,
        )
    # 晚间 AI 自我进化/补跑
    scheduler.add_job(
        lambda: _job_wrapper("AI模拟交易/进化", lambda: run_evolution()),
        CronTrigger(day_of_week="mon-fri", hour=20, minute=0, timezone="Asia/Shanghai"),
        id="ai_evolution", replace_existing=True,
    )
    # RSSHub 轮询（每 30 秒，单源限频由 interval_sec 控制）
    scheduler.add_job(
        lambda: _job_wrapper("RSSHub轮询", lambda: run_rss_poll()),
        "interval", seconds=30, id="rss_poll", replace_existing=True,
    )
    logger.info("定时任务调度已配置 (10:25/13:30/14:50 交易时段决策, 15:10收盘, 18:00复盘, 20:00进化, 30s RSSHub轮询)")
    return scheduler


def scheduler_jobs() -> list:
    if not scheduler.running:
        return []
    jobs = []
    for j in scheduler.get_jobs():
        jobs.append({
            "id": j.id,
            "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return jobs


def start_scheduler():
    if scheduler.running:
        return scheduler
    setup_scheduler()
    scheduler.start()
    return scheduler