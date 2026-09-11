"""RSS/Atom/JSON Feed 抓取与统一解析（仅读取，不做去重）"""
import re
import json
import urllib.request
import urllib.error
import email.utils
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

from app.utils.logger import logger

_ST_RE = re.compile(r"(?<![A-Za-z0-9])(?:S[*★]?ST|\*?ST)(?![A-Za-z0-9])", re.IGNORECASE)
_IMPORTANCE_KW_HIGH = ["暴雷", "违规", "处罚", "警示", "重大", "利空", "退市", "立案", "诉讼"]
_IMPORTANCE_KW_MID = ["涨停", "跌停", "增持", "减持", "业绩预告", "分红", "增持计划", "回购"]
_SYMBOL_RE = re.compile(r"(?:[shSH]|sh|sz|SZ)?([036]\d{5})")
_CN_TZ = timezone(timedelta(hours=8))

__all__ = ["fetch_feed", "FeedItem"]


class FeedItem:
    __slots__ = ("guid", "title", "summary", "link", "author", "pub_time",
                 "is_st", "importance", "symbol")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k, ""))
        if isinstance(self.pub_time, str):
            self.pub_time = _parse_dt(self.pub_time)

    def to_dict(self) -> dict:
        return {
            "guid": self.guid or self.link or "",
            "title": self.title or "",
            "summary": self.summary or "",
            "link": self.link or "",
            "author": self.author or "",
            "pub_time": self.pub_time,
            "is_st": bool(self.is_st),
            "importance": self.importance or 3,
            "symbol": self.symbol or "",
        }


def fetch_feed(url: str, timeout: float = 10.0) -> list[FeedItem]:
    """拉取单个 RSSHub/自定义订阅地址，返回统一 FeedItem 列表"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DeepAStockBot/1.0; +https://github.com)",
            "Accept": "application/rss+xml, application/xml, application/json, text/xml, */*",
        },
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read()
    content_type = resp.headers.get("Content-Type", "")
    text = _decode(raw, content_type)

    if text.lstrip().startswith("{"):
        return _parse_json(text)
    return _parse_xml(text)


# ── XML（RSS 2.0 / Atom / RSS 1.0）───────────────────────────

def _parse_xml(text: str) -> list[FeedItem]:
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        logger.warning(f"XML 解析失败: {e}")
        return []
    ns = root.tag.split("}")[0] + "}" if "{" in root.tag else ""
    # Atom: feed/entry
    if root.tag.endswith("feed") or (ns and "atom" in root.nsmap.get("", ns.strip("{}")).lower()):
        return [_atom_entry(e) for e in root.findall(f"{ns}entry") or root.findall("entry")]
    # RSS 1.0 (rdf:RDF) → item
    rdf_ns = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
              "rss": "http://purl.org/rss/1.0/"}
    rdf_items = root.findall(".//rdf:item", rdf_ns) or root.findall(".//rss:item", rdf_ns)
    if rdf_items:
        return [_rss1_item(e, rdf_ns) for e in rdf_items]
    # RSS 2.0: channel/item
    items = root.findall(".//item") or root.findall(".//channel/item")
    return [_rss2_item(e) for e in items]


def _rss2_item(el) -> FeedItem:
    def txt(tag, default=""):
        node = el.find(tag)
        return (node.text or "").strip() if node is not None else default
    title = txt("title")
    summary = txt("description")
    pub = txt("pubDate")
    guid = txt("guid") or txt("link") or title
    author = txt("author") or txt("{http://purl.org/dc/elements/1.1/}creator")
    st = _ST_RE.search(title) or _ST_RE.search(summary)
    return FeedItem(guid=guid, title=title, summary=summary, link=txt("link"),
                    author=author, pub_time=pub, is_st=st,
                    importance=_calc_importance(title, summary),
                    symbol=_extract_symbol(title + summary))


def _atom_entry(el) -> FeedItem:
    ns = el.tag.split("}")[0] + "}" if "{" in el.tag else ""
    def txt(tag, default=""):
        node = el.find(f"{ns}{tag}") or el.find(tag)
        if node is None:
            return default
        return (node.text or "").strip() or node.get("title", "") or ""
    title = txt("title")
    summary = txt("summary") or txt("content")
    link_node = el.find(f"{ns}link") or el.find("link")
    link = link_node.get("href", "") if link_node is not None else ""
    pub = txt("published") or txt("updated") or txt("dc:date")
    guid = txt("id") or link or title
    st = _ST_RE.search(title) or _ST_RE.search(summary)
    return FeedItem(guid=guid, title=title, summary=summary, link=link, pub_time=pub,
                    is_st=st, importance=_calc_importance(title, summary),
                    symbol=_extract_symbol(title + summary))


def _rss1_item(el, ns) -> FeedItem:
    def txt(tag, default=""):
        node = el.find(f"rss:{tag}", ns) or el.find(tag)
        return (node.text or "").strip() if node is not None else default
    title = txt("title")
    summary = txt("description")
    link = txt("link")
    pub = txt("date")
    guid = txt("{http://purl.org/dc/elements/1.1/}identifier") or link or title
    st = _ST_RE.search(title) or _ST_RE.search(summary)
    return FeedItem(guid=guid, title=title, summary=summary, link=link, pub_time=pub,
                    is_st=st, importance=_calc_importance(title, summary),
                    symbol=_extract_symbol(title + summary))


# ── JSON Feed ──────────────────────────────────────────────────

def _parse_json(text: str) -> list[FeedItem]:
    try:
        data = json.loads(text)
    except Exception as e:
        logger.warning(f"JSON Feed 解析失败: {e}")
        return []
    items = data.get("items", [])
    out = []
    for it in items:
        title = (it.get("title") or "").strip()
        summary = (it.get("content_text") or it.get("content_html") or "").strip()
        link = it.get("url") or ""
        guid = it.get("id") or link or title
        pub = it.get("date_published") or it.get("date_modified") or ""
        author_obj = it.get("author") or {}
        author = author_obj.get("name", "") if isinstance(author_obj, dict) else str(author_obj)
        st = _ST_RE.search(title) or _ST_RE.search(summary)
        out.append(FeedItem(guid=guid, title=title, summary=summary, link=link,
                            author=author, pub_time=pub, is_st=st,
                            importance=_calc_importance(title, summary),
                            symbol=_extract_symbol(title + summary)))
    return out


# ── 通用工具 ──────────────────────────────────────────────────

def _decode(raw: bytes, ct: str) -> str:
    import re as _re
    m = _re.search(r"charset=([^\s;]+)", ct, _re.IGNORECASE)
    enc = m.group(1) if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime(*email.utils.parsedate_tz(s)[:6],
                        tzinfo=_CN_TZ if email.utils.parsedate_tz(s)[9] == 0 else None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_CN_TZ)
            return dt
        except ValueError:
            continue
    return None


def _calc_importance(title: str, summary: str) -> int:
    txt = title + summary
    if any(kw in txt for kw in _IMPORTANCE_KW_HIGH):
        return 1
    if any(kw in txt for kw in _IMPORTANCE_KW_MID):
        return 2
    return 3


def _extract_symbol(txt: str) -> str:
    m = _SYMBOL_RE.search(txt)
    return m.group(1) if m else ""