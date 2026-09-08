"""Compatibility shim.

The old coordinate/OCR parser was quarantined to legacy/parser_coord_ocr.py
because it produced incorrect numbers (wrong year columns, mis-mapped net assets,
invented sparse keys).

Use extract.parse_filing_from_metadata / extract.parse_filing_bytes instead.
"""

from extract import parse_filing_from_metadata


def fetch_and_parse_filing(document_metadata_url, api_key):
    """Deprecated wrapper — returns first year as a flat-ish diagnostic dict."""
    years, meta = parse_filing_from_metadata(document_metadata_url, api_key)
    if not years:
        return {"parsing_status": "failed", "meta": meta}
    y = years[0]
    income = y.get("income_statement") or {}
    balance = y.get("balance_sheet") or {}
    cash = y.get("cash_flow") or {}

    def v(section, key):
        item = section.get(key) or {}
        return item.get("value")

    return {
        "parsing_status": y.get("parsing_status"),
        "period": y.get("period"),
        "is_revenue": v(income, "Revenue"),
        "is_ebit": v(income, "EBIT"),
        "is_net_income": v(income, "Net Income"),
        "bs_curr_assets": v(balance, "Current Assets"),
        "bs_total_assets": v(balance, "Total Assets"),
        "bs_curr_liab": v(balance, "Current Liabilities"),
        "bs_total_liab": v(balance, "Total Liabilities"),
        "bs_net_assets": v(balance, "Net Assets"),
        "cf_operations": v(cash, "Operating CF"),
        "cf_investing": v(cash, "Investing CF"),
        "cf_financing": v(cash, "Financing CF"),
        "years": years,
        "meta": meta,
    }
