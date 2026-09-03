#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
咖啡资讯每日聚合器 —— 多源 -> 一条 RSS 2.0（零依赖，仅用 Python 标准库）

功能：
  - 读 feeds.toml（可编辑的订阅源清单）
  - 支持两类源：
      type=rss     : 源站自带 RSS/Atom，直接拉取合并
      type=scrape  : 源站无 RSS，按内置 scraper 抓取（scraper 见 SCRAPERS）
  - 合并、去重、按发布时间倒序，输出一条 feed.xml（RSS 2.0）
  - 同时生成 index.html 方便在 Pages 上预览

设计目标：能在 GitHub Actions 里只用 Python 标准库跑起来，
每天定时生成 feed.xml 并发布到 GitHub Pages，得到一个永久订阅链接。

用法：
  python coffee_news_aggregator.py                 # 输出到 ./public/feed.xml + index.html
  python coffee_news_aggregator.py --limit 40      # 限制条目数
  python coffee_news_aggregator.py --with-content  # 抓正文摘要（更慢）
  python coffee_news_aggregator.py --config feeds.toml --out public
"""

import argparse
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# 说明：部分站点（Perfect Daily Grind / Sprudge）的 WAF 会按 UA 拦截
# 浏览器 UA 与 "Mozilla/5.0 (compatible; ...)" 均被 403；
# 经验证 "curl/8.0" 对全部源均可正常返回 200。
UA = "curl/8.0"
CST = timezone(timedelta(hours=8))  # 中国时区 +0800


# ----------------------------------------------------------------------------
# 网络与文本工具
# ----------------------------------------------------------------------------
def fetch(url: str, timeout: int = 25, retries: int = 3) -> str:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            enc = "utf-8"
            m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw, re.I)
            if m:
                enc = m.group(1).decode("ascii", "ignore") or "utf-8"
            try:
                return raw.decode(enc, errors="ignore")
            except (LookupError, UnicodeDecodeError):
                return raw.decode("utf-8", errors="ignore")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                import time

                time.sleep(2 * attempt)
    raise last_err if last_err else RuntimeError("fetch failed")


def clean(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def esc(text: str) -> str:
    if text is None:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ----------------------------------------------------------------------------
# 日期解析
# ----------------------------------------------------------------------------
def parse_date_any(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=CST)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=CST)
    except ValueError:
        pass
    m = re.search(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})日?", s)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=CST
            )
        except ValueError:
            pass
    return None


def to_rfc822(dt):
    if dt is None:
        dt = datetime.now(CST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CST)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


# ----------------------------------------------------------------------------
# 条目结构
# ----------------------------------------------------------------------------
def mk(title, link, pub, desc, source, layer):
    return {
        "title": title or "(无标题)",
        "link": link or "",
        "pub": pub,
        "desc": desc or "",
        "source": source or "",
        "layer": layer or "",
    }


# ----------------------------------------------------------------------------
# RSS / Atom 解析
# ----------------------------------------------------------------------------
def text_of(parent, tag):
    el = parent.find(tag)
    if el is None:
        # 也尝试带命名空间
        for child in parent.iter():
            if child.tag.split("}")[-1] == tag.split("}")[-1]:
                el = child
                break
    return clean(el.text) if el is not None and el.text else ""


def atom_link(entry):
    # Atom <link href="...">
    for el in entry.iter():
        if el.tag.split("}")[-1] == "link":
            href = el.get("href")
            if href:
                return href
    return ""


def parse_feed(xml_text: str, source_name: str, layer: str):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0
    for item in root.iter("item"):
        title = text_of(item, "title")
        link = text_of(item, "link") or atom_link(item)
        pub = parse_date_any(text_of(item, "pubDate"))
        desc = text_of(item, "description")
        if title:
            items.append(mk(title, link, pub, desc, source_name, layer))
    if items:
        return items

    # Atom
    for entry in root.iter():
        if entry.tag.split("}")[-1] != "entry":
            continue
        title = text_of(entry, "{http://www.w3.org/2005/Atom}title") or text_of(
            entry, "title"
        )
        link = atom_link(entry)
        raw = text_of(entry, "updated") or text_of(entry, "published")
        pub = parse_date_any(raw)
        desc = (
            text_of(entry, "{http://www.w3.org/2005/Atom}summary")
            or text_of(entry, "{http://www.w3.org/2005/Atom}content")
            or text_of(entry, "summary")
        )
        if title:
            items.append(mk(title, link, pub, desc, source_name, layer))
    return items


# ----------------------------------------------------------------------------
# 抓取器（scraper）：源站无 RSS 时用
# ----------------------------------------------------------------------------
def scrape_yunnong(url: str):
    """云南省农业农村厅·云农快讯：ul.zxwj-list-ul > li"""
    html = fetch(url)
    items = []
    ul = re.search(r'<ul class="zxwj-list-ul">(.*?)</ul>', html, re.S)
    if not ul:
        return items
    base = "https://nync.yn.gov.cn"
    for li in re.findall(r"<li>(.*?)</li>", ul.group(1), re.S):
        a = re.search(r'<a href="(/html/[^"]+\.html)"[^>]*>(.*?)</a>', li, re.S)
        if not a:
            continue
        title = clean(a.group(2))
        if not title:
            continue
        href = a.group(1)
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", li)
        pub = parse_date_any(dm.group(1)) if dm else None
        items.append(mk(title, base + href, pub, "", "云南省农业农村厅·云农快讯", "yunnan"))
    return items


def scrape_coffinance(url: str):
    """咖啡金融网：首页价格快讯 + /mess/ 最新文章"""
    base = url.rstrip("/")
    items = []

    # 1) 首页价格快讯（标题自带日期）
    try:
        home = fetch(base + "/")
        for href, t in re.findall(
            r'<a[^>]*class="news-title[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            home,
            re.S,
        ):
            title = clean(t)
            if len(title) < 6:
                continue
            dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", title)
            pub = parse_date_any(dm.group(0)) if dm else None
            link = base + (href if href.startswith("/") else "/mess/")
            items.append(mk(title, link, pub, "", "咖啡金融网", "china"))
    except Exception as e:
        print(f"[warn] 咖啡金融网首页抓取失败：{e}", file=sys.stderr)

    # 2) /mess/ 最新文章（真实 /detail/ 链接，补抓发布日期）
    try:
        mhtml = fetch(base + "/mess/")
        arts = re.findall(
            r'<a href="(/detail/\d+)"[^>]*target="_blank"[^>]*>\s*&nbsp;\s*(.*?)\s*</a>',
            mhtml,
            re.S,
        )
        for href, t in arts[:8]:
            title = clean(t)
            if not title:
                continue
            pub = None
            try:
                d = fetch(base + href)
                dm = re.search(r"(\d{4}-\d{2}-\d{2})", d)
                if dm:
                    pub = parse_date_any(dm.group(1))
            except Exception:
                pass
            items.append(mk(title, base + href, pub, "", "咖啡金融网", "china"))
    except Exception as e:
        print(f"[warn] 咖啡金融网/mess/抓取失败：{e}", file=sys.stderr)

    return items


SCRAPERS = {
    "yunnong": scrape_yunnong,
    "coffinance": scrape_coffinance,
}


# ----------------------------------------------------------------------------
# 聚合
# ----------------------------------------------------------------------------
def aggregate(sources, limit=None):
    all_items = []
    for s in sources:
        name = s.get("name", "?")
        layer = s.get("layer", "")
        typ = s.get("type")
        url = s.get("url", "")
        try:
            if typ == "rss":
                its = parse_feed(fetch(url), name, layer)
            elif typ == "scrape":
                sc = s.get("scraper")
                its = SCRAPERS[sc](url) if sc in SCRAPERS else []
            else:
                its = []
            print(f"[info] {name}: {len(its)} 条", file=sys.stderr)
            all_items.extend(its)
        except Exception as e:
            print(f"[warn] {name} 抓取失败：{e}", file=sys.stderr)

    # 去重：优先以 link 去重，link 为空则退回 title
    seen = set()
    uniq = []
    for it in all_items:
        key = it["link"] or it["title"]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # 排序：有日期的按日期倒序在前，无日期的放最后（保持源顺序）
    def sort_key(it):
        p = it["pub"]
        if p is None or p.tzinfo is None:
            return datetime(1970, 1, 1, tzinfo=CST)
        return p

    uniq.sort(key=sort_key, reverse=True)
    if limit:
        uniq = uniq[:limit]
    return uniq


# ----------------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------------
def build_rss(items, feed_base=""):
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<rss version="2.0">')
    out.append("  <channel>")
    out.append("    <title>咖啡资讯每日聚合</title>")
    out.append(f"    <link>{esc(feed_base or 'https://github.com/')}</link>")
    out.append(
        "    <description>全球 / 全国 / 云南咖啡资讯每日聚合（新闻·价格·政策），由脚本生成</description>"
    )
    out.append(f"    <lastBuildDate>{to_rfc822(datetime.now(CST))}</lastBuildDate>")
    out.append("    <generator>CoffeeNewsAggregator 1.0</generator>")
    for it in items:
        desc = it["desc"] or f'<a href="{esc(it["link"])}">查看原文（来源：{esc(it["source"])}）</a>'
        out.append("    <item>")
        out.append(f"      <title>{esc(it['title'])}</title>")
        out.append(f"      <link>{esc(it['link'])}</link>")
        out.append(f"      <guid isPermaLink=\"true\">{esc(it['link'])}</guid>")
        out.append(f"      <pubDate>{to_rfc822(it['pub'])}</pubDate>")
        if it["layer"]:
            out.append(f"      <category>{esc(it['layer'])}</category>")
        out.append(f"      <source url=\"{esc(it['link'])}\">{esc(it['source'])}</source>")
        out.append(f"      <description><![CDATA[{desc}]]></description>")
        out.append("    </item>")
    out.append("  </channel>")
    out.append("</rss>")
    return "\n".join(out)


LAYER_ZH = {"global": "全球", "china": "全国", "yunnan": "云南", "policy": "政策"}


def build_index(items, feed_base=""):
    rows = []
    for it in items[:50]:
        zh = LAYER_ZH.get(it["layer"], it["layer"] or "其他")
        date = it["pub"].strftime("%Y-%m-%d") if it["pub"] else "—"
        rows.append(
            f'      <li><span class="tag">{esc(zh)}</span> '
            f'<a href="{esc(it["link"])}" target="_blank">{esc(it["title"])}</a>'
            f'<span class="meta">{esc(it["source"])} · {date}</span></li>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>咖啡资讯每日聚合</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.6; }}
  h1 {{ font-size: 1.5rem; }}
  .sub {{ color: #666; font-size: .9rem; margin-bottom: 1rem; }}
  .rss-btn {{ display:inline-block; background:#6f4e37; color:#fff; padding:.4rem .9rem;
             border-radius:6px; text-decoration:none; font-size:.85rem; }}
  ul {{ list-style:none; padding:0; }}
  li {{ padding:.55rem 0; border-bottom:1px solid #eee; }}
  .tag {{ display:inline-block; font-size:.7rem; padding:.1rem .45rem; border-radius:4px;
          background:#f0e6dd; color:#6f4e37; margin-right:.5rem; }}
  .meta {{ display:block; color:#999; font-size:.78rem; margin-top:.15rem; }}
  a {{ color:#2b2b2b; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
  <h1>☕ 咖啡资讯每日聚合</h1>
  <p class="sub">全球 / 全国 / 云南 · 新闻 · 价格 · 政策 &nbsp;|&nbsp; 更新于 {datetime.now(CST).strftime("%Y-%m-%d %H:%M")}</p>
  <p><a class="rss-btn" href="feed.xml">订阅 RSS</a></p>
  <ul>
{chr(10).join(rows)}
  </ul>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser(description="咖啡资讯每日聚合器")
    ap.add_argument("--config", default="feeds.toml", help="订阅源配置文件")
    ap.add_argument("--out", default="public", help="输出目录")
    ap.add_argument("--limit", type=int, default=60, help="最多生成的条目数")
    ap.add_argument("--with-content", action="store_true", help="抓取正文摘要（更慢）")
    ap.add_argument("--base", default="", help="feed 自托管基础地址（用于 RSS <link>）")
    args = ap.parse_args()

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    sources = cfg.get("sources", [])

    items = aggregate(sources, limit=args.limit)

    if not items:
        print("[error] 没有解析到任何条目，请检查 feeds.toml 或站点结构。", file=sys.stderr)
        sys.exit(1)

    import os

    os.makedirs(args.out, exist_ok=True)
    rss = build_rss(items, feed_base=args.base)
    with open(os.path.join(args.out, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(rss)
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(items, feed_base=args.base))

    print(
        f"[ok] 已生成 {len(items)} 条 -> {args.out}/feed.xml + index.html",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
