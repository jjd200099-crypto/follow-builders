#!/usr/bin/env python3
"""
每日简报 v2 — Daily Briefing Generator
5-section briefing: AI Funding → AI Tech → VC Updates → Podcasts → Industry Blogs
Gmail SMTP + Gemini AI summaries (detailed, Chinese)
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

# ── Config ──────────────────────────────────────────────────────────────────

PODCAST_FEED_URL = "https://raw.githubusercontent.com/jjd200099-crypto/follow-builders/main/feed-podcasts.json"

# --- AI & Tech News (for funding headlines + tech breakthroughs) ---
AI_NEWS_SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "Ars Technica AI", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

# --- Top Bay Area VC Blogs ---
VC_BLOG_SOURCES = [
    {"name": "a16z", "url": "https://a16z.com/feed/"},
    {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/feed/"},
    {"name": "Greylock Partners", "url": "https://greylock.com/feed/"},
    {"name": "First Round Review", "url": "https://review.firstround.com/feed.xml"},
    {"name": "Bessemer Venture Partners", "url": "https://www.bvp.com/atlas/feed"},
    {"name": "Lightspeed Venture Partners", "url": "https://lsvp.com/feed/"},
    {"name": "Founders Fund", "url": "https://foundersfund.com/feed/"},
    {"name": "Above the Crowd (Benchmark)", "url": "https://abovethecrowd.com/feed/"},
    {"name": "Felicis Ventures", "url": "https://www.felicis.com/feed"},
    {"name": "Union Square Ventures", "url": "https://www.usv.com/feed"},
]

# --- Independent Analysts & Newsletters ---
BLOG_SOURCES = [
    {"name": "Stratechery", "url": "https://stratechery.com/feed/"},
    {"name": "Tom Tunguz", "url": "https://tomtunguz.com/feed/"},
    {"name": "Different Funds", "url": "https://differentfunds.substack.com/feed"},
    {"name": "Accelerated Capital", "url": "https://accelerated.substack.com/feed"},
    {"name": "Alex Danco", "url": "https://alexdanco.substack.com/feed"},
    {"name": "Not Boring", "url": "https://www.notboring.co/feed"},
    {"name": "Late Checkout", "url": "https://www.latecheckout.co/feed"},
    {"name": "Electric Sheep", "url": "https://electricsheep.substack.com/feed"},
    {"name": "NBT (Next Big Thing)", "url": "https://nbt.substack.com/feed"},
    {"name": "Lenny's Newsletter", "url": "https://www.lennysnewsletter.com/feed"},
    {"name": "kwokchain", "url": "https://kwokchain.com/feed/"},
    {"name": "Deconstructor of Fun", "url": "https://www.deconstructoroffun.com/blog?format=rss"},
]

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "jjd200099@gmail.com")

BJT = timezone(timedelta(hours=8))


# ── Fetching ────────────────────────────────────────────────────────────────

def http_get(url, timeout=15):
    req = Request(url, headers={"User-Agent": "FollowBuilders/2.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_podcast_feed():
    try:
        data = json.loads(http_get(PODCAST_FEED_URL))
        return data.get("podcasts", [])
    except Exception as e:
        print(f"[WARN] Podcast feed error: {e}", file=sys.stderr)
        return []


def parse_rss_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def fetch_rss_entries(sources, cutoff):
    """Generic RSS fetcher for any list of sources."""
    entries = []
    for source in sources:
        try:
            xml_text = http_get(source["url"])
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            # RSS 2.0
            items = root.findall(".//item")
            if items:
                for item in items[:8]:
                    title = item.findtext("title", "Untitled")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    desc = item.findtext("description", "")
                    dt = parse_rss_date(pub_date)
                    if dt and dt >= cutoff:
                        entries.append({
                            "source": source["name"],
                            "title": strip_html(title),
                            "url": link.strip(),
                            "publishedAt": dt.isoformat(),
                            "snippet": strip_html(desc)[:600],
                        })
                continue

            # Atom
            atom_entries = root.findall("atom:entry", ns)
            if not atom_entries:
                atom_entries = root.findall("entry")
            for entry in atom_entries[:8]:
                title = entry.findtext("atom:title", "", ns) or entry.findtext("title", "Untitled")
                link_el = (entry.find("atom:link[@rel='alternate']", ns)
                           or entry.find("atom:link", ns) or entry.find("link"))
                link = link_el.get("href", "") if link_el is not None else ""
                pub = (entry.findtext("atom:published", "", ns)
                       or entry.findtext("atom:updated", "", ns)
                       or entry.findtext("published", "")
                       or entry.findtext("updated", ""))
                summary = (entry.findtext("atom:summary", "", ns)
                           or entry.findtext("atom:content", "", ns)
                           or entry.findtext("summary", "")
                           or entry.findtext("content", ""))
                dt = parse_rss_date(pub)
                if dt and dt >= cutoff:
                    entries.append({
                        "source": source["name"],
                        "title": strip_html(title),
                        "url": link.strip(),
                        "publishedAt": dt.isoformat(),
                        "snippet": strip_html(summary)[:600],
                    })

        except Exception as e:
            print(f"[WARN] RSS error {source['name']}: {e}", file=sys.stderr)

    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries


# ── Gemini AI ──────────────────────────────────────────────────────────────

def gemini_call(prompt, max_tokens=4096):
    """Call Gemini 2.0 Flash and return text response."""
    if not GEMINI_API_KEY:
        return ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
    }).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"[WARN] Gemini error: {e}", file=sys.stderr)
        return ""


def classify_and_summarize_news(ai_news):
    """Use Gemini to classify AI news into funding vs tech breakthroughs."""
    if not ai_news:
        return {"funding": [], "tech": []}

    items_text = []
    for i, item in enumerate(ai_news):
        items_text.append(
            f"[{i}] [{item['source']}] {item['title']}\n"
            f"    摘要片段: {item.get('snippet', '')[:300]}\n"
            f"    链接: {item['url']}"
        )

    prompt = f"""你是一位资深的科技投资领域分析师。请完成以下两个任务：

任务1：将下面的新闻分类为 "FUNDING"（融资、投资、收购、IPO、估值相关）或 "TECH"（技术突破、产品发布、研究进展、模型更新）。

任务2：为每条新闻写一段详细的中文摘要（4-6句话），包括：
- 核心事件是什么
- 涉及哪些公司/机构
- 金额或技术细节
- 市场影响或意义

新闻列表：
{chr(10).join(items_text)}

请严格按以下JSON格式输出（不要加markdown代码块标记）：
[
  {{"index": 0, "category": "FUNDING", "summary": "详细中文摘要..."}},
  {{"index": 1, "category": "TECH", "summary": "详细中文摘要..."}}
]"""

    text = gemini_call(prompt, max_tokens=4096)
    # Extract JSON from response
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        classified = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in response
        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            try:
                classified = json.loads(m.group())
            except json.JSONDecodeError:
                classified = []
        else:
            classified = []

    funding, tech = [], []
    for item in classified:
        idx = item.get("index", -1)
        if 0 <= idx < len(ai_news):
            entry = {**ai_news[idx], "ai_summary": item.get("summary", "")}
            if item.get("category") == "FUNDING":
                funding.append(entry)
            else:
                tech.append(entry)

    return {"funding": funding, "tech": tech}


def summarize_vc_blogs(vc_entries):
    """Generate detailed Chinese summaries for VC blog posts."""
    if not vc_entries:
        return {}
    items_text = []
    for i, entry in enumerate(vc_entries):
        items_text.append(
            f"{i+1}. [{entry['source']}] {entry['title']}\n"
            f"   内容片段: {entry.get('snippet', '')[:400]}"
        )
    prompt = (
        "你是一位资深的科技投资领域分析师。请为以下湾区顶级 VC 的博客文章各写一段详细的中文摘要（4-6句话）。\n"
        "摘要需要包括：核心论点、关键数据或案例、对投资者和创业者的启示。\n"
        "如果文章涉及具体的投资案例或portfolio公司，请特别提及。\n\n"
        + "\n".join(items_text)
        + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
    )
    text = gemini_call(prompt, max_tokens=4096)
    summaries = {}
    for m in re.finditer(r"(\d+)\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL):
        summaries[int(m.group(1)) - 1] = m.group(2).strip()
    return summaries


def summarize_podcasts(podcasts):
    """Generate detailed Chinese summaries for podcast episodes."""
    if not podcasts:
        return {}
    items_text = []
    for i, ep in enumerate(podcasts):
        text = f"{i+1}. [{ep.get('name','')}] {ep.get('title','')}"
        if ep.get("transcript"):
            text += f"\n   逐字稿片段: {ep['transcript'][:1000]}"
        items_text.append(text)
    prompt = (
        "你是一位资深的科技投资领域分析师。请为以下播客节目各写一段详细的中文摘要（4-6句话）。\n"
        "摘要需要包括：节目主题、嘉宾背景（如可推断）、核心观点和讨论的关键问题。\n"
        "如果标题是英文，请先翻译再总结。\n\n"
        + "\n".join(items_text)
        + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
    )
    text = gemini_call(prompt, max_tokens=4096)
    summaries = {}
    for m in re.finditer(r"(\d+)\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL):
        summaries[int(m.group(1)) - 1] = m.group(2).strip()
    return summaries


def summarize_blogs(blog_entries):
    """Generate detailed Chinese summaries for independent blog/newsletter posts."""
    if not blog_entries:
        return {}
    items_text = []
    for i, entry in enumerate(blog_entries):
        items_text.append(
            f"{i+1}. [{entry['source']}] {entry['title']}\n"
            f"   内容片段: {entry.get('snippet', '')[:400]}"
        )
    prompt = (
        "你是一位资深的科技投资领域分析师。请为以下博客/newsletter文章各写一段详细的中文摘要（4-6句话）。\n"
        "摘要需要包括：文章核心论点、关键数据或洞察、作者的独特视角。\n\n"
        + "\n".join(items_text)
        + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
    )
    text = gemini_call(prompt, max_tokens=4096)
    summaries = {}
    for m in re.finditer(r"(\d+)\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL):
        summaries[int(m.group(1)) - 1] = m.group(2).strip()
    return summaries


# ── Email Formatting ───────────────────────────────────────────────────────

def format_section_item(idx, entry, summary=None):
    """Format a single item in any section."""
    lines = []
    source = entry.get("source", entry.get("name", ""))
    title = entry.get("title", "Untitled")
    url = entry.get("url", "")
    pub = entry.get("publishedAt", "")[:16].replace("T", " ")

    lines.append(f"  {idx}. [{source}] {title}")
    lines.append(f"     🕐 {pub}")
    if url:
        lines.append(f"     🔗 {url}")
    # Use ai_summary (from classification) or passed summary
    s = entry.get("ai_summary") or summary
    if s:
        # Wrap long summaries nicely
        lines.append(f"     📝 {s}")
    lines.append("")
    return lines


def format_briefing(funding, tech, vc_entries, vc_summaries,
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

    # ── Section 1: AI Funding ──
    lines.append(f"💰 AI 融资头条  （{len(funding)} 条）")
    lines.append(sep)
    lines.append("")
    if funding:
        for i, entry in enumerate(funding):
            lines.extend(format_section_item(i + 1, entry))
    else:
        lines.append("  今日暂无融资新闻")
        lines.append("")
    lines.append("")

    # ── Section 2: AI Tech Breakthroughs ──
    lines.append(f"🔬 AI 技术突破  （{len(tech)} 条）")
    lines.append(sep)
    lines.append("")
    if tech:
        for i, entry in enumerate(tech):
            lines.extend(format_section_item(i + 1, entry))
    else:
        lines.append("  今日暂无技术突破资讯")
        lines.append("")
    lines.append("")

    # ── Section 3: Top VC Updates ──
    lines.append(f"🏛 湾区顶级 VC 动态  （{len(vc_entries)} 篇）")
    lines.append(sep)
    lines.append("")
    if vc_entries:
        for i, entry in enumerate(vc_entries):
            lines.extend(format_section_item(i + 1, entry, vc_summaries.get(i)))
    else:
        lines.append("  今日暂无 VC 博客更新")
        lines.append("")
    lines.append("")

    # ── Section 4: Podcasts ──
    lines.append(f"🎙 播客追踪  （{len(podcasts)} 期新节目）")
    lines.append(sep)
    lines.append("")
    if podcasts:
        for i, ep in enumerate(podcasts):
            lines.extend(format_section_item(i + 1, ep, podcast_summaries.get(i)))
    else:
        lines.append("  今日暂无新节目")
        lines.append("")
    lines.append("")

    # ── Section 5: Industry Blogs ──
    lines.append(f"📰 行业资讯  （{len(blogs)} 篇新文章）")
    lines.append(sep)
    lines.append("")
    if blogs:
        for i, entry in enumerate(blogs):
            lines.extend(format_section_item(i + 1, entry, blog_summaries.get(i)))
    else:
        lines.append("  今日暂无新文章")
        lines.append("")
    lines.append("")

    lines.append(double_sep)
    lines.append("  Generated by Follow Builders 每日简报")
    lines.append(double_sep)

    return "\n".join(lines)


# ── Email Sending ──────────────────────────────────────────────────────────

def send_gmail(subject, body):
    msg = MIMEMultipart("alternative")
    msg["From"] = f"每日简报 <{GMAIL_USER}>"
    msg["To"] = RECIPIENT
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT, msg.as_string())
    print(f"Email sent to {RECIPIENT}", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("GMAIL_USER or GMAIL_APP_PASSWORD not set", file=sys.stderr)
        sys.exit(0)

    today = datetime.now(BJT).strftime("%Y-%m-%d")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # 1. Fetch podcast feed
    print("Fetching podcast feed...", file=sys.stderr)
    all_podcasts = fetch_podcast_feed()
    podcasts = []
    for ep in all_podcasts:
        pub = ep.get("publishedAt", "")
        if not pub:
            continue
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if dt >= cutoff:
                podcasts.append(ep)
        except ValueError:
            pass
    podcasts.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    print(f"  {len(podcasts)} podcast episodes", file=sys.stderr)

    # 2. Fetch AI news (for funding + tech sections)
    print("Fetching AI news feeds...", file=sys.stderr)
    ai_news = fetch_rss_entries(AI_NEWS_SOURCES, cutoff)
    print(f"  {len(ai_news)} AI news articles", file=sys.stderr)

    # 3. Fetch VC blogs
    print("Fetching VC blog feeds...", file=sys.stderr)
    vc_entries = fetch_rss_entries(VC_BLOG_SOURCES, cutoff)
    print(f"  {len(vc_entries)} VC blog posts", file=sys.stderr)

    # 4. Fetch independent blogs/newsletters
    print("Fetching industry blog feeds...", file=sys.stderr)
    blogs = fetch_rss_entries(BLOG_SOURCES, cutoff)
    print(f"  {len(blogs)} blog posts", file=sys.stderr)

    # 5. AI classification + summaries (parallel Gemini calls)
    print("Generating AI summaries (this may take a moment)...", file=sys.stderr)

    # Classify AI news into funding vs tech
    classified = classify_and_summarize_news(ai_news)
    funding = classified["funding"]
    tech = classified["tech"]
    print(f"  AI news: {len(funding)} funding + {len(tech)} tech", file=sys.stderr)

    # Summarize other sections
    vc_summaries = summarize_vc_blogs(vc_entries)
    podcast_summaries = summarize_podcasts(podcasts)
    blog_summaries = summarize_blogs(blogs)
    print(f"  Summaries: {len(vc_summaries)} VC + {len(podcast_summaries)} podcast + {len(blog_summaries)} blog", file=sys.stderr)

    # 6. Format and send
    body = format_briefing(funding, tech, vc_entries, vc_summaries,
                           podcasts, podcast_summaries, blogs, blog_summaries)
    total = len(funding) + len(tech) + len(vc_entries) + len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total} 条更新）"

    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)


if __name__ == "__main__":
    main()
