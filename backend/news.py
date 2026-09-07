"""UK business / financial news via RSS (feedparser)."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import quote_plus

import feedparser

FEEDS = [
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Guardian Business", "https://www.theguardian.com/uk/business/rss"),
    ("FT Companies", "https://www.ft.com/companies?format=rss"),
]

VALUATION_RE = re.compile(
    r"(?:valued?\s+at|valuation\s+of|worth)\s*"
    r"(?P<currency>£|\$|€|GBP|USD|EUR)?\s*"
    r"(?P<amount>[\d,.]+)\s*"
    r"(?P<scale>billion|bn|million|m|trillion|tn)?",
    re.IGNORECASE,
)


def _parse_valuation(text: str) -> Optional[dict]:
    m = VALUATION_RE.search(text or "")
    if not m:
        return None
    raw_amount = m.group("amount").replace(",", "")
    try:
        amount = float(raw_amount)
    except ValueError:
        return None
    scale = (m.group("scale") or "").lower()
    mult = 1.0
    if scale in ("billion", "bn"):
        mult = 1000.0
    elif scale in ("million", "m"):
        mult = 1.0
    elif scale in ("trillion", "tn"):
        mult = 1_000_000.0
    currency = m.group("currency") or "£"
    if currency.upper() in ("GBP",):
        currency = "£"
    elif currency.upper() in ("USD",):
        currency = "$"
    elif currency.upper() in ("EUR",):
        currency = "€"
    return {
        "amount_m": amount * mult,
        "currency": currency,
        "raw": m.group(0).strip(),
    }


def _entry_to_item(entry: Any, source: str, company_name: Optional[str] = None) -> Optional[dict]:
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or ""
    link = getattr(entry, "link", "") or ""
    published = (
        getattr(entry, "published", None)
        or getattr(entry, "updated", None)
        or ""
    )
    if company_name:
        hay = f"{title} {summary}".lower()
        tokens = [t for t in re.split(r"\W+", company_name.lower()) if len(t) > 2]
        # Require at least one meaningful token match for company-filtered feeds
        if tokens and not any(t in hay for t in tokens[:3]):
            # Still allow Google News query results through (already filtered by query)
            if "news.google.com" not in (getattr(entry, "link", "") or ""):
                pass  # keep; caller may use Google News primarily when name set

    text = f"{title} {summary}"
    item = {
        "title": title,
        "link": link,
        "published": published,
        "source": source,
    }
    val = _parse_valuation(text)
    if val:
        item["valuation_data"] = val
    return item


def fetch_news(name: Optional[str] = None, limit: int = 20) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()

    feeds = list(FEEDS)
    if name:
        q = quote_plus(f"{name} UK business OR finance OR valuation")
        feeds.insert(
            0,
            (
                "Google News",
                f"https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en",
            ),
        )

    for source, url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            continue
        for entry in parsed.entries[:15]:
            item = _entry_to_item(entry, source, company_name=name)
            if not item or not item.get("link"):
                continue
            if item["link"] in seen_links:
                continue
            # When filtering by name against general feeds, prefer title match
            if name and source != "Google News":
                tokens = [t for t in re.split(r"\W+", name.lower()) if len(t) > 2]
                hay = item["title"].lower()
                if tokens and not any(t in hay for t in tokens[:2]):
                    continue
            seen_links.add(item["link"])
            items.append(item)
            if len(items) >= limit:
                return items

    return items[:limit]
