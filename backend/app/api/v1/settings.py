"""系统设置接口"""
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.settings import snapshot, update_settings, test_database_url

router = APIRouter(prefix="/api/v1/settings", tags=["设置"])


class UpdateBody(BaseModel):
    updates: dict[str, str]


class TestDBBody(BaseModel):
    url: str


@router.get("")
async def get_settings():
    return snapshot()


@router.put("")
async def put_settings(body: UpdateBody = Body(...), db: AsyncSession = Depends(get_db)):
    return await update_settings(db, body.updates)


@router.post("/test-database")
async def post_test_database(body: TestDBBody = Body(...)):
    return await test_database_url(body.url)