# Top-50 UK private companies — parser eval

- Generated (UTC): `2026-09-08T13:54:06.183421+00:00`
- Companies evaluated: **29**
- max_filings=2, allow_ocr=True, ocr_budget=29, sleep_sec=0.5

## Pass rates

| Metric | Count | Rate |
| --- | ---: | ---: |
| Any year parsed | 29 | 100% |
| Income statement line | 27 | 93% |
| Balance sheet line | 24 | 83% |
| Cash flow line | 11 | 38% |
| Errors | 0 | 0% |
| OCR companies used | 28 | — |

## Results

| # | Company | Number | Any | IS | BS | CF | Statuses | Sec | Error |
| ---: | --- | --- | :---: | :---: | :---: | :---: | --- | ---: | --- |
| 1 | Moto Hospitality Limited | 00734299 | Y | Y | Y | N | pdf_ocr | 147.6 | — |
| 2 | Virgin Media Limited | 02591237 | Y | N | N | N | partial | 175.1 | — |
| 3 | Hutchison 3G UK Limited | 03885486 | Y | Y | Y | N | pdf_ocr | 168.0 | — |
| 4 | Keepmoat Homes Limited | 02207338 | Y | Y | Y | N | pdf_ocr | 115.0 | — |
| 5 | P&O Ferries Limited | 00237626 | Y | Y | Y | N | partial,pdf_ocr | 137.7 | — |
| 6 | Associated British Ports Holdings Limited | 01612178 | Y | Y | Y | Y | partial,pdf_ocr | 120.3 | — |
| 7 | New Look Limited | 01996366 | Y | Y | Y | N | partial,pdf_ocr | 97.4 | — |
| 8 | River Island Clothing Co. Limited | 00636095 | Y | Y | Y | N | pdf_ocr | 91.3 | — |
| 9 | Poundland Limited | 02495645 | Y | Y | Y | N | partial,pdf_ocr | 144.3 | — |
| 10 | Caffe Nero Group Holdings Ltd | 05936386 | Y | Y | Y | Y | pdf_ocr | 138.9 | — |
| 11 | Octopus Energy Group Limited | 09718624 | Y | Y | Y | Y | partial,pdf_ocr | 179.7 | — |
| 12 | GoCardless Ltd | 07495895 | Y | Y | Y | Y | partial,pdf_ocr | 175.9 | — |
| 13 | Modulr FS Limited | 09897919 | Y | Y | Y | N | pdf_ocr | 85.6 | — |
| 14 | ClearBank Limited | 09736376 | Y | Y | Y | Y | pdf_ocr | 124.6 | — |
| 15 | Thought Machine Group Limited | 11114277 | Y | Y | Y | N | pdf_ocr | 155.9 | — |
| 16 | Oxa Autonomy Ltd | 09242359 | Y | Y | Y | Y | pdf_ocr | 92.3 | — |
| 17 | Heathrow Airport Limited | 01991017 | Y | Y | N | N | partial,pdf_ocr | 45.3 | — |
| 18 | Gatwick Airport Limited | 01991018 | Y | Y | Y | N | pdf_ocr | 156.9 | — |
| 19 | Laing O'Rourke plc | 04222545 | Y | Y | Y | N | pdf_ocr | 210.9 | — |
| 20 | Sir Robert McAlpine Limited | 00566823 | Y | Y | Y | Y | pdf_ocr | 121.0 | — |
| 21 | Mace Limited | 02410626 | Y | Y | Y | Y | pdf_ocr | 111.2 | — |
| 22 | Willmott Dixon Holdings Limited | 00198032 | Y | N | Y | N | pdf_ocr | 172.3 | — |
| 23 | Samworth Brothers Limited | 03116767 | Y | Y | Y | N | partial,pdf_ocr | 139.7 | — |
| 24 | 2 Sisters Food Group Limited | 02826929 | Y | Y | N | N | pdf_ocr | 152.9 | — |
| 25 | Warburtons Limited | 00178711 | Y | Y | Y | N | pdf_ocr | 136.7 | — |
| 26 | Cosmetic Warriors Limited | 04165681 | Y | Y | Y | Y | pdf_ocr | 120.9 | — |
| 27 | Featurespace Limited | 05640420 | Y | Y | N | Y | pdf_ocr | 108.0 | — |
| 28 | Synthesia Limited | 10933652 | Y | Y | N | N | pdf_ocr | 137.1 | — |
| 29 | Graphcore Limited | 10185006 | Y | Y | Y | Y | partial,pdf_ocr | 164.1 | — |

## Notable failures / gaps

- **Virgin Media Limited** (`02591237`): missing IS, BS, CF [statuses=partial]
- **Heathrow Airport Limited** (`01991017`): missing BS, CF [statuses=partial,pdf_ocr]
- **Willmott Dixon Holdings Limited** (`00198032`): missing IS, CF [statuses=pdf_ocr]
- **2 Sisters Food Group Limited** (`02826929`): missing BS, CF [statuses=pdf_ocr]
- **Featurespace Limited** (`05640420`): missing BS [statuses=pdf_ocr]
- **Synthesia Limited** (`10933652`): missing BS, CF [statuses=pdf_ocr]
