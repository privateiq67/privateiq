"""Canonical CapIQ-style financial statement schema for PrivateIQ.

Assumptions documented here and in README:
- Values are absolute GBP (scale already applied), not thousands/millions.
- Line items may be omitted when not present; null values are dropped in API output.
- `provenance` on each line is optional but preferred for auditability.
- `parsing_status` is one of: ixbrl | pdf | fixture | partial | failed

Optional / extended keys (beyond core CapIQ) are documented below so iXBRL can
surface FRS 102 and bank P&L lines without inventing a second schema:
- Income: Administrative Expenses, Staff Costs, Finance Income, Finance Costs,
  Tax, Comprehensive Income, Net Interest Income, Fee and Commission Income,
  Total Income
- Balance: Net Current Assets (UK GAAP subtotal; not used as Total Assets)
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

SCHEMA_VERSION = "1.1"

INCOME_STATEMENT_KEYS = [
    "Revenue",
    "Net Interest Income",
    "Fee and Commission Income",
    "Total Income",
    "Cost of Sales",
    "Gross Profit",
    "Administrative Expenses",
    "Staff Costs",
    "Operating Profit",
    "EBIT",
    "EBITDA (Est)",
    "Finance Income",
    "Finance Costs",
    "Profit Before Tax",
    "Tax",
    "Net Income",
    "Comprehensive Income",
]

BALANCE_SHEET_KEYS = [
    "Current Assets",
    "Non-Current Assets",
    "Total Assets",
    "Current Liabilities",
    "Non-Current Liabilities",
    "Total Liabilities",
    "Equity",
    "Net Assets",
    "Net Current Assets",
]

CASH_FLOW_KEYS = [
    "Operating CF",
    "Investing CF",
    "Financing CF",
    "Net Change in Cash",
]

# Confidence tiers used by the normaliser when resolving conflicts
CONFIDENCE_TAXONOMY = 100  # iXBRL concept match
CONFIDENCE_LABEL_EXACT = 80  # exact synonym map on PDF/text label
CONFIDENCE_LABEL_FUZZY = 50  # contains / fuzzy label match
CONFIDENCE_DERIVED = 30  # arithmetic estimate (e.g. EBITDA)


class Provenance(TypedDict, total=False):
    method: str  # ixbrl | pdf | fixture | derived
    raw_label: str
    raw_value: str
    concept: str
    context_id: str
    period_end: str
    scale_applied: int
    page: int
    unit: str
    confidence: int
    notes: str


class LineItem(TypedDict, total=False):
    value: Optional[float]
    source: Optional[str]
    estimated: bool
    provenance: Provenance


def line(
    value: Optional[float],
    *,
    source: Optional[str] = None,
    estimated: bool = False,
    provenance: Optional[Provenance] = None,
) -> LineItem:
    item: LineItem = {"value": value}
    if source:
        item["source"] = source
    if estimated:
        item["estimated"] = True
    if provenance:
        item["provenance"] = provenance
    return item


def year_block(
    period: str,
    filing_date: str = "",
    parsing_status: str = "partial",
    income: Optional[dict] = None,
    balance: Optional[dict] = None,
    cash_flow: Optional[dict] = None,
    warnings: Optional[list] = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "period": period,
        "filing_date": filing_date,
        "parsing_status": parsing_status,
        "income_statement": income or {},
        "balance_sheet": balance or {},
        "cash_flow": cash_flow or {},
    }
    if warnings:
        block["warnings"] = warnings
    return block


def financials_response(
    company_number: str,
    years: list[dict],
    *,
    extra: Optional[dict] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "company_number": company_number,
        "years": years,
        "schema_version": SCHEMA_VERSION,
    }
    if extra:
        out.update(extra)
    return out
