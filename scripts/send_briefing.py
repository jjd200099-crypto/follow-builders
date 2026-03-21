#!/usr/bin/env python3
"""
每日简报 v3 — 6-section Daily Briefing
1. 💰 融资头条 (AI funding deals)
2. 🚀 技术突破 (AI product launches & breakthroughs)
3. 🏛 湾区顶级VC动态 (VC blog posts)
4. 📡 科技媒体更新 (general tech media)
5. 🎙 播客追踪 (podcast episodes)
6. 📰 行业资讯 (independent blogs/newsletters)

Gmail SMTP + Gemini 2.0 Flash for structured Chinese summaries
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

# --- Funding-specific sources ---
FUNDING_SOURCES = [
    {"name": "FinSMES", "url": "https://www.finsmes.com/feed"},
    {"name": "Crunchbase News", "url": "https://news.crunchbase.com/feed/"},
    {"name": "Fortune AI", "url": "https://fortune.com/tag/artificial-intelligence/feed/"},
    {"name": "TechCrunch Funding", "url": "https://techcrunch.com/category/venture/feed/"},
    {"name": "SaaStr", "url": "https://www.saastr.com/feed/"},
]

# --- AI company blogs (for tech breakthroughs) ---
TECH_SOURCES = [
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Anthropic News", "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Meta AI Blog", "url": "https://ai.meta.com/blog/rss/"},
    {"name": "NVIDIA Blog", "url": "https://blogs.nvidia.com/feed/"},
    {"name": "Microsoft AI Blog", "url": "https://blogs.microsoft.com/ai/feed/"},
    {"name": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Apple ML Research", "url": "https://machinelearning.apple.com/rss.xml"},
    {"name": "Mistral AI Blog", "url": "https://mistral.ai/feed.xml"},
]

# --- General tech media ---
MEDIA_SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "The Information", "url": "https://www.theinformation.com/feed"},
    {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
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
    req = Request(url, headers={"User-Agent": "FollowBuilders/3.0"})
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
                            "url": link.strip(),
                            "publishedAt": dt.isoformat(),
                            "snippet": strip_html(desc)[:800],
                        })
                continue

            atom_entries = root.findall("atom:entry", ns)
            if not atom_entries:
                atom_entries = root.findall("entry")
            for entry in atom_entries[:10]:
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
                        "snippet": strip_html(summary)[:800],
                    })

        except Exception as e:
            print(f"[WARN] RSS error {source['name']}: {e}", file=sys.stderr)

    entries.sort(key=lambda x: x.get("publishedAt", ""), reverse=True)
    return entries


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
    """Use Gemini to extract structured funding deals from news articles."""
    if not funding_entries:
        return ""

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

如果某条新闻不是融资交易（比如是行业分析、观点文章），请跳过它。

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
领投方：投资机构名称
发布时间：X小时前
原文：链接URL

如果没有找到任何融资交易，请输出"暂无融资交易"。"""

    return gemini_call(prompt, max_tokens=4096)


def extract_tech_breakthroughs(tech_entries):
    """Use Gemini to extract structured tech breakthrough summaries."""
    if not tech_entries:
        return ""

    items_text = []
    for i, item in enumerate(tech_entries):
        items_text.append(
            f"[{i}] 来源: {item['source']}\n"
            f"    标题: {item['title']}\n"
            f"    内容: {item.get('snippet', '')}\n"
            f"    链接: {item['url']}\n"
            f"    发布时间: {item['publishedAt'][:16].replace('T', ' ')}"
        )

    prompt = f"""你是一位资深的AI技术分析师。请从以下新闻中筛选出所有重要的AI技术突破、产品发布和模型更新，并按以下格式输出。

筛选标准：新模型发布、重大产品更新、研究突破、开源项目发布、基准测试新记录等。跳过一般性的行业评论或融资新闻。

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
发布时间：X小时前
原文：链接URL

如果没有找到重要技术突破，请输出"暂无重大技术突破"。"""

    return gemini_call(prompt, max_tokens=4096)


def summarize_section(entries, section_desc):
    """Generate detailed Chinese summaries for a section."""
    if not entries:
        return {}
    items_text = []
    for i, entry in enumerate(entries):
        name = entry.get("source", entry.get("name", ""))
        title = entry.get("title", "")
        snippet = entry.get("snippet", entry.get("transcript", ""))
        items_text.append(
            f"{i+1}. [{name}] {title}\n"
            f"   内容片段: {str(snippet)[:500]}"
        )
    prompt = (
        f"你是一位资深的科技投资领域分析师。请为以下{section_desc}各写一段详细的中文摘要（4-6句话）。\n"
        f"摘要需包括：核心论点、关键数据或案例、对投资者和创业者的启示。\n\n"
        + "\n".join(items_text)
        + "\n\n请按编号逐条给出摘要，格式：\n1. 摘要内容\n2. 摘要内容\n..."
    )
    text = gemini_call(prompt, max_tokens=4096)
    summaries = {}
    for m in re.finditer(r"(\d+)\.\s*(.+?)(?=\n\d+\.|\Z)", text, re.DOTALL):
        summaries[int(m.group(1)) - 1] = m.group(2).strip()
    return summaries


# ── Email Formatting ───────────────────────────────────────────────────────

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


def format_briefing(funding_text, tech_text, vc_entries, vc_summaries,
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

    # ── 1. Funding Deals ──
    lines.append("💰 融资头条（过去 24 小时）")
    lines.append(sep)
    lines.append("")
    lines.append(funding_text if funding_text else "  暂无融资交易")
    lines.append("")
    lines.append("")

    # ── 2. Tech Breakthroughs ──
    lines.append("🚀 技术突破（过去 24 小时）")
    lines.append(sep)
    lines.append("")
    lines.append(tech_text if tech_text else "  暂无重大技术突破")
    lines.append("")
    lines.append("")

    # ── 3. VC Updates ──
    lines.append(f"🏛 湾区顶级 VC 动态（{len(vc_entries)} 篇）")
    lines.append(sep)
    lines.append("")
    if vc_entries:
        for i, entry in enumerate(vc_entries):
            lines.extend(format_item(i + 1, entry, vc_summaries.get(i)))
    else:
        lines.append("  今日暂无 VC 博客更新")
        lines.append("")
    lines.append("")

    # ── 4. Tech Media ──
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

    # ── 5. Podcasts ──
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

    # ── 6. Industry Blogs ──
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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)

    # 1. Podcasts
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
    print(f"  {len(podcasts)} podcasts", file=sys.stderr)

    # 2. Funding sources
    print("Fetching funding news...", file=sys.stderr)
    funding_entries = fetch_rss_entries(FUNDING_SOURCES, cutoff)
    print(f"  {len(funding_entries)} funding articles", file=sys.stderr)

    # 3. Tech company blogs
    print("Fetching tech blogs...", file=sys.stderr)
    tech_entries = fetch_rss_entries(TECH_SOURCES, cutoff)
    print(f"  {len(tech_entries)} tech articles", file=sys.stderr)

    # 4. General media
    print("Fetching tech media...", file=sys.stderr)
    media_entries = fetch_rss_entries(MEDIA_SOURCES, cutoff)
    print(f"  {len(media_entries)} media articles", file=sys.stderr)

    # 5. VC blogs
    print("Fetching VC blogs...", file=sys.stderr)
    vc_entries = fetch_rss_entries(VC_BLOG_SOURCES, cutoff)
    print(f"  {len(vc_entries)} VC posts", file=sys.stderr)

    # 6. Independent blogs
    print("Fetching industry blogs...", file=sys.stderr)
    blogs = fetch_rss_entries(BLOG_SOURCES, cutoff)
    print(f"  {len(blogs)} blog posts", file=sys.stderr)

    # 7. Gemini: structured extraction + summaries
    print("Generating AI analysis (may take 30-60s)...", file=sys.stderr)

    funding_text = extract_funding_deals(funding_entries)
    print(f"  Funding deals extracted", file=sys.stderr)

    tech_text = extract_tech_breakthroughs(tech_entries)
    print(f"  Tech breakthroughs extracted", file=sys.stderr)

    vc_summaries = summarize_section(vc_entries, "湾区顶级VC博客文章")
    media_summaries = summarize_section(media_entries[:15], "科技媒体报道")
    podcast_summaries = summarize_section(podcasts, "播客节目")
    blog_summaries = summarize_section(blogs, "独立分析师/newsletter文章")
    print(f"  All summaries generated", file=sys.stderr)

    # 8. Format and send
    body = format_briefing(
        funding_text, tech_text,
        vc_entries, vc_summaries,
        media_entries[:15], media_summaries,
        podcasts, podcast_summaries,
        blogs, blog_summaries,
    )
    total = len(vc_entries) + len(media_entries[:15]) + len(podcasts) + len(blogs)
    subject = f"📋 每日简报 — {today}（{total}+ 条更新）"

    print(f"Sending: {subject}", file=sys.stderr)
    send_gmail(subject, body)


if __name__ == "__main__":
    main()
