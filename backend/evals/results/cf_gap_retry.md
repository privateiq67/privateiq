# Top-50 UK private companies — parser eval

- Generated (UTC): `2026-09-08T16:13:57.982630+00:00`
- Companies evaluated: **39**
- max_filings=1, allow_ocr=True, ocr_budget=45, sleep_sec=0.35

## Pass rates

| Metric | Count | Rate |
| --- | ---: | ---: |
| Any year parsed | 38 | 97% |
| Income statement line | 33 | 85% |
| Balance sheet line | 30 | 77% |
| Cash flow line | 6 | 15% |
| Errors | 1 | 3% |
| OCR companies used | 34 | — |

## Results

| # | Company | Number | Any | IS | BS | CF | Statuses | Sec | Error |
| ---: | --- | --- | :---: | :---: | :---: | :---: | --- | ---: | --- |
| 1 | Gymshark Ltd | 08130873 | Y | Y | Y | N | pdf_ocr | 149.4 | — |
| 2 | Monzo Bank Limited | 09446231 | Y | Y | Y | Y | pdf_ocr | 144.4 | — |
| 3 | TrueLayer Limited | 10278251 | Y | Y | Y | N | ixbrl | 4.0 | — |
| 4 | Nscale Global Holdings Limited | 15749408 | Y | N | Y | N | partial,pdf_ocr | 166.3 | — |
| 5 | Bet365 Group Limited | 04241161 | Y | Y | Y | N | pdf_ocr | 151.7 | — |
| 6 | John Lewis Partnership plc | 00238937 | Y | Y | Y | Y | partial,pdf_ocr | 154.3 | — |
| 7 | John Swire & Sons Limited | 00133143 | Y | Y | Y | Y | partial,pdf_ocr | 201.9 | — |
| 8 | Iceland Foods Limited | 01107406 | Y | N | Y | N | pdf_ocr | 156.8 | — |
| 9 | Dyson Limited | 02627406 | Y | Y | Y | N | pdf_ocr | 109.8 | — |
| 10 | INEOS Industries Limited | 06959146 | Y | Y | N | N | partial,pdf_ocr | 200.8 | — |
| 11 | Bestway Wholesale Limited | 01207120 | Y | Y | Y | N | pdf_ocr | 144.1 | — |
| 12 | Holland & Barrett Retail Limited | 02758955 | Y | Y | Y | N | pdf_ocr | 124.8 | — |
| 13 | The Very Group Limited | 04730752 | N | N | N | N | — | 88.5 | no_years_parsed |
| 14 | Pret A Manger (Europe) Limited | 01854213 | Y | Y | Y | N | partial,pdf_ocr | 154.9 | — |
| 15 | Starling Bank Limited | 09092149 | Y | N | N | N | partial | 71.0 | — |
| 16 | Revolut Ltd | 08804411 | Y | Y | Y | N | pdf_ocr | 202.6 | — |
| 17 | Checkout Ltd | 08037323 | Y | Y | N | N | partial,pdf_ocr | 163.6 | — |
| 18 | Asda Stores Limited | 00464777 | Y | Y | N | N | partial,pdf_ocr | 141.9 | — |
| 19 | Moto Hospitality Limited | 00734299 | Y | Y | Y | N | pdf_ocr | 149.4 | — |
| 20 | Virgin Media Limited | 02591237 | Y | Y | Y | N | partial,pdf_ocr | 183.2 | — |
| 21 | Hutchison 3G UK Limited | 03885486 | Y | Y | Y | N | pdf_ocr | 187.6 | — |
| 22 | Keepmoat Homes Limited | 02207338 | Y | Y | Y | N | pdf_ocr | 119.8 | — |
| 23 | Galliard Homes Limited | 02158998 | Y | Y | Y | N | ixbrl | 4.0 | — |
| 24 | Canary Wharf Group plc | 04191122 | Y | Y | Y | N | partial,pdf_ocr | 133.9 | — |
| 25 | P&O Ferries Limited | 00237626 | Y | Y | Y | N | pdf_ocr | 153.5 | — |
| 26 | New Look Limited | 01996366 | Y | Y | Y | N | partial,pdf_ocr | 106.4 | — |
| 27 | River Island Clothing Co. Limited | 00636095 | Y | Y | Y | N | pdf_ocr | 95.3 | — |
| 28 | Poundland Limited | 02495645 | Y | Y | Y | N | partial,pdf_ocr | 150.3 | — |
| 29 | Modulr FS Limited | 09897919 | Y | Y | Y | N | pdf_ocr | 87.2 | — |
| 30 | Thought Machine Group Limited | 11114277 | Y | Y | Y | Y | pdf_ocr | 162.7 | — |
| 31 | Heathrow Airport Limited | 01991017 | Y | Y | N | N | partial,pdf_ocr | 45.3 | — |
| 32 | Gatwick Airport Limited | 01991018 | Y | N | N | N | pdf_ocr | 174.6 | — |
| 33 | Laing O'Rourke plc | 04222545 | Y | Y | Y | N | pdf_ocr | 231.3 | — |
| 34 | Willmott Dixon Holdings Limited | 00198032 | Y | N | N | N | partial | 191.4 | — |
| 35 | Samworth Brothers Limited | 03116767 | Y | Y | Y | N | partial,pdf_ocr | 133.0 | — |
| 36 | 2 Sisters Food Group Limited | 02826929 | Y | Y | N | N | pdf_ocr | 157.4 | — |
| 37 | Warburtons Limited | 00178711 | Y | Y | Y | N | pdf_ocr | 149.3 | — |
| 38 | Featurespace Limited | 05640420 | Y | Y | Y | Y | pdf_ocr | 118.8 | — |
| 39 | Synthesia Limited | 10933652 | Y | Y | Y | Y | pdf_ocr | 149.8 | — |

## Notable failures / gaps

- **Nscale Global Holdings Limited** (`15749408`): missing IS, CF [statuses=partial,pdf_ocr]
- **Iceland Foods Limited** (`01107406`): missing IS, CF [statuses=pdf_ocr]
- **INEOS Industries Limited** (`06959146`): missing BS, CF [statuses=partial,pdf_ocr]
- **The Very Group Limited** (`04730752`): no_years_parsed [statuses=none]
- **Starling Bank Limited** (`09092149`): missing IS, BS, CF [statuses=partial]
- **Checkout Ltd** (`08037323`): missing BS, CF [statuses=partial,pdf_ocr]
- **Asda Stores Limited** (`00464777`): missing BS, CF [statuses=partial,pdf_ocr]
- **Heathrow Airport Limited** (`01991017`): missing BS, CF [statuses=partial,pdf_ocr]
- **Gatwick Airport Limited** (`01991018`): missing IS, BS, CF [statuses=pdf_ocr]
- **Willmott Dixon Holdings Limited** (`00198032`): missing IS, BS, CF [statuses=partial]
- **2 Sisters Food Group Limited** (`02826929`): missing BS, CF [statuses=pdf_ocr]
