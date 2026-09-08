# CF-gap retry + combined rate update

- Generated (UTC): `2026-09-08T16:17:27.076959+00:00`
- Focused retry: **39** companies missing CF and/or incomplete IS/BS from prior combined (max_filings=1, OCR on)
- Artifacts: `cf_gap_retry.{json,md,log}`

## Focused retry pass rates (gap set only)

| Metric | Count | Rate |
| --- | ---: | ---: |
| Any year | 38 | 97% |
| Income statement | 33 | 85% |
| Balance sheet | 30 | 77% |
| Cash flow | 6 | 15% |
| Errors | 1 | 3% |

On this CF-heavy gap set, raw CF%=15% looks low because most selected cos still have **no CF statement**. Absolute lift vs baseline on the same names: **+5 companies newly gained CF**.

## Combined top-60 rates (improvement-only merge)

| Metric | Baseline | After CF-gap retry |
| --- | ---: | ---: |
| Any year | 100% | 100% |
| Income statement | 90% | 93% (56/60) |
| Balance sheet | 82% | **88%** (53/60) |
| Cash flow | 37% (22/60) | **45%** (27/60) |
| Errors | 0% | 0% |

## What improved

### New CF lines
- **Monzo Bank Limited** (`09446231`)
- **John Lewis Partnership plc** (`00238937`)
- **John Swire & Sons Limited** (`00133143`)
- **Thought Machine Group Limited** (`11114277`)
- **Synthesia Limited** (`10933652`)

### New IS lines
- **Monzo Bank Limited** (`09446231`)
- **Virgin Media Limited** (`02591237`)

### New BS lines
- **John Lewis Partnership plc** (`00238937`)
- **Virgin Media Limited** (`02591237`)
- **Featurespace Limited** (`05640420`)
- **Synthesia Limited** (`10933652`)

## Remaining hard CF cases (honest)

Most remaining CF misses are **not** synonym bugs:

1. **No CF statement in the filing** — common under FRS 102 for medium/subsidiary UK privates (Gymshark: P&amp;L+BS only in scanned accounts).
2. **iXBRL without CF facts** — TrueLayer / Galliard etc. tag P&amp;L+BS only; visible "cash flow" text is policy notes.
3. **Long scanned reports** — CF page still outside OCR candidate budget on some 150–200pp banks/groups.
4. **OCR label noise** — mitigated for `Net cash (used)/generated from operating activities` (Featurespace Operating CF + BS now recovered).

Retry used max_filings=1; a few names looked worse in the raw retry log (Iceland IS, Gatwick, Willmott BS) — those regressions are **not** folded into combined rates.

## Code shipped

- `ixbrl.py`: expanded UK CF `CONCEPT_MAP`
- `pdf_extract.py`: CF section/OCR `fiows` tolerance; statement-header OCR priority + gap fill; clear sticky Fixed/Current assets headers at creditors/provisions
- `normalize.py`: CF `(used)/generated` synonyms + net-cash matcher; equity attributable *to the owners*; Equity/Net Assets from TA−|TL|
- tests in `test_pdf_normalize.py`, `test_pdf_ocr.py`, `test_ixbrl.py`
