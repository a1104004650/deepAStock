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
from app.utils import shanghai_now


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
        if not rows:
            await self._recalc_positions(user_id)
            rows = (await self.db.execute(
                select(UserPosition).where(UserPosition.user_id == user_id))).scalars().all()
            return [self._pos_dict(p) for p in rows]
        # 有持仓记录时，刷新每只股票的实时价格
        symbols = list({p.symbol for p in rows})
        rt_map = {}
        try:
            rt = await self.dsm.get_realtime(symbols)
            rt_map = rt if isinstance(rt, dict) else {}
        except Exception:
            pass
        result = []
        for p in rows:
            cur_price = float(rt_map.get(p.symbol, {}).get("price", 0) or 0)
            if cur_price > 0:
                mv = cur_price * p.remaining_qty
                r = mv - float(p.total_cost)
                p.total_return = r
                p.return_rate = r / float(p.total_cost) if float(p.total_cost) else 0
            result.append(self._pos_dict(p))
        return result

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

    async def review_trade(self, user_id: int, trade_id: int) -> dict:
        """AI 点评单笔交易（综合量价、板块、情绪分析）"""
        import json
        trade = (await self.db.execute(
            select(UserTrade).where(UserTrade.id == trade_id, UserTrade.user_id == user_id)
        )).scalars().first()
        if not trade:
            return {"error": "交易记录不存在"}

        # 获取同股票历史交易
        sym_trades = (await self.db.execute(
            select(UserTrade).where(UserTrade.user_id == user_id, UserTrade.symbol == trade.symbol)
            .order_by(UserTrade.trade_date)
        )).scalars().all()

        # 获取当前持仓
        positions = await self.get_positions(user_id)
        pos = next((p for p in positions if p["symbol"] == trade.symbol), None)

        # 获取股票基本信息
        stock_info = ""
        try:
            basic = await self.dsm.get_realtime([trade.symbol])
            if basic and trade.symbol in basic:
                rt = basic[trade.symbol]
                stock_info = (
                    f"\n实时行情:\n"
                    f"  最新价: {rt.get('price', 0)}\n"
                    f"  涨跌幅: {rt.get('change_pct', 0)}%\n"
                    f"  量比: {rt.get('volume_ratio', 0)}\n"
                    f"  换手率: {rt.get('turnover_rate', 0)}%\n"
                )
        except Exception:
            pass

        # 获取日K线（近20根）
        kline_info = ""
        try:
            kline_data = await self.dsm.get_kline(trade.symbol, period="day", count=20)
            if kline_data:
                recent = kline_data[-5:] if len(kline_data) >= 5 else kline_data
                kline_info = "\n近5日K线:\n"
                for k in recent:
                    kline_info += f"  {k.get('dt', '')}: 开{k.get('open', 0):.2f} 高{k.get('high', 0):.2f} 低{k.get('low', 0):.2f} 收{k.get('close', 0):.2f}\n"
                
                # 计算支撑位和压力位
                if len(kline_data) >= 10:
                    lows = [k.get('low', 0) for k in kline_data[-10:]]
                    highs = [k.get('high', 0) for k in kline_data[-10:]]
                    support = min(lows)
                    resistance = max(highs)
                    kline_info += f"  近10日支撑位: {support:.2f}\n"
                    kline_info += f"  近10日压力位: {resistance:.2f}\n"
        except Exception:
            pass

        # 构建 prompt
        trade_info = (
            f"交易日期: {trade.trade_date.isoformat()}\n"
            f"股票: {trade.name}({trade.symbol})\n"
            f"方向: {'买入' if trade.action == 'buy' else '卖出'}\n"
            f"数量: {trade.quantity}股\n"
            f"价格: {float(trade.price):.2f}元\n"
        )

        position_info = ""
        if pos:
            position_info = (
                f"\n当前持仓:\n"
                f"  持仓数量: {pos['remaining_qty']}股\n"
                f"  持仓均价: {pos['avg_cost']:.2f}元\n"
                f"  浮动盈亏: {pos['total_return']:.2f}元 ({pos['return_rate']*100:.2f}%)\n"
            )

        prompt = f"""请作为专业A股交易分析师，综合分析以下交易：

{trade_info}{position_info}{stock_info}{kline_info}

请从以下维度深度分析：

1. **量价分析**：结合K线形态、成交量、换手率判断买卖点合理性
2. **板块分析**：该股票所属板块当前强弱，是否为板块龙头
3. **位置分析**：当前股价在近期走势中的位置（高位/中位/低位）
4. **情绪分析**：市场情绪对该板块/个股的影响
5. **逻辑预期**：后续走势的逻辑判断

**输出格式（严格JSON）**：
{{
    "rating": "good/neutral/poor",
    "score": 0-100,
    "analysis": "量价分析+板块分析+位置分析（3-4句话）",
    "support": "支撑位（具体价格，防量化精确到分）",
    "resistance": "止盈位（具体价格）",
    "stop_loss": "止损位（具体价格）",
    "suggestion": "操作建议（1-2句话）",
    "logic": "后续逻辑预期（1-2句话）"
}}"""

        system_prompt = (
            "你是专业A股短线交易分析师，擅长量价分析和板块轮动分析。"
            "给出的支撑位要精确到分（如10.23），且支撑位要设在当前价下方防止量化扫货。"
            "止盈位和止损位也要具体。"
            "分析要客观专业，风险第一。"
        )

        try:
            from app.core.agent.llm_client import LLMClient, LLMNotConfigured
            from app.models.agent import AgentConfig
            from sqlalchemy import select as sa_select

            cfg = (await self.db.execute(
                sa_select(AgentConfig).limit(1)
            )).scalars().first()

            llm = LLMClient(
                api_base=cfg.api_base if cfg else "",
                api_key=cfg.api_key if cfg else "",
                model=cfg.model_name if cfg else "deepseek-chat",
                temperature=0.3,
                max_tokens=1500,
            )

            result = await llm.complete_json(prompt, system_prompt)
            
            # 保存点评到交易记录
            trade.note = json.dumps(result, ensure_ascii=False)
            await self.db.commit()
            
            return result

        except LLMNotConfigured:
            return self._local_trade_review(trade, pos, sym_trades)
        except Exception as e:
            logger.warning(f"AI review failed: {e}")
            return self._local_trade_review(trade, pos, sym_trades)

    def _local_trade_review(self, trade, pos, sym_trades) -> dict:
        """本地启发式交易点评"""
        import json
        is_buy = trade.action == "buy"
        price = float(trade.price)
        score = 60
        analysis = ""

        if pos:
            avg_cost = pos["avg_cost"]
            if is_buy and price < avg_cost * 0.98:
                score += 10
                analysis = "买入价格低于持仓均价，有摊薄成本效果"
            elif is_buy and price > avg_cost * 1.02:
                score -= 10
                analysis = "买入价格高于持仓均价，追高风险"
            elif not is_buy and price > avg_cost:
                score += 10
                analysis = "卖出价格高于均价，盈利出局"
            elif not is_buy and price < avg_cost:
                score -= 5
                analysis = "卖出价格低于均价，止损出局"
        
        if not analysis:
            analysis = "交易操作符合常规逻辑"

        # 计算支撑位和压力位（基于价格估算）
        support = round(price * 0.97, 2)  # 下方3%
        resistance = round(price * 1.05, 2)  # 上方5%
        stop_loss = round(price * 0.95, 2)  # 止损5%

        rating = "good" if score >= 70 else "neutral" if score >= 50 else "poor"

        result = {
            "rating": rating,
            "score": min(max(score, 30), 95),
            "analysis": analysis,
            "support": str(support),
            "resistance": str(resistance),
            "stop_loss": str(stop_loss),
            "suggestion": "建议设定明确的止盈止损位，严格执行交易纪律",
            "logic": "后续走势需观察量能配合和板块轮动情况",
        }

        # 保存点评
        trade.note = json.dumps(result, ensure_ascii=False)
        return result

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