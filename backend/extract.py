"""Orchestrator: iXBRL first, PDF fallback, then normalise + cache."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ixbrl import fetch_document_content, parse_ixbrl_document
from normalize import apply_labelled_items, merge_ixbrl_year
from pdf_extract import extract_from_pdf_bytes, rows_to_year_dicts
from schema import financials_response

logger = logging.getLogger(__name__)
YEAR_RE = re.compile(r"\b(20[1-3]\d)\b")


def period_from_filing(filing: dict) -> str:
    # Prefer accounts period end from description / action date
    for key in ("description", "type", "date"):
        val = filing.get(key) or ""
        if isinstance(val, dict):
            continue
        m = YEAR_RE.search(str(val))
        if m:
            # Prefer last year mentioned in description (often period end)
            years = YEAR_RE.findall(str(val))
            if years:
                return years[-1]
    date = filing.get("date") or ""
    m = YEAR_RE.search(str(date))
    return m.group(1) if m else str(date)[:4]


def parse_filing_bytes(
    content: bytes,
    kind: str,
    *,
    filing_date: str = "",
    source_url: Optional[str] = None,
    allow_ocr: bool = True,
) -> tuple[list[dict], dict[str, Any]]:
    """Parse a single filing document into normalised year blocks."""
    meta: dict[str, Any] = {"kind": kind}

    if kind == "xhtml":
        years, stats = parse_ixbrl_document(
            content, filing_date=filing_date, source_url=source_url
        )
        meta["ixbrl"] = stats
        normalised = [merge_ixbrl_year(y) for y in years]
        if normalised:
            return normalised, meta
        # Fall through to try treating bytes as HTML text tables? If iXBRL empty, try PDF path only if PDF magic
        if content.lstrip().startswith(b"%PDF"):
            kind = "pdf"
        else:
            meta["note"] = "ixbrl_produced_no_years"
            return [], meta

    if kind == "pdf":
        rows, stats = extract_from_pdf_bytes(content, allow_ocr=allow_ocr)
        meta["pdf"] = stats
        intermediate = rows_to_year_dicts(rows, filing_date=filing_date, source_url=source_url)
        normalised = []
        for block in intermediate:
            normalised.append(
                apply_labelled_items(
                    block.get("labelled") or [],
                    period=block.get("period") or "unknown",
                    filing_date=block.get("filing_date") or filing_date,
                    parsing_status="pdf",
                )
            )
        return normalised, meta

    return [], {**meta, "error": f"unsupported_kind:{kind}"}


def parse_filing_from_metadata(
    document_metadata_url: str,
    api_key: str,
    *,
    filing_date: str = "",
    allow_ocr: bool = True,
) -> tuple[list[dict], dict[str, Any]]:
    content, kind, content_url, info = fetch_document_content(document_metadata_url, api_key)
    meta = {"fetch": info, "content_url": content_url}
    if not content or not kind:
        meta["error"] = "download_failed"
        return [], meta
    years, parse_meta = parse_filing_bytes(
        content,
        kind,
        filing_date=filing_date,
        source_url=content_url,
        allow_ocr=allow_ocr,
    )
    meta.update(parse_meta)
    return years, meta


def build_financials_for_company(
    company_number: str,
    filings: list[dict],
    api_key: str,
    *,
    max_filings: int = 5,
    allow_ocr: bool = True,
    cache_get=None,
    cache_put=None,
) -> dict[str, Any]:
    """
    Walk accounts filings, prefer cache hits, parse iXBRL/PDF, merge by period.
    cache_get(company_number, period) -> year dict | None
    cache_put(company_number, year_dict) -> None
    """
    by_period: dict[str, dict] = {}
    parse_log: list[dict] = []

    for filing in filings:
        if len(by_period) >= max_filings and len(parse_log) >= max_filings:
            break
        links = filing.get("links") or {}
        meta_url = links.get("document_metadata")
        if not meta_url:
            continue
        filing_date = filing.get("date") or ""
        period_hint = period_from_filing(filing)

        if cache_get and period_hint:
            cached = cache_get(company_number, period_hint)
            if cached and cached.get("parsing_status") in ("ixbrl", "pdf", "fixture"):
                # Only reuse if it has some numbers
                has = any(
                    cached.get(s)
                    for s in ("income_statement", "balance_sheet", "cash_flow")
                )
                if has:
                    by_period.setdefault(period_hint, cached)
                    parse_log.append({"period": period_hint, "source": "cache"})
                    continue

        years, meta = parse_filing_from_metadata(
            meta_url,
            api_key,
            filing_date=filing_date,
            allow_ocr=allow_ocr,
        )
        parse_log.append({"period_hint": period_hint, "meta": meta, "years": [y.get("period") for y in years]})

        for y in years:
            p = y.get("period") or period_hint
            if not p:
                continue
            y["period"] = p
            # Prefer ixbrl over pdf for same period; prefer more populated
            existing = by_period.get(p)
            if existing is None:
                by_period[p] = y
            else:
                rank = {"ixbrl": 3, "pdf": 2, "fixture": 1, "partial": 0, "failed": -1}
                if rank.get(y.get("parsing_status"), 0) > rank.get(existing.get("parsing_status"), 0):
                    by_period[p] = y
            if cache_put:
                try:
                    cache_put(company_number, by_period[p])
                except Exception as e:
                    logger.warning("cache_put failed: %s", e)

        if len(by_period) >= 3:
            # Keep scanning a bit for better status upgrades but stop early enough
            if all(
                by_period[p].get("parsing_status") == "ixbrl"
                for p in list(by_period)[:3]
            ):
                break

    years_sorted = [by_period[k] for k in sorted(by_period.keys(), reverse=True)]
    return financials_response(
        company_number,
        years_sorted[:5],
        extra={"parse_log": parse_log} if logger.isEnabledFor(logging.DEBUG) else None,
    )
