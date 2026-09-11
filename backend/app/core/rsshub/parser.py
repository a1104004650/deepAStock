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
_WEIBO_USER_RE = re.compile(r"/weibo/user/(\d+)")
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
    # 微博用户订阅：直连 m.weibo.cn，无需 RSSHub / docker 环境变量
    m = _WEIBO_USER_RE.search(url)
    if m:
        return _fetch_weibo_user(m.group(1), timeout)

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

    # 明确的网页而非订阅源：直接报错，避免 silently 返回空导致「看起来没有同步」
    head = text.lstrip()[:128].lower()
    if (content_type.startswith("text/html")
            or head.startswith("<!doctype html") or head.startswith("<html")):
        raise ValueError(
            f"地址返回的是 HTML 网页（{url}），不是 RSS/Atom/JSON 订阅；"
            "微博等平台需使用 RSSHub 路径，如 /weibo/user/{uid}")

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

def _fetch_weibo_user(uid: str, timeout: float = 10.0) -> list[FeedItem]:
    """直连 m.weibo.cn 拉取用户微博（复用「设置 → RSSHub 订阅」里的 weibo_cookies）"""
    from app.core.settings.service import get_setting
    cookie = get_setting("weibo_cookies", "")
    if not cookie:
        raise ValueError("微博订阅需要登录 Cookie：请在「设置 → RSSHub 订阅」/「订阅消息 → RSSHub 配置」填写微博 Cookie")

    def _get(url: str):
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": f"https://m.weibo.cn/u/{uid}",
            "Cookie": cookie,
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    try:
        idx = _get(f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}")
    except urllib.error.HTTPError as e:
        raise ValueError(f"微博接口返回 {e.code}：Cookie 可能失效，请重新登录 m.weibo.cn 更新") from e
    data = idx.get("data") or {}
    tabs = ((data.get("tabsInfo") or {}).get("tabs")) or []
    containerid = next((t.get("containerid") for t in tabs if t.get("tab_type") == "weibo"), None)
    if not containerid:
        raise ValueError("微博页面未找到内容 Tab：Cookie 可能失效，请重新登录 m.weibo.cn 后更新")
    user_name = (data.get("userInfo") or {}).get("screen_name") or uid
    cards_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid={containerid}"
    cards = (_get(cards_url).get("data") or {}).get("cards") or []

    out: list[FeedItem] = []
    for card in cards:
        mb = card.get("mblog")
        if not mb:
            continue
        bid = mb.get("bid") or mb.get("id") or ""
        text = _weibo_html_to_text(mb.get("text") or "")
        if (mb.get("pics") or []) and text:
            text += "\n" + "\n".join(
                f"[图片] {p.get('large', {}).get('url') or p.get('url', '')}"
                for p in mb["pics"] if p.get("large", {}).get("url") or p.get("url"))
        ret = mb.get("retweeted_status")
        if ret and ret.get("text"):
            text += ("\n[转发] " + _weibo_html_to_text(ret["text"]))
        title = text[:60].strip() or bid
        raw_t = mb.get("created_at") or ""
        st = _ST_RE.search(text) or _ST_RE.search(title)
        out.append(FeedItem(
            guid=f"weibo:{uid}:{bid}",
            title=title,
            summary=text,
            link=f"https://m.weibo.cn/detail/{bid}" if bid else f"https://m.weibo.cn/u/{uid}",
            author=user_name,
            pub_time=_parse_weibo_dt(raw_t),
            is_st=st,
            importance=_calc_importance(title, text),
            symbol=_extract_symbol(text + title),
        ))
    if not out:
        raise ValueError("微博接口未返回内容（Cookie 可能失效或该用户无可见微博）")
    return out


def _weibo_html_to_text(html: str) -> str:
    import html as _h
    txt = _h.unescape(html or "")
    txt = re.sub(r"<br\s*/?>", "\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{2,}", "\n", txt)
    return txt.strip()


def _parse_weibo_dt(s: str):
    """m.weibo.cn 时间格式如 'Wed Apr 12 10:00:00 +0800 2023'"""
    m = re.search(r"(\w{3} \w{3} \d{2} \d{2}:\d{2}:\d{2}) \+0800 (\d{4})", s or "")
    if not m:
        return _parse_dt(s)
    try:
        return datetime.strptime(m.group(1) + " " + m.group(2), "%a %b %d %H:%M:%S %Y").replace(tzinfo=_CN_TZ)
    except ValueError:
        return _parse_dt(s)

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