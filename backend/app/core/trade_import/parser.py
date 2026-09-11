"""实盘交易导入 + 盈亏计算 + AI点评"""
import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trade import UserTrade, UserPosition
from app.core.datasource.manager import DataSourceManager
from app.utils.logger import logger


# ---------- 券商交割单 / 通用 CSV 解析 ----------
# 表头别名统一映射（兼容同花顺/东方财富/各券商交割单与本站模板）
_HEADER_ALIAS = {
    "symbol": ["证券代码", "股票代码", "证券编号", "股票编号", "代码", "symbol"],
    "name": ["证券名称", "股票名称", "证券简称", "名称", "name"],
    "action": ["买卖标志", "买卖方向", "成交方向", "操作", "方向", "成交类别", "成交类型", "业务名称",
               "委托标志", "交易类别", "action"],
    "date": ["成交日期", "交易日期", "发生日期", "委托日期", "下单日期", "日期", "date", "trade_date"],
    "time": ["成交时间", "委托时间", "time"],
    "quantity": ["成交数量", "委托数量", "成交股数", "股数", "成交量", "数量", "quantity"],
    "price": ["成交价格", "委托价格", "成交均价", "委托均价", "成交价", "价格", "price"],
    "amount": ["成交金额", "发生金额", "收付金额", "清算金额", "资金发生额", "金额", "amount"],
    "fee_commission": ["手续费", "佣金", "fee"],
    "fee_tax": ["印花税", "印花"],
    "fee_transfer": ["过户费", "结算费", "结算费用", "经手费", "证管费", "其他费用", "委托费"],
    "note": ["备注", "note"],
}
_DIV_SKIP = ("派息", "股息", "红利", "利息", "资金划转", "申购配号", "配号", "中标", "市值")


def _norm_hdr(h) -> str:
    h = str(h or "").strip()
    h = re.sub(r"[（(）)【】\[\]:：,，;；.。·\-–—/\\\s]+", "", h)
    return h


def _map_headers(headers: list) -> dict:
    """把实际表头映射到标准字段；返回 {字段: [列索引,...]}"""
    idx = {}
    norms = {k: [_norm_hdr(a) for a in aliases] for k, aliases in _HEADER_ALIAS.items()}
    for i, h in enumerate(headers):
        nh = _norm_hdr(h)
        if not nh:
            continue
        for k, alias_list in norms.items():
            if nh in alias_list:
                idx.setdefault(k, []).append(i)
                break
    return idx


def _cell(row: list, cols) -> str:
    if not cols:
        return ""
    i = cols[0]
    if i >= len(row):
        return ""
    return row[i]


def _num(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return None
    s = str(v).replace(",", "").replace("，", "").replace(" ", "").strip()
    if not s or s in ("-", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_cell_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if hasattr(v, "to_pydatetime"):  # numpy/pandas 时间
        try:
            return v.to_pydatetime().date().isoformat()
        except Exception:
            pass
    s = str(v).strip()
    if re.fullmatch(r"\d{5}", s):  # Excel 日期序列号
        try:
            base = date(1899, 12, 30)
            d = base + __import__("datetime").timedelta(days=int(s))
            if 1990 <= d.year <= 2100:
                return d.isoformat()
        except Exception:
            pass
    if s.isdigit() and len(s) == 8:  # 20260901
        try:
            return datetime.strptime(s, "%Y%m%d").date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except (ValueError, IndexError):
            continue
    return s


def _action(v):
    s = str(v or "").strip().upper()
    if not s:
        return None
    for w in _DIV_SKIP:
        if w in str(v):
            return None
    if s in ("S", "SELL", "SL") or "卖" in s:
        return "sell"
    if s in ("B", "BUY", "BY") or "买" in s or "申购" in s:
        return "buy"
    return None


def normalize_symbol(code) -> str:
    """券商交割单代码 → 标准 SH/SZ/BJxxxxxx"""
    s = str(code or "").strip().upper()
    if not s:
        return ""
    s = re.sub(r"[^0-9]", "", s)
    if len(s) < 6:
        return ""
    s = s[-6:]
    if s.startswith(("60", "68", "9")) or s.startswith(("50", "51", "56", "58")):
        return "SH" + s
    if s.startswith(("43", "83", "87", "92")):
        return "BJ" + s
    return "SZ" + s


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            s = raw.decode(enc)
            if "\x00" not in s:
                return s
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _csv_rows(text: str) -> list:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    head = "\n".join(lines[:5])
    delim = "\t" if head.count("\t") > head.count(",") else ","
    return [r for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
            if any(str(c).strip() for c in r)]


def _excel_rows(content: bytes) -> list:
    try:
        import pandas as pd
    except ImportError:
        raise ValueError("缺少 pandas，无法解析 Excel，请安装 pandas/openpyxl")
    xl = pd.ExcelFile(io.BytesIO(content))
    best = None
    for sh in xl.sheet_names:
        df = xl.parse(sh, header=None)
        if best is None or len(df) > len(best):
            best = df
    rows = []
    for _, line in best.iterrows():
        cells = []
        for v in line.tolist():
            if v is None or not re.search(r"[^\s]", str(v)) or (isinstance(v, float) and pd.isna(v)):
                v = ""
            cells.append(v)
        if any(str(c).strip() for c in cells):
            rows.append(cells)
    return rows


def _build_trades(rows: list, idx: dict) -> tuple:
    trades, skipped = [], 0
    for r in rows:
        sym = normalize_symbol(_cell(r, idx.get("symbol")))
        act = _action(_cell(r, idx.get("action")))
        if not sym or not act:
            skipped += 1
            continue
        qty = _num(_cell(r, idx.get("quantity")))
        price = _num(_cell(r, idx.get("price")))
        amount = _num(_cell(r, idx.get("amount")))
        if price is None and amount is not None:
            price = amount / qty if qty else None
        if qty is None and amount is not None and price:
            qty = amount / price
        if not qty or not price or qty <= 0 or price <= 0:
            skipped += 1
            continue
        fee = sum(x for x in (
            _num(_cell(r, idx.get("fee_commission"))),
            _num(_cell(r, idx.get("fee_tax"))),
            _num(_cell(r, idx.get("fee_transfer"))),
        ) if x) or 0.0
        d = _fmt_cell_date(_cell(r, idx.get("date"))) or date.today().isoformat()
        t = str(_cell(r, idx.get("time"))).strip() or None
        trades.append({
            "symbol": sym,
            "name": str(_cell(r, idx.get("name")) or "").strip(),
            "action": act,
            "quantity": int(round(qty)),
            "price": round(float(price), 4),
            "fee": round(float(fee), 2),
            "date": d,
            "time": t,
            "note": "交割单导入",
            "imported_from": "file",
        })
    return trades, skipped


def parse_file_content(content: bytes) -> tuple:
    """解析交割单 CSV/Excel 或本站模板 → (trades, skipped)

    自动识别：UTF-8/GBK 编码、xlsx/xls（openpyxl/xlrd）、表头行位置、字段别名。
    支持同花顺/东方财富/各大券商交割单（成交日期/证券代码/买卖标志/成交数量/成交价格/成交金额/手续费/印花税/过户费）。
    """
    if content[:2] == b"PK" or content[:4] == b"\xd0\xcf\x11\xe0":
        rows = _excel_rows(content)
    else:
        rows = _csv_rows(_decode_bytes(content))
    for i in range(min(len(rows), 30)):
        idx = _map_headers(rows[i])
        if len(idx) >= 3:
            body = rows[i + 1:]
            return _build_trades(body, idx)
    raise ValueError("无法识别表头：未找到代码/日期/数量/买卖标志等列")


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

    async def import_file(self, user_id: int, content: bytes, filename: str = "file") -> dict:
        """批量导入：券商交割单 CSV/Excel 或本站模板 CSV"""
        trades, skipped = parse_file_content(content)
        result = await self.import_trades(user_id, trades)
        result["skipped"] = skipped
        result["raw"] = len(trades) + skipped
        return result

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