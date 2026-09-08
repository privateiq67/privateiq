"""period_from_filing must prefer made_up_date / action_date over filing date."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extract import period_from_filing


def test_period_prefers_made_up_date_over_filing_date():
    filing = {
        "date": "2026-05-10",
        "type": "AA",
        "description": "accounts-with-accounts-type-full",
        "description_values": {"made_up_date": "2025-07-31"},
        "action_date": "2025-07-31",
    }
    assert period_from_filing(filing) == "2025"


def test_period_prefers_action_date():
    filing = {
        "date": "2026-08-27",
        "description": "accounts-with-accounts-type-full",
        "action_date": "2026-03-31",
    }
    assert period_from_filing(filing) == "2026"


def test_period_falls_back_to_filing_date():
    filing = {"date": "2024-10-15", "description": "accounts-with-accounts-type-full"}
    assert period_from_filing(filing) == "2024"
