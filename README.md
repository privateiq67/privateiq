# PrivateIQ

CapIQ-style terminal for **UK private company financials** — Companies House filings (iXBRL preferred, PDF fallback), normalised Income Statement / Balance Sheet / Cash Flow, plus UK business news.

## Architecture

- `frontend/` Next.js 16 + React 19 + Tailwind 4 (dark CapIQ UI)
- `backend/` FastAPI
  - `ixbrl.py` Proper iXBRL/XHTML parser (contexts, scale, sign, taxonomy map)
  - `pdf_extract.py` PDF digital-text + smart OCR for scanned CH accounts (year columns, units, sections)
  - `normalize.py` Synonym map + confidence-aware merge + soft BS validation
  - `extract.py` Orchestrator: iXBRL then PDF then cache
  - `fixtures.py` Demo companies when no API key
  - `db.py` SQLite cache (`backend/data/privateiq.db`)
  - `news.py` BBC / Guardian / FT / Google News RSS
  - `legacy/` Quarantined broken coordinate/OCR parser (do not use)

Financials API shape: `years[]` with `income_statement` / `balance_sheet` / `cash_flow` line items `{value, provenance?}`, `parsing_status` in `ixbrl|pdf|fixture|partial`, `schema_version: "1.0"`.

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# For scanned Companies House PDFs (common on recent full accounts):
#   sudo apt-get install -y tesseract-ocr
# Docker image already installs tesseract-ocr.
cp .env.example .env
uvicorn main:app --reload --port 8000
```

Or `./scripts/dev-backend.sh`.

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Default API URL is `http://localhost:8000` via `NEXT_PUBLIC_API_URL`.

### Companies House API key

1. Register at https://developer.company-information.service.gov.uk/
2. Set `COMPANIES_HOUSE_API_KEY` or legacy `COMPANIES_HOUSE_KEY` in `backend/.env`
3. Restart uvicorn — `/api/health` shows `"demo_mode": false`

Without a key, demo fixtures power search, profile, and multi-year statements.

### Docker (optional)

```bash
docker compose up --build
```

## Tests

```bash
cd backend && source .venv/bin/activate && pytest tests/ -v
```

Includes iXBRL dual-year contexts + scale/sign, PDF year-column binding + GBP thousands scale, confidence rules (no invented EBITDA), and demo API smoke tests.

## What was wrong with the old parser

The previous `parser.py` (now `legacy/parser_coord_ocr.py`):

- Ignored comparative year columns (took first right-hand number only)
- Mapped net assets to total assets incorrectly
- Returned a flat key bag instead of `years[]` schema
- Could mis-associate OCR tokens with labels

**Replacement:** iXBRL-first with context/period grouping; PDF fallback with section detection, unit scale, year-column alignment; synonym + confidence normalisation; provenance on each line.

## Known parsing limits

- Curated FRS 102 / IFRS concept subset — uncommon tags skipped, not guessed
- Dimensional iXBRL breakdowns ignored so segments do not overwrite entity totals
- Unusual PDF note columns / wrapped labels can still mis-bind
- **Many recent Companies House full accounts are scanned image-only PDFs** (no digital text). Extraction then requires **tesseract** (`tesseract-ocr` apt package + `pytesseract`). Without tesseract, those filings surface `ocr_required` instead of silently returning empty statements.
- Smart OCR probes low-res / every-Nth page for Balance Sheet / P&L / Cash Flow / Turnover, then full-OCR only candidate pages (±1 neighbour) — not all 50 pages blindly
- EBITDA is never invented without D&A
- Balance sheet identity checks are warnings, not hard failures
- FRS 102 entity accounts often omit a cash-flow statement; CF will be empty when absent from the filing

## Future work

- Broader official taxonomy packages
- Progress UI for long parses
- Comps / multiples panel
- Auth + watchlists
