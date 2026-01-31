from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import feedparser
from parser import fetch_and_parse_filing 

app = FastAPI()

# UPDATED CORS SECTION
origins = [
    "http://localhost:3000",
    "*", # WARNING: This allows ALL connections. Good for MVP, bad for production.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- YOUR API KEY ---
API_KEY = "3909a176-a4c8-41e5-b05b-203f15401a66"
BASE_URL = "https://api.company-information.service.gov.uk"

@app.get("/api/search")
def search(q: str):
    # Search for companies by name
    response = requests.get(
        f"{BASE_URL}/search/companies", 
        params={"q": q, "items_per_page": 5}, 
        auth=(API_KEY, '')
    )
    return response.json()

@app.get("/api/company/{company_id}/financials")
def get_real_financials(company_id: str):
    # Get the list of filings
    filing_url = f"{BASE_URL}/company/{company_id}/filing-history"
    response = requests.get(filing_url, params={"category": "accounts", "items_per_page": 5}, auth=(API_KEY, ''))

    if response.status_code != 200:
        return {"years": []}

    items = response.json().get('items', [])
    years_data = []

    # Process the top 3 filings
    for item in items[:3]:
        if 'links' not in item or 'document_metadata' not in item['links']:
            continue

        doc_meta_url = item['links']['document_metadata']
        filing_date = item.get('date')

        # Use our parser to get real numbers
        print(f"Analyzing filing from {filing_date}...")
        parsed_data = fetch_and_parse_filing(doc_meta_url, API_KEY)

        human_url = f"https://beta.companieshouse.gov.uk{item['links']['self']}/document"

        # Build the data object
        rev = parsed_data.get('revenue') if parsed_data else None
        profit = parsed_data.get('op_profit') if parsed_data else None
        assets = parsed_data.get('net_assets') if parsed_data else None
        cash = parsed_data.get('cash') if parsed_data else None
        status = parsed_data.get('parsing_status') if parsed_data else "error"

        years_data.append({
            "period": filing_date[:4],
            "source_doc": human_url,
            "parsing_status": status,
            "income_statement": {
                "Revenue": {"value": rev, "source": human_url},
                "Operating Profit": {"value": profit, "source": human_url},
            },
            "balance_sheet": {
                "Net Assets": {"value": assets, "source": human_url},
                "Cash": {"value": cash, "source": human_url},
            }
        })

    return {"years": years_data, "company_id": company_id}

# CHANGE 1: Update the route to remove {name} from the path
@app.get("/api/news")  
def get_news(name: str): # CHANGE 2: 'name' is now a query parameter
    try:
        # Keep the logic safe
        if not name:
            return {"news": []}
            
        clean_name = name.replace("LIMITED", "").replace("LTD", "").strip()
        # Use simple string formatting for the Google News URL
        rss = f"https://news.google.com/rss/search?q={clean_name}+valuation+OR+funding&hl=en-GB&gl=GB"
        
        feed = feedparser.parse(rss)
        items = []
        for x in feed.entries[:5]:
            items.append({
                "title": x.title, 
                "link": x.link, 
                "published": x.published
            })
        return {"news": items}
    except Exception as e:
        print(f"News Error: {e}")
        return {"news": []}