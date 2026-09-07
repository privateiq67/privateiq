"""Normalisation: synonym map + confidence-aware merge into CapIQ schema.

Rules:
- Never silently overwrite a higher-confidence value with a lower one.
- Taxonomy-backed (iXBRL) beats PDF label matches beats derived estimates.
- Soft balance-sheet identity checks emit warnings, not hard failures.
- Drop null-valued lines from API output; keep stable keys when present.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from schema import (
    CONFIDENCE_DERIVED,
    CONFIDENCE_LABEL_EXACT,
    CONFIDENCE_LABEL_FUZZY,
    CONFIDENCE_TAXONOMY,
    line,
    year_block,
)

# Explicit synonym map: normalised label -> (statement, schema_key)
SYNONYMS: dict[str, tuple[str, str]] = {
    "turnover": ("income_statement", "Revenue"),
    "revenue": ("income_statement", "Revenue"),
    "total revenue": ("income_statement", "Revenue"),
    "total turnover": ("income_statement", "Revenue"),
    "sales": ("income_statement", "Revenue"),
    "cost of sales": ("income_statement", "Cost of Sales"),
    "cost of goods sold": ("income_statement", "Cost of Sales"),
    "gross profit": ("income_statement", "Gross Profit"),
    "gross profit/(loss)": ("income_statement", "Gross Profit"),
    "gross profit (loss)": ("income_statement", "Gross Profit"),
    "operating profit": ("income_statement", "Operating Profit"),
    "operating loss": ("income_statement", "Operating Profit"),
    "operating profit/(loss)": ("income_statement", "Operating Profit"),
    "operating (loss)/profit": ("income_statement", "Operating Profit"),
    "profit from operations": ("income_statement", "Operating Profit"),
    "loss from operations": ("income_statement", "Operating Profit"),
    "ebit": ("income_statement", "EBIT"),
    "ebitda": ("income_statement", "EBITDA (Est)"),
    "profit before tax": ("income_statement", "Profit Before Tax"),
    "loss before tax": ("income_statement", "Profit Before Tax"),
    "profit/(loss) before tax": ("income_statement", "Profit Before Tax"),
    "profit before taxation": ("income_statement", "Profit Before Tax"),
    "loss before taxation": ("income_statement", "Profit Before Tax"),
    "(loss)/profit before taxation": ("income_statement", "Profit Before Tax"),
    "profit/(loss) before taxation": ("income_statement", "Profit Before Tax"),
    "profit on ordinary activities before taxation": ("income_statement", "Profit Before Tax"),
    "profit for the year": ("income_statement", "Net Income"),
    "loss for the year": ("income_statement", "Net Income"),
    "profit/(loss) for the year": ("income_statement", "Net Income"),
    "profit for the financial year": ("income_statement", "Net Income"),
    "loss for the financial year": ("income_statement", "Net Income"),
    "(loss)/profit for the financial year": ("income_statement", "Net Income"),
    "profit/(loss) for the financial year": ("income_statement", "Net Income"),
    "profit for the period": ("income_statement", "Net Income"),
    "profit after tax": ("income_statement", "Net Income"),
    "net income": ("income_statement", "Net Income"),
    "current assets": ("balance_sheet", "Current Assets"),
    "total current assets": ("balance_sheet", "Current Assets"),
    "fixed assets": ("balance_sheet", "Non-Current Assets"),
    "non-current assets": ("balance_sheet", "Non-Current Assets"),
    "non current assets": ("balance_sheet", "Non-Current Assets"),
    "total fixed assets": ("balance_sheet", "Non-Current Assets"),
    "total assets": ("balance_sheet", "Total Assets"),
    "current liabilities": ("balance_sheet", "Current Liabilities"),
    "creditors: amounts falling due within one year": ("balance_sheet", "Current Liabilities"),
    "creditors amounts falling due within one year": ("balance_sheet", "Current Liabilities"),
    "creditors: amounts falling due after more than one year": (
        "balance_sheet",
        "Non-Current Liabilities",
    ),
    "creditors amounts falling due after more than one year": (
        "balance_sheet",
        "Non-Current Liabilities",
    ),
    "non-current liabilities": ("balance_sheet", "Non-Current Liabilities"),
    "total liabilities": ("balance_sheet", "Total Liabilities"),
    "equity": ("balance_sheet", "Equity"),
    "total equity": ("balance_sheet", "Equity"),
    "shareholders funds": ("balance_sheet", "Equity"),
    "shareholders' funds": ("balance_sheet", "Equity"),
    "capital and reserves": ("balance_sheet", "Equity"),
    "net assets": ("balance_sheet", "Net Assets"),
    "net assets/(liabilities)": ("balance_sheet", "Net Assets"),
    "net assets (liabilities)": ("balance_sheet", "Net Assets"),
    "net cash from operating activities": ("cash_flow", "Operating CF"),
    "net cash generated from operating activities": ("cash_flow", "Operating CF"),
    "cash flows from operating activities": ("cash_flow", "Operating CF"),
    "net cash from investing activities": ("cash_flow", "Investing CF"),
    "cash flows from investing activities": ("cash_flow", "Investing CF"),
    "net cash from financing activities": ("cash_flow", "Financing CF"),
    "cash flows from financing activities": ("cash_flow", "Financing CF"),
    "net increase/(decrease) in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net increase in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net decrease in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net increase/(decrease) in cash": ("cash_flow", "Net Change in Cash"),
}


def _norm_label(label: str) -> str:
    s = label.lower().replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip(" :")
    # Strip trailing note refs like "3" / "(note 4)"
    s = re.sub(r"\s*\(note\s*\d+\)\s*$", "", s)
    s = re.sub(r"\s+\d{1,2}$", "", s)
    return s.strip()


def resolve_label(label: str) -> Optional[tuple[str, str, int]]:
    """Return (statement, schema_key, confidence) or None."""
    key = _norm_label(label)
    if key in SYNONYMS:
        stmt, sk = SYNONYMS[key]
        return stmt, sk, CONFIDENCE_LABEL_EXACT
    # OCR-tolerant UK creditors headings (word order often scrambled)
    if "creditors" in key and "within" in key:
        return "balance_sheet", "Current Liabilities", CONFIDENCE_LABEL_FUZZY
    if "creditors" in key and ("after" in key or "more than one" in key):
        return "balance_sheet", "Non-Current Liabilities", CONFIDENCE_LABEL_FUZZY
    # Reject note-line / KPI / charge descriptions that merely contain a synonym
    if re.search(
        r"\b(depreciation|amortisation|amortization|impairment|lease charges?|"
        r"revenue growth|gross profit margin|weekly|compared|underpinned)\b",
        key,
    ):
        return None
    # Prefer longest alias; require alias to dominate the label (avoid
    # "net current assets" → Current Assets, "total assets less..." → Total Assets)
    best = None
    best_len = 0
    for alias, target in SYNONYMS.items():
        if len(alias) < 5:
            continue
        if alias not in key:
            continue
        if key.startswith(alias):
            rest = key[len(alias):].strip(" :.-")
            # Allow trailing note refs only; reject "total assets less current..."
            if rest and not re.fullmatch(r"\d{1,2}", rest):
                if len(alias) < 0.85 * len(key):
                    continue
        elif len(alias) < 0.55 * len(key):
            continue
        if len(alias) > best_len:
            best = (target[0], target[1], CONFIDENCE_LABEL_FUZZY)
            best_len = len(alias)
    return best


def _conf_of(item: dict) -> int:
    prov = item.get("provenance") or {}
    if "confidence" in prov:
        return int(prov["confidence"])
    if item.get("estimated"):
        return CONFIDENCE_DERIVED
    return CONFIDENCE_LABEL_EXACT


def _set_if_better(bucket: dict, schema_key: str, item: dict) -> None:
    if item.get("value") is None:
        return
    existing = bucket.get(schema_key)
    if existing is None or existing.get("value") is None:
        bucket[schema_key] = item
        return
    if _conf_of(item) > _conf_of(existing):
        bucket[schema_key] = item
        return
    # Equal confidence: keep existing (first wins) — do not silently overwrite
    return


def apply_labelled_items(
    labelled: list[dict],
    *,
    period: str,
    filing_date: str = "",
    parsing_status: str = "partial",
) -> dict:
    income: dict = {}
    balance: dict = {}
    cash: dict = {}
    buckets = {
        "income_statement": income,
        "balance_sheet": balance,
        "cash_flow": cash,
    }

    for entry in labelled:
        label = entry.get("label") or ""
        value = entry.get("value")
        resolved = resolve_label(label)
        if not resolved:
            continue
        stmt, schema_key, conf = resolved
        # Prefer section hint if present and conflicts with synonym statement — trust synonym
        prov = dict(entry.get("provenance") or {})
        prov.setdefault("confidence", conf)
        prov.setdefault("raw_label", label)
        item = line(
            float(value),
            source=entry.get("source"),
            provenance=prov,  # type: ignore[arg-type]
        )
        _set_if_better(buckets[stmt], schema_key, item)

    warnings = derive_and_validate(income, balance, cash)
    income = {k: v for k, v in income.items() if v.get("value") is not None}
    balance = {k: v for k, v in balance.items() if v.get("value") is not None}
    cash = {k: v for k, v in cash.items() if v.get("value") is not None}

    status = parsing_status
    if not income and not balance and not cash:
        status = "partial"

    return year_block(
        period=period,
        filing_date=filing_date,
        parsing_status=status,
        income=income,
        balance=balance,
        cash_flow=cash,
        warnings=warnings or None,
    )


def merge_ixbrl_year(year: dict) -> dict:
    """Run derive/validate on an already-schema-shaped iXBRL year block."""
    income = dict(year.get("income_statement") or {})
    balance = dict(year.get("balance_sheet") or {})
    cash = dict(year.get("cash_flow") or {})
    warnings = derive_and_validate(income, balance, cash)
    year = dict(year)
    year["income_statement"] = {k: v for k, v in income.items() if v.get("value") is not None}
    year["balance_sheet"] = {k: v for k, v in balance.items() if v.get("value") is not None}
    year["cash_flow"] = {k: v for k, v in cash.items() if v.get("value") is not None}
    if warnings:
        year["warnings"] = warnings
    return year


def derive_and_validate(income: dict, balance: dict, cash: dict) -> list[str]:
    """Fill safe derived lines; emit soft validation warnings."""
    warnings: list[str] = []

    def val(bucket, key):
        item = bucket.get(key) or {}
        return item.get("value")

    def set_derived(bucket, key, value, note: str):
        if value is None:
            return
        existing = bucket.get(key)
        if existing and existing.get("value") is not None:
            return
        bucket[key] = line(
            value,
            estimated=True,
            provenance={
                "method": "derived",
                "confidence": CONFIDENCE_DERIVED,
                "notes": note,
            },
        )

    rev = val(income, "Revenue")
    cogs = val(income, "Cost of Sales")
    if val(income, "Gross Profit") is None and rev is not None and cogs is not None:
        set_derived(income, "Gross Profit", rev - abs(cogs), "Revenue - |Cost of Sales|")

    op = val(income, "Operating Profit")
    ebit = val(income, "EBIT")
    if ebit is None and op is not None:
        set_derived(income, "EBIT", op, "EBIT aliased from Operating Profit")
    if op is None and ebit is not None:
        set_derived(income, "Operating Profit", ebit, "Operating Profit aliased from EBIT")

    ebit_v = val(income, "EBIT")
    if val(income, "EBITDA (Est)") is None and ebit_v is not None:
        # Honest: without D&A we cannot know EBITDA — leave absent rather than invent
        # (Previous MVP invented EBIT*1.15; that is forbidden under correctness mandate.)
        pass

    ca = val(balance, "Current Assets")
    nca = val(balance, "Non-Current Assets")
    ta = val(balance, "Total Assets")
    if ta is None and ca is not None and nca is not None:
        set_derived(balance, "Total Assets", ca + nca, "CA + NCA")

    cl = val(balance, "Current Liabilities")
    ncl = val(balance, "Non-Current Liabilities")
    tl = val(balance, "Total Liabilities")
    if tl is None and cl is not None and ncl is not None:
        set_derived(balance, "Total Liabilities", cl + ncl, "CL + NCL")

    eq = val(balance, "Equity")
    na = val(balance, "Net Assets")
    if na is None and eq is not None:
        set_derived(balance, "Net Assets", eq, "Net Assets aliased from Equity")
    if eq is None and na is not None:
        set_derived(balance, "Equity", na, "Equity aliased from Net Assets")

    ocf, icf, fcf = val(cash, "Operating CF"), val(cash, "Investing CF"), val(cash, "Financing CF")
    if val(cash, "Net Change in Cash") is None and None not in (ocf, icf, fcf):
        set_derived(cash, "Net Change in Cash", ocf + icf + fcf, "OCF+ICF+FCF")

    # Soft identity checks
    ta = val(balance, "Total Assets")
    tl = val(balance, "Total Liabilities")
    eq = val(balance, "Equity")
    na = val(balance, "Net Assets")
    if ta is not None and tl is not None and eq is not None:
        residual = ta - tl - eq
        if abs(residual) > max(1.0, abs(ta) * 0.02):
            warnings.append(
                f"Balance sheet identity weak: Assets ({ta}) - Liabilities ({tl}) - Equity ({eq}) = {residual:.2f}"
            )
    if na is not None and eq is not None and abs(na - eq) > max(1.0, abs(na) * 0.02):
        warnings.append(f"Net Assets ({na}) differs from Equity ({eq})")

    return warnings


def prune_year(year: dict) -> dict:
    for section in ("income_statement", "balance_sheet", "cash_flow"):
        year[section] = {
            k: v
            for k, v in (year.get(section) or {}).items()
            if v and v.get("value") is not None
        }
    return year
