#!/usr/bin/env python3
"""
每日简报 v9 — 6-section Daily Briefing
VC blogs: WP API + HTML scraping + Sitemap (no Google News)
"""

import json
import os
import re
import smtplib
import sys
import time
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

# ── VC Sources ─────────────────────────────────────────────────────────────
# Tier 1: WordPress JSON API
VC_WP_API = [
    {"name": "Greylock Partners", "api": "https://greylock.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Lightspeed", "api": "https://lsvp.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Kleiner Perkins", "api": "https://www.kleinerperkins.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Union Square Ventures", "api": "https://www.usv.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Founders Fund", "api": "https://foundersfund.com/wp-json/wp/v2/posts?per_page=5"},
    {"name": "Above the Crowd (Benchmark)", "api": "https://abovethecrowd.com/wp-json/wp/v2/posts?per_page=5"},
]

# Tier 2: HTML scraping (server-side rendered)
VC_HTML_SCRAPE = [
    {"name": "a16z", "url": "https://a16z.com/content/", "base": "https://a16z.com"},
    {"name": "Accel", "url": "https://www.accel.com/noteworthy", "base": "https://www.accel.com"},
    {"name": "Index Ventures", "url": "https://www.indexventures.com/perspectives", "base": "https://www.indexventures.com"},
    {"name": "Felicis Ventures", "url": "https://www.felicis.com/insight", "base": "https://www.felicis.com"},
    {"name": "Bessemer Venture Partners", "url": "https://www.bvp.com/atlas", "base": "https://www.bvp.com"},
    {"name": "NEA", "url": "https://www.nea.com/blog", "base": "https://www.nea.com"},
    {"name": "8VC", "url": "https://www.8vc.com/resources", "base": "https://www.8vc.com"},
]

# Tier 3: RSS
VC_RSS = [
    {"name": "Y Combinator", "url": "https://www.ycombinator.com/blog/rss/"},
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

# ── HTTP ────────────────────────────────────────────────────────────────────

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
    return unescape(re.sub(r"<[^>]+>", "", text)).strip()

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
                    dt = parse_rss_date(item.findtext("pubDate", ""))
                    if dt and dt >= cutoff:
                        entries.append({
                            "source": source["name"],
                            "title": strip_html(item.findtext("title", "Untitled")),
                            "url": (item.findtext("link", "") or "").strip(),
                            "publishedAt": dt.isoformat(),
                            "snippet": strip_html(item.findtext("description", ""))[:800],
                        })
                continue
            for entry in (root.findall("atom:entry", ns) or root.findall("entry") or [])[:10]:
                title = entry.findtext("atom:title", "", ns) or entry.findtext("title", "Untitled")
                link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns) or entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                pub = entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or entry.findtext("published", "") or entry.findtext("updated", "")
                summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or entry.findtext("summary", "") or entry.findtext("content", "")
                dt = parse_rss_date(pub)
                if dt and dt >= cutoff:
                    entries.append({
                        "source": source["name"], "title": strip_html(title),
                        "url": (link or "").strip(), "publishedAt": dt.isoformat(),
                        "snippet": strip_html(summary)[:800],
                    })
        except Exception as e:
            print(f"[WARN] RSS error {source['name']}: {e}", file=sys.stderr)
    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries

def fetch_podcast_feed():
    try:
        return json.loads(http_get(PODCAST_FEED_URL)).get("podcasts", [])
    except Exception as e:
        print(f"[WARN] Podcast feed error: {e}", file=sys.stderr)
        return []

# ── VC Fetching ────────────────────────────────────────────────────────────

def fetch_vc_wp_api(cutoff):
    entries = []
    for vc in VC_WP_API:
        try:
            data = json.loads(http_get(vc["api"]))
            for post in data:
                dt = parse_rss_date(post.get("date_gmt", post.get("date", "")))
                if dt and dt >= cutoff:
                    entries.append({
                        "source": vc["name"],
                        "title": strip_html(post.get("title", {}).get("rendered", "Untitled")),
                        "url": post.get("link", ""),
                        "publishedAt": dt.isoformat(),
                        "snippet": strip_html(post.get("excerpt", {}).get("rendered", "") or post.get("content", {}).get("rendered", ""))[:800],
                    })
            print(f"    ✓ {vc['name']}", file=sys.stderr)
        except Exception as e:
            print(f"    ✗ {vc['name']}: {e}", file=sys.stderr)
    return entries

def fetch_vc_html(lookback_hours):
    """Scrape HTML pages and use Gemini to extract recent posts."""
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    pages = {}
    for vc in VC_HTML_SCRAPE:
        try:
            html = http_get(vc["url"], timeout=20)
            html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<nav[\s\S]*?</nav>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<footer[\s\S]*?</footer>", "", html, flags=re.IGNORECASE)
            pages[vc["name"]] = {"html": html[:10000], "url": vc["url"], "base": vc["base"]}
            print(f"    ✓ {vc['name']}", file=sys.stderr)
        except Exception as e:
            print(f"    ✗ {vc['name']}: {e}", file=sys.stderr)

    if not pages:
        return []

    pages_text = []
    for name, info in pages.items():
        pages_text.append(f"=== {name} ===\n页面URL: {info['url']}\n站点根URL: {info['base']}\nHTML:\n{info['html'][:8000]}\n")

    prompt = f"""你是一位资深的科技投资分析师。今天是 {today}。

我从以下湾区顶级 VC 的官网博客页面抓取了 HTML。请从中提取过去 {lookback_hours} 小时内发布的新文章/观点。

重要规则：
- 只提取 VC 自己写的原创文章/观点，不是转载新闻
- 根据页面上的日期判断是否在 {lookback_hours} 小时内
- 如果页面没有显示日期但文章在页面最顶部，标注"日期未确定，疑似近期发布"
- 从 HTML 中的 <a> 标签提取完整文章 URL（如果是相对路径，拼接站点根URL）
- 不要编造不存在的文章

请严格按以下 JSON 格式输出（不加 markdown 代码块标记）：
[
  {{"source": "VC名称", "title": "文章标题", "url": "完整URL", "snippet": "文章简介或摘要（如HTML中有的话）"}}
]

如果没有找到近期文章，输出空数组 []

HTML 内容：
{chr(10).join(pages_text)}"""

    text = gemini_call(prompt, 4096)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            try:
                items = json.loads(m.group())
            except json.JSONDecodeError:
                items = []
        else:
            items = []

    entries = []
    for item in items:
        entries.append({
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "publishedAt": datetime.now(timezone.utc).isoformat(),  # approximate
            "snippet": item.get("snippet", ""),
        })
    return entries

def fetch_all_vc_content(cutoff, lookback_hours):
    print("  WP API:", file=sys.stderr)
    wp = fetch_vc_wp_api(cutoff)
    print("  HTML scraping:", file=sys.stderr)
    html_entries = fetch_vc_html(lookback_hours)
    print("  RSS:", file=sys.stderr)
    rss = fetch_rss_entries(VC_RSS, cutoff)

    all_entries = wp + html_entries + rss
    # Dedup by title
    seen = set()
    unique = []
    for e in all_entries:
        key = e["title"].lower()[:50]
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return unique


# ── Gemini ─────────────────────────────────────────────────────────────────

def gemini_call(prompt, max_tokens=8192):
    if not GEMINI_API_KEY:
        return ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
    }).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 10 * (attempt + 1)
                print(f"  Gemini rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"[WARN] Gemini error: {e}", file=sys.stderr)
            return ""
    return ""

def extract_funding_deals(entries):
    if not entries:
        return "暂无融资交易"
    items = [f"[{i}] 来源: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')}\n    链接: {e['url']}\n    时间: {e['publishedAt'][:16].replace('T',' ')}" for i, e in enumerate(entries)]
    prompt = f"""你是一位资深的AI行业投融资分析师。请从以下新闻中筛选出所有与AI/科技相关的融资交易，跳过非融资新闻。

新闻列表：
{chr(10).join(items)}

格式（每笔交易空行分隔）：

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
    items = [f"[{i}] 来源: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')}\n    链接: {e['url']}\n    时间: {e['publishedAt'][:16].replace('T',' ')}" for i, e in enumerate(entries)]
    prompt = f"""你是一位资深的AI技术分析师。请筛选出重要的AI技术突破、新模型发布、重大产品更新。跳过融资和一般评论。

新闻列表：
{chr(10).join(items)}

格式（每条空行分隔）：

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
    if not entries:
        return "暂无 VC 博客更新"
    items = [f"[{i}] VC: {e['source']}\n    标题: {e['title']}\n    内容: {e.get('snippet','')[:500]}\n    链接: {e['url']}" for i, e in enumerate(entries)]
    prompt = f"""你是一位资深的科技投资领域分析师。请为以下湾区顶级 VC 的最新原创文章/观点各写一段详细的中文分析。

内容列表：
{chr(10).join(items)}

对于每条内容，请按以下格式输出：

[VC名称] 文章标题（中文翻译）
简介：2-3句话概述核心内容
核心观点：
• 观点1
• 观点2
• 观点3（如有）
涉及公司/领域：提到的具体公司或投资领域
原文：链接URL

要求：
- 英文标题请翻译成中文
- 重点提炼 VC 的独特观点和投资逻辑
- 如涉及具体投资案例，注明金额和轮次"""
    return gemini_call(prompt, 6144)

def summarize_items(entries, section_desc):
    if not entries:
        return {}
    items = [f"{i+1}. [{e.get('source', e.get('name',''))}] {e.get('title','')}\n   内容片段: {str(e.get('snippet', e.get('transcript','')))[:500] or '无'}" for i, e in enumerate(entries)]
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
    lines.append(f"  {idx}. [{source}] {entry.get('title', 'Untitled')}")
    lines.append(f"     🕐 {entry.get('publishedAt', '')[:16].replace('T', ' ')}")
    url = entry.get("url", "")
    if url:
        lines.append(f"     🔗 {url}")
    if summary:
        lines.append(f"     📝 {summary}")
    lines.append("")
    return lines

def format_briefing(funding_text, tech_text, vc_text,
                    media, media_sum, podcasts, pod_sum, blogs, blog_sum):
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    sep, dsep = "─" * 52, "═" * 60
    L = [dsep, f"  📋 每日简报 — {today}", dsep, ""]

    for title, content in [("💰 融资头条", funding_text), ("🚀 技术突破", tech_text), ("🏛 湾区顶级 VC 动态", vc_text)]:
        L.extend([title, sep, "", content or f"  暂无", "", ""])

    for emoji, label, items, sums in [
        ("📡", "科技媒体更新", media, media_sum),
        ("🎙", "播客追踪", podcasts, pod_sum),
        ("📰", "行业资讯", blogs, blog_sum),
    ]:
        L.extend([f"{emoji} {label}（{len(items)} 篇）", sep, ""])
        if items:
            for i, e in enumerate(items):
                L.extend(format_item(i + 1, e, sums.get(i)))
        else:
            L.extend([f"  暂无{label}", ""])
        L.append("")

    L.extend([dsep, "  Generated by VC 每日简报", dsep])
    return "\n".join(L)

def send_gmail(subject, body):
    msg = MIMEMultipart("alternative")
    msg["From"] = f"每日简报 <{GMAIL_USER}>"
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENTS, msg.as_string())
    print(f"Email sent to {len(RECIPIENTS)} recipients", file=sys.stderr)

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("GMAIL_USER or GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(0)

    today = datetime.now(BJT).strftime("%Y-%m-%d")
    lookback_hours = 72
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    print("Fetching podcast feed...", file=sys.stderr)
    podcasts = [ep for ep in fetch_podcast_feed()
                if ep.get("publishedAt") and ensure_aware(
                    datetime.fromisoformat(ep["publishedAt"].replace("Z", "+00:00"))
                ) >= cutoff]
    podcasts.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    print(f"  {len(podcasts)} podcasts", file=sys.stderr)

    print("Fetching funding news...", file=sys.stderr)
    funding = fetch_rss_entries(FUNDING_SOURCES, cutoff)
    print(f"  {len(funding)} articles", file=sys.stderr)

    print("Fetching tech blogs...", file=sys.stderr)
    tech = fetch_rss_entries(TECH_SOURCES, cutoff)
    print(f"  {len(tech)} articles", file=sys.stderr)

    print("Fetching media...", file=sys.stderr)
    media = fetch_rss_entries(MEDIA_SOURCES, cutoff)
    print(f"  {len(media)} articles", file=sys.stderr)

    print("Fetching blogs...", file=sys.stderr)
    blogs = fetch_rss_entries(BLOG_SOURCES, cutoff)
    print(f"  {len(blogs)} posts", file=sys.stderr)

    print("Fetching VC content...", file=sys.stderr)
    vc = fetch_all_vc_content(cutoff, lookback_hours)
    print(f"  Total: {len(vc)} VC items", file=sys.stderr)

    print("Generating AI analysis...", file=sys.stderr)
    funding_text = extract_funding_deals(funding)
    print("  ✓ Funding", file=sys.stderr)
    tech_text = extract_tech_breakthroughs(tech)
    print("  ✓ Tech", file=sys.stderr)
    vc_text = summarize_vc_content(vc)
    print("  ✓ VC", file=sys.stderr)
    media_sum = summarize_items(media[:15], "科技媒体报道")
    print(f"  ✓ {len(media_sum)} media", file=sys.stderr)
    pod_sum = summarize_items(podcasts, "播客节目（请根据标题推断内容）")
    print(f"  ✓ {len(pod_sum)} podcasts", file=sys.stderr)
    blog_sum = summarize_items(blogs, "独立分析师/newsletter文章")
    print(f"  ✓ {len(blog_sum)} blogs", file=sys.stderr)

    body = format_briefing(funding_text, tech_text, vc_text,
                           media[:15], media_sum, podcasts, pod_sum, blogs, blog_sum)
    total = len(vc) + len(media[:15]) + len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total}+ 条更新）"
    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)

if __name__ == "__main__":
    main()
