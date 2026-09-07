"""SQLite cache for parsed financials keyed by company_number + period."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "privateiq.db")


def _ensure_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def connect():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS financials_cache (
                company_number TEXT NOT NULL,
                period TEXT NOT NULL,
                filing_date TEXT,
                parsing_status TEXT,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (company_number, period)
            )
            """
        )


def get_cached_year(company_number: str, period: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM financials_cache WHERE company_number=? AND period=?",
            (company_number, period),
        ).fetchone()
        if row:
            return json.loads(row["payload"])
    return None


def get_cached_financials(company_number: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM financials_cache
            WHERE company_number=?
            ORDER BY period DESC
            """,
            (company_number,),
        ).fetchall()
        if not rows:
            return None
        years = [json.loads(r["payload"]) for r in rows]
        return {
            "company_number": company_number,
            "years": years,
            "schema_version": "1.0",
            "cached": True,
        }


def upsert_year(company_number: str, year_payload: dict[str, Any]) -> None:
    period = year_payload.get("period") or "unknown"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO financials_cache
                (company_number, period, filing_date, parsing_status, payload, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_number, period) DO UPDATE SET
                filing_date=excluded.filing_date,
                parsing_status=excluded.parsing_status,
                payload=excluded.payload,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                company_number,
                period,
                year_payload.get("filing_date"),
                year_payload.get("parsing_status"),
                json.dumps(year_payload),
            ),
        )


def upsert_financials(company_number: str, financials: dict[str, Any]) -> None:
    for year in financials.get("years") or []:
        upsert_year(company_number, year)
