#!/usr/bin/env python3
"""Reproducible Top-50 UK private company financials parser eval.

Usage (from backend/):
  python evals/run_top50.py --limit 5
  python evals/run_top50.py
  python evals/run_top50.py --numbers 08130873,01824828 --no-ocr
  python evals/run_top50.py --ocr-budget 15

Respects Companies House rate limits with small sleeps. Uses the SQLite
financials cache. Does not print or commit API keys.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from db import get_cached_year, init_db, upsert_year  # noqa: E402
from extract import build_financials_for_company  # noqa: E402

BASE_URL = "https://api.company-information.service.gov.uk"
COMPANY_SET = Path(__file__).resolve().parent / "top50_uk_private.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_JSON = RESULTS_DIR / "top50_latest.json"
RESULTS_MD = RESULTS_DIR / "top50_latest.md"

INCOME_KEYS = (
    "Revenue",
    "Gross Profit",
    "Operating Profit",
    "Profit Before Tax",
    "Net Income",
    "Total Income",
    "Net Interest Income",
)
BALANCE_KEYS = ("Total Assets", "Equity", "Net Assets")
CASH_KEYS = ("Operating CF", "Investing CF", "Financing CF", "Net Change in Cash")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("eval_top50")


def get_api_key() -> str:
    key = (
        os.getenv("COMPANIES_HOUSE_API_KEY")
        or os.getenv("COMPANIES_HOUSE_KEY")
        or ""
    ).strip()
    if not key:
        raise SystemExit("COMPANIES_HOUSE_API_KEY / COMPANIES_HOUSE_KEY missing in backend/.env")
    return key


def ch_get(path: str, key: str, *, params: Optional[dict] = None) -> requests.Response:
    return requests.get(
        f"{BASE_URL}{path}",
        params=params or {},
        auth=(key, ""),
        timeout=60,
    )


def fetch_accounts_filings(company_number: str, key: str) -> list[dict]:
    res = ch_get(
        f"/company/{company_number}/filing-history",
        key,
        params={"category": "accounts", "items_per_page": 25},
    )
    if res.status_code != 200:
        raise RuntimeError(f"filing_history_status_{res.status_code}")
    return list(res.json().get("items") or [])


def _section_has_any(year: dict, section: str, keys: tuple[str, ...]) -> bool:
    block = year.get(section) or {}
    for k in keys:
        item = block.get(k)
        if isinstance(item, dict) and item.get("value") is not None:
            return True
        if item is not None and not isinstance(item, dict):
            return True
    return False


def score_result(result: dict) -> dict[str, Any]:
    years = result.get("years") or []
    has_any_year = bool(years)
    has_income = any(_section_has_any(y, "income_statement", INCOME_KEYS) for y in years)
    has_balance = any(_section_has_any(y, "balance_sheet", BALANCE_KEYS) for y in years)
    has_cash = any(_section_has_any(y, "cash_flow", CASH_KEYS) for y in years)
    statuses = sorted({str(y.get("parsing_status") or "unknown") for y in years}) if years else []
    periods = [y.get("period") for y in years]
    return {
        "has_any_year": has_any_year,
        "has_income_line": has_income,
        "has_balance_line": has_balance,
        "has_cash_line": has_cash,
        "parsing_statuses": statuses,
        "periods": periods,
        "n_years": len(years),
    }


def load_companies(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return list(data.get("companies") or [])


def write_markdown(summary: dict, rows: list[dict], path: Path) -> None:
    s = summary
    lines = [
        "# Top-50 UK private companies — parser eval",
        "",
        f"- Generated (UTC): `{s.get('generated_at_utc')}`",
        f"- Companies evaluated: **{s.get('n_companies')}**",
        f"- max_filings={s.get('max_filings')}, allow_ocr={s.get('allow_ocr')}, "
        f"ocr_budget={s.get('ocr_budget')}, sleep_sec={s.get('sleep_sec')}",
        "",
        "## Pass rates",
        "",
        f"| Metric | Count | Rate |",
        f"| --- | ---: | ---: |",
        f"| Any year parsed | {s['n_any_year']} | {s['pct_any_year']:.0%} |",
        f"| Income statement line | {s['n_income']} | {s['pct_income']:.0%} |",
        f"| Balance sheet line | {s['n_balance']} | {s['pct_balance']:.0%} |",
        f"| Cash flow line | {s['n_cash']} | {s['pct_cash']:.0%} |",
        f"| Errors | {s['n_errors']} | {s['pct_errors']:.0%} |",
        f"| OCR companies used | {s.get('ocr_used', 0)} | — |",
        "",
        "## Results",
        "",
        "| # | Company | Number | Any | IS | BS | CF | Statuses | Sec | Error |",
        "| ---: | --- | --- | :---: | :---: | :---: | :---: | --- | ---: | --- |",
    ]
    for i, r in enumerate(rows, 1):
        err = (r.get("error") or "").replace("|", "/")[:80]
        statuses = ",".join(r.get("parsing_statuses") or []) or "—"
        lines.append(
            f"| {i} | {r.get('name','')} | {r.get('company_number','')} | "
            f"{'Y' if r.get('has_any_year') else 'N'} | "
            f"{'Y' if r.get('has_income_line') else 'N'} | "
            f"{'Y' if r.get('has_balance_line') else 'N'} | "
            f"{'Y' if r.get('has_cash_line') else 'N'} | "
            f"{statuses} | {r.get('elapsed_sec', 0):.1f} | {err or '—'} |"
        )
    failures = [
        r
        for r in rows
        if r.get("error") or not (r.get("has_income_line") and r.get("has_balance_line"))
    ]
    lines.extend(["", "## Notable failures / gaps", ""])
    if not failures:
        lines.append("None — all companies produced IS + BS lines.")
    else:
        for r in failures:
            reason = r.get("error") or (
                "missing "
                + ", ".join(
                    x
                    for x, ok in (
                        ("IS", r.get("has_income_line")),
                        ("BS", r.get("has_balance_line")),
                        ("CF", r.get("has_cash_line")),
                    )
                    if not ok
                )
            )
            lines.append(
                f"- **{r.get('name')}** (`{r.get('company_number')}`): {reason} "
                f"[statuses={','.join(r.get('parsing_statuses') or []) or 'none'}]"
            )
    lines.append("")
    path.write_text("\n".join(lines))


def summarise(rows: list[dict], meta: dict) -> dict:
    n = len(rows) or 1
    n_any = sum(1 for r in rows if r.get("has_any_year"))
    n_is = sum(1 for r in rows if r.get("has_income_line"))
    n_bs = sum(1 for r in rows if r.get("has_balance_line"))
    n_cf = sum(1 for r in rows if r.get("has_cash_line"))
    n_err = sum(1 for r in rows if r.get("error"))
    return {
        **meta,
        "n_companies": len(rows),
        "n_any_year": n_any,
        "n_income": n_is,
        "n_balance": n_bs,
        "n_cash": n_cf,
        "n_errors": n_err,
        "pct_any_year": n_any / n,
        "pct_income": n_is / n,
        "pct_balance": n_bs / n,
        "pct_cash": n_cf / n,
        "pct_errors": n_err / n,
        "ocr_used": sum(1 for r in rows if r.get("ocr_used")),
    }


def eval_company(
    company: dict,
    *,
    key: str,
    max_filings: int,
    allow_ocr: bool,
    sleep_sec: float,
) -> dict[str, Any]:
    number = company["company_number"]
    name = company.get("name") or number
    row: dict[str, Any] = {
        "name": name,
        "company_number": number,
        "sector": company.get("sector"),
        "has_any_year": False,
        "has_income_line": False,
        "has_balance_line": False,
        "has_cash_line": False,
        "parsing_statuses": [],
        "periods": [],
        "n_years": 0,
        "elapsed_sec": 0.0,
        "error": None,
        "ocr_used": False,
        "filings_fetched": 0,
    }
    t0 = time.perf_counter()
    try:
        time.sleep(sleep_sec)
        filings = fetch_accounts_filings(number, key)
        row["filings_fetched"] = len(filings)
        if not filings:
            row["error"] = "no_accounts_filings"
            row["elapsed_sec"] = time.perf_counter() - t0
            return row

        time.sleep(sleep_sec)
        result = build_financials_for_company(
            number,
            filings,
            key,
            max_filings=max_filings,
            allow_ocr=allow_ocr,
            cache_get=get_cached_year,
            cache_put=upsert_year,
        )
        scored = score_result(result)
        row.update(scored)
        # Detect OCR usage from parse path via year statuses / cache payloads
        if any(s in ("pdf_ocr",) for s in scored.get("parsing_statuses") or []):
            row["ocr_used"] = True
        # Also peek parse years for pdf_ocr when DEBUG extra missing
        for y in result.get("years") or []:
            if y.get("parsing_status") == "pdf_ocr":
                row["ocr_used"] = True
        if not scored["has_any_year"]:
            row["error"] = row.get("error") or "no_years_parsed"
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
        logger.exception("Failed %s %s", number, name)
        row["traceback"] = traceback.format_exc()[-2000:]
    row["elapsed_sec"] = round(time.perf_counter() - t0, 2)
    return row


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Eval PrivateIQ parser on top UK private cos")
    ap.add_argument("--limit", type=int, default=0, help="Only first N companies (smoke)")
    ap.add_argument(
        "--numbers",
        type=str,
        default="",
        help="Comma-separated company numbers filter",
    )
    ap.add_argument("--max-filings", type=int, default=2)
    ap.add_argument("--no-ocr", action="store_true", help="iXBRL / digital-PDF only")
    ap.add_argument(
        "--ocr-budget",
        type=int,
        default=15,
        help="Max companies allowed to use OCR this run (rest force no-OCR)",
    )
    ap.add_argument("--sleep", type=float, default=0.45, help="CH rate-limit sleep seconds")
    ap.add_argument("--company-set", type=Path, default=COMPANY_SET)
    ap.add_argument("--out-json", type=Path, default=RESULTS_JSON)
    ap.add_argument("--out-md", type=Path, default=RESULTS_MD)
    args = ap.parse_args(argv)

    key = get_api_key()
    init_db()
    companies = load_companies(args.company_set)

    if args.numbers.strip():
        wanted = {n.strip() for n in args.numbers.split(",") if n.strip()}
        companies = [c for c in companies if c["company_number"] in wanted]
    if args.limit and args.limit > 0:
        companies = companies[: args.limit]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    allow_ocr_global = not args.no_ocr
    ocr_used_count = 0
    rows: list[dict] = []

    logger.info(
        "Starting eval: %d companies, max_filings=%d, allow_ocr=%s, ocr_budget=%d",
        len(companies),
        args.max_filings,
        allow_ocr_global,
        args.ocr_budget,
    )

    for idx, company in enumerate(companies, 1):
        # Budget: after ocr_budget OCR successes/attempts that needed OCR path,
        # force no-OCR for remaining companies so the run finishes.
        allow_ocr = allow_ocr_global and (ocr_used_count < args.ocr_budget)
        if allow_ocr_global and not allow_ocr:
            logger.info(
                "[%d/%d] OCR budget exhausted — iXBRL/digital-only for %s",
                idx,
                len(companies),
                company["company_number"],
            )
        logger.info(
            "[%d/%d] %s (%s) ocr=%s",
            idx,
            len(companies),
            company.get("name"),
            company["company_number"],
            allow_ocr,
        )
        row = eval_company(
            company,
            key=key,
            max_filings=args.max_filings,
            allow_ocr=allow_ocr,
            sleep_sec=args.sleep,
        )
        if row.get("ocr_used"):
            ocr_used_count += 1
        rows.append(row)
        logger.info(
            "  -> any=%s IS=%s BS=%s CF=%s statuses=%s err=%s t=%.1fs",
            row.get("has_any_year"),
            row.get("has_income_line"),
            row.get("has_balance_line"),
            row.get("has_cash_line"),
            row.get("parsing_statuses"),
            row.get("error"),
            row.get("elapsed_sec") or 0,
        )

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_filings": args.max_filings,
        "allow_ocr": allow_ocr_global,
        "ocr_budget": args.ocr_budget,
        "sleep_sec": args.sleep,
        "company_set": str(args.company_set),
    }
    summary = summarise(rows, meta)
    payload = {"summary": summary, "results": rows}
    args.out_json.write_text(json.dumps(payload, indent=2))
    write_markdown(summary, rows, args.out_md)
    logger.info(
        "Done. IS=%.0f%% BS=%.0f%% CF=%.0f%% any=%.0f%% errors=%d → %s",
        100 * summary["pct_income"],
        100 * summary["pct_balance"],
        100 * summary["pct_cash"],
        100 * summary["pct_any_year"],
        summary["n_errors"],
        args.out_json,
    )
    print(
        json.dumps(
            {
                "n": summary["n_companies"],
                "pct_income": round(summary["pct_income"], 3),
                "pct_balance": round(summary["pct_balance"], 3),
                "pct_cash": round(summary["pct_cash"], 3),
                "pct_any_year": round(summary["pct_any_year"], 3),
                "n_errors": summary["n_errors"],
                "out_json": str(args.out_json),
                "out_md": str(args.out_md),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
