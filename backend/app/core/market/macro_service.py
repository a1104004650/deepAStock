"""宏观经济指标抓取服务 — akshare + JSON 每日缓存"""
import json
import re
import importlib
import traceback
from datetime import datetime, date
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# CATALOG
# ---------------------------------------------------------------------------
CATALOG = [
    {"key": "cpi",           "name": "CPI（居民消费价格指数）",             "unit": "%（同比）",  "group": "价格", "func": "macro_china_cpi_monthly",             "type": "jin10"},
    {"key": "ppi",           "name": "PPI（工业生产者出厂价格指数）",       "unit": "%（同比）",  "group": "价格", "func": "macro_china_ppi_yearly",               "type": "jin10"},
    {"key": "pmi",           "name": "制造业PMI",                          "unit": "",           "group": "景气", "func": "macro_china_pmi_yearly",               "type": "jin10"},
    {"key": "gdp",           "name": "GDP（国内生产总值）",                 "unit": "%（同比）",  "group": "增长", "func": "macro_china_gdp_yearly",               "type": "jin10"},
    {"key": "retail",        "name": "社会消费品零售总额",                  "unit": "亿元（当月）","group": "消费", "func": "macro_china_consumer_goods_retail",   "type": "retail"},
    {"key": "exports",       "name": "出口（美元计）",                      "unit": "%（同比）",  "group": "贸易", "func": "macro_china_exports_yoy",              "type": "jin10"},
    {"key": "imports",       "name": "进口（美元计）",                      "unit": "%（同比）",  "group": "贸易", "func": "macro_china_imports_yoy",              "type": "jin10"},
    {"key": "trade_balance", "name": "贸易差额（美元计）",                  "unit": "亿美元",     "group": "贸易", "func": "macro_china_trade_balance",            "type": "jin10"},
    {"key": "unemployment",  "name": "城镇调查失业率",                      "unit": "%",          "group": "就业", "func": "macro_china_urban_unemployment",       "type": "unemp"},
    {"key": "house_price",   "name": "70城新建商品住宅价格指数",            "unit": "（同比指数，100=持平）","group": "房价", "func": "macro_china_new_house_price","type": "house"},
    {"key": "real_estate",   "name": "国房景气指数",                        "unit": "",           "group": "房价", "func": "macro_china_real_estate",              "type": "estate"},
    {"key": "m2",            "name": "M2（广义货币供应量）同比增长",        "unit": "%",          "group": "货币", "func": "macro_china_supply_of_money",          "type": "money_m2"},
    {"key": "deposits",      "name": "居民储蓄存款余额",                    "unit": "亿元",       "group": "存款", "func": "macro_china_supply_of_money",          "type": "money_save"},
    {"key": "fed_funds",     "name": "美联储联邦基金目标利率",               "unit": "%",          "group": "美联储", "func": "macro_bank_usa_interest_rate",      "type": "jin10"},
    {"key": "us_cpi",        "name": "美国CPI（消费价格指数）",              "unit": "%（同比）",  "group": "美联储", "func": "macro_usa_cpi_monthly",             "type": "jin10"},
    {"key": "us_nfp",        "name": "美国非农就业（新增）",                 "unit": "万人",       "group": "美联储", "func": "macro_usa_non_farm",                  "type": "jin10"},
]

# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _parse_jin10(df: pd.DataFrame) -> list[dict]:
    df = df.dropna(subset=["今值"]).copy()
    df["date"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
    df["value"] = df["今值"].astype(float)
    rows = df[["date", "value"]].sort_values("date").tail(60).to_dict("records")
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for r in rows]


def _parse_retail(df: pd.DataFrame) -> list[dict]:
    def parse_month(s):
        m = re.match(r"(\d{4})年(\d{1,2})月份", str(s))
        return f"{m.group(1)}-{int(m.group(2)):02d}" if m else str(s)
    df = df.copy()
    df["date"] = df["月份"].apply(parse_month)
    df["value"] = pd.to_numeric(df["同比增长"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for _, r in df.iterrows()]


def _parse_unemp(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    mask = df["item"].str.contains("全国城镇", na=False) & ~df["item"].str.contains("本地|外来|户籍", na=False)
    df = df[mask].dropna(subset=["value"]).copy()
    df["date"] = df["date"].apply(lambda s: f"{str(s)[:4]}-{str(s)[4:6]}" if len(str(s)) == 6 else str(s))
    df = df.sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for _, r in df.iterrows()]


def _parse_house(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["value"] = pd.to_numeric(df.get("新建商品住宅价格指数-同比"), errors="coerce")
    df = df.dropna(subset=["value"]).copy()
    df["date"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
    agg = df.groupby("date")["value"].mean().reset_index().sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 1)} for _, r in agg.iterrows()]


def _parse_estate(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["value"] = pd.to_numeric(df["最新值"], errors="coerce")
    df["date"] = pd.to_datetime(df["日期"]).dt.strftime("%Y-%m-%d")
    df = df.dropna(subset=["value"]).sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for _, r in df.iterrows()]


def _parse_money_m2(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["date"] = df["统计时间"].apply(lambda s: str(s).replace(".", "-"))
    df["value"] = pd.to_numeric(df["货币和准货币（广义货币M2）同比增长"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for _, r in df.iterrows()]


def _parse_money_save(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["date"] = df["统计时间"].apply(lambda s: str(s).replace(".", "-"))
    df["value"] = pd.to_numeric(df["储蓄存款"], errors="coerce")
    df = df.dropna(subset=["value"]).sort_values("date").tail(60)
    return [{"date": str(r["date"]), "value": round(float(r["value"]), 2)} for _, r in df.iterrows()]


PARSERS = {
    "jin10":     _parse_jin10,
    "retail":    _parse_retail,
    "unemp":     _parse_unemp,
    "house":     _parse_house,
    "estate":    _parse_estate,
    "money_m2":  _parse_money_m2,
    "money_save": _parse_money_save,
}

# ---------------------------------------------------------------------------
# Cache & fetch
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
_CACHE_FILE = _CACHE_DIR / "macro_daily.json"


def fetch_all_indicators(force: bool = False) -> dict:
    """每日抓取一次 akshare 宏观指标，结果缓存到 JSON 文件。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force and _CACHE_FILE.exists():
        try:
            cache = json.loads(_CACHE_FILE.read_text("utf-8"))
            if cache.get("fetched_date") == date.today().isoformat():
                return cache
        except Exception:
            pass

    ak = importlib.import_module("akshare")
    results = []
    for ind in CATALOG:
        try:
            func = getattr(ak, ind["func"])
            df = func()
            parser = PARSERS[ind["type"]]
            history = parser(df)
            latest = history[-1] if history else None
            prev = history[-2] if len(history) >= 2 else None
            delta = None
            if latest and prev:
                delta = round(latest["value"] - prev["value"], 2)
            results.append({
                "key":          ind["key"],
                "name":         ind["name"],
                "unit":         ind["unit"],
                "group":        ind["group"],
                "latest_value": latest["value"] if latest else None,
                "latest_date":  latest["date"] if latest else None,
                "delta":        delta,
                "history":      history[-36:],
                "error":        None,
            })
        except Exception as e:
            results.append({
                "key":          ind["key"],
                "name":         ind["name"],
                "unit":         ind["unit"],
                "group":        ind["group"],
                "latest_value": None,
                "latest_date":  None,
                "delta":        None,
                "history":      [],
                "error":        str(e)[:200],
            })

    payload = {
        "indicators":  results,
        "fetched_date": date.today().isoformat(),
        "fetched_at":   datetime.now().isoformat(),
    }
    try:
        _CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    except Exception:
        pass
    return payload
