from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import feedparser
import re
import urllib.parse  # <--- FIXED: Added to handle spaces in URLs safely
from parser import fetch_and_parse_filing 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# YOUR KEY (Keep this safe!)
API_KEY = "3909a176-a4c8-41e5-b05b-203f15401a66"
BASE_URL = "https://api.company-information.service.gov.uk"

@app.get("/api/search")
def search(q: str):
    response = requests.get(
        f"{BASE_URL}/search/companies", 
        params={"q": q, "items_per_page": 5}, 
        auth=(API_KEY, '')
    )
    if response.status_code == 200:
        return response.json()
    return {"items": []}

@app.get("/api/company/{company_id}/financials")
def get_real_financials(company_id: str):
    print(f"Fetching filings for {company_id}...")
    filing_url = f"{BASE_URL}/company/{company_id}/filing-history"
    response = requests.get(filing_url, params={"category": "accounts", "items_per_page": 5}, auth=(API_KEY, ''))
    
    if response.status_code != 200:
        return {"years": []}
    
    items = response.json().get('items', [])
    years_data = [] 
    
    for item in items[:3]:
        # Skip if no document attached
        if 'links' not in item or 'document_metadata' not in item['links']:
            continue
            
        doc_meta_url = item['links']['document_metadata']
        filing_date = item.get('date')
        
        # Human Link
        try:
            self_link = item['links']['self']
            human_url = f"https://find-and-update.company-information.service.gov.uk{self_link}/document?format=pdf&download=0"
        except:
            human_url = "#"

        # Parse Data
        print(f"Analyzing {filing_date}...")
        parsed_data = fetch_and_parse_filing(doc_meta_url, API_KEY)
        
        if parsed_data is None:
            parsed_data = {}
        
        years_data.append({
            "period": filing_date[:4],
            "parsing_status": parsed_data.get('parsing_status', 'error'),
            "income_statement": {
                "Revenue": {"value": parsed_data.get('is_revenue'), "source": human_url},
                "EBITDA (Est)": {"value": parsed_data.get('is_ebitda'), "source": human_url},
                "EBIT": {"value": parsed_data.get('is_ebit'), "source": human_url},
                "Net Income": {"value": parsed_data.get('is_net_income'), "source": human_url},
            },
            "balance_sheet": {
                "Current Assets": {"value": parsed_data.get('bs_curr_assets'), "source": human_url},
                "Total Assets": {"value": parsed_data.get('bs_total_assets'), "source": human_url},
                "Current Liabilities": {"value": parsed_data.get('bs_curr_liab'), "source": human_url},
                "Total Liabilities": {"value": parsed_data.get('bs_total_liab'), "source": human_url},
            },
            "cash_flow": {
                "Operating CF": {"value": parsed_data.get('cf_operations'), "source": human_url},
                "Investing CF": {"value": parsed_data.get('cf_investing'), "source": human_url},
                "Financing CF": {"value": parsed_data.get('cf_financing'), "source": human_url},
            }
        })
        
    return {"years": years_data, "company_id": company_id}

@app.get("/api/news")
def get_news(name: str):
    try:
        if not name: return {"news": []}
        clean_name = name.replace("LIMITED", "").replace("LTD", "").strip()
        
        # --- FIXED: Use urllib to safely encode spaces ---
        encoded_query = urllib.parse.quote(f"{clean_name} valuation OR raised OR funding")
        rss = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-GB&gl=GB"
        
        feed = feedparser.parse(rss)
        items = []
        
        money_pattern = r'([£$€])(\d+(?:\.\d+)?)\s?(k|m|b|million|billion|trillion)?'

        for x in feed.entries[:6]:
            title = x.title
            extracted_val = None
            # --- FIXED: re is now imported ---
            match = re.search(money_pattern, title, re.IGNORECASE)
            
            if match and ("valuation" in title.lower() or "worth" in title.lower()):
                currency = match.group(1)
                amount = float(match.group(2))
                multiplier = match.group(3).lower() if match.group(3) else ""
                
                if 'b' in multiplier: amount *= 1000
                elif 'k' in multiplier: amount /= 1000
                
                extracted_val = {
                    "raw": match.group(0),
                    "amount_m": amount,
                    "currency": currency
                }

            items.append({
                "title": title, 
                "link": x.link, 
                "published": x.published,
                "valuation_data": extracted_val
            })
            
        return {"news": items}
    except Exception as e:
        print(f"News Error: {e}")
        return {"news": []}