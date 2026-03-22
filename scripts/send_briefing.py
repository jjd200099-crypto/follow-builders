#!/usr/bin/env python3
"""
每日简报 v8 — 6-section Daily Briefing
VC blogs via WP API + Sitemap + Google News RSS fallback
"""

import json
import os
import re
import smtplib
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import unescape
from urllib.request import Request, urlopen

PODCAST_FEED_URL = "https://raw.githubusercontent.com/jjd200099-crypto/vc-daily-briefing/main/feed-podcasts.json"

FUNDING_SOURCES = [
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/"},
    {"name": "TechCrunch Venture", "url": "https://techcrunch.com/category/venture/feed/"},
    {"name": "SaaStr", "url": "https://www.saastr.com/feed/"},
    {"name": "CB Insights", "url": "https://www.cbinsights.com/research/feed/"},
    {"name": "AlleyWatch", "url": "https://www.alleywatch.com/feed/"},
    {"name": "Sifted (EU)", "url": "https://sifted.eu/feed"},
    {"name": "Bloomberg Tech", "url": "https://feeds.bloomberg.com/technology/news.rss"},
    {"name": "36Kr", "url": "https://36kr.com/feed"},
    {"name": "FinSMES", "url": "https://www.finsmes.com/feed"},
]

TECH_SOURCES = [
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/"},
    {"name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/"},
    {"name": "Microsoft AI Blog", "url": "https://blogs.microsoft.com/ai/feed/"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Apple ML Research", "url": "https://machinelearning.apple.com/rss.xml"},
]

MEDIA_SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
]

# ── VC Sources: 3 tiers ───────────────────────────────────────────────────
# Tier 1: WordPress JSON API (reliable, structured)
VC_WP_API = [
    {"name": "Greylock Partners", "api": "https://greylock.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Lightspeed", "api": "https://lsvp.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Kleiner Perkins", "api": "https://www.kleinerperkins.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Union Square Ventures", "api": "https://www.usv.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Founders Fund", "api": "https://foundersfund.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Above the Crowd (Benchmark)", "api": "https://abovethecrowd.com/wp-json/wp/v2/posts?per_page=5"},
]

# Tier 2: Sitemap parsing (has dates)
VC_SITEMAP = [
    {"name": "a16z", "sitemap": "https://a16z.com/post-sitemap3.xml", "base": "https://a16z.com"},
    {"name": "Bessemer Venture Partners", "sitemap": "https://www.bvp.com/post-sitemap.xml", "base": "https://www.bvp.com"},
]

# Tier 3: RSS feed
VC_RSS = [
    {"name": "Y Combinator", "url": "https://www.ycombinator.com/blog/rss/"},
]

# Tier 4: Google News RSS (universal fallback for VCs without APIs)
VC_GOOGLE_NEWS = [
    {"name": "a16z / Andreessen Horowitz", "query": '"andreessen horowitz" OR "a16z"'},
    {"name": "Sequoia Capital", "query": '"sequoia capital"'},
    {"name": "Accel", "query": '"accel partners" OR "accel ventures"'},
    {"name": "General Catalyst", "query": '"general catalyst"'},
    {"name": "Index Ventures", "query": '"index ventures"'},
    {"name": "Felicis Ventures", "query": '"felicis ventures"'},
    {"name": "Khosla Ventures", "query": '"khosla ventures"'},
    {"name": "Tiger Global", "query": '"tiger global"'},
]

BLOG_SOURCES = [
    {"name": "Stratechery", "url": "https://stratechery.com/feed/"},
    {"name": "Not Boring", "url": "https://www.notboring.co/feed"},
    {"name": "Lenny's Newsletter", "url": "https://www.lennysnewsletter.com/feed"},
    {"name": "Late Checkout", "url": "https://www.latecheckout.co/feed"},
    {"name": "kwokchain", "url": "https://kwokchain.com/feed/"},
    {"name": "Deconstructor of Fun", "url": "https://www.deconstructoroffun.com/blog?format=rss"},
]

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
RECIPIENTS = [e.strip() for e in os.environ.get("RECIPIENT_EMAIL", "jjd200099@gmail.com").split(",") if e.strip()]
BJT = timezone(timedelta(hours=8))

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ── HTTP Helpers ────────────────────────────────────────────────────────────

def http_get(url, timeout=15):
    req = Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "text/html, application/rss+xml, application/xml, application/json, */*",
    })
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def ensure_aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def parse_rss_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    try:
        return ensure_aware(datetime.fromisoformat(date_str.replace("Z", "+00:00")))
    except ValueError:
        pass
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%a, %d %b %Y %H:%M:%S", "%d %b %Y %H:%M:%S %z",
                "%d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return ensure_aware(datetime.strptime(date_str, fmt))
        except ValueError:
            continue
    return None

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()

# ── RSS Fetching ────────────────────────────────────────────────────────────

def fetch_rss_entries(sources, cutoff):
    entries = []
    for source in sources:
        try:
            xml_text = http_get(source["url"])
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//item")
            if items:
                for item in items[:10]:
                    title = item.findtext("title", "Untitled")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    desc = item.findtext("description", "")
                    dt = parse_rss_date(pub_date)
                    if dt and dt >= cutoff:
                        entries.append({
                            "source": source["name"], "title": strip_html(title),
                            "url": (link or "").strip(), "publishedAt": dt.isoformat(),
                            "snippet": strip_html(desc)[:800],
                        })
                continue
            atom_entries = root.findall("atom:entry", ns)
            if not atom_entries:
                atom_entries = root.findall("entry")
            for entry in (atom_entries or [])[:10]:
                title = entry.findtext("atom:title", "", ns) or entry.findtext("title", "Untitled")
                link_el = (entry.find("atom:link[@rel='alternate']", ns)
                           or entry.find("atom:link", ns) or entry.find("link"))
                link = link_el.get("href", "") if link_el is not None else ""
                pub = (entry.findtext("atom:published", "", ns)
                       or entry.findtext("atom:updated", "", ns)
                       or entry.findtext("published", "")
                       or entry.findtext("updated", ""))
                summary_el = (entry.findtext("atom:summary", "", ns)
                              or entry.findtext("atom:content", "", ns)
                              or entry.findtext("summary", "")
                              or entry.findtext("content", ""))
                dt = parse_rss_date(pub)
                if dt and dt >= cutoff:
                    entries.append({
                        "source": source["name"], "title": strip_html(title),
                        "url": (link or "").strip(), "publishedAt": dt.isoformat(),
                        "snippet": strip_html(summary_el)[:800],
                    })
        except Exception as e:
            print(f"[WARN] RSS error {source['name']}: {e}", file=sys.stderr)
    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries

def fetch_podcast_feed():
    try:
        data = json.loads(http_get(PODCAST_FEED_URL))
        return data.get("podcasts", [])
    except Exception as e:
        print(f"[WARN] Podcast feed error: {e}", file=sys.stderr)
        return []

# ── VC Blog Fetching (3-tier) ──────────────────────────────────────────────

def fetch_vc_wp_api(cutoff):
    """Tier 1: Fetch from WordPress JSON API."""
    entries = []
    for vc in VC_WP_API:
        try:
            data = json.loads(http_get(vc["api"]))
            for post in data:
                pub = post.get("date_gmt", post.get("date", ""))
                dt = parse_rss_date(pub)
                if dt and dt >= cutoff:
                    title = strip_html(post.get("title", {}).get("rendered", "Untitled"))
                    link = post.get("link", "")
                    excerpt = strip_html(post.get("excerpt", {}).get("rendered", ""))
                    content = strip_html(post.get("content", {}).get("rendered", ""))
                    entries.append({
                        "source": vc["name"], "title": title,
                        "url": link, "publishedAt": dt.isoformat(),
                        "snippet": (excerpt or content)[:800],
                    })
            print(f"  WP API: {vc['name']} OK", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] WP API {vc['name']}: {e}", file=sys.stderr)
    return entries

def fetch_vc_sitemap(cutoff):
    """Tier 2: Parse sitemap.xml for recent posts."""
    entries = []
    for vc in VC_SITEMAP:
        try:
            xml_text = http_get(vc["sitemap"])
            root = ET.fromstring(xml_text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            urls = root.findall(".//sm:url", ns)
            if not urls:
                urls = root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url")
            count = 0
            for url_el in urls:
                loc = url_el.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc", "")
                lastmod = url_el.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod", "")
                dt = parse_rss_date(lastmod)
                if dt and dt >= cutoff and loc:
                    # Extract title from URL slug
                    slug = loc.rstrip("/").split("/")[-1]
                    title = slug.replace("-", " ").title()
                    entries.append({
                        "source": vc["name"], "title": title,
                        "url": loc, "publishedAt": dt.isoformat(),
                        "snippet": "",
                    })
                    count += 1
                    if count >= 5:
                        break
            print(f"  Sitemap: {vc['name']} → {count} posts", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Sitemap {vc['name']}: {e}", file=sys.stderr)
    return entries

def fetch_vc_google_news(cutoff):
    """Tier 4: Google News RSS search for VCs without APIs."""
    entries = []
    for vc in VC_GOOGLE_NEWS:
        try:
            from urllib.parse import quote
            query = quote(vc["query"])
            rss_url = f"https://news.google.com/rss/search?q={query}+when:3d&hl=en-US&gl=US&ceid=US:en"
            xml_text = http_get(rss_url)
            root = ET.fromstring(xml_text)
            count = 0
            for item in root.findall(".//item")[:5]:
                title = strip_html(item.findtext("title", ""))
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                dt = parse_rss_date(pub_date)
                if dt and dt >= cutoff:
                    entries.append({
                        "source": vc["name"], "title": title,
                        "url": link, "publishedAt": dt.isoformat(),
                        "snippet": strip_html(item.findtext("description", ""))[:500],
                    })
                    count += 1
            print(f"  Google News: {vc['name']} → {count} articles", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Google News {vc['name']}: {e}", file=sys.stderr)
    return entries

def fetch_all_vc_content(cutoff):
    """Combine all VC content from all tiers."""
    print("  Tier 1: WordPress API...", file=sys.stderr)
    wp = fetch_vc_wp_api(cutoff)
    print("  Tier 2: Sitemap...", file=sys.stderr)
    sitemap = fetch_vc_sitemap(cutoff)
    print("  Tier 3: RSS...", file=sys.stderr)
    rss = fetch_rss_entries(VC_RSS, cutoff)
    for e in rss:
        e["source"] = "Y Combinator"  # ensure source name
    print("  Tier 4: Google News...", file=sys.stderr)
    gnews = fetch_vc_google_news(cutoff)

    all_entries = wp + sitemap + rss + gnews
    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for e in all_entries:
        key = e["title"].lower()[:50]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(e)
    unique.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return unique


# ── Gemini AI ──────────────────────────────────────────────────────────────

def gemini_call(prompt, max_tokens=8192):
    if not GEMINI_API_KEY:
        return ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
    }).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[WARN] Gemini error: {e}", file=sys.stderr)
        return ""

def extract_funding_deals(entries):
    if not entries:
        return "暂无融资交易"
    items = []
    for i, e in enumerate(entries):
        items.append(f"[{i}] 来源: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')}\n    链接: {e['url']}\n    时间: {e['publishedAt'][:16].replace('T',' ')}")
    prompt = f"""你是一位资深的AI行业投融资分析师。请从以下新闻中筛选出所有与AI/科技相关的融资交易（Series A/B/C/D、种子轮、IPO、收购等），并按以下格式输出。跳过非融资新闻。

新闻列表：
{chr(10).join(items)}

格式（每笔交易之间空行分隔）：

公司名 - $金额 - 轮次
公司简介：一句话描述
业务亮点：
• 亮点1
• 亮点2
• 亮点3（如有）
融资用途：一句话
领投方：机构名（未提及写"未披露"）
发布时间：从原文推断
原文：链接URL

没有则输出"暂无融资交易"。"""
    return gemini_call(prompt, 6144)

def extract_tech_breakthroughs(entries):
    if not entries:
        return "暂无重大技术突破"
    items = []
    for i, e in enumerate(entries):
        items.append(f"[{i}] 来源: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')}\n    链接: {e['url']}\n    时间: {e['publishedAt'][:16].replace('T',' ')}")
    prompt = f"""你是一位资深的AI技术分析师。请从以下新闻中筛选出重要的AI技术突破、新模型发布、重大产品更新。跳过融资和一般评论。

新闻列表：
{chr(10).join(items)}

格式（每条之间空行分隔）：

产品/模型名称
简介：一句话概述
核心突破：为什么重要
关键特性：
• 特性1
• 特性2
• 特性3（如有）
发布时间：从原文推断
原文：链接URL

没有则输出"暂无重大技术突破"。"""
    return gemini_call(prompt, 6144)

def summarize_vc_content(entries):
    """Generate structured VC update summaries."""
    if not entries:
        return "暂无 VC 动态更新"
    items = []
    for i, e in enumerate(entries):
        items.append(f"[{i}] VC: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')[:500]}\n    链接: {e['url']}\n    时间: {e['publishedAt'][:16].replace('T',' ')}")
    prompt = f"""你是一位资深的科技投资领域分析师。请为以下湾区顶级VC的最新动态各写一段详细的中文摘要。

内容列表：
{chr(10).join(items)}

对于每条内容，请按以下格式输出：

[VC名称] 文章/新闻标题
简介：1-2句话概述
核心观点：
• 观点1
• 观点2
• 观点3（如有）
涉及公司/领域：提到的公司或投资领域
原文：链接URL

请确保：
- 如果标题是英文，翻译成中文后再分析
- 如果内容是关于投资交易，说明金额、轮次、被投公司
- 如果是观点文章，提炼核心论点
- 跳过明显过时或无实质内容的条目"""
    return gemini_call(prompt, 6144)

def summarize_items(entries, section_desc):
    if not entries:
        return {}
    items = []
    for i, e in enumerate(entries):
        name = e.get("source", e.get("name", "Unknown"))
        snippet = e.get("snippet", e.get("transcript", ""))
        items.append(f"{i+1}. [{name}] {e.get('title','')}\n   内容片段: {str(snippet)[:500] if snippet else '无'}")
    prompt = (
        f"你是一位资深的科技投资领域分析师。请为以下{section_desc}各写一段详细的中文摘要（4-6句话）。\n"
        f"摘要需包括：核心论点、关键数据或案例、对投资者/创业者/从业者的启示。\n"
        f"如果标题是英文，请翻译后再总结。\n\n"
        + "\n".join(items) + "\n\n请严格按编号给出摘要：\n1. 摘要\n2. 摘要\n..."
    )
    text = gemini_call(prompt, 6144)
    if not text:
        return {}
    summaries = {}
    for m in re.finditer(r"(\d+)[.、]\s*(.+?)(?=\n\d+[.、]|\Z)", text, re.DOTALL):
        summaries[int(m.group(1)) - 1] = m.group(2).strip()
    return summaries

# ── Email ──────────────────────────────────────────────────────────────────

def format_item(idx, entry, summary=None):
    lines = []
    source = entry.get("source", entry.get("name", ""))
    title = entry.get("title", "Untitled")
    url = entry.get("url", "")
    pub = entry.get("publishedAt", "")[:16].replace("T", " ")
    lines.append(f"  {idx}. [{source}] {title}")
    lines.append(f"     🕐 {pub}")
    if url:
        lines.append(f"     🔗 {url}")
    if summary:
        lines.append(f"     📝 {summary}")
    lines.append("")
    return lines

def format_briefing(funding_text, tech_text, vc_text,
                    media_entries, media_summaries,
                    podcasts, podcast_summaries, blogs, blog_summaries):
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    sep = "─" * 52
    double_sep = "═" * 60
    lines = [double_sep, f"  📋 每日简报 — {today}", double_sep, ""]

    lines.append("💰 融资头条")
    lines.append(sep)
    lines.append("")
    lines.append(funding_text or "  暂无融资交易")
    lines.extend(["", ""])

    lines.append("🚀 技术突破")
    lines.append(sep)
    lines.append("")
    lines.append(tech_text or "  暂无重大技术突破")
    lines.extend(["", ""])

    lines.append("🏛 湾区顶级 VC 动态")
    lines.append(sep)
    lines.append("")
    lines.append(vc_text or "  暂无 VC 动态更新")
    lines.extend(["", ""])

    lines.append(f"📡 科技媒体更新（{len(media_entries)} 篇）")
    lines.append(sep)
    lines.append("")
    if media_entries:
        for i, e in enumerate(media_entries):
            lines.extend(format_item(i + 1, e, media_summaries.get(i)))
    else:
        lines.append("  今日暂无媒体更新")
        lines.append("")
    lines.append("")

    lines.append(f"🎙 播客追踪（{len(podcasts)} 期新节目）")
    lines.append(sep)
    lines.append("")
    if podcasts:
        for i, ep in enumerate(podcasts):
            lines.extend(format_item(i + 1, ep, podcast_summaries.get(i)))
    else:
        lines.append("  今日暂无新节目")
        lines.append("")
    lines.append("")

    lines.append(f"📰 行业资讯（{len(blogs)} 篇新文章）")
    lines.append(sep)
    lines.append("")
    if blogs:
        for i, e in enumerate(blogs):
            lines.extend(format_item(i + 1, e, blog_summaries.get(i)))
    else:
        lines.append("  今日暂无新文章")
        lines.append("")
    lines.append("")

    lines.extend([double_sep, "  Generated by VC 每日简报", double_sep])
    return "\n".join(lines)

def send_gmail(subject, body):
    msg = MIMEMultipart("alternative")
    msg["From"] = f"每日简报 <{GMAIL_USER}>"
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENTS, msg.as_string())
    print(f"Email sent to {len(RECIPIENTS)} recipients: {', '.join(RECIPIENTS)}", file=sys.stderr)

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("GMAIL_USER or GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(0)

    today = datetime.now(BJT).strftime("%Y-%m-%d")
    lookback_hours = 72
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Podcasts
    print("Fetching podcast feed...", file=sys.stderr)
    all_podcasts = fetch_podcast_feed()
    podcasts = []
    for ep in all_podcasts:
        pub = ep.get("publishedAt", "")
        if not pub:
            continue
        try:
            dt = ensure_aware(datetime.fromisoformat(pub.replace("Z", "+00:00")))
            if dt >= cutoff:
                podcasts.append(ep)
        except ValueError:
            pass
    podcasts.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    print(f"  {len(podcasts)} podcasts", file=sys.stderr)

    # RSS sections
    print("Fetching funding news...", file=sys.stderr)
    funding_entries = fetch_rss_entries(FUNDING_SOURCES, cutoff)
    print(f"  {len(funding_entries)} funding articles", file=sys.stderr)

    print("Fetching tech blogs...", file=sys.stderr)
    tech_entries = fetch_rss_entries(TECH_SOURCES, cutoff)
    print(f"  {len(tech_entries)} tech articles", file=sys.stderr)

    print("Fetching tech media...", file=sys.stderr)
    media_entries = fetch_rss_entries(MEDIA_SOURCES, cutoff)
    print(f"  {len(media_entries)} media articles", file=sys.stderr)

    print("Fetching industry blogs...", file=sys.stderr)
    blogs = fetch_rss_entries(BLOG_SOURCES, cutoff)
    print(f"  {len(blogs)} blog posts", file=sys.stderr)

    # VC content (multi-tier)
    print("Fetching VC content (multi-tier)...", file=sys.stderr)
    vc_entries = fetch_all_vc_content(cutoff)
    print(f"  Total: {len(vc_entries)} VC items", file=sys.stderr)

    # Gemini analysis
    print("Generating AI analysis...", file=sys.stderr)
    funding_text = extract_funding_deals(funding_entries)
    print("  ✓ Funding deals", file=sys.stderr)
    tech_text = extract_tech_breakthroughs(tech_entries)
    print("  ✓ Tech breakthroughs", file=sys.stderr)
    vc_text = summarize_vc_content(vc_entries)
    print("  ✓ VC updates", file=sys.stderr)
    media_summaries = summarize_items(media_entries[:15], "科技媒体报道")
    print(f"  ✓ {len(media_summaries)} media summaries", file=sys.stderr)
    podcast_summaries = summarize_items(podcasts, "播客节目（请根据标题和嘉宾信息推断内容）")
    print(f"  ✓ {len(podcast_summaries)} podcast summaries", file=sys.stderr)
    blog_summaries = summarize_items(blogs, "独立分析师/newsletter文章")
    print(f"  ✓ {len(blog_summaries)} blog summaries", file=sys.stderr)

    # Send
    body = format_briefing(
        funding_text, tech_text, vc_text,
        media_entries[:15], media_summaries,
        podcasts, podcast_summaries, blogs, blog_summaries,
    )
    total = len(vc_entries) + len(media_entries[:15]) + len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total}+ 条更新）"
    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)

if __name__ == "__main__":
    main()
