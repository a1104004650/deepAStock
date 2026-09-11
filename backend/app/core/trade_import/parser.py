"""实盘交易导入 + 盈亏计算 + AI点评"""
import csv
import io
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trade import UserTrade, UserPosition
from app.core.datasource.manager import DataSourceManager
from app.utils.logger import logger


class TradeImportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.dsm = DataSourceManager(db)

    async def import_trades(self, user_id: int, trades: list[dict]) -> dict:
        """批量导入交易记录
        trades: [{symbol, action, quantity, price, date, fee, note, name}]
        """
        imported = 0
        for t in trades:
            try:
                trade = UserTrade(
                    user_id=user_id,
                    symbol=t.get("symbol"),
                    name=t.get("name"),
                    action=t.get("action", "buy"),
                    quantity=int(t.get("quantity", 0)),
                    price=Decimal(str(t.get("price", 0))),
                    fee=Decimal(str(t.get("fee", 0) or 0)),
                    trade_date=parse_date(t.get("date", t.get("trade_date"))),
                    trade_time=parse_time(t.get("time")) if t.get("time") else None,
                    note=t.get("note"),
                    imported_from=t.get("imported_from", "manual"),
                )
                self.db.add(trade)
                imported += 1
            except Exception as e:
                logger.warning(f"import trade failed: {e}")
        await self.db.commit()
        await self._recalc_positions(user_id)
        return {"imported": imported}

    async def import_csv(self, user_id: int, content: bytes, source: str = "csv") -> dict:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        trades = []
        for row in reader:
            trades.append({
                "symbol": row.get("symbol", row.get("代码", "")),
                "name": row.get("name", row.get("名称", "")),
                "action": "buy" if row.get("action", row.get("操作", "buy")) in ("买入", "buy", "B", "BUY") else "sell",
                "quantity": int(float(row.get("quantity", row.get("股数", 0)))),
                "price": float(row.get("price", row.get("价格", 0))),
                "fee": float(row.get("fee", row.get("手续费", 0)) or 0),
                "date": row.get("date", row.get("日期", date.today().isoformat())),
                "note": row.get("note", ""),
                "imported_from": source,
            })
        return await self.import_trades(user_id, trades)

    async def get_positions(self, user_id: int) -> list[dict]:
        rows = (await self.db.execute(
            select(UserPosition).where(UserPosition.user_id == user_id))).scalars().all()
        if rows:
            return [self._pos_dict(p) for p in rows]
        await self._recalc_positions(user_id)
        rows = (await self.db.execute(
            select(UserPosition).where(UserPosition.user_id == user_id))).scalars().all()
        return [self._pos_dict(p) for p in rows]

    async def get_trades(self, user_id: int, limit: int = 200) -> list[dict]:
        rows = (await self.db.execute(
            select(UserTrade).where(UserTrade.user_id == user_id)
            .order_by(UserTrade.trade_date.desc()).limit(limit))).scalars().all()
        return [{"id": t.id, "symbol": t.symbol, "name": t.name, "action": t.action,
                 "quantity": t.quantity, "price": float(t.price), "fee": float(t.fee),
                 "trade_date": t.trade_date.isoformat(), "note": t.note,
                 "amount": round(t.quantity * float(t.price), 2)} for t in rows]

    async def delete_trade(self, user_id: int, trade_id: int) -> bool:
        row = (await self.db.execute(select(UserTrade).where(
            UserTrade.id == trade_id, UserTrade.user_id == user_id))).scalars().first()
        if not row:
            return False
        await self.db.delete(row)
        await self.db.commit()
        await self._recalc_positions(user_id)
        return True

    async def delete_all(self, user_id: int) -> int:
        rows = (await self.db.execute(select(UserTrade).where(UserTrade.user_id == user_id))).scalars().all()
        n = len(rows)
        for r in rows:
            await self.db.delete(r)
        await self.db.commit()
        await self._recalc_positions(user_id)
        return n

    async def get_pnl_summary(self, user_id: int) -> dict:
        positions = await self.get_positions(user_id)
        total_cost = sum(float(p["total_cost"]) for p in positions)
        total_market = sum(float(p["market_value"]) for p in positions)
        total_return = sum(float(p["total_return"]) for p in positions)
        return {
            "total_cost": round(total_cost, 2),
            "total_market_value": round(total_market, 2),
            "total_return": round(total_return, 2),
            "position_count": len(positions),
            "positions": positions,
        }

    async def _recalc_positions(self, user_id: int):
        """从交易流水重算持仓"""
        trades = (await self.db.execute(
            select(UserTrade).where(UserTrade.user_id == user_id).order_by(UserTrade.trade_date, UserTrade.id))).scalars().all()

        # 删除旧持仓
        old = (await self.db.execute(select(UserPosition).where(UserPosition.user_id == user_id))).scalars().all()
        for p in old:
            await self.db.delete(p)

        agg = {}
        for t in trades:
            sym = t.symbol
            a = agg.setdefault(sym, {"buy_qty": 0, "sell_qty": 0, "cost": 0.0, "name": t.name})
            if t.action == "buy":
                a["buy_qty"] += t.quantity
                a["cost"] += t.quantity * float(t.price) + float(t.fee or 0)
            else:
                a["sell_qty"] += t.quantity
        await self.db.flush()

        for sym, a in agg.items():
            remaining = a["buy_qty"] - a["sell_qty"]
            if remaining <= 0:
                continue
            avg_cost = a["cost"] / a["buy_qty"] if a["buy_qty"] else 0
            try:
                rt = await self.dsm.get_realtime([sym])
                price = float(rt.get(sym, {}).get("price", avg_cost))
            except Exception:
                price = avg_cost
            total_cost = avg_cost * remaining
            market_value = price * remaining
            r = market_value - total_cost
            self.db.add(UserPosition(
                user_id=user_id, symbol=sym, name=a["name"],
                total_buy_qty=a["buy_qty"], total_sell_qty=a["sell_qty"],
                remaining_qty=remaining, avg_cost=avg_cost, total_cost=total_cost,
                total_return=r, return_rate=(r / total_cost if total_cost else 0),
            ))
        await self.db.commit()

    @staticmethod
    def _pos_dict(p) -> dict:
        return {"symbol": p.symbol, "name": p.name, "remaining_qty": p.remaining_qty,
                "avg_cost": float(p.avg_cost), "total_cost": float(p.total_cost),
                "total_return": float(p.total_return), "return_rate": float(p.return_rate),
                "market_value": round(float(p.total_cost) + float(p.total_return), 2),
                "last_price": round(float(p.avg_cost) + (float(p.total_return) / p.remaining_qty if p.remaining_qty else 0), 2)}


def parse_date(s) -> date:
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except (ValueError, IndexError):
            continue
    return date.today()


def parse_time(s) -> object:
    try:
        t = str(s).strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(t, fmt).time()
            except ValueError:
                continue
    except Exception:
        pass
    return None