"""实盘交易导入接口"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.trade_import.parser import TradeImportService
from app.schemas.common import TradeImportRequest

router = APIRouter(prefix="/api/v1/trade", tags=["实盘交易"])


@router.get("/positions")
async def get_positions(db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    return await svc.get_positions(0)


@router.get("/trades")
async def get_trades(limit: int = 200, db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    return await svc.get_trades(0, limit)


@router.delete("/trades")
async def delete_all_trades(db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    n = await svc.delete_all(0)
    return {"deleted": n}


@router.post("/reset")
async def reset_trading_ledger(db: AsyncSession = Depends(get_db)):
    """重置实盘导入账本：删除全部交易流水并重建为空持仓。"""
    svc = TradeImportService(db)
    n = await svc.delete_all(0)
    return {"ok": True, "deleted": n, "positions": 0}


@router.delete("/trades/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    ok = await svc.delete_trade(0, trade_id)
    return {"ok": ok}


@router.post("/import/json")
async def import_json(body: TradeImportRequest, db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    trades = [t.model_dump() | {"date": t.date} for t in body.trades]
    for t in trades:
        t["date"] = t.get("date") or t.get("trade_date")
    return await svc.import_trades(0, trades)


@router.post("/import/file")
async def import_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    svc = TradeImportService(db)
    return await svc.import_file(0, content, filename=file.filename or "file")


@router.post("/import/csv")
async def import_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    svc = TradeImportService(db)
    return await svc.import_file(0, content, filename="csv")


@router.get("/pnl/summary")
async def pnl_summary(db: AsyncSession = Depends(get_db)):
    svc = TradeImportService(db)
    return await svc.get_pnl_summary(0)


@router.post("/trades/{trade_id}/review")
async def review_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    """AI 点评单笔交易"""
    svc = TradeImportService(db)
    return await svc.review_trade(0, trade_id)
