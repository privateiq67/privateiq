"""Tests for scanned-PDF / OCR probe + section detection (no live tesseract required)."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pdf_extract import (
    Word,
    detect_scale,
    detect_scale_prefer_header,
    detect_section,
    expand_candidate_pages,
    extract_from_pdf_bytes,
    extract_rows_from_words,
    is_image_only_pdf,
    page_mentions_financials,
    prioritize_ocr_candidates,
    probe_financial_pages,
    rows_to_year_dicts,
    select_probe_indices,
)
from normalize import apply_labelled_items


def test_detect_section_on_ocr_noisy_headings():
    assert detect_section("GYMSHARK LTD\nPROFIT AND LOSS ACCOUNT\nFOR THE YEAR ENDED 31 JULY 2025") == (
        "income_statement"
    )
    assert detect_section("BALANCE SHEET\nAS AT 31 JULY 2025") == "balance_sheet"
    assert detect_section("Consolidated Statement of Cash Flows") == "cash_flow"
    assert detect_section("Profit and Loss AcCount for the year") == "income_statement"
    assert page_mentions_financials("Turnover 3 490,142 458,624")
    assert page_mentions_financials("Fixed assets and Current assets")
    assert not page_mentions_financials("Directors report only going concern waffle")


def test_is_image_only_pdf_detection():
    assert is_image_only_pdf(["", "", ""])
    assert is_image_only_pdf(["   ", "\n"])
    assert not is_image_only_pdf(["x" * 100, ""])


def test_expand_candidate_pages_neighbours():
    assert expand_candidate_pages([10], 50, neighbour=1) == [9, 10, 11]
    assert expand_candidate_pages([0], 5, neighbour=1) == [0, 1]
    assert expand_candidate_pages([4], 5, neighbour=1) == [3, 4]


def _ocr_fixture_words():
    """Synthetic OCR word boxes mimicking a £'000 P&L + balance sheet."""
    pl_text = (
        "PROFIT AND LOSS ACCOUNT FOR THE YEAR ENDED 31 JULY 2025 "
        "Notes £'000 £'000 2025 2024 "
        "Turnover 490142 458624 "
        "Operating (loss)/profit (9177) 317 "
        "(Loss)/profit for the financial year (5124) 1887"
    )
    words = [
        Word("PROFIT", 40, 90, 40, 52, 0),
        Word("AND", 95, 120, 40, 52, 0),
        Word("LOSS", 125, 160, 40, 52, 0),
        Word("ACCOUNT", 165, 230, 40, 52, 0),
        Word("£'000", 400, 440, 70, 82, 0),
        Word("£'000", 480, 520, 70, 82, 0),
        Word("2025", 400, 440, 90, 102, 0),
        Word("2024", 480, 520, 90, 102, 0),
        Word("Turnover", 40, 120, 130, 142, 0),
        Word("490,142", 400, 460, 130, 142, 0),
        Word("458,624", 480, 540, 130, 142, 0),
        Word("Operating", 40, 110, 160, 172, 0),
        Word("(loss)/profit", 115, 220, 160, 172, 0),
        Word("(9,177)", 400, 460, 160, 172, 0),
        Word("317", 480, 520, 160, 172, 0),
        Word("(Loss)/profit", 40, 150, 190, 202, 0),
        Word("for", 155, 175, 190, 202, 0),
        Word("the", 180, 205, 190, 202, 0),
        Word("financial", 210, 280, 190, 202, 0),
        Word("year", 285, 320, 190, 202, 0),
        Word("(5,124)", 400, 460, 190, 202, 0),
        Word("1,887", 480, 530, 190, 202, 0),
    ]

    bs_text = (
        "BALANCE SHEET AS AT 31 JULY 2025 Notes £'000 £'000 2025 2024 "
        "Fixed assets 59594 159077 Current assets 138376 142383 "
        "Net assets 71774 102920 Total equity 71774 102920"
    )
    bs_words = [
        Word("BALANCE", 40, 110, 40, 52, 1),
        Word("SHEET", 115, 165, 40, 52, 1),
        Word("£'000", 400, 440, 70, 82, 1),
        Word("£'000", 480, 520, 70, 82, 1),
        Word("2025", 400, 440, 90, 102, 1),
        Word("2024", 480, 520, 90, 102, 1),
        Word("Fixed", 40, 80, 130, 142, 1),
        Word("assets", 85, 140, 130, 142, 1),
        Word("59,594", 400, 460, 130, 142, 1),
        Word("159,077", 480, 545, 130, 142, 1),
        Word("Current", 40, 100, 160, 172, 1),
        Word("assets", 105, 155, 160, 172, 1),
        Word("138,376", 400, 470, 160, 172, 1),
        Word("142,383", 480, 550, 160, 172, 1),
        Word("Net", 40, 70, 190, 202, 1),
        Word("assets", 75, 130, 190, 202, 1),
        Word("71,774", 400, 460, 190, 202, 1),
        Word("102,920", 480, 545, 190, 202, 1),
        Word("Total", 40, 80, 220, 232, 1),
        Word("equity", 85, 140, 220, 232, 1),
        Word("71,774", 400, 460, 220, 232, 1),
        Word("102,920", 480, 545, 220, 232, 1),
    ]

    return words + bs_words, [pl_text, bs_text]


def test_ocr_fixture_section_and_year_extraction():
    words, page_texts = _ocr_fixture_words()
    rows, stats = extract_rows_from_words(
        words, page_texts, default_method="pdf_ocr", ocr_page_set={0, 1}, y_tol=8.0
    )
    assert "income_statement" in stats["sections"]
    assert "balance_sheet" in stats["sections"]

    turnover = [r for r in rows if "turnover" in r.label.lower()]
    assert turnover, rows
    assert turnover[0].values_by_year.get("2025") == 490_142_000
    assert turnover[0].values_by_year.get("2024") == 458_624_000
    assert turnover[0].method == "pdf_ocr"
    assert turnover[0].scale == 1000

    net_income = [r for r in rows if "financial year" in r.label.lower()]
    assert net_income
    assert net_income[0].values_by_year.get("2025") == -5_124_000

    net_assets = [r for r in rows if r.label.lower().startswith("net assets")]
    assert net_assets
    assert net_assets[0].values_by_year.get("2025") == 71_774_000


def test_ocr_fixture_normalises_to_schema():
    words, page_texts = _ocr_fixture_words()
    rows, _ = extract_rows_from_words(
        words, page_texts, default_method="pdf_ocr", ocr_page_set={0, 1}, y_tol=8.0
    )
    blocks = rows_to_year_dicts(rows, filing_date="2025-07-31")
    assert blocks[0]["parsing_status"] == "pdf_ocr"
    y2025 = next(b for b in blocks if b["period"] == "2025")
    year = apply_labelled_items(
        y2025["labelled"],
        period="2025",
        filing_date="2025-07-31",
        parsing_status="pdf_ocr",
    )
    assert year["income_statement"]["Revenue"]["value"] == 490_142_000
    assert year["income_statement"]["Net Income"]["value"] == -5_124_000
    assert year["balance_sheet"]["Net Assets"]["value"] == 71_774_000
    assert year["income_statement"]["Revenue"]["provenance"]["method"] == "pdf_ocr"


def test_image_only_without_ocr_surfaces_requirement(monkeypatch):
    """Empty digital text + allow_ocr=False must not silently return success."""
    empty = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

    def fake_plumber(_content):
        return [], ["", "", ""]

    monkeypatch.setattr("pdf_extract._words_from_pdfplumber", fake_plumber)
    monkeypatch.setattr("pdf_extract._pdf_page_count", lambda _c: 3)
    rows, stats = extract_from_pdf_bytes(empty, allow_ocr=False)
    assert rows == []
    assert stats.get("image_only") is True
    assert stats.get("ocr_required") is True
    assert stats.get("parsing_status") == "ocr_required"


def test_build_financials_does_not_skip_newer_pdfs_for_old_ixbrl():
    """Older iXBRL years must not early-exit before newer PDF filings are tried."""
    from extract import build_financials_for_company
    import extract as extract_mod

    calls: list[str] = []

    filings = [
        {
            "date": "2025-12-20",
            "description": "accounts-with-accounts-type-full accounts made up to 2025-07-31",
            "links": {"document_metadata": "https://example/meta/2025"},
        },
        {
            "date": "2024-12-20",
            "description": "accounts-with-accounts-type-full accounts made up to 2024-07-31",
            "links": {"document_metadata": "https://example/meta/2024"},
        },
        {
            "date": "2021-12-20",
            "description": "accounts-with-accounts-type-full accounts made up to 2020-07-31",
            "links": {"document_metadata": "https://example/meta/2020"},
        },
        {
            "date": "2020-12-20",
            "description": "accounts-with-accounts-type-full accounts made up to 2019-07-31",
            "links": {"document_metadata": "https://example/meta/2019"},
        },
    ]

    def fake_parse(url, api_key, *, filing_date="", allow_ocr=True):
        calls.append(url)
        if url.endswith("2020"):
            return (
                [
                    {
                        "period": "2020",
                        "parsing_status": "ixbrl",
                        "income_statement": {"Revenue": {"value": 1}},
                        "balance_sheet": {},
                        "cash_flow": {},
                    },
                    {
                        "period": "2019",
                        "parsing_status": "ixbrl",
                        "income_statement": {"Revenue": {"value": 2}},
                        "balance_sheet": {},
                        "cash_flow": {},
                    },
                ],
                {"kind": "xhtml"},
            )
        if url.endswith("2019"):
            return (
                [
                    {
                        "period": "2019",
                        "parsing_status": "ixbrl",
                        "income_statement": {"Revenue": {"value": 2}},
                        "balance_sheet": {},
                        "cash_flow": {},
                    },
                    {
                        "period": "2018",
                        "parsing_status": "ixbrl",
                        "income_statement": {"Revenue": {"value": 3}},
                        "balance_sheet": {},
                        "cash_flow": {},
                    },
                ],
                {"kind": "xhtml"},
            )
        year = "2025" if url.endswith("2025") else "2024"
        return (
            [
                {
                    "period": year,
                    "parsing_status": "pdf_ocr",
                    "income_statement": {"Revenue": {"value": 100}},
                    "balance_sheet": {"Net Assets": {"value": 50}},
                    "cash_flow": {},
                }
            ],
            {"kind": "pdf", "pdf": {"ocr_used": True}},
        )

    orig = extract_mod.parse_filing_from_metadata
    extract_mod.parse_filing_from_metadata = fake_parse
    try:
        result = build_financials_for_company("08130873", filings, "dummy", max_filings=4)
    finally:
        extract_mod.parse_filing_from_metadata = orig

    assert any(u.endswith("2025") for u in calls)
    assert any(u.endswith("2024") for u in calls)
    periods = {y["period"] for y in result["years"]}
    assert "2025" in periods
    assert "2024" in periods


def test_contents_page_hints_and_creditors_ocr():
    from pdf_extract import contents_page_hints
    from normalize import resolve_label

    assert contents_page_hints("Profit and loss account ...... 17\nBalance sheet 18-19") == [
        17,
        18,
        19,
    ]
    resolved = resolve_label("one Creditors: year amounts falling due within 20")
    assert resolved is not None
    assert resolved[1] == "Current Liabilities"


def test_detect_scale_ocr_noisy_thousands_variants():
    """OCR-like unit strings must resolve to £'000 / £m without false positives."""
    thousands = [
        "£'000",
        "£000",
        "£'000s",
        "£000s",
        "E'000",
        "E000",
        "L'000",
        "£'OOO",  # O vs 0
        "£’000",  # curly quote
        "'000",
        "'000s",
        "000s",
        "in thousands",
        "All figures in £'000",
        "figures are in £000s",
        "£ thousand",
        "£ thousands",
        "(£'000)",
        "$000",  # OCR often maps £ → $
        "Notes $000 $000",
        "Notes £'000 £'000 2024 2023",
    ]
    for s in thousands:
        assert detect_scale(s) == 1000, s

    millions = ["£m", "£ m", "in millions", "All figures in £m", "Em"]
    for s in millions:
        assert detect_scale(s) == 1_000_000, s

    assert detect_scale("Revenue was strong this year") == 1
    # Bare "l m" across word boundary must not look like £m
    assert detect_scale("Material misstatements that arise") == 1
    # Body "thousands of customers" alone must not flip units via header preference
    assert detect_scale_prefer_header(
        "The group serves thousands of customers worldwide."
    ) == 1
    # Unit near statement header / year columns should win
    pl = (
        "CONSOLIDATED STATEMENT OF COMPREHENSIVE INCOME\n"
        "Notes  £’OOO  £’OOO\n2024 2023\nRevenue 1,413,094 1,306,696"
    )
    assert detect_scale_prefer_header(pl) == 1000
    assert (
        detect_scale_prefer_header("no units", header_extra="Notes £'000 2024 2023")
        == 1000
    )


def test_scale_sticky_across_pages_when_unit_ocr_missed():
    """Once £'000 is seen on P&L, following BS page keeps scale if OCR drops unit."""
    pl_text = (
        "PROFIT AND LOSS ACCOUNT FOR THE YEAR ENDED 31 DECEMBER 2024 "
        "Notes £'000 £'000 2024 2023 Revenue 1413094 1306696"
    )
    # Balance sheet page deliberately omits unit markers (OCR miss)
    bs_text = (
        "BALANCE SHEET AS AT 31 DECEMBER 2024 "
        "2024 2023 Total current liabilities (779264) (675476) "
        "Total equity 160470 137166"
    )
    words = [
        Word("PROFIT", 40, 90, 40, 52, 0),
        Word("AND", 95, 120, 40, 52, 0),
        Word("LOSS", 125, 160, 40, 52, 0),
        Word("ACCOUNT", 165, 230, 40, 52, 0),
        Word("£'000", 400, 440, 70, 82, 0),
        Word("£'000", 480, 520, 70, 82, 0),
        Word("2024", 400, 440, 90, 102, 0),
        Word("2023", 480, 520, 90, 102, 0),
        Word("Revenue", 40, 120, 130, 142, 0),
        Word("1,413,094", 400, 470, 130, 142, 0),
        Word("1,306,696", 480, 550, 130, 142, 0),
        Word("BALANCE", 40, 110, 40, 52, 1),
        Word("SHEET", 115, 165, 40, 52, 1),
        Word("2024", 400, 440, 90, 102, 1),
        Word("2023", 480, 520, 90, 102, 1),
        Word("Total", 40, 80, 160, 172, 1),
        Word("current", 85, 145, 160, 172, 1),
        Word("liabilities", 150, 240, 160, 172, 1),
        Word("(779,264)", 400, 470, 160, 172, 1),
        Word("(675,476)", 480, 550, 160, 172, 1),
        Word("Total", 40, 80, 190, 202, 1),
        Word("equity", 85, 140, 190, 202, 1),
        Word("160,470", 400, 460, 190, 202, 1),
        Word("137,166", 480, 545, 190, 202, 1),
    ]
    rows, stats = extract_rows_from_words(
        words, [pl_text, bs_text], default_method="pdf_ocr", ocr_page_set={0, 1}, y_tol=8.0
    )
    rev = [r for r in rows if r.label.lower() == "revenue"]
    assert rev and rev[0].scale == 1000
    assert rev[0].values_by_year["2024"] == 1_413_094_000
    liab = [r for r in rows if "current liabilities" in r.label.lower()]
    assert liab, rows
    assert liab[0].scale == 1000  # sticky from P&L page
    assert liab[0].values_by_year["2024"] == -779_264_000  # sign still from parens at extract


def test_liability_totals_normalised_positive():
    """Parenthesised liability OCR amounts become positive schema magnitudes."""
    year = apply_labelled_items(
        [
            {
                "label": "Total current liabilities",
                "value": -779_264_000,
                "provenance": {"confidence": 65, "method": "pdf_ocr", "scale_applied": 1000},
            },
            {
                "label": "Total non-current liabilities",
                "value": -112_000,
                "provenance": {"confidence": 65, "method": "pdf_ocr", "scale_applied": 1000},
            },
            {
                "label": "Total liabilities",
                "value": -779_376_000,
                "provenance": {"confidence": 65, "method": "pdf_ocr", "scale_applied": 1000},
            },
            {
                "label": "Cost of sales",
                "value": -849_480_000,
                "provenance": {"confidence": 65, "method": "pdf_ocr", "scale_applied": 1000},
            },
            {
                "label": "Current Liabilities",
                "value": 50_000,  # already positive — do not double-flip
                "provenance": {"confidence": 40, "method": "pdf"},
            },
        ],
        period="2024",
        parsing_status="pdf_ocr",
    )
    assert year["balance_sheet"]["Current Liabilities"]["value"] == 779_264_000
    assert year["balance_sheet"]["Non-Current Liabilities"]["value"] == 112_000
    assert year["balance_sheet"]["Total Liabilities"]["value"] == 779_376_000
    # Signed P&L expense convention retained
    assert year["income_statement"]["Cost of Sales"]["value"] == -849_480_000



def test_long_document_probe_selection_covers_whole_doc():
    """150–200 page reports must probe mid/back, not only the first ~50 pages."""
    for n in (154, 204):
        indices, stride = select_probe_indices(n)
        assert stride >= 3
        assert max(indices) >= n - 5
        assert min(indices) == 0
        # Front contents density
        assert all(i in indices for i in range(0, min(12, n)))
        mid = int(n * 0.35)
        assert any(i >= mid for i in indices), indices[-10:]
        assert len(indices) <= 80
        # Cap still yields meaningful mid/back coverage
        mid_back = [i for i in indices if i >= mid]
        assert len(mid_back) >= 15


def test_prioritize_ocr_candidates_prefers_contents_and_caps():
    hits = [5, 10, 86, 120]
    contents = [86, 87]
    out = prioritize_ocr_candidates(
        hits, 154, contents_hits=contents, neighbour=2, max_pages=12
    )
    assert len(out) <= 12
    # Probe/section hits (±1) are reserved so real statement pages are not
    # starved by noisy contents guesses; mid/back hits still included.
    assert 86 in out
    assert 120 in out or 119 in out or 121 in out


def test_prioritize_reserves_section_hits_over_noisy_contents():
    """Featurespace-style: IS+CF section hits must keep the BS page between them."""
    hits = [14, 16, 19] + list(range(20, 35))
    contents = list(range(0, 5)) + list(range(20, 35))  # noisy front + notes
    section_hits = [14, 19]
    out = prioritize_ocr_candidates(
        hits,
        38,
        contents_hits=contents,
        section_hits=section_hits,
        neighbour=2,
        max_pages=28,
    )
    assert 14 in out and 15 in out and 19 in out
    # Gap close should retain the consolidated BS page
    assert 15 in out or 16 in out


def test_detect_section_cash_flow_ocr_variants():
    assert detect_section("CONSOLIDATED STATEMENT OF CASH FLOWS") == "cash_flow"
    assert detect_section("Consolidated Statement of Cash Fiows") == "cash_flow"
    assert detect_section("Group cash flow statement") == "cash_flow"


def test_probe_financial_pages_injectable_ocr_covers_back_half():
    """Synthetic page_count + hit indices via injectable OCR text fn."""
    n = 160
    # Financial statement pages only in the back half
    hit_set = {92, 93, 110}

    def fake_ocr(_content, i):
        if i in (2, 3):
            return "Contents\nConsolidated income statement ...... 93\nGroup balance sheet 94"
        if i in hit_set:
            return "Consolidated income statement\nTurnover 1,000 900"
        if i % 7 == 0:
            return "Strategic report narrative only"
        return "Directors report waffle"

    hits, stats = probe_financial_pages(b"%PDF", n, ocr_text_fn=fake_ocr)
    assert any(i >= 90 for i in stats["probed_pages"]), stats["probed_pages"][-5:]
    assert 92 in hits or 93 in hits
    assert stats.get("contents_printed_pages")
    assert 93 in stats["contents_printed_pages"]


def test_expand_candidate_pages_default_neighbour_is_two():
    assert expand_candidate_pages([10], 50) == [8, 9, 10, 11, 12]


def test_group_contents_page_hints():
    from pdf_extract import contents_page_hints

    pages = contents_page_hints(
        "Consolidated income statement ..... 86\n"
        "Group balance sheet 87-88\n"
        "Consolidated cash flow statement 90"
    )
    assert 86 in pages and 87 in pages and 88 in pages and 90 in pages


def test_detect_section_prefers_earliest_header():
    """Balance sheet header must win over a later P&L cross-reference."""
    text = (
        "Consolidated balance sheet\nAt 31 December 2025\nFixed assets 10\n"
        "See note 4 and the profit and loss account for further detail."
    )
    assert detect_section(text) == "balance_sheet"


def test_year_ended_and_millions_ocr_recovery():
    from pdf_extract import year_ended_from_text, parse_number_token

    assert year_ended_from_text("For the year ended 31 December 2025") == "2025"
    assert parse_number_token("2.2963", scale_hint=1_000_000) == 2296.3
    assert parse_number_token("2,488.6", scale_hint=1_000_000) == 2488.6
