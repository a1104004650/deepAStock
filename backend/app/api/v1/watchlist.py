"""自选股接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.market.watchlist_service import WatchlistService
from app.schemas.common import (WatchlistGroupCreate, WatchlistGroupUpdate,
                                WatchlistItemCreate, WatchlistNoteUpdate, WatchlistBatchDeleteRequest)

router = APIRouter(prefix="/api/v1/watchlist", tags=["自选股"])


@router.get("/groups")
async def get_groups(db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    return await svc.get_groups()


@router.post("/groups")
async def create_group(body: WatchlistGroupCreate, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    return await svc.create_group(body.name, body.icon)


@router.put("/groups/{group_id}")
async def update_group(group_id: int, body: WatchlistGroupUpdate, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    return await svc.rename_group(group_id, body.name, body.icon)


@router.delete("/groups/{group_id}")
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    await svc.delete_group(group_id)
    return {"ok": True}


@router.post("/items")
async def add_item(body: WatchlistItemCreate, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    return await svc.add_item(body.group_id, body.symbol, body.name, body.note)


@router.delete("/items/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    await svc.delete_item(item_id)
    return {"ok": True}


@router.post("/items/batch-delete")
async def delete_items_batch(body: WatchlistBatchDeleteRequest, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    deleted = await svc.delete_items_batch(body.ids)
    return {"ok": True, "deleted": deleted}


@router.put("/items/{item_id}/note")
async def update_note(item_id: int, body: WatchlistNoteUpdate, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    await svc.update_note(item_id, body.note)
    return {"ok": True}


@router.get("/preview")
async def get_preview(group_id: int = None, db: AsyncSession = Depends(get_db)):
    svc = WatchlistService(db)
    return await svc.get_preview(group_id)