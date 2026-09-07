"""Proper iXBRL / XHTML accounts parser for Companies House filings.

Handles:
- XML namespaces (ix:, xbrli:, xbrldi:, link:, etc.)
- Contexts: instant vs duration, entity identifier
- Units and scale/decimals/sign on ix:nonFraction
- Taxonomy concept local-names (UK GAAP / FRS 102 / IFRS common tags)
- Multi-year: groups facts by period end date so current vs comparative are distinct

Does NOT invent numbers. Unmapped concepts are ignored (logged in debug stats).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy concept local-name -> PrivateIQ schema key
# Keys are (statement, schema_key). Prefer specific FRS 102 / IFRS names.
# ---------------------------------------------------------------------------
CONCEPT_MAP: dict[str, tuple[str, str]] = {
    # Income / P&L
    "Turnover": ("income_statement", "Revenue"),
    "TurnoverRevenue": ("income_statement", "Revenue"),
    "Revenue": ("income_statement", "Revenue"),
    "RevenueFromSaleOfGoods": ("income_statement", "Revenue"),
    "RevenueFromContractsWithCustomers": ("income_statement", "Revenue"),
    "CostSales": ("income_statement", "Cost of Sales"),
    "CostOfSales": ("income_statement", "Cost of Sales"),
    "GrossProfitLoss": ("income_statement", "Gross Profit"),
    "OperatingProfitLoss": ("income_statement", "Operating Profit"),
    "ProfitLossFromOperatingActivities": ("income_statement", "Operating Profit"),
    "ProfitLossOnOrdinaryActivitiesBeforeTax": ("income_statement", "Profit Before Tax"),
    "ProfitLossBeforeTax": ("income_statement", "Profit Before Tax"),
    "ProfitLossOnOrdinaryActivitiesBeforeTaxation": ("income_statement", "Profit Before Tax"),
    "ProfitLoss": ("income_statement", "Net Income"),
    "ProfitLossForPeriod": ("income_statement", "Net Income"),
    "ProfitLossAttributableToOwnersOfParent": ("income_statement", "Net Income"),
    "ProfitLossForPeriodAttributableToOwnersOfParent": ("income_statement", "Net Income"),
    # Balance sheet
    "CurrentAssets": ("balance_sheet", "Current Assets"),
    "FixedAssets": ("balance_sheet", "Non-Current Assets"),
    "NoncurrentAssets": ("balance_sheet", "Non-Current Assets"),
    "PropertyPlantEquipment": ("balance_sheet", "Non-Current Assets"),  # weak; only if FixedAssets absent
    "TotalAssets": ("balance_sheet", "Total Assets"),
    "Assets": ("balance_sheet", "Total Assets"),
    "Creditors": ("balance_sheet", "Total Liabilities"),  # ambiguous; low priority via confidence
    "CreditorsDueWithinOneYear": ("balance_sheet", "Current Liabilities"),
    "CreditorsAmountsFallingDueWithinOneYear": ("balance_sheet", "Current Liabilities"),
    "CurrentLiabilities": ("balance_sheet", "Current Liabilities"),
    "CreditorsDueAfterOneYear": ("balance_sheet", "Non-Current Liabilities"),
    "CreditorsAmountsFallingDueAfterMoreThanOneYear": ("balance_sheet", "Non-Current Liabilities"),
    "NoncurrentLiabilities": ("balance_sheet", "Non-Current Liabilities"),
    "TotalLiabilities": ("balance_sheet", "Total Liabilities"),
    "Liabilities": ("balance_sheet", "Total Liabilities"),
    "Equity": ("balance_sheet", "Equity"),
    "EquityAttributableToOwnersOfParent": ("balance_sheet", "Equity"),
    "ShareholdersFunds": ("balance_sheet", "Equity"),
    "CapitalAndReserves": ("balance_sheet", "Equity"),
    "NetAssetsLiabilities": ("balance_sheet", "Net Assets"),
    "NetAssetsLiabilitiesIncludingPensionAssetLiability": ("balance_sheet", "Net Assets"),
    "TotalAssetsLessCurrentLiabilities": ("balance_sheet", "Net Assets"),  # UK GAAP total; treat carefully
    # Cash flow
    "NetCashFlowsFromUsedInOperatingActivities": ("cash_flow", "Operating CF"),
    "CashFlowsFromUsedInOperatingActivities": ("cash_flow", "Operating CF"),
    "NetCashFromUsedInOperatingActivities": ("cash_flow", "Operating CF"),
    "NetCashFlowsFromUsedInInvestingActivities": ("cash_flow", "Investing CF"),
    "CashFlowsFromUsedInInvestingActivities": ("cash_flow", "Investing CF"),
    "NetCashFlowsFromUsedInFinancingActivities": ("cash_flow", "Financing CF"),
    "CashFlowsFromUsedInFinancingActivities": ("cash_flow", "Financing CF"),
    "IncreaseDecreaseInCashCashEquivalentsBeforeEffectOfExchangeRateChanges": (
        "cash_flow",
        "Net Change in Cash",
    ),
    "IncreaseDecreaseInCashAndCashEquivalents": ("cash_flow", "Net Change in Cash"),
    "NetIncreaseDecreaseInCashAndCashEquivalents": ("cash_flow", "Net Change in Cash"),
}

# Concepts that should NOT be used as primary for Total Assets / Net Assets collisions
WEAK_CONCEPTS = {
    "PropertyPlantEquipment",  # component, not total non-current
    "Creditors",  # ambiguous
    "TotalAssetsLessCurrentLiabilities",  # UK intermediate total, not always Net Assets
}


@dataclass
class ContextInfo:
    id: str
    instant: Optional[str] = None  # YYYY-MM-DD
    start: Optional[str] = None
    end: Optional[str] = None
    entity: Optional[str] = None
    dimensions: dict[str, str] = field(default_factory=dict)

    @property
    def period_end(self) -> Optional[str]:
        return self.instant or self.end

    @property
    def period_year(self) -> Optional[str]:
        pe = self.period_end
        if not pe:
            return None
        return pe[:4]

    @property
    def is_dimensional(self) -> bool:
        return bool(self.dimensions)


@dataclass
class Fact:
    concept_local: str
    value: float
    context_id: str
    period_end: Optional[str]
    period_year: Optional[str]
    unit: Optional[str]
    decimals: Optional[str]
    scale: int
    raw_text: str
    statement: str
    schema_key: str
    confidence: int


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.split(":")[-1]
    return tag


def _parse_number(text: str) -> Optional[float]:
    if text is None:
        return None
    t = str(text).strip().replace("\xa0", "").replace(",", "")
    if not t or t in ("—", "–", "-", "−", ""):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    # Strip currency symbols / spaces
    t = re.sub(r"[£$€\s]", "", t)
    t = t.replace("−", "-")
    try:
        val = float(t)
        return -abs(val) if neg else val
    except ValueError:
        return None


def _apply_scale_sign(val: float, scale: Optional[str], sign: Optional[str]) -> float:
    s = 0
    if scale is not None and str(scale).strip() != "":
        try:
            s = int(scale)
        except ValueError:
            s = 0
    out = val * (10 ** s)
    if sign == "-":
        out = -abs(out)
    return out


def _soup_attrs(tag) -> dict:
    # BeautifulSoup lowercases attrs; keep access helper
    return {str(k).lower(): v for k, v in tag.attrs.items()}


def parse_contexts_from_soup(soup: BeautifulSoup) -> dict[str, ContextInfo]:
    contexts: dict[str, ContextInfo] = {}
    # Match xbrli:context regardless of prefix
    for tag in soup.find_all(True):
        if _local(tag.name or "").lower() != "context":
            continue
        attrs = _soup_attrs(tag)
        cid = attrs.get("id")
        if not cid:
            continue
        instant = None
        start = end = None
        entity = None
        dims: dict[str, str] = {}

        for child in tag.find_all(True):
            ln = _local(child.name or "").lower()
            if ln == "identifier":
                entity = (child.get_text() or "").strip()
            elif ln == "instant":
                instant = (child.get_text() or "").strip()
            elif ln == "startdate":
                start = (child.get_text() or "").strip()
            elif ln == "enddate":
                end = (child.get_text() or "").strip()
            elif ln == "explicitmember":
                dim = child.get("dimension") or child.get("Dimension") or ""
                dims[_local(dim)] = (child.get_text() or "").strip()

        contexts[cid] = ContextInfo(
            id=cid,
            instant=instant,
            start=start,
            end=end,
            entity=entity,
            dimensions=dims,
        )
    return contexts


def _map_concept(local_name: str) -> Optional[tuple[str, str, int]]:
    mapped = CONCEPT_MAP.get(local_name)
    if not mapped:
        return None
    conf = 100
    if local_name in WEAK_CONCEPTS:
        conf = 40
    return mapped[0], mapped[1], conf


def extract_facts(content: bytes) -> tuple[list[Fact], dict[str, Any]]:
    """Parse iXBRL bytes into typed Facts + debug stats."""
    stats: dict[str, Any] = {
        "facts_total": 0,
        "facts_mapped": 0,
        "contexts": 0,
        "unmapped_concepts": [],
        "errors": [],
    }
    facts: list[Fact] = []

    try:
        from bs4 import XMLParsedAsHTMLWarning
        import warnings
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        try:
            soup = BeautifulSoup(content, "lxml-xml")
            if soup.find() is None:
                raise ValueError("empty xml parse")
        except Exception:
            soup = BeautifulSoup(content, "lxml")
    except Exception as e:
        stats["errors"].append(f"soup_parse: {e}")
        return [], stats

    contexts = parse_contexts_from_soup(soup)
    stats["contexts"] = len(contexts)

    for tag in soup.find_all(True):
        name = (tag.name or "").lower()
        local_tag = _local(name).lower()
        if local_tag != "nonfraction":
            continue

        stats["facts_total"] += 1
        attrs = _soup_attrs(tag)
        concept = attrs.get("name") or ""
        concept_local = concept.split(":")[-1] if concept else ""
        mapped = _map_concept(concept_local)
        if not mapped:
            if concept_local and concept_local not in stats["unmapped_concepts"]:
                if len(stats["unmapped_concepts"]) < 50:
                    stats["unmapped_concepts"].append(concept_local)
            continue

        statement, schema_key, confidence = mapped
        ctx_id = attrs.get("contextref") or ""
        ctx = contexts.get(ctx_id)
        # Skip heavily dimensional breakdowns (segment/product) for totals
        if ctx and ctx.is_dimensional:
            # Allow if only unused dimension types we don't care about? Prefer undimensional.
            continue

        raw_text = tag.get_text(strip=True)
        base = _parse_number(raw_text)
        if base is None:
            continue

        scale = attrs.get("scale")
        sign = attrs.get("sign")
        value = _apply_scale_sign(base, scale, sign)
        try:
            scale_int = int(scale) if scale is not None and str(scale).strip() != "" else 0
        except ValueError:
            scale_int = 0

        facts.append(
            Fact(
                concept_local=concept_local,
                value=value,
                context_id=ctx_id,
                period_end=ctx.period_end if ctx else None,
                period_year=ctx.period_year if ctx else None,
                unit=attrs.get("unitref"),
                decimals=attrs.get("decimals"),
                scale=scale_int,
                raw_text=raw_text,
                statement=statement,
                schema_key=schema_key,
                confidence=confidence,
            )
        )
        stats["facts_mapped"] += 1

    return facts, stats


def facts_to_years(
    facts: list[Fact],
    *,
    filing_date: str = "",
    source_url: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Group facts by period_year into PrivateIQ year blocks (without final prune)."""
    from schema import line

    by_year: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if not f.period_year:
            continue
        by_year[f.period_year].append(f)

    years: list[dict] = []
    for year in sorted(by_year.keys(), reverse=True):
        income: dict = {}
        balance: dict = {}
        cash: dict = {}
        buckets = {
            "income_statement": income,
            "balance_sheet": balance,
            "cash_flow": cash,
        }
        # Within a year, prefer higher confidence; on tie prefer later period_end (current)
        # and prefer stronger concepts (already in confidence).
        candidates: dict[tuple[str, str], Fact] = {}
        for f in by_year[year]:
            key = (f.statement, f.schema_key)
            prev = candidates.get(key)
            if prev is None:
                candidates[key] = f
                continue
            if f.confidence > prev.confidence:
                candidates[key] = f
                continue
            if f.confidence == prev.confidence:
                # Prefer fact whose period_end is later (same year, e.g. restated)
                if (f.period_end or "") > (prev.period_end or ""):
                    candidates[key] = f
                # Prefer more precise decimals if available
                elif f.decimals not in (None, "INF") and prev.decimals in (None, "INF"):
                    candidates[key] = f

        period_end = None
        for f in candidates.values():
            if f.period_end and (period_end is None or f.period_end > period_end):
                period_end = f.period_end
            prov = {
                "method": "ixbrl",
                "raw_label": f.concept_local,
                "raw_value": f.raw_text,
                "concept": f.concept_local,
                "context_id": f.context_id,
                "period_end": f.period_end or "",
                "scale_applied": f.scale,
                "unit": f.unit or "",
                "confidence": f.confidence,
            }
            buckets[f.statement][f.schema_key] = line(
                f.value,
                source=source_url,
                provenance=prov,  # type: ignore[arg-type]
            )

        years.append(
            {
                "period": year,
                "filing_date": filing_date or (period_end or ""),
                "parsing_status": "ixbrl",
                "income_statement": income,
                "balance_sheet": balance,
                "cash_flow": cash,
            }
        )

    return years


def parse_ixbrl_document(
    content: bytes,
    *,
    filing_date: str = "",
    source_url: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Public entry: bytes -> (year_blocks, stats)."""
    facts, stats = extract_facts(content)
    years = facts_to_years(facts, filing_date=filing_date, source_url=source_url)
    stats["years_found"] = [y["period"] for y in years]
    return years, stats


# ---------------------------------------------------------------------------
# Document fetch helper (Companies House document API)
# ---------------------------------------------------------------------------
def fetch_document_content(
    document_metadata_url: str,
    api_key: str,
    *,
    timeout: int = 60,
) -> tuple[Optional[bytes], Optional[str], Optional[str], dict]:
    """
    Returns (content_bytes, kind, content_url, meta_info).
    kind is 'xhtml' | 'pdf' | None.
    Prefers application/xhtml+xml over PDF.
    """
    import requests

    info: dict[str, Any] = {}
    meta_res = requests.get(document_metadata_url, auth=(api_key, ""), timeout=timeout)
    if meta_res.status_code != 200:
        info["meta_status"] = meta_res.status_code
        return None, None, None, info

    meta = meta_res.json()
    info["resources"] = list((meta.get("resources") or {}).keys())
    resources = meta.get("resources") or {}
    content_url = None
    kind = None

    if "application/xhtml+xml" in resources:
        content_url = resources["application/xhtml+xml"].get("content_url")
        kind = "xhtml"
    elif "application/pdf" in resources:
        content_url = resources["application/pdf"].get("content_url")
        kind = "pdf"

    if not content_url:
        content_url = f"{document_metadata_url.rstrip('/')}/content"
        kind = kind or "pdf"

    accept = "application/xhtml+xml" if kind == "xhtml" else "application/pdf"
    doc_res = requests.get(
        content_url,
        auth=(api_key, ""),
        headers={"Accept": accept},
        timeout=timeout,
    )
    if doc_res.status_code != 200 and kind == "xhtml":
        doc_res = requests.get(
            content_url,
            auth=(api_key, ""),
            headers={"Accept": "application/pdf"},
            timeout=timeout,
        )
        kind = "pdf"

    if doc_res.status_code != 200:
        info["doc_status"] = doc_res.status_code
        return None, None, content_url, info

    ctype = (doc_res.headers.get("Content-Type") or "").lower()
    if "xhtml" in ctype or "html" in ctype or "xml" in ctype:
        kind = "xhtml"
    elif "pdf" in ctype:
        kind = "pdf"

    # Sniff content
    head = doc_res.content[:200].lstrip().lower()
    if head.startswith(b"<?xml") or b"<html" in head or b"ix:header" in head or b"xbrl" in head:
        kind = "xhtml"
    elif head.startswith(b"%pdf"):
        kind = "pdf"

    info["content_type"] = ctype
    info["kind"] = kind
    info["bytes"] = len(doc_res.content)
    return doc_res.content, kind, content_url, info
