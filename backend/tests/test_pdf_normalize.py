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
