"""自选股服务"""
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.watchlist import WatchlistGroup, WatchlistItem
from app.core.datasource.manager import DataSourceManager


class WatchlistService:
    def __init__(self, db: AsyncSession, user_id: int = 0):
        self.db = db
        self.user_id = user_id
        self.dsm = DataSourceManager(db)

    async def get_groups(self) -> list[dict]:
        rows = (await self.db.execute(
            select(WatchlistGroup).where(WatchlistGroup.user_id == self.user_id)
            .order_by(WatchlistGroup.sort_order, WatchlistGroup.id))).scalars().all()
        groups = [{"id": g.id, "name": g.name, "icon": g.icon, "sort_order": g.sort_order} for g in rows]

        # 无分组时创建一个默认分组
        if not groups:
            g = WatchlistGroup(user_id=self.user_id, name="默认分组", icon="📁", sort_order=0)
            self.db.add(g)
            await self.db.commit()
            await self.db.refresh(g)
            groups = [{"id": g.id, "name": g.name, "icon": g.icon, "sort_order": g.sort_order}]

        for g in groups:
            items = (await self.db.execute(
                select(WatchlistItem).where(WatchlistItem.group_id == g["id"]).order_by(WatchlistItem.id))).scalars().all()
            symbols = [i.symbol for i in items]
            rt = await self.dsm.get_realtime(symbols) if symbols else {}
            g["items"] = [{
                "id": i.id, "symbol": i.symbol, "name": i.name, "note": i.note,
                "alert_price": float(i.alert_price) if i.alert_price else None,
                **rt.get(i.symbol, {}),
            } for i in items]
        return groups

    async def create_group(self, name: str, icon: str = None) -> dict:
        g = WatchlistGroup(user_id=self.user_id, name=name, icon=icon or "📁",
                           sort_order=0)
        self.db.add(g)
        await self.db.commit()
        await self.db.refresh(g)
        return {"id": g.id, "name": g.name, "icon": g.icon, "sort_order": g.sort_order, "items": []}

    async def delete_group(self, group_id: int) -> None:
        await self.db.execute(delete(WatchlistItem).where(WatchlistItem.group_id == group_id))
        await self.db.execute(delete(WatchlistGroup).where(WatchlistGroup.id == group_id, WatchlistGroup.user_id == self.user_id))
        await self.db.commit()

    async def rename_group(self, group_id: int, name: str, icon: str = None) -> dict:
        g = (await self.db.execute(select(WatchlistGroup).where(WatchlistGroup.id == group_id))).scalars().first()
        if g:
            g.name = name
            if icon:
                g.icon = icon
            await self.db.commit()
            return {"id": g.id, "name": g.name, "icon": g.icon}
        return {}

    async def add_item(self, group_id: int, symbol: str, name: str = None, note: str = None) -> dict:
        symbol = (symbol or "").strip().upper()
        digits = symbol[-6:]
        if not (symbol.startswith(("SH", "SZ", "BJ")) and digits.isdigit()):
            return {"ok": False, "error": "无效的股票代码", "message": f"「{symbol}」不是有效的 A 股代码（应形如 SH600519 / SZ000001）",
                    "hint": "请先搜索并选择一只股票，或输入6位数字代码后搜索确认"}
        rt = await self.dsm.get_realtime([symbol])
        if not name:
            name = rt.get(symbol, {}).get("name")
            if not name:
                name = symbol
        dup = (await self.db.execute(
            select(WatchlistItem).where(WatchlistItem.group_id == group_id, WatchlistItem.symbol == symbol)
        )).scalars().first()
        if dup:
            return {"ok": False, "error": "already_exists",
                    "message": f"「{name}」已在当前分组的自选中", "id": dup.id, "symbol": symbol, "name": name}
        item = WatchlistItem(group_id=group_id, symbol=symbol, name=name, note=note)
        self.db.add(item)
        try:
            await self.db.commit()
            await self.db.refresh(item)
        except Exception:
            await self.db.rollback()
            existing = (await self.db.execute(
                select(WatchlistItem).where(WatchlistItem.group_id == group_id, WatchlistItem.symbol == symbol))).scalars().first()
            return {"ok": False, "error": "already_exists",
                    "message": f"「{name}」已在当前分组的自选中", "id": existing.id, "symbol": symbol, "name": name}
        return {"ok": True, "id": item.id, "symbol": symbol, "name": name, "note": note}

    async def delete_item(self, item_id: int) -> None:
        await self.db.execute(delete(WatchlistItem).where(WatchlistItem.id == item_id))
        await self.db.commit()

    async def delete_items_batch(self, ids: list[int]) -> int:
        if not ids:
            return 0
        await self.db.execute(delete(WatchlistItem).where(WatchlistItem.id.in_(ids)))
        await self.db.commit()
        return len(ids)

    async def update_note(self, item_id: int, note: str) -> None:
        item = (await self.db.execute(select(WatchlistItem).where(WatchlistItem.id == item_id))).scalars().first()
        if item:
            item.note = note
            await self.db.commit()

    async def get_preview(self, group_id: int = None) -> list[dict]:
        """自选股概览（全部或某个分组）"""
        groups = await self.get_groups()
        if group_id:
            groups = [g for g in groups if g["id"] == group_id]
        return [item for g in groups for item in g.get("items", [])]

    async def get_all_symbols(self) -> list[str]:
        rows = (await self.db.execute(select(WatchlistItem.symbol))).scalars().all()
        return list(rows)