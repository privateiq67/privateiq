from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from parser import fetch_and_parse_filing
import os
import requests

app = FastAPI()

# --- FIX: ALLOW FRONTEND TO TALK TO BACKEND ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows ALL domains (easiest for testing)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],
)

API_KEY = os.getenv("COMPANIES_HOUSE_KEY")
BASE_URL = "https://api.company-information.service.gov.uk"

@app.get("/api/search")
def search_companies(q: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API Key not configured")
    
    auth = (API_KEY, '')
    response = requests.get(f"{BASE_URL}/search/companies?q={q}", auth=auth)
    
    if response.status_code != 200:
        return {"items": []}
        
    return response.json()

@app.get("/api/company/{company_number}/financials")
def get_financials(company_number: str):
    # 1. Get Filing History
    filing_url = f"{BASE_URL}/company/{company_number}/filing-history?category=accounts"
    auth = (API_KEY, '')
    
    hist_res = requests.get(filing_url, auth=auth)
    if hist_res.status_code != 200:
        raise HTTPException(status_code=404, detail="Company not found")
        
    items = hist_res.json().get('items', [])
    if not items:
        return {"message": "No accounts found"}

    # 2. Analyze the last 3 years
    results = {}
    years_found = 0
    
    for filing in items:
        if years_found >= 3: break
        
        # We need the 'links' -> 'document_metadata' to get the PDF
        if 'links' in filing and 'document_metadata' in filing['links']:
            meta_url = filing['links']['document_metadata']
            date_label = filing.get('date', 'Unknown')
            
            print(f"Analyzing filing from {date_label}...")
            
            # CALL YOUR PARSER
            data = fetch_and_parse_filing(meta_url, API_KEY)
            
            if data:
                # Use year as key (e.g., "2024")
                # For now, we just use the filing date as the key to keep it simple
                results[date_label] = data
                years_found += 1
                
    return results

@app.get("/api/news")
def get_news(name: str):
    # Placeholder for news logic
    return {"news": []}