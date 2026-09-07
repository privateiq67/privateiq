"""Smoke tests for demo mode endpoints (no API key)."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

# Clear before and after importing main — load_dotenv() reloads backend/.env
os.environ.pop("COMPANIES_HOUSE_API_KEY", None)
os.environ.pop("COMPANIES_HOUSE_KEY", None)

from fastapi.testclient import TestClient

from main import app

os.environ.pop("COMPANIES_HOUSE_API_KEY", None)
os.environ.pop("COMPANIES_HOUSE_KEY", None)

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True


def test_demo_search():
    r = client.get("/api/search", params={"q": "gymshark"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["company_number"] == "08489098" for i in items)


def test_demo_profile_and_financials_shape():
    r = client.get("/api/company/08489098")
    assert r.status_code == 200
    profile = r.json()
    assert profile["company_name"]
    assert profile["sic_codes"]

    f = client.get("/api/company/08489098/financials")
    assert f.status_code == 200
    data = f.json()
    assert data["schema_version"] == "1.0"
    assert data["years"]
    y0 = data["years"][0]
    assert "income_statement" in y0
    assert "balance_sheet" in y0
    assert "cash_flow" in y0
    assert y0["income_statement"]["Revenue"]["value"] > 0
    assert y0["parsing_status"] == "fixture"


def test_news_endpoint():
    r = client.get("/api/news", params={"name": "Gymshark"})
    assert r.status_code == 200
    body = r.json()
    assert "news" in body
    # May be empty offline; structure must hold
    assert isinstance(body["news"], list)
