#!/usr/bin/env python3
"""Build an RSS 2.0 feed for the Ministry of Finance statistics column."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = "https://gks.mof.gov.cn/tongjishuju/"
SHANGHAI_TZ = timezone(timedelta(hours=8))
ATOM_NS = "http://www.w3.org/2005/Atom"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MOF-Statistics-RSS/1.0; "
        "+https://verymark.github.io/bj-sh-dashboard/)"
    )
}


@dataclass(frozen=True)
class FeedItem:
    title: str
    url: str
    published: datetime


def fetch(url: str) -> str:
    """Fetch with curl, whose TLS stack is compatible with the ministry CDN."""
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--compressed",
        "--retry",
        "3",
        "--retry-all-errors",
        "--connect-timeout",
        "20",
        "--max-time",
        "60",
        "--user-agent",
        HEADERS["User-Agent"],
        url,
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    return result.stdout.decode("utf-8", errors="replace")


def parse_items(html: str, page_url: str) -> list[FeedItem]:
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for row in soup.select("ul.liBox > li"):
        anchor = row.select_one("a[href]")
        date_node = row.select_one("span")
        if not anchor or not date_node:
            continue

        title = (anchor.get("title") or anchor.get_text(" ", strip=True)).strip()
        href = anchor.get("href", "").strip()
        date_text = date_node.get_text(strip=True)
        if not title or not href:
            continue

        try:
            published_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        items.append(
            FeedItem(
                title=title,
                url=urljoin(page_url, href),
                published=datetime.combine(published_date, time(8, 0), SHANGHAI_TZ),
            )
        )

    return items


def page_count(html: str) -> int:
    match = re.search(r"var\s+countPage\s*=\s*(\d+)", html)
    return int(match.group(1)) if match else 1


def collect_items(max_items: int = 50) -> list[FeedItem]:
    first_html = fetch(INDEX_URL)
    items = parse_items(first_html, INDEX_URL)

    for page_number in range(1, page_count(first_html)):
        page_url = urljoin(INDEX_URL, f"index_{page_number}.htm")
        items.extend(parse_items(fetch(page_url), page_url))

    unique = {item.url: item for item in items}
    return sorted(unique.values(), key=lambda item: item.published, reverse=True)[:max_items]


def build_feed(items: list[FeedItem], feed_url: str) -> bytes:
    if not items:
        raise RuntimeError("No entries found on the Ministry of Finance statistics page")

    ET.register_namespace("atom", ATOM_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "财政部国库司统计数据"
    ET.SubElement(channel, "link").text = INDEX_URL
    ET.SubElement(channel, "description").text = (
        "中华人民共和国财政部国库司“统计数据”栏目更新"
    )
    ET.SubElement(channel, "language").text = "zh-cn"
    ET.SubElement(channel, "generator").text = "MOF Statistics RSS Generator"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(items[0].published)
    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
    )

    for entry in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = entry.title
        ET.SubElement(item, "link").text = entry.url
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = entry.url
        ET.SubElement(item, "pubDate").text = format_datetime(entry.published)
        kind = "PDF 数据文件" if entry.url.lower().endswith(".pdf") else "统计数据发布"
        ET.SubElement(item, "description").text = f"{kind}。点击标题查看财政部原文。"

    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--feed-url", required=True)
    parser.add_argument("--max-items", type=int, default=50)
    args = parser.parse_args()

    items = collect_items(max_items=args.max_items)
    xml = build_feed(items, args.feed_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(xml)
    print(f"Wrote {len(items)} items to {args.output}")


if __name__ == "__main__":
    main()
