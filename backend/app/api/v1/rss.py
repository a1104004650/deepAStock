"""RSS 订阅管理接口"""
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.rsshub.service import RssService, seed_default_sources

router = APIRouter(prefix="/api/v1/rss", tags=["订阅"])

RSSHUB_DOC_URL = "https://rsshub-doc.pages.dev/traditional-media.html"
"""官方路由文档入口（页面粘贴展示用）"""


class SourceBody(BaseModel):
    name: str = ""
    rss_type: str = "http"        # http / rsshub_local
    url: str | None = None
    tags: list[str] = []
    remark: str = ""
    interval_min: int = 5
    enabled: bool = True


class TestFeedBody(BaseModel):
    url: str


@router.get("/doc-url")
async def doc_url():
    return {"doc": RSSHUB_DOC_URL}


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


@router.post("/sources/{source_id}/net-test")
async def net_test_source(source_id: int, db: AsyncSession = Depends(get_db)):
    return await RssService(db).net_test_source(source_id)


@router.post("/sources/{source_id}/poll")
async def poll_source(source_id: int, db: AsyncSession = Depends(get_db)):
    return await RssService(db).poll_source(source_id)


@router.get("/items")
async def list_items(limit: int = 50, source_id: int | None = None,
                     q: str | None = None, importance: int | None = None,
                     platform: str | None = None,
                     db: AsyncSession = Depends(get_db)):
    return await RssService(db).get_items(limit, source_id, q, importance, platform)


@router.delete("/items")
async def clear_items(db: AsyncSession = Depends(get_db)):
    return {"ok": True, "cleared": await RssService(db).clear_items()}


@router.get("/stats")
async def rss_stats(db: AsyncSession = Depends(get_db)):
    return await RssService(db).stats()


@router.get("/recent")
async def recent_added(limit: int = 50, db: AsyncSession = Depends(get_db)):
    return await RssService(db).recent_added(limit)


@router.post("/poll")
async def poll_now(db: AsyncSession = Depends(get_db)):
    return await RssService(db).poll_sources()


@router.post("/seed")
async def seed_defaults(db: AsyncSession = Depends(get_db)):
    await seed_default_sources(db)
    return await RssService(db).list_sources()