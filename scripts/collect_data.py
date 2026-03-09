#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "sources.json"
RAW_DIR = ROOT / "data" / "raw"
HISTORY_PATH = ROOT / "data" / "history.csv"
LATEST_PATH = ROOT / "data" / "latest_metrics.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


@dataclass
class Metric:
    city: str
    city_code: str
    indicator: str
    value: float
    unit: str
    source_url: str
    capture_date: str


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_html(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text


def extract_candidate_links(html: str, base_url: str, link_keywords: Iterable[str]) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    candidates: List[Tuple[str, str]] = []
    seen = set()

    for a in soup.select("a[href]"):
        text = a.get_text(" ", strip=True)
        href = a.get("href", "")
        full_url = urljoin(base_url, href)
        combined = f"{text} {href}"
        score = sum(1 for kw in link_keywords if kw in combined)
        if score <= 0:
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        candidates.append((full_url, text))

    candidates.sort(key=lambda x: len(x[1]), reverse=True)
    return candidates[:25]


def extract_first_number(text: str) -> float | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not numbers:
        return None
    for raw in reversed(numbers):
        try:
            value = float(raw)
        except ValueError:
            continue
        if abs(value) > 1900:
            continue
        return value
    return None


def detect_unit(text: str) -> str:
    for unit in ["亿元", "万亿元", "亿元人民币", "万", "%", "元", "亿美元"]:
        if unit in text:
            return unit
    return ""


def extract_from_tables(html: str, indicator_keywords: Dict[str, List[str]]) -> Dict[str, Tuple[float, str]]:
    results: Dict[str, Tuple[float, str]] = {}
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        return results

    for table in tables:
        table = table.fillna("")
        for _, row in table.iterrows():
            row_text = " ".join(str(item) for item in row.tolist())
            for indicator, keywords in indicator_keywords.items():
                if indicator in results:
                    continue
                if not any(k in row_text for k in keywords):
                    continue
                value = extract_first_number(row_text)
                if value is None:
                    continue
                results[indicator] = (value, detect_unit(row_text))
    return results


def extract_from_text(html: str, indicator_keywords: Dict[str, List[str]]) -> Dict[str, Tuple[float, str]]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    results: Dict[str, Tuple[float, str]] = {}

    for indicator, keywords in indicator_keywords.items():
        for kw in keywords:
            for match in re.finditer(re.escape(kw), text):
                segment = text[max(0, match.start() - 16) : match.end() + 32]
                value = extract_first_number(segment)
                if value is None:
                    continue
                results[indicator] = (value, detect_unit(segment))
                break
            if indicator in results:
                break
    return results


def collect_city_metrics(city_cfg: dict, link_keywords: List[str], indicator_keywords: Dict[str, List[str]]) -> List[Metric]:
    capture_date = date.today().isoformat()
    source_pool: List[str] = []

    for seed in city_cfg["seed_urls"]:
        try:
            html = fetch_html(seed)
        except Exception:
            continue
        source_pool.append(seed)
        for link, _ in extract_candidate_links(html, city_cfg["base_url"], link_keywords):
            if link not in source_pool:
                source_pool.append(link)

    metrics_by_indicator: Dict[str, Metric] = {}

    for url in source_pool[:30]:
        try:
            html = fetch_html(url)
        except Exception:
            continue

        table_data = extract_from_tables(html, indicator_keywords)
        text_data = extract_from_text(html, indicator_keywords)
        merged = {**text_data, **table_data}

        for indicator, (value, unit) in merged.items():
            if indicator in metrics_by_indicator:
                continue
            metrics_by_indicator[indicator] = Metric(
                city=city_cfg["name"],
                city_code=city_cfg["code"],
                indicator=indicator,
                value=value,
                unit=unit,
                source_url=url,
                capture_date=capture_date,
            )

        if len(metrics_by_indicator) >= len(indicator_keywords):
            break

    return list(metrics_by_indicator.values())


def save_outputs(metrics: List[Metric]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    snapshot = [m.__dict__ for m in metrics]
    snapshot_name = f"snapshot_{date.today().isoformat()}.json"
    (RAW_DIR / snapshot_name).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    new_rows = pd.DataFrame(snapshot)
    if HISTORY_PATH.exists():
        history = pd.read_csv(HISTORY_PATH)
        history = pd.concat([history, new_rows], ignore_index=True)
    else:
        history = new_rows

    history = history.drop_duplicates(
        subset=["capture_date", "city_code", "indicator"],
        keep="last",
    )
    history = history.sort_values(["capture_date", "city_code", "indicator"])
    history.to_csv(HISTORY_PATH, index=False, encoding="utf-8")

    latest = (
        history.sort_values("capture_date")
        .groupby(["city_code", "indicator"], as_index=False)
        .tail(1)
        .sort_values(["indicator", "city_code"])
    )
    latest.to_csv(LATEST_PATH, index=False, encoding="utf-8")


def main() -> None:
    cfg = load_config()
    all_metrics: List[Metric] = []

    for city in cfg["cities"]:
        all_metrics.extend(
            collect_city_metrics(
                city_cfg=city,
                link_keywords=cfg["link_keywords"],
                indicator_keywords=cfg["indicator_keywords"],
            )
        )

    if not all_metrics:
        if HISTORY_PATH.exists():
            print("No new metrics collected today. Keeping existing history.")
            return
        raise RuntimeError("No metrics were collected. Check source URLs and keyword settings.")

    save_outputs(all_metrics)


if __name__ == "__main__":
    main()
