"""Demo-mode fixtures for UK private companies when no Companies House API key is set."""

from __future__ import annotations

from schema import financials_response, line, year_block

# Fictionalised but realistic multi-year statements inspired by well-known UK privates.
DEMO_COMPANIES = [
    {
        "company_number": "08489098",
        "title": "GYMSHARK GROUP LIMITED",
        "company_status": "active",
        "company_type": "ltd",
        "date_of_creation": "2013-04-15",
        "address_snippet": "1 Fox Way, Shirebrook, Mansfield, NG20 8RX",
        "description": "08489098 - Incorporated on 15 April 2013",
        "sic_codes": ["47710", "47910"],
        "registered_office": {
            "address_line_1": "1 Fox Way",
            "locality": "Shirebrook",
            "postal_code": "NG20 8RX",
            "country": "England",
        },
        "officers_summary": [{"name": "CHAUDHARY, Hussain", "role": "director"}],
    },
    {
        "company_number": "09465813",
        "title": "MONZO BANK LIMITED",
        "company_status": "active",
        "company_type": "ltd",
        "date_of_creation": "2015-03-02",
        "address_snippet": "Broadwalk House, 5 Appold Street, London, EC2A 2AG",
        "description": "09465813 - Incorporated on 2 March 2015",
        "sic_codes": ["64191"],
        "registered_office": {
            "address_line_1": "Broadwalk House",
            "address_line_2": "5 Appold Street",
            "locality": "London",
            "postal_code": "EC2A 2AG",
            "country": "England",
        },
        "officers_summary": [{"name": "DEMO DIRECTOR", "role": "director"}],
    },
    {
        "company_number": "03977902",
        "title": "REVOLUT LTD",
        "company_status": "active",
        "company_type": "ltd",
        "date_of_creation": "2000-04-06",
        "address_snippet": "7 Westferry Circus, Canary Wharf, London, E14 4HD",
        "description": "03977902 - Incorporated on 6 April 2000",
        "sic_codes": ["62090", "64999"],
        "registered_office": {
            "address_line_1": "7 Westferry Circus",
            "locality": "London",
            "postal_code": "E14 4HD",
            "country": "England",
        },
        "officers_summary": [{"name": "DEMO DIRECTOR", "role": "director"}],
    },
    {
        "company_number": "08180741",
        "title": "DELIVEROO PLC",
        "company_status": "active",
        "company_type": "plc",
        "date_of_creation": "2012-08-15",
        "address_snippet": "The River Building, 1 Cousin Lane, London, EC4R 3TE",
        "description": "08180741 - Incorporated on 15 August 2012",
        "sic_codes": ["63120", "82990"],
        "registered_office": {
            "address_line_1": "The River Building",
            "address_line_2": "1 Cousin Lane",
            "locality": "London",
            "postal_code": "EC4R 3TE",
            "country": "England",
        },
        "officers_summary": [{"name": "DEMO DIRECTOR", "role": "director"}],
    },
    {
        "company_number": "07432262",
        "title": "BREWDOG PLC",
        "company_status": "active",
        "company_type": "plc",
        "date_of_creation": "2010-11-08",
        "address_snippet": "Balmacassie Commercial Park, Ellon, Aberdeenshire, AB41 8BX",
        "description": "07432262 - Incorporated on 8 November 2010",
        "sic_codes": ["11050", "56302"],
        "registered_office": {
            "address_line_1": "Balmacassie Commercial Park",
            "locality": "Ellon",
            "postal_code": "AB41 8BX",
            "country": "Scotland",
        },
        "officers_summary": [{"name": "DEMO DIRECTOR", "role": "director"}],
    },
]


def _y(
    period: str,
    filing_date: str,
    revenue,
    cogs,
    gross,
    op,
    ebit,
    ebitda,
    pbt,
    ni,
    ca,
    nca,
    ta,
    cl,
    ncl,
    tl,
    equity,
    na,
    ocf,
    icf,
    fcf,
    ncc,
):
    return year_block(
        period=period,
        filing_date=filing_date,
        parsing_status="fixture",
        income={
            "Revenue": line(revenue),
            "Cost of Sales": line(cogs),
            "Gross Profit": line(gross),
            "Operating Profit": line(op),
            "EBIT": line(ebit),
            "EBITDA (Est)": line(ebitda),
            "Profit Before Tax": line(pbt),
            "Net Income": line(ni),
        },
        balance={
            "Current Assets": line(ca),
            "Non-Current Assets": line(nca),
            "Total Assets": line(ta),
            "Current Liabilities": line(cl),
            "Non-Current Liabilities": line(ncl),
            "Total Liabilities": line(tl),
            "Equity": line(equity),
            "Net Assets": line(na),
        },
        cash_flow={
            "Operating CF": line(ocf),
            "Investing CF": line(icf),
            "Financing CF": line(fcf),
            "Net Change in Cash": line(ncc),
        },
    )


DEMO_FINANCIALS: dict[str, dict] = {
    # Gymshark-like consumer brand (£)
    "08489098": financials_response(
        "08489098",
        [
            _y(
                "2024", "2024-09-30",
                520_000_000, -208_000_000, 312_000_000,
                78_000_000, 78_000_000, 95_000_000, 72_000_000, 55_000_000,
                180_000_000, 95_000_000, 275_000_000,
                95_000_000, 40_000_000, 135_000_000, 140_000_000, 140_000_000,
                68_000_000, -22_000_000, -15_000_000, 31_000_000,
            ),
            _y(
                "2023", "2023-09-30",
                445_000_000, -187_000_000, 258_000_000,
                62_000_000, 62_000_000, 78_000_000, 55_000_000, 42_000_000,
                155_000_000, 82_000_000, 237_000_000,
                88_000_000, 35_000_000, 123_000_000, 114_000_000, 114_000_000,
                55_000_000, -18_000_000, -10_000_000, 27_000_000,
            ),
            _y(
                "2022", "2022-09-30",
                380_000_000, -171_000_000, 209_000_000,
                48_000_000, 48_000_000, 62_000_000, 41_000_000, 31_000_000,
                132_000_000, 70_000_000, 202_000_000,
                78_000_000, 28_000_000, 106_000_000, 96_000_000, 96_000_000,
                42_000_000, -15_000_000, -8_000_000, 19_000_000,
            ),
        ],
    ),
    # Monzo-like neobank (illustrative)
    "09465813": financials_response(
        "09465813",
        [
            _y(
                "2024", "2024-02-29",
                890_000_000, None, None,
                45_000_000, 45_000_000, 120_000_000, 38_000_000, 28_000_000,
                4_200_000_000, 180_000_000, 4_380_000_000,
                3_900_000_000, 120_000_000, 4_020_000_000, 360_000_000, 360_000_000,
                95_000_000, -40_000_000, 80_000_000, 135_000_000,
            ),
            _y(
                "2023", "2023-02-28",
                712_000_000, None, None,
                -12_000_000, -12_000_000, 55_000_000, -18_000_000, -22_000_000,
                3_500_000_000, 150_000_000, 3_650_000_000,
                3_300_000_000, 100_000_000, 3_400_000_000, 250_000_000, 250_000_000,
                40_000_000, -35_000_000, 120_000_000, 125_000_000,
            ),
            _y(
                "2022", "2022-02-28",
                480_000_000, None, None,
                -85_000_000, -85_000_000, -20_000_000, -92_000_000, -95_000_000,
                2_800_000_000, 120_000_000, 2_920_000_000,
                2_700_000_000, 80_000_000, 2_780_000_000, 140_000_000, 140_000_000,
                -30_000_000, -25_000_000, 200_000_000, 145_000_000,
            ),
        ],
    ),
    "03977902": financials_response(
        "03977902",
        [
            _y(
                "2024", "2024-12-31",
                2_200_000_000, None, None,
                480_000_000, 480_000_000, 620_000_000, 450_000_000, 380_000_000,
                18_000_000_000, 900_000_000, 18_900_000_000,
                16_500_000_000, 800_000_000, 17_300_000_000, 1_600_000_000, 1_600_000_000,
                520_000_000, -180_000_000, 250_000_000, 590_000_000,
            ),
            _y(
                "2023", "2023-12-31",
                1_650_000_000, None, None,
                210_000_000, 210_000_000, 340_000_000, 180_000_000, 140_000_000,
                14_000_000_000, 700_000_000, 14_700_000_000,
                13_200_000_000, 600_000_000, 13_800_000_000, 900_000_000, 900_000_000,
                280_000_000, -150_000_000, 400_000_000, 530_000_000,
            ),
            _y(
                "2022", "2022-12-31",
                1_100_000_000, None, None,
                -50_000_000, -50_000_000, 80_000_000, -70_000_000, -90_000_000,
                10_500_000_000, 500_000_000, 11_000_000_000,
                10_000_000_000, 450_000_000, 10_450_000_000, 550_000_000, 550_000_000,
                100_000_000, -120_000_000, 350_000_000, 330_000_000,
            ),
        ],
    ),
    "08180741": financials_response(
        "08180741",
        [
            _y(
                "2024", "2024-12-31",
                2_030_000_000, -1_420_000_000, 610_000_000,
                -45_000_000, -45_000_000, 95_000_000, -60_000_000, -55_000_000,
                620_000_000, 480_000_000, 1_100_000_000,
                550_000_000, 200_000_000, 750_000_000, 350_000_000, 350_000_000,
                80_000_000, -90_000_000, 20_000_000, 10_000_000,
            ),
            _y(
                "2023", "2023-12-31",
                2_030_000_000, -1_450_000_000, 580_000_000,
                -120_000_000, -120_000_000, 40_000_000, -140_000_000, -130_000_000,
                580_000_000, 520_000_000, 1_100_000_000,
                520_000_000, 230_000_000, 750_000_000, 350_000_000, 350_000_000,
                20_000_000, -70_000_000, 50_000_000, 0,
            ),
            _y(
                "2022", "2022-12-31",
                1_980_000_000, -1_480_000_000, 500_000_000,
                -280_000_000, -280_000_000, -100_000_000, -300_000_000, -290_000_000,
                650_000_000, 550_000_000, 1_200_000_000,
                500_000_000, 280_000_000, 780_000_000, 420_000_000, 420_000_000,
                -50_000_000, -80_000_000, 100_000_000, -30_000_000,
            ),
        ],
    ),
    "07432262": financials_response(
        "07432262",
        [
            _y(
                "2024", "2024-12-31",
                340_000_000, -170_000_000, 170_000_000,
                -15_000_000, -15_000_000, 25_000_000, -28_000_000, -30_000_000,
                95_000_000, 220_000_000, 315_000_000,
                110_000_000, 180_000_000, 290_000_000, 25_000_000, 25_000_000,
                18_000_000, -22_000_000, 5_000_000, 1_000_000,
            ),
            _y(
                "2023", "2023-12-31",
                315_000_000, -165_000_000, 150_000_000,
                -35_000_000, -35_000_000, 8_000_000, -48_000_000, -50_000_000,
                88_000_000, 230_000_000, 318_000_000,
                100_000_000, 190_000_000, 290_000_000, 28_000_000, 28_000_000,
                5_000_000, -25_000_000, 15_000_000, -5_000_000,
            ),
            _y(
                "2022", "2022-12-31",
                290_000_000, -160_000_000, 130_000_000,
                -55_000_000, -55_000_000, -10_000_000, -70_000_000, -72_000_000,
                80_000_000, 240_000_000, 320_000_000,
                95_000_000, 200_000_000, 295_000_000, 25_000_000, 25_000_000,
                -10_000_000, -30_000_000, 40_000_000, 0,
            ),
        ],
    ),
}


def search_demo(q: str) -> dict:
    q_lower = (q or "").strip().lower()
    items = []
    for c in DEMO_COMPANIES:
        hay = f"{c['title']} {c['company_number']} {c.get('address_snippet', '')}".lower()
        if not q_lower or q_lower in hay or any(tok in hay for tok in q_lower.split()):
            items.append(
                {
                    "company_number": c["company_number"],
                    "title": c["title"],
                    "company_status": c["company_status"],
                    "company_type": c["company_type"],
                    "date_of_creation": c["date_of_creation"],
                    "address_snippet": c["address_snippet"],
                    "description": c["description"],
                }
            )
    return {"items": items, "demo": True}


def get_demo_profile(company_number: str) -> dict | None:
    for c in DEMO_COMPANIES:
        if c["company_number"] == company_number:
            return {
                "company_number": c["company_number"],
                "company_name": c["title"],
                "title": c["title"],
                "company_status": c["company_status"],
                "company_type": c["company_type"],
                "date_of_creation": c["date_of_creation"],
                "registered_office": c["registered_office"],
                "address_snippet": c["address_snippet"],
                "sic_codes": c["sic_codes"],
                "officers_summary": c["officers_summary"],
                "demo": True,
            }
    return None


def get_demo_financials(company_number: str) -> dict | None:
    return DEMO_FINANCIALS.get(company_number)
