"""Unit tests for iXBRL extraction — correctness over convenience."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extract import parse_filing_bytes
from ixbrl import extract_facts, parse_ixbrl_document
from normalize import merge_ixbrl_year

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_frs102.xhtml"


def test_fixture_exists():
    assert FIXTURE.exists()


def test_extracts_two_years_and_correct_revenue():
    content = FIXTURE.read_bytes()
    facts, stats = extract_facts(content)
    assert stats["facts_mapped"] > 0
    years, _ = parse_ixbrl_document(content, filing_date="2024-09-30")
    periods = {y["period"] for y in years}
    assert "2024" in periods
    assert "2023" in periods

    y2024 = next(y for y in years if y["period"] == "2024")
    y2023 = next(y for y in years if y["period"] == "2023")

    assert y2024["income_statement"]["Revenue"]["value"] == 520_000_000
    assert y2023["income_statement"]["Revenue"]["value"] == 445_000_000
    # Segmental turnover (100) must NOT overwrite
    assert y2024["income_statement"]["Revenue"]["value"] != 100


def test_scale_and_sign_on_balance_sheet():
    content = FIXTURE.read_bytes()
    years, _ = parse_ixbrl_document(content)
    y2024 = merge_ixbrl_year(next(y for y in years if y["period"] == "2024"))

    # scale=3 on 95000 -> 95_000_000
    assert y2024["balance_sheet"]["Non-Current Assets"]["value"] == 95_000_000
    assert y2024["balance_sheet"]["Current Assets"]["value"] == 180_000_000
    # sign="-" on creditors
    assert y2024["balance_sheet"]["Current Liabilities"]["value"] == 95_000_000
    assert y2024["balance_sheet"]["Net Assets"]["value"] == 140_000_000
    assert y2024["balance_sheet"]["Equity"]["value"] == 140_000_000


def test_cash_flow_and_negative_investing():
    content = FIXTURE.read_bytes()
    years, _ = parse_ixbrl_document(content)
    y2024 = next(y for y in years if y["period"] == "2024")
    assert y2024["cash_flow"]["Operating CF"]["value"] == 68_000_000
    assert y2024["cash_flow"]["Investing CF"]["value"] == -22_000_000
    assert y2024["cash_flow"]["Financing CF"]["value"] == -15_000_000
    assert y2024["cash_flow"]["Net Change in Cash"]["value"] == 31_000_000


def test_provenance_present():
    content = FIXTURE.read_bytes()
    years, _ = parse_ixbrl_document(content)
    y2024 = next(y for y in years if y["period"] == "2024")
    prov = y2024["income_statement"]["Revenue"]["provenance"]
    assert prov["method"] == "ixbrl"
    assert prov["concept"] == "Turnover"
    assert prov["scale_applied"] == 0
    assert "FY2024" in prov["context_id"]


def test_orchestrator_xhtml_path():
    content = FIXTURE.read_bytes()
    years, meta = parse_filing_bytes(content, "xhtml", filing_date="2024-09-30")
    assert meta["kind"] == "xhtml"
    assert len(years) == 2
    assert years[0]["parsing_status"] == "ixbrl"
    assert years[0]["income_statement"]["Revenue"]["value"] == 520_000_000


def test_cost_of_sales_negative_sign():
    content = FIXTURE.read_bytes()
    years, _ = parse_ixbrl_document(content)
    y2024 = next(y for y in years if y["period"] == "2024")
    assert y2024["income_statement"]["Cost of Sales"]["value"] == -208_000_000


EXTENDED = pathlib.Path(__file__).parent / "fixtures" / "sample_frs102_extended.xhtml"


def test_extended_fixture_maps_frs102_concepts_and_prefers_consolidated():
    content = EXTENDED.read_bytes()
    facts, stats = extract_facts(content)
    assert stats["facts_mapped"] >= 15
    years, _ = parse_ixbrl_document(content, filing_date="2024-12-31")
    y = merge_ixbrl_year(next(y for y in years if y["period"] == "2024"))

    # Consolidated P&L preferred over parent-company ProfitLoss
    assert y["income_statement"]["Net Income"]["value"] == -37_100_000
    assert y["income_statement"]["Administrative Expenses"]["value"] == 57_000_000
    assert y["income_statement"]["Cost of Sales"]["value"] == 6_100_000
    assert y["income_statement"]["Finance Income"]["value"] == 1_800_000
    assert y["income_statement"]["Finance Costs"]["value"] == 320_000
    assert y["income_statement"]["Tax"]["value"] == -1_450_000
    assert y["income_statement"]["Comprehensive Income"]["value"] == -37_200_000
    assert y["income_statement"]["Staff Costs"]["value"] == 40_000_000
    assert y["income_statement"]["Net Interest Income"]["value"] == 9_000_000
    assert y["income_statement"]["Total Income"]["value"] == 12_000_000
    # Segmental admin (1) must not win
    assert y["income_statement"]["Administrative Expenses"]["value"] != 1

    # CurrentAssets total beats CashBankOnHand / Debtors components
    assert y["balance_sheet"]["Current Assets"]["value"] == 55_000_000
    assert y["balance_sheet"]["Current Assets"]["provenance"]["concept"] == "CurrentAssets"
    # Creditors + CurrentFinancialInstruments → Current Liabilities
    assert y["balance_sheet"]["Current Liabilities"]["value"] == 6_750_000
    assert y["balance_sheet"]["Net Assets"]["value"] == 42_500_000
    # Consolidated InvestmentsFixedAssets preferred for NCA when no FixedAssets total
    assert y["balance_sheet"]["Non-Current Assets"]["value"] == 386_000

    assert y["cash_flow"]["Operating CF"]["value"] == 39_300_000
    assert y["cash_flow"]["Operating CF"]["provenance"]["concept"] == "NetCashGeneratedFromOperations"
    assert y["cash_flow"]["Investing CF"]["value"] == -5_000_000
    assert y["cash_flow"]["Financing CF"]["value"] == 10_000_000


def test_weak_components_do_not_override_totals():
    """Synthetic: CurrentAssets total + CashBankOnHand — total wins."""
    content = EXTENDED.read_bytes()
    years, _ = parse_ixbrl_document(content)
    y = next(y for y in years if y["period"] == "2024")
    ca = y["balance_sheet"]["Current Assets"]
    assert ca["value"] == 55_000_000
    assert ca["provenance"]["confidence"] >= 100


def test_concept_map_includes_common_uk_cf_tags():
    from ixbrl import CONCEPT_MAP

    for concept, key in (
        ("NetCashFlowsFromOperatingActivities", "Operating CF"),
        ("NetCashUsedInOperatingActivities", "Operating CF"),
        ("NetCashInflowFromOperatingActivities", "Operating CF"),
        ("NetCashFromInvestingActivities", "Investing CF"),
        ("NetCashFromFinancingActivities", "Financing CF"),
        ("NetIncreaseInCashAndCashEquivalents", "Net Change in Cash"),
    ):
        assert CONCEPT_MAP[concept] == ("cash_flow", key)
