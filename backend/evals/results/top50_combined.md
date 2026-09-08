# Top-60 UK private companies — combined parser eval

- Generated (UTC): `2026-09-08T14:19:09.309143+00:00`
- Companies: **60** (initial run + OCR retry on failures)

## Pass rates

| Metric | Count | Rate |
| --- | ---: | ---: |
| Any year parsed | 60 | 100% |
| Income statement line | 54 | 90% |
| Balance sheet line | 49 | 82% |
| Cash flow line | 22 | 37% |
| Errors | 0 | 0% |

## Gaps (any-year OK but missing statement families)

- **Monzo Bank Limited** (`09446231`): missing IS, CF [['pdf_ocr']]
- **Nscale Global Holdings Limited** (`15749408`): missing IS, CF [['pdf_ocr']]
- **John Lewis Partnership plc** (`00238937`): missing BS, CF [['pdf_ocr']]
- **INEOS Industries Limited** (`06959146`): missing BS, CF [['partial', 'pdf_ocr']]
- **The Very Group Limited** (`04730752`): missing IS, BS, CF [['partial']]
- **Starling Bank Limited** (`09092149`): missing IS, BS, CF [['partial']]
- **Checkout Ltd** (`08037323`): missing BS, CF [['partial', 'pdf_ocr']]
- **Asda Stores Limited** (`00464777`): missing BS, CF [['pdf_ocr']]
- **Virgin Media Limited** (`02591237`): missing IS, BS, CF [['partial']]
- **Heathrow Airport Limited** (`01991017`): missing BS, CF [['partial', 'pdf_ocr']]
- **Willmott Dixon Holdings Limited** (`00198032`): missing IS, CF [['pdf_ocr']]
- **2 Sisters Food Group Limited** (`02826929`): missing BS, CF [['pdf_ocr']]
- **Featurespace Limited** (`05640420`): missing BS [['pdf_ocr']]
- **Synthesia Limited** (`10933652`): missing BS, CF [['pdf_ocr']]
