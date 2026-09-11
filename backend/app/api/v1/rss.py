"""RSSHub 订阅管理接口"""
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.rsshub.service import RssService

router = APIRouter(prefix="/api/v1/rss", tags=["订阅"])


class SourceBody(BaseModel):
    name: str
    platform: str = "generic"
    route: str | None = None
    url: str | None = None
    tags: list[str] = []
    enabled: bool = True
    interval_sec: int = 30
    filter_st: bool = True


class TestFeedBody(BaseModel):
    url: str


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    return await RssService(db).list_sources()


@router.post("/sources")
async def create_source(body: SourceBody = Body(...), db: AsyncSession = Depends(get_db)):
    return await RssService(db).create_source(body.model_dump())


@router.put("/sources/{source_id}")
async def update_source(source_id: int, body: SourceBody = Body(...),
                        db: AsyncSession = Depends(get_db)):
    return await RssService(db).update_source(source_id, body.model_dump())


@router.delete("/sources/{source_id}")
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    ok = await RssService(db).delete_source(source_id)
    return {"ok": ok}


@router.post("/test")
async def test_feed(body: TestFeedBody = Body(...), db: AsyncSession = Depends(get_db)):
    return await RssService(db).test_feed(body.url)


@router.get("/items")
async def list_items(limit: int = 50, source_id: int | None = None,
                     q: str | None = None, importance: int | None = None,
                     platform: str | None = None,
                     db: AsyncSession = Depends(get_db)):
    return await RssService(db).get_items(limit, source_id, q, importance, platform)


@router.post("/poll")
async def poll_now(db: AsyncSession = Depends(get_db)):
    return await RssService(db).poll_sources()