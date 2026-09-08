# Top-60 UK private companies — combined parser eval

- Generated (UTC): `2026-09-08T16:17:27.076959+00:00`
- Companies: **60** (initial run + OCR retry + CF-gap retry, improvement-only merge)
- Detail: `cf_gap_retry_note.md`, focused run `cf_gap_retry.md`

## Pass rates

| Metric | Count | Rate |
| --- | ---: | ---: |
| Any year parsed | 60 | 100% |
| Income statement line | 56 | 93% |
| Balance sheet line | 53 | 88% |
| Cash flow line | 27 | 45% |
| Errors | 0 | 0% |

Prior baseline: any-year 100%, IS 90%, BS 82%, CF 37%, errors 0%.

## Gaps (any-year OK but missing IS/BS — CF-only gaps omitted; see note)

- **Nscale Global Holdings Limited** (`15749408`): missing IS, CF ['pdf_ocr']
- **INEOS Industries Limited** (`06959146`): missing BS, CF ['partial', 'pdf_ocr']
- **The Very Group Limited** (`04730752`): missing IS, BS, CF ['partial']
- **Starling Bank Limited** (`09092149`): missing IS, BS, CF ['partial']
- **Checkout Ltd** (`08037323`): missing BS, CF ['partial', 'pdf_ocr']
- **Asda Stores Limited** (`00464777`): missing BS, CF ['pdf_ocr']
- **Heathrow Airport Limited** (`01991017`): missing BS, CF ['partial', 'pdf_ocr']
- **Willmott Dixon Holdings Limited** (`00198032`): missing IS, CF ['pdf_ocr']
- **2 Sisters Food Group Limited** (`02826929`): missing BS, CF ['pdf_ocr']
