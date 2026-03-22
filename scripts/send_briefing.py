#!/usr/bin/env python3
"""
每日简报 v6 — 6-section Daily Briefing
1. 💰 融资头条   2. 🚀 技术突破   3. 🏛 VC动态 (HTML scraping)
4. 📡 科技媒体   5. 🎙 播客追踪   6. 📰 行业资讯
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

PODCAST_FEED_URL = "https://raw.githubusercontent.com/jjd200099-crypto/follow-builders/main/feed-podcasts.json"

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

# Top VC blog pages to scrape (HTML, not RSS)
VC_SCRAPE_SOURCES = [
    {"name": "a16z", "url": "https://a16z.com/blog/"},
    {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/articles/"},
    {"name": "Greylock Partners", "url": "https://greylock.com/greymatter/"},
    {"name": "Benchmark (Above the Crowd)", "url": "https://abovethecrowd.com/"},
    {"name": "Lightspeed", "url": "https://lsvp.com/blog/"},
    {"name": "Bessemer Venture Partners", "url": "https://www.bvp.com/atlas"},
    {"name": "Accel", "url": "https://www.accel.com/noteworthy"},
    {"name": "Kleiner Perkins", "url": "https://www.kleinerperkins.com/perspectives"},
    {"name": "General Catalyst", "url": "https://www.generalcatalyst.com/perspectives"},
    {"name": "Index Ventures", "url": "https://www.indexventures.com/perspectives"},
    {"name": "Founders Fund", "url": "https://foundersfund.com/the-future/"},
    {"name": "Y Combinator", "url": "https://www.ycombinator.com/blog/"},
    {"name": "Union Square Ventures", "url": "https://www.usv.com/writing/"},
    {"name": "Felicis Ventures", "url": "https://www.felicis.com/insight"},
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

# ── HTTP ────────────────────────────────────────────────────────────────────

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def http_get(url, timeout=15):
    req = Request(url, headers={
        "User-Agent": BROWSER_UA,
        "Accept": "text/html, application/rss+xml, application/xml, text/xml, */*",
    })
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def fetch_podcast_feed():
    try:
        data = json.loads(http_get(PODCAST_FEED_URL))
        return data.get("podcasts", [])
    except Exception as e:
        print(f"[WARN] Podcast feed error: {e}", file=sys.stderr)
        return []

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
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S %z",
        "%d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]:
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
                            "source": source["name"],
                            "title": strip_html(title),
                            "url": (link or "").strip(),
                            "publishedAt": dt.isoformat(),
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
                        "source": source["name"],
                        "title": strip_html(title),
                        "url": (link or "").strip(),
                        "publishedAt": dt.isoformat(),
                        "snippet": strip_html(summary_el)[:800],
                    })
        except Exception as e:
            print(f"[WARN] RSS error {source['name']}: {e}", file=sys.stderr)
    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries


# ── VC Blog Scraping ───────────────────────────────────────────────────────

def scrape_vc_blogs(lookback_hours):
    """Scrape VC blog pages and use Gemini to extract recent posts."""
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    all_html = {}
    for vc in VC_SCRAPE_SOURCES:
        try:
            html = http_get(vc["url"], timeout=20)
            # Trim HTML: remove scripts/styles, keep text + links, limit size
            html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<nav[\s\S]*?</nav>", "", html, flags=re.IGNORECASE)
            html = re.sub(r"<footer[\s\S]*?</footer>", "", html, flags=re.IGNORECASE)
            # Keep first 8000 chars of cleaned HTML (enough for recent posts)
            all_html[vc["name"]] = html[:8000]
            print(f"  Scraped {vc['name']} ({len(html)} chars)", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Scrape error {vc['name']}: {e}", file=sys.stderr)

    if not all_html:
        return "暂无 VC 博客更新"

    # Build prompt with all scraped HTML
    pages_text = []
    for name, html in all_html.items():
        vc_info = next((v for v in VC_SCRAPE_SOURCES if v["name"] == name), {})
        pages_text.append(
            f"=== {name} ===\n"
            f"URL: {vc_info.get('url', '')}\n"
            f"HTML内容:\n{html[:6000]}\n"
        )

    prompt = f"""你是一位资深的科技投资领域分析师。今天是 {today}。

我从以下湾区顶级 VC 的官网博客页面抓取了 HTML 内容。请从中提取过去 {lookback_hours} 小时内发布的新文章。

对于每篇文章，请按以下格式输出：

[VC名称] 文章标题
简介：1-2句话概述文章内容
核心观点：
• 观点1
• 观点2
• 观点3（如有）
涉及公司/领域：提到的公司名或投资领域
原文：完整URL（从HTML中的<a>标签提取）

注意：
- 只输出过去 {lookback_hours} 小时内的新文章（根据页面上显示的日期判断）
- 如果某个 VC 没有新文章，跳过它
- 如果无法确定发布日期，但文章出现在页面最顶部，可以包含它（注明"日期未知，疑似近期发布"）
- 如果所有 VC 都没有新内容，输出"暂无 VC 博客更新"
- 不要编造不存在的文章

以下是抓取到的页面内容：

{chr(10).join(pages_text)}"""

    return gemini_call(prompt, max_tokens=6144)


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


def extract_funding_deals(funding_entries):
    if not funding_entries:
        return "暂无融资交易"
    items_text = []
    for i, item in enumerate(funding_entries):
        items_text.append(
            f"[{i}] 来源: {item['source']}\n"
            f"    标题: {item['title']}\n"
            f"    内容: {item.get('snippet', '')}\n"
            f"    链接: {item['url']}\n"
            f"    发布时间: {item['publishedAt'][:16].replace('T', ' ')}"
        )
    prompt = f"""你是一位资深的AI行业投融资分析师。请从以下新闻中筛选出所有与AI/科技相关的融资交易（Series A/B/C/D、种子轮、IPO、收购等），并按以下格式输出每笔交易。

如果某条新闻不是融资交易（比如是行业分析、观点文章、产品发布），请跳过它。

新闻列表：
{chr(10).join(items_text)}

请严格按以下格式输出每笔交易（每笔交易之间用空行分隔）：

公司名 - $金额 - 轮次
公司简介：一句话描述公司做什么
业务亮点：
• 亮点1
• 亮点2
• 亮点3（如有）
融资用途：一句话说明资金用途
领投方：投资机构名称（如文中未提及，写"未披露"）
发布时间：从原文推断的时间
原文：链接URL

如果没有找到任何融资交易，请输出"暂无融资交易"。不要输出任何其他解释文字。"""
    return gemini_call(prompt, max_tokens=6144)


def extract_tech_breakthroughs(tech_entries):
    if not tech_entries:
        return "暂无重大技术突破"
    items_text = []
    for i, item in enumerate(tech_entries):
        items_text.append(
            f"[{i}] 来源: {item['source']}\n"
            f"    标题: {item['title']}\n"
            f"    内容: {item.get('snippet', '')}\n"
            f"    链接: {item['url']}\n"
            f"    发布时间: {item['publishedAt'][:16].replace('T', ' ')}"
        )
    prompt = f"""你是一位资深的AI技术分析师。请从以下新闻中筛选出重要的AI技术突破、新模型发布、重大产品更新，并按以下格式输出。

跳过一般性的行业评论、融资新闻或非技术内容。

新闻列表：
{chr(10).join(items_text)}

请严格按以下格式输出每条技术突破（每条之间用空行分隔）：

产品/模型名称
简介：一句话概述
核心突破：这项技术为什么重要
关键特性：
• 特性1
• 特性2
• 特性3（如有）
发布时间：从原文推断的时间
原文：链接URL

如果没有找到重要技术突破，请输出"暂无重大技术突破"。不要输出任何其他解释文字。"""
    return gemini_call(prompt, max_tokens=6144)


def summarize_items(entries, section_desc):
    if not entries:
        return {}
    items_text = []
    for i, entry in enumerate(entries):
        name = entry.get("source", entry.get("name", "Unknown"))
        title = entry.get("title", "")
        snippet = entry.get("snippet", entry.get("transcript", ""))
        items_text.append(
            f"{i+1}. [{name}] {title}\n"
            f"   内容片段: {str(snippet)[:500] if snippet else '无'}"
        )
    prompt = (
        f"你是一位资深的科技投资领域分析师。请为以下{section_desc}各写一段详细的中文摘要（4-6句话）。\n"
        f"摘要需包括：核心论点、关键数据或案例、对投资者/创业者/从业者的启示。\n"
        f"如果标题是英文，请翻译后再总结。\n\n"
        + "\n".join(items_text)
        + "\n\n请严格按编号逐条给出摘要，格式如下：\n1. 摘要内容\n2. 摘要内容\n..."
    )
    text = gemini_call(prompt, max_tokens=6144)
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

    lines = [
        double_sep,
        f"  📋 每日简报 — {today}",
        double_sep,
        "",
    ]

    # 1. Funding
    lines.append("💰 融资头条")
    lines.append(sep)
    lines.append("")
    lines.append(funding_text if funding_text else "  暂无融资交易")
    lines.append("")
    lines.append("")

    # 2. Tech
    lines.append("🚀 技术突破")
    lines.append(sep)
    lines.append("")
    lines.append(tech_text if tech_text else "  暂无重大技术突破")
    lines.append("")
    lines.append("")

    # 3. VC (scraped from HTML)
    lines.append("🏛 湾区顶级 VC 动态")
    lines.append(sep)
    lines.append("")
    lines.append(vc_text if vc_text else "  暂无 VC 博客更新")
    lines.append("")
    lines.append("")

    # 4. Media
    lines.append(f"📡 科技媒体更新（{len(media_entries)} 篇）")
    lines.append(sep)
    lines.append("")
    if media_entries:
        for i, entry in enumerate(media_entries):
            lines.extend(format_item(i + 1, entry, media_summaries.get(i)))
    else:
        lines.append("  今日暂无媒体更新")
        lines.append("")
    lines.append("")

    # 5. Podcasts
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

    # 6. Blogs
    lines.append(f"📰 行业资讯（{len(blogs)} 篇新文章）")
    lines.append(sep)
    lines.append("")
    if blogs:
        for i, entry in enumerate(blogs):
            lines.extend(format_item(i + 1, entry, blog_summaries.get(i)))
    else:
        lines.append("  今日暂无新文章")
        lines.append("")
    lines.append("")

    lines.append(double_sep)
    lines.append("  Generated by Follow Builders 每日简报")
    lines.append(double_sep)

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
    lookback_hours = 24
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # 1. Podcasts
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

    # 2. RSS sections
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

    # 3. Scrape VC blogs (HTML)
    print("Scraping VC blog pages...", file=sys.stderr)
    vc_text = scrape_vc_blogs(lookback_hours)
    print("  ✓ VC blogs scraped and analyzed", file=sys.stderr)

    # 4. Gemini summaries
    print("Generating AI analysis...", file=sys.stderr)

    funding_text = extract_funding_deals(funding_entries)
    print("  ✓ Funding deals", file=sys.stderr)

    tech_text = extract_tech_breakthroughs(tech_entries)
    print("  ✓ Tech breakthroughs", file=sys.stderr)

    media_summaries = summarize_items(media_entries[:15], "科技媒体报道")
    print(f"  ✓ {len(media_summaries)} media summaries", file=sys.stderr)

    podcast_summaries = summarize_items(podcasts, "播客节目（请根据标题和嘉宾信息推断内容）")
    print(f"  ✓ {len(podcast_summaries)} podcast summaries", file=sys.stderr)

    blog_summaries = summarize_items(blogs, "独立分析师/newsletter文章")
    print(f"  ✓ {len(blog_summaries)} blog summaries", file=sys.stderr)

    # 5. Format and send
    body = format_briefing(
        funding_text, tech_text, vc_text,
        media_entries[:15], media_summaries,
        podcasts, podcast_summaries,
        blogs, blog_summaries,
    )
    total = len(media_entries[:15]) + len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total}+ 条更新）"

    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)


if __name__ == "__main__":
    main()
