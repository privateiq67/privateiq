"""PrivateIQ FastAPI backend — Companies House + iXBRL/PDF financials + news."""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from db import get_cached_year, init_db, upsert_year
from extract import build_financials_for_company
from fixtures import get_demo_financials, get_demo_profile, search_demo
from news import fetch_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("privateiq")

from contextlib import asynccontextmanager

BASE_URL = "https://api.company-information.service.gov.uk"


def get_api_key() -> Optional[str]:
    return (
        os.getenv("COMPANIES_HOUSE_API_KEY")
        or os.getenv("COMPANIES_HOUSE_KEY")
        or ""
    ).strip() or None


def demo_mode() -> bool:
    return get_api_key() is None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    mode = "DEMO (fixtures)" if demo_mode() else "LIVE (Companies House)"
    logger.info("PrivateIQ backend starting in %s mode", mode)
    yield


app = FastAPI(title="PrivateIQ", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "demo_mode": demo_mode(),
        "schema_version": "1.0",
    }


@app.get("/api/search")
def search_companies(q: str = Query(..., min_length=1)):
    if demo_mode():
        return search_demo(q)

    key = get_api_key()
    try:
        response = requests.get(
            f"{BASE_URL}/search/companies",
            params={"q": q},
            auth=(key, ""),
            timeout=30,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Companies House unreachable: {e}") from e

    if response.status_code != 200:
        logger.warning("CH search status %s", response.status_code)
        return {"items": [], "error": f"ch_status_{response.status_code}"}

    data = response.json()
    return {"items": data.get("items") or [], "total_results": data.get("total_results")}


@app.get("/api/company/{company_number}")
def company_profile(company_number: str):
    if demo_mode():
        profile = get_demo_profile(company_number)
        if not profile:
            raise HTTPException(status_code=404, detail="Demo company not found")
        return profile

    key = get_api_key()
    try:
        res = requests.get(
            f"{BASE_URL}/company/{company_number}",
            auth=(key, ""),
            timeout=30,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail="Company not found")

    data = res.json()
    officers_summary = []
    try:
        off = requests.get(
            f"{BASE_URL}/company/{company_number}/officers",
            params={"items_per_page": 5},
            auth=(key, ""),
            timeout=20,
        )
        if off.status_code == 200:
            for item in (off.json().get("items") or [])[:5]:
                officers_summary.append(
                    {
                        "name": item.get("name"),
                        "role": item.get("officer_role"),
                        "appointed_on": item.get("appointed_on"),
                    }
                )
    except requests.RequestException:
        pass

    address = data.get("registered_office_address") or {}
    return {
        "company_number": data.get("company_number") or company_number,
        "company_name": data.get("company_name"),
        "title": data.get("company_name"),
        "company_status": data.get("company_status"),
        "company_type": data.get("type"),
        "date_of_creation": data.get("date_of_creation"),
        "registered_office": address,
        "address_snippet": ", ".join(
            str(address[k])
            for k in (
                "address_line_1",
                "address_line_2",
                "locality",
                "postal_code",
                "country",
            )
            if address.get(k)
        ),
        "sic_codes": data.get("sic_codes") or [],
        "officers_summary": officers_summary,
        "demo": False,
    }


@app.get("/api/company/{company_number}/financials")
def get_financials(company_number: str, max_filings: int = Query(5, ge=1, le=10)):
    if demo_mode():
        fin = get_demo_financials(company_number)
        if not fin:
            # Unknown demo number — empty schema-shaped response
            return {
                "company_number": company_number,
                "years": [],
                "schema_version": "1.0",
                "demo": True,
                "message": "No demo financials for this company number",
            }
        return fin

    key = get_api_key()
    try:
        hist = requests.get(
            f"{BASE_URL}/company/{company_number}/filing-history",
            params={"category": "accounts", "items_per_page": 20},
            auth=(key, ""),
            timeout=30,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    if hist.status_code != 200:
        raise HTTPException(status_code=hist.status_code, detail="Filing history unavailable")

    items = hist.json().get("items") or []
    if not items:
        return {
            "company_number": company_number,
            "years": [],
            "schema_version": "1.0",
            "message": "No accounts filings found",
        }

    result = build_financials_for_company(
        company_number,
        items,
        key,
        max_filings=max_filings,
        allow_ocr=True,
        cache_get=get_cached_year,
        cache_put=upsert_year,
    )
    return result


@app.get("/api/news")
def get_news(name: Optional[str] = None, limit: int = Query(20, ge=1, le=50)):
    try:
        items = fetch_news(name=name, limit=limit)
    except Exception as e:
        logger.exception("news fetch failed")
        return {"news": [], "error": str(e)}
    return {"news": items}
