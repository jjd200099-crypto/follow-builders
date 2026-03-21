#!/usr/bin/env python3
"""
每日简报 — Daily Briefing Generator
Fetches podcast feed + blog RSS, generates Chinese AI summaries via Gemini,
sends multi-section email via Gmail SMTP.

Env vars: GMAIL_USER, GMAIL_APP_PASSWORD, GEMINI_API_KEY
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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── Config ──────────────────────────────────────────────────────────────────

PODCAST_FEED_URL = "https://raw.githubusercontent.com/jjd200099-crypto/follow-builders/main/feed-podcasts.json"

BLOG_SOURCES = [
    {"name": "Stratechery", "url": "https://stratechery.com/feed/"},
    {"name": "Tom Tunguz", "url": "https://tomtunguz.com/feed/"},
    {"name": "Above the Crowd", "url": "https://abovethecrowd.com/feed/"},
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
    """Simple HTTP GET returning text."""
    req = Request(url, headers={"User-Agent": "FollowBuilders/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_podcast_feed():
    """Fetch podcast episodes from the pre-generated feed."""
    try:
        data = json.loads(http_get(PODCAST_FEED_URL))
        return data.get("podcasts", [])
    except Exception as e:
        print(f"[WARN] Failed to fetch podcast feed: {e}", file=sys.stderr)
        return []


def parse_rss_date(date_str):
    """Parse various RSS date formats to datetime."""
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
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def fetch_blog_entries():
    """Fetch recent entries from all blog RSS sources."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    entries = []

    for source in BLOG_SOURCES:
        try:
            xml_text = http_get(source["url"])
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            items = root.findall(".//item")
            if items:
                for item in items[:5]:
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
                            "snippet": strip_html(desc)[:500],
                        })
                continue

            atom_entries = root.findall("atom:entry", ns)
            if not atom_entries:
                atom_entries = root.findall("entry")
            for entry in atom_entries[:5]:
                title = entry.findtext("atom:title", "", ns) or entry.findtext("title", "Untitled")
                link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns) or entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                pub = entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or entry.findtext("published", "") or entry.findtext("updated", "")
                summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns) or entry.findtext("summary", "") or entry.findtext("content", "")
                dt = parse_rss_date(pub)
                if dt and dt >= cutoff:
                    entries.append({
                        "source": source["name"],
                        "title": strip_html(title),
                        "url": link.strip(),
                        "publishedAt": dt.isoformat(),
                        "snippet": strip_html(summary)[:500],
                    })

        except Exception as e:
            print(f"[WARN] RSS error for {source['name']}: {e}", file=sys.stderr)

    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries


# ── Gemini AI Summary ──────────────────────────────────────────────────────

def gemini_summarize(items, section_type="podcast"):
    """Call Gemini 2.0 Flash to generate Chinese summaries for items."""
    if not GEMINI_API_KEY or not items:
        return {}

    if section_type == "podcast":
        item_texts = []
        for i, ep in enumerate(items):
            text = f"{i+1}. [{ep.get('name','')}] {ep.get('title','')}"
            if ep.get("transcript"):
                text += f"\n   逐字稿片段: {ep['transcript'][:800]}"
            item_texts.append(text)
        prompt = (
            "你是一位专业的科技投资领域分析师。请为以下播客节目各写一段中文摘要（2-3句话），"
            "概括核心议题和关键观点。如果标题是英文，请翻译后再总结。\n\n"
            + "\n".join(item_texts)
            + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
        )
    else:
        item_texts = []
        for i, entry in enumerate(items):
            text = f"{i+1}. [{entry['source']}] {entry['title']}"
            if entry.get("snippet"):
                text += f"\n   内容片段: {entry['snippet'][:400]}"
            item_texts.append(text)
        prompt = (
            "你是一位专业的科技投资领域分析师。请为以下博客文章各写一段中文摘要（2-3句话），"
            "概括核心论点和关键洞察。如果标题是英文，请翻译后再总结。\n\n"
            + "\n".join(item_texts)
            + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
        )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
    }).encode()

    req = Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        text = result["candidates"][0]["content"]["parts"][0]["text"]

        summaries = {}
        for m in re.finditer(r"(\d+)\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL):
            idx = int(m.group(1)) - 1
            summaries[idx] = m.group(2).strip()
        return summaries
    except Exception as e:
        print(f"[WARN] Gemini API error: {e}", file=sys.stderr)
        return {}


# ── Email Formatting ───────────────────────────────────────────────────────

def format_briefing(podcasts, blogs, podcast_summaries, blog_summaries):
    """Build the multi-section briefing text."""
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    sep = "─" * 48
    double_sep = "═" * 56

    lines = [
        double_sep,
        f"  📋 每日简报 — {today}",
        double_sep,
        "",
    ]

    lines.append(f"🎙 播客追踪  （过去 24 小时共 {len(podcasts)} 期新节目）")
    lines.append(sep)
    lines.append("")

    if podcasts:
        for i, ep in enumerate(podcasts):
            name = ep.get("name", "Unknown")
            title = ep.get("title", "Untitled")
            url = ep.get("url", "")
            pub = ep.get("publishedAt", "")[:16].replace("T", " ")

            lines.append(f"  {i+1}. [{name}] {title}")
            lines.append(f"     🕐 {pub}")
            if url:
                lines.append(f"     🔗 {url}")
            summary = podcast_summaries.get(i)
            if summary:
                lines.append(f"     📝 {summary}")
            lines.append("")
    else:
        lines.append("  暂无新节目")
        lines.append("")

    lines.append("")
    lines.append(f"📰 行业资讯  （过去 24 小时共 {len(blogs)} 篇新文章）")
    lines.append(sep)
    lines.append("")

    if blogs:
        for i, entry in enumerate(blogs):
            source = entry.get("source", "Unknown")
            title = entry.get("title", "Untitled")
            url = entry.get("url", "")
            pub = entry.get("publishedAt", "")[:16].replace("T", " ")

            lines.append(f"  {i+1}. [{source}] {title}")
            lines.append(f"     🕐 {pub}")
            if url:
                lines.append(f"     🔗 {url}")
            summary = blog_summaries.get(i)
            if summary:
                lines.append(f"     📝 {summary}")
            lines.append("")
    else:
        lines.append("  暂无新文章")
        lines.append("")

    lines.append("")
    lines.append(double_sep)
    lines.append("  Generated by Follow Builders 每日简报")
    lines.append(double_sep)

    return "\n".join(lines)


# ── Email Sending ──────────────────────────────────────────────────────────

def send_gmail(subject, body):
    """Send email via Gmail SMTP."""
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

    print("Fetching podcast feed...", file=sys.stderr)
    all_podcasts = fetch_podcast_feed()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
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
    print(f"  {len(podcasts)} podcast episodes in last 24h", file=sys.stderr)

    print("Fetching blog RSS feeds...", file=sys.stderr)
    blogs = fetch_blog_entries()
    print(f"  {len(blogs)} blog entries in last 24h", file=sys.stderr)

    if not podcasts and not blogs:
        print("No new content in past 24 hours — sending empty briefing", file=sys.stderr)

    print("Generating AI summaries...", file=sys.stderr)
    podcast_summaries = gemini_summarize(podcasts, "podcast") if podcasts else {}
    blog_summaries = gemini_summarize(blogs, "blog") if blogs else {}
    print(f"  Got {len(podcast_summaries)} podcast + {len(blog_summaries)} blog summaries", file=sys.stderr)

    body = format_briefing(podcasts, blogs, podcast_summaries, blog_summaries)
    total = len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total} 条更新）"

    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)


if __name__ == "__main__":
    main()
