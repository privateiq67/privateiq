"""Tests for PDF row extraction (from synthetic word positions) and normalisation."""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from normalize import apply_labelled_items, resolve_label
from pdf_extract import Word, extract_rows_from_words, rows_to_year_dicts
from schema import CONFIDENCE_LABEL_EXACT

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_accounts_text.json"


def _load_words():
    data = json.loads(FIXTURE.read_text())
    words: list[Word] = []
    page_texts: list[str] = []
    for i, page in enumerate(data["pages"]):
        page_texts.append(page["text"])
        for w in page["words"]:
            words.append(
                Word(
                    text=w["text"],
                    x0=w["x0"],
                    x1=w["x1"],
                    top=w["top"],
                    bottom=w["bottom"],
                    page=i,
                )
            )
    return words, page_texts


def test_synonym_turnover_to_revenue():
    assert resolve_label("Turnover") == ("income_statement", "Revenue", CONFIDENCE_LABEL_EXACT)
    assert resolve_label("Profit for the year")[1] == "Net Income"
    assert resolve_label("Creditors: amounts falling due within one year")[1] == "Current Liabilities"


def test_pdf_rows_split_years_correctly():
    words, page_texts = _load_words()
    rows, stats = extract_rows_from_words(words, page_texts)
    assert "income_statement" in stats["sections"]
    assert "balance_sheet" in stats["sections"]

    # Find turnover row
    turnover = [r for r in rows if "turnover" in r.label.lower()]
    assert turnover, "expected Turnover row"
    t = turnover[0]
    assert t.values_by_year.get("2024") == 520_000_000
    assert t.values_by_year.get("2023") == 445_000_000


def test_pdf_scale_thousands_on_balance_sheet():
    words, page_texts = _load_words()
    rows, _ = extract_rows_from_words(words, page_texts)
    fixed = [r for r in rows if r.label.lower().startswith("fixed assets")]
    assert fixed
    # £000 scale -> 95_000 * 1000
    assert fixed[0].values_by_year["2024"] == 95_000_000
    assert fixed[0].scale == 1000


def test_normalise_pdf_rows_to_schema():
    words, page_texts = _load_words()
    rows, _ = extract_rows_from_words(words, page_texts)
    intermediate = rows_to_year_dicts(rows, filing_date="2024-09-30")
    assert {b["period"] for b in intermediate} >= {"2024", "2023"}

    y2024_block = next(b for b in intermediate if b["period"] == "2024")
    year = apply_labelled_items(
        y2024_block["labelled"],
        period="2024",
        filing_date="2024-09-30",
        parsing_status="pdf",
    )
    assert year["income_statement"]["Revenue"]["value"] == 520_000_000
    assert year["income_statement"]["Net Income"]["value"] == 55_000_000
    assert year["balance_sheet"]["Current Assets"]["value"] == 180_000_000
    assert year["balance_sheet"]["Net Assets"]["value"] == 140_000_000
    # Provenance retained
    assert year["income_statement"]["Revenue"]["provenance"]["method"] == "pdf"
    assert year["income_statement"]["Revenue"]["provenance"]["page"] >= 1


def test_confidence_prefers_higher():
    from normalize import _set_if_better
    from schema import line

    bucket = {}
    low = line(1, provenance={"confidence": 30, "method": "derived"})
    high = line(2, provenance={"confidence": 100, "method": "ixbrl"})
    _set_if_better(bucket, "Revenue", low)
    _set_if_better(bucket, "Revenue", high)
    assert bucket["Revenue"]["value"] == 2
    # Lower cannot overwrite
    _set_if_better(bucket, "Revenue", line(99, provenance={"confidence": 40}))
    assert bucket["Revenue"]["value"] == 2


def test_no_invented_ebitda_without_da():
    year = apply_labelled_items(
        [{"label": "Operating profit", "value": 100, "provenance": {"confidence": 80}}],
        period="2024",
        parsing_status="pdf",
    )
    assert "EBIT" in year["income_statement"]  # aliased
    assert "EBITDA (Est)" not in year["income_statement"]  # must not invent


def test_ocr_noisy_construction_labels():
    """Wates/group OCR mangling must still map to schema keys."""
    cases = [
        ("Tumover", "Revenue"),
        ("Operatlng proflt", "Operating Profit"),
        ("Profit before taxatlon", "Profit Before Tax"),
        ("Cost of saies", "Cost of Sales"),
        ("Adminlstrative expenses", "Administrative Expenses"),
        ("Tota1 equity", "Equity"),
        ("Group turnover", "Revenue"),
        ("Group operating profit", "Operating Profit"),
        ("Net assels", "Net Assets"),
        ("Currcnt assets", "Current Assets"),
    ]
    for raw, expected in cases:
        resolved = resolve_label(raw)
        assert resolved is not None, raw
        assert resolved[1] == expected, (raw, resolved)


def test_noisy_labelled_rows_become_schema_keys():
    """17 OCR rows with values must not collapse to empty years after normalize."""
    labelled = [
        {"label": "Tumover", "value": 1_413_094_000.0, "section": "income_statement"},
        {"label": "Cost of saies", "value": -1_200_000_000.0, "section": "income_statement"},
        {"label": "Operatlng proflt", "value": 45_000_000.0, "section": "income_statement"},
        {"label": "Profit before taxatlon", "value": 40_000_000.0, "section": "income_statement"},
        {"label": "Fixed assels", "value": 100_000_000.0, "section": "balance_sheet"},
        {"label": "Currcnt assets", "value": 500_000_000.0, "section": "balance_sheet"},
        {"label": "Tota1 equity", "value": 160_000_000.0, "section": "balance_sheet"},
        {"label": "Net assels", "value": 160_000_000.0, "section": "balance_sheet"},
    ]
    year = apply_labelled_items(labelled, period="2024", parsing_status="pdf_ocr")
    assert year["period"] == "2024"
    assert year["income_statement"]["Revenue"]["value"] == 1_413_094_000.0
    assert year["income_statement"]["Operating Profit"]["value"] == 45_000_000.0
    assert year["income_statement"]["Profit Before Tax"]["value"] == 40_000_000.0
    assert year["balance_sheet"]["Equity"]["value"] == 160_000_000.0
    assert year["balance_sheet"]["Current Assets"]["value"] == 500_000_000.0


def test_net_current_assets_not_current_assets():
    assert resolve_label("Net current assets") is None
    assert resolve_label("Group statutory turnover")[1] == "Revenue"
    assert resolve_label("Group operating profit/(loss) | 4 25.2)")[1] == "Operating Profit"


def test_cash_flow_net_used_generated_synonyms():
    assert resolve_label("Net cash (used)/generated from operating activities")[1] == "Operating CF"
    assert resolve_label("Net cash used in operating activities")[1] == "Operating CF"
    assert resolve_label("Net cash from/(used in) investing activities")[1] == "Investing CF"
    assert resolve_label("Net cash (used)/generated from financing activities")[1] == "Financing CF"


def test_equity_attributable_with_the_owners():
    assert resolve_label("Equity attributable to the owners of the parent company")[1] == "Equity"
    assert resolve_label("Equity attributable to the owners of the parent")[1] == "Equity"


def test_derive_equity_from_assets_minus_liabilities():
    year = apply_labelled_items(
        [
            {"label": "Total assets", "value": 285_285_000.0},
            {"label": "Total liabilities", "value": 317_035_000.0},
        ],
        period="2024",
        parsing_status="pdf_ocr",
    )
    assert year["balance_sheet"]["Equity"]["value"] == 285_285_000.0 - 317_035_000.0
    assert year["balance_sheet"]["Net Assets"]["value"] == 285_285_000.0 - 317_035_000.0


def test_derive_total_assets_from_ca_plus_nca():
    year = apply_labelled_items(
        [
            {"label": "Current assets", "value": 100.0},
            {"label": "Fixed assets", "value": 40.0},
        ],
        period="2024",
        parsing_status="pdf",
    )
    assert year["balance_sheet"]["Total Assets"]["value"] == 140.0


def test_operating_cf_from_labelled_featurespace_style():
    year = apply_labelled_items(
        [
            {"label": "Net cash (used)/generated from operating activities", "value": -16_236_348.0},
            {"label": "Net cash from investing activities", "value": 521_761.0},
            {"label": "Net cash from financing activities", "value": 20_028_314.0},
            {"label": "Net increase in cash and cash equivalents", "value": 313_727.0},
        ],
        period="2024",
        parsing_status="pdf_ocr",
    )
    assert year["cash_flow"]["Operating CF"]["value"] == -16_236_348.0
    assert year["cash_flow"]["Investing CF"]["value"] == 521_761.0
    assert year["cash_flow"]["Financing CF"]["value"] == 20_028_314.0
    assert year["cash_flow"]["Net Change in Cash"]["value"] == 313_727.0
