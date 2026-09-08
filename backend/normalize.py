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
    "net interest income": ("income_statement", "Net Interest Income"),
    "net interest income after impairment losses": ("income_statement", "Net Interest Income"),
    "net interest income after provisions": ("income_statement", "Net Interest Income"),
    "interest income": ("income_statement", "Net Interest Income"),
    "interest receivable and similar income": ("income_statement", "Finance Income"),
    "interest expense": ("income_statement", "Finance Costs"),
    "interest payable and similar expenses": ("income_statement", "Finance Costs"),
    "net fee and commission income": ("income_statement", "Fee and Commission Income"),
    "net operating income": ("income_statement", "Total Income"),
    "total operating income before operating expenses": ("income_statement", "Total Income"),
    "profit/(loss) before taxation from continuing operations": ("income_statement", "Profit Before Tax"),
    "fee and commission income": ("income_statement", "Fee and Commission Income"),
    "fees and commissions income": ("income_statement", "Fee and Commission Income"),
    "total operating income": ("income_statement", "Total Income"),
    "total income": ("income_statement", "Total Income"),
    "administrative expenses": ("income_statement", "Administrative Expenses"),
    "admin expenses": ("income_statement", "Administrative Expenses"),
    "staff costs": ("income_statement", "Staff Costs"),
    "employee benefits expense": ("income_statement", "Staff Costs"),
    "finance income": ("income_statement", "Finance Income"),
    "interest receivable": ("income_statement", "Finance Income"),
    "finance costs": ("income_statement", "Finance Costs"),
    "interest payable": ("income_statement", "Finance Costs"),
    "interest payable and similar charges": ("income_statement", "Finance Costs"),
    "tax": ("income_statement", "Tax"),
    "tax on profit": ("income_statement", "Tax"),
    "tax on profit/(loss)": ("income_statement", "Tax"),
    "taxation": ("income_statement", "Tax"),
    "comprehensive income": ("income_statement", "Comprehensive Income"),
    "total comprehensive income": ("income_statement", "Comprehensive Income"),
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
    "net cash generated from operations": ("cash_flow", "Operating CF"),
    "net cash generated/(used) from operating activities": ("cash_flow", "Operating CF"),
    "net cash generated/(used) in operating activities": ("cash_flow", "Operating CF"),
    "net cash (used)/generated from operating activities": ("cash_flow", "Operating CF"),
    "net cash (used)/generated in operating activities": ("cash_flow", "Operating CF"),
    "net cash (used in)/generated from operating activities": ("cash_flow", "Operating CF"),
    "net cash used in operating activities": ("cash_flow", "Operating CF"),
    "net cash used/(generated) from operating activities": ("cash_flow", "Operating CF"),
    "net cash from/(used in) operating activities": ("cash_flow", "Operating CF"),
    "net cash inflow/(outflow) from operating activities": ("cash_flow", "Operating CF"),
    "cash flows from operating activities": ("cash_flow", "Operating CF"),
    "net cash from investing activities": ("cash_flow", "Investing CF"),
    "cash flows from investing activities": ("cash_flow", "Investing CF"),
    "net cash generated/(used) from investing activities": ("cash_flow", "Investing CF"),
    "net cash (used)/generated from investing activities": ("cash_flow", "Investing CF"),
    "net cash from/(used in) investing activities": ("cash_flow", "Investing CF"),
    "net cash from financing activities": ("cash_flow", "Financing CF"),
    "cash flows from financing activities": ("cash_flow", "Financing CF"),
    "net cash generated/(used) from financing activities": ("cash_flow", "Financing CF"),
    "net cash (used)/generated from financing activities": ("cash_flow", "Financing CF"),
    "net cash from/(used in) financing activities": ("cash_flow", "Financing CF"),
    "net increase/(decrease) in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net increase/(decrease) in cash and cash equivalents before exchange": ("cash_flow", "Net Change in Cash"),
    "net increase in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net decrease in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "net increase/(decrease) in cash": ("cash_flow", "Net Change in Cash"),
    "increase/(decrease) in cash and cash equivalents": ("cash_flow", "Net Change in Cash"),
    "increase/(decrease) in cash": ("cash_flow", "Net Change in Cash"),
    # Construction / UK group common labels
    "group turnover": ("income_statement", "Revenue"),
    "group revenue": ("income_statement", "Revenue"),
    "continuing operations - turnover": ("income_statement", "Revenue"),
    "continuing operations turnover": ("income_statement", "Revenue"),
    "revenue from continuing operations": ("income_statement", "Revenue"),
    "turnover from continuing operations": ("income_statement", "Revenue"),
    "administration expenses": ("income_statement", "Administrative Expenses"),
    "operating profit (loss)": ("income_statement", "Operating Profit"),
    "group operating profit": ("income_statement", "Operating Profit"),
    "group operating profit/(loss)": ("income_statement", "Operating Profit"),
    "profit before tax from continuing operations": ("income_statement", "Profit Before Tax"),
    "profit before taxation from continuing operations": ("income_statement", "Profit Before Tax"),
    "total equity attributable to owners": ("balance_sheet", "Equity"),
    "equity attributable to owners of the parent": ("balance_sheet", "Equity"),
    "equity attributable to the owners of the parent": ("balance_sheet", "Equity"),
    "equity attributable to the owners of the parent company": ("balance_sheet", "Equity"),
    "equity attributable to owners of the parent company": ("balance_sheet", "Equity"),
    "total equity attributable to the owners of the parent": ("balance_sheet", "Equity"),
    "equity shareholders funds": ("balance_sheet", "Equity"),
    "net cash inflow from operating activities": ("cash_flow", "Operating CF"),
    "net cash outflow from operating activities": ("cash_flow", "Operating CF"),
    "net cash inflow/(outflow) from operating activities": ("cash_flow", "Operating CF"),
    "net cash used in investing activities": ("cash_flow", "Investing CF"),
    "net cash used in financing activities": ("cash_flow", "Financing CF"),
    "net cash from/(used in) investing activities": ("cash_flow", "Investing CF"),
    "net cash from/(used in) financing activities": ("cash_flow", "Financing CF"),
    "group turnover": ("income_statement", "Revenue"),
    "group statutory turnover": ("income_statement", "Revenue"),
    "statutory turnover": ("income_statement", "Revenue"),
    "group and share of joint ventures and associates": ("income_statement", "Revenue"),
    "group operating profit/(loss)": ("income_statement", "Operating Profit"),
    "group operating profit (loss)": ("income_statement", "Operating Profit"),
    "group statutory profit/(loss) before tax": ("income_statement", "Profit Before Tax"),
    "group statutory profit before tax": ("income_statement", "Profit Before Tax"),
    "group profit/(loss) before tax": ("income_statement", "Profit Before Tax"),
    "group profit before tax": ("income_statement", "Profit Before Tax"),
    "group profit/(loss) for the financial year": ("income_statement", "Net Income"),
    "group profit for the financial year": ("income_statement", "Net Income"),
    "group profit/(loss) for the year": ("income_statement", "Net Income"),
    "shareholders funds": ("balance_sheet", "Equity"),
    "shareholders' funds": ("balance_sheet", "Equity"),
    "shareholders’ funds": ("balance_sheet", "Equity"),
}




# CapIQ-style schema stores liability *totals* as positive magnitudes owed.
# UK accounts / OCR often wrap liability figures in parentheses — treat those
# as presentation, not a negative liability stock.
LIABILITY_POSITIVE_KEYS = frozenset(
    {
        "Current Liabilities",
        "Non-Current Liabilities",
        "Total Liabilities",
    }
)


def _norm_label(label: str) -> str:
    s = label.lower().replace("–", "-").replace("—", "-").replace("’", "'").replace("'", "'")
    # Pipe often separates label from OCR junk — drop trailing pipe segments with digits
    s = s.replace("|", " ")
    s = re.sub(r"\s+", " ", s).strip(" :.-")
    # Strip trailing note refs like "3" / "(note 4)"
    s = re.sub(r"\s*\(note\s*\d+\)\s*$", "", s)
    # Strip trailing numeric / £m / OCR crumbs glued onto labels (repeat)
    for _ in range(8):
        n = re.sub(r"[\s,]+[\d.,()£$€m/-]+$", "", s)
        n = re.sub(r"\s+[a-z]\d{0,3}$", "", n)  # o7, a1
        n = re.sub(r"\s+\d{1,2}$", "", n)
        if n == s:
            break
        s = n
    return s.strip(" :.-$,")


# Common OCR confusions on key UK line labels (conservative, key-lines only).
_OCR_LABEL_FIXES = (
    (r"\btumover\b", "turnover"),  # rn→m
    (r"\btum over\b", "turnover"),
    (r"\brevenue\b", "revenue"),
    (r"\brevenuc\b", "revenue"),
    (r"\brevenuee\b", "revenue"),
    (r"\boperatlng\b", "operating"),  # i→l
    (r"\boperat1ng\b", "operating"),
    (r"\boperatIng\b", "operating"),
    (r"\bproflt\b", "profit"),
    (r"\bprolit\b", "profit"),
    (r"\bprof1t\b", "profit"),
    (r"\bloss\b", "loss"),
    (r"\badminlstrative\b", "administrative"),
    (r"\badministratlve\b", "administrative"),
    (r"\bexpenSes\b", "expenses"),
    (r"\bexpenses\b", "expenses"),
    (r"\bexpenscs\b", "expenses"),
    (r"\bliabillties\b", "liabilities"),
    (r"\bliabilitles\b", "liabilities"),
    (r"\bliabilit1es\b", "liabilities"),
    (r"\bcurrcnt\b", "current"),
    (r"\btota1\b", "total"),
    (r"\btotai\b", "total"),
    (r"\bequily\b", "equity"),
    (r"\bequitv\b", "equity"),
    (r"\bflxed\b", "fixed"),
    (r"\bassels\b", "assets"),
    (r"\basses\b", "assets"),
    (r"\btaxatlon\b", "taxation"),
    (r"\bbefore taxatlon\b", "before taxation"),
    (r"\bcost of saies\b", "cost of sales"),
    (r"\bcost of sa1es\b", "cost of sales"),
    (r"\bgross proflt\b", "gross profit"),
    (r"\bnet assels\b", "net assets"),
    (r"\bsharehoiders\b", "shareholders"),
    (r"\bshareh0lders\b", "shareholders"),
    (r"\bcash\s*fiows?\b", "cash flows"),  # l→i
    (r"\bcashfiows?\b", "cash flows"),
    (r"\boperatlng activities\b", "operating activities"),
    (r"\binvestlng activities\b", "investing activities"),
    (r"\bfinancIng activities\b", "financing activities"),
    (r"\bfinanc1ng activities\b", "financing activities"),
)


def _ocr_fold_label(label: str) -> str:
    """Apply conservative OCR character-fold fixes then normalise."""
    s = _norm_label(label)
    for pat, repl in _OCR_LABEL_FIXES:
        s = re.sub(pat, repl, s, flags=re.I)
    # Collapsed rn→m already handled; also try m→rn reverse for rare OCR
    # Only for known mangled tokens, not globally (too reckless).
    return s


def _looks_like_primary_line(key: str) -> bool:
    """True for short statement-line labels (not narrative sentences)."""
    if not key or len(key) > 70:
        return False
    if len(key.split()) > 12:
        return False
    if re.search(r"\b(which|where|because|during|company's|directors?)\b", key):
        return False
    return True



def _match_net_cash_flow_label(label: str) -> Optional[tuple[str, str]]:
    """Map noisy net cash-flow totals; ignore subsection headers without 'net'."""
    s = label or ""
    if "cash" not in s:
        return None
    # Net change in cash
    if re.search(r"\b(?:net\s+)?increase\s*/\s*\(?\s*decrease\s*\)?\s+in\s+cash", s) or re.search(
        r"\bnet\s+(?:increase|decrease)\s+in\s+cash", s
    ):
        if "equivalent" in s or s.endswith("cash") or "in cash" in s:
            return "cash_flow", "Net Change in Cash"
    # Require net + operating/investing/financing (avoid mapping bare section headers
    # that already have exact synonyms; this catches parenthesis OCR variants).
    if not re.search(r"\bnet\s+cash\b", s):
        return None
    if re.search(r"\boperat", s):
        return "cash_flow", "Operating CF"
    if re.search(r"\binvest", s):
        return "cash_flow", "Investing CF"
    if re.search(r"\bfinanc", s):
        return "cash_flow", "Financing CF"
    return None


def resolve_label(label: str) -> Optional[tuple[str, str, int]]:
    """Return (statement, schema_key, confidence) or None."""
    key = _norm_label(label)
    folded = _ocr_fold_label(label)
    for candidate in (key, folded):
        if candidate in SYNONYMS:
            stmt, sk = SYNONYMS[candidate]
            conf = CONFIDENCE_LABEL_EXACT if candidate == key else CONFIDENCE_LABEL_FUZZY
            return stmt, sk, conf
    # "Net current assets" is a UK GAAP intermediate — never map to Current Assets
    for candidate in (key, folded):
        if candidate.startswith("net current assets") or candidate.startswith("net current liabilities"):
            return None
    # OCR-tolerant UK creditors headings (word order often scrambled)
    for candidate in (key, folded):
        if "creditors" in candidate and "within" in candidate:
            return "balance_sheet", "Current Liabilities", CONFIDENCE_LABEL_FUZZY
        if "creditors" in candidate and ("after" in candidate or "more than one" in candidate):
            return "balance_sheet", "Non-Current Liabilities", CONFIDENCE_LABEL_FUZZY
    # Cash-flow net lines: tolerate (used)/generated / from/in OCR variants
    for candidate in (key, folded):
        cf_hit = _match_net_cash_flow_label(candidate)
        if cf_hit:
            return cf_hit[0], cf_hit[1], CONFIDENCE_LABEL_FUZZY
        if "equity attributable" in candidate and "owner" in candidate:
            return "balance_sheet", "Equity", CONFIDENCE_LABEL_FUZZY
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
    for probe in (key, folded):
        for alias, target in SYNONYMS.items():
            if len(alias) < 5:
                continue
            if alias not in probe:
                continue
            if probe.startswith(alias):
                rest = probe[len(alias):].strip(" :.-")
                # Allow trailing note refs only; reject "total assets less current..."
                if rest and not re.fullmatch(r"\d{1,2}", rest):
                    if len(alias) < 0.85 * len(probe):
                        continue
            elif len(alias) < 0.55 * len(probe):
                continue
            if len(alias) > best_len:
                best = (target[0], target[1], CONFIDENCE_LABEL_FUZZY)
                best_len = len(alias)
    if best:
        return best

    # Conservative edit-distance match for short OCR-mangled primary lines only.
    # Max 2 char edits vs synonym keys of similar length — avoids narrative false hits.
    if _looks_like_primary_line(folded):
        fuzzy = _fuzzy_synonym_match(folded)
        if fuzzy:
            return fuzzy
    return None


def _fuzzy_synonym_match(key: str) -> Optional[tuple[str, str, int]]:
    """Very tight Levenshtein-style match against synonym keys (len ≥ 6)."""
    if len(key) < 6:
        return None
    best = None
    best_dist = 99
    for alias, target in SYNONYMS.items():
        if abs(len(alias) - len(key)) > 2:
            continue
        if len(alias) < 6:
            continue
        # Cheap gate: first char or first 3-char bigram overlap
        if alias[0] != key[0] and alias[:3] not in key and key[:3] not in alias:
            continue
        dist = _levenshtein(key, alias, max_dist=2)
        if dist is None:
            continue
        if dist < best_dist or (dist == best_dist and best and len(alias) > len(best[3])):
            best = (target[0], target[1], CONFIDENCE_LABEL_FUZZY, alias)
            best_dist = dist
    if best and best_dist <= 2:
        return best[0], best[1], best[2]
    return None


def _levenshtein(a: str, b: str, *, max_dist: int = 2) -> Optional[int]:
    """Levenshtein distance with early exit when > max_dist."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > max_dist:
        return None
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        row_min = i
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur[j] = min(ins, delete, sub)
            row_min = min(row_min, cur[j])
        if row_min > max_dist:
            return None
        prev = cur
    return prev[lb] if prev[lb] <= max_dist else None


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
        num = float(value)
        # Liability totals: always positive magnitudes (do not double-flip positives).
        if schema_key in LIABILITY_POSITIVE_KEYS:
            num = abs(num)
        item = line(
            num,
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

    # Force liability totals positive before deriving / identity checks.
    # iXBRL sign="-" and OCR parentheses must not leave negative liability stock.
    for _lk in LIABILITY_POSITIVE_KEYS:
        _item = balance.get(_lk)
        if _item and _item.get("value") is not None and float(_item["value"]) < 0:
            _fixed = dict(_item)
            _fixed["value"] = abs(float(_item["value"]))
            balance[_lk] = _fixed

    cl = val(balance, "Current Liabilities")
    ncl = val(balance, "Non-Current Liabilities")
    tl = val(balance, "Total Liabilities")
    if tl is None and cl is not None and ncl is not None:
        set_derived(balance, "Total Liabilities", abs(cl) + abs(ncl), "CL + NCL")

    eq = val(balance, "Equity")
    na = val(balance, "Net Assets")
    if na is None and eq is not None:
        set_derived(balance, "Net Assets", eq, "Net Assets aliased from Equity")
    if eq is None and na is not None:
        set_derived(balance, "Equity", na, "Equity aliased from Net Assets")

    # Holdings / banks sometimes tag Assets + Liabilities but omit Equity line.
    ta2 = val(balance, "Total Assets")
    tl2 = val(balance, "Total Liabilities")
    if val(balance, "Equity") is None and ta2 is not None and tl2 is not None:
        set_derived(balance, "Equity", ta2 - abs(tl2), "Total Assets - |Total Liabilities|")
    if val(balance, "Net Assets") is None and ta2 is not None and tl2 is not None:
        set_derived(balance, "Net Assets", ta2 - abs(tl2), "Total Assets - |Total Liabilities|")

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
