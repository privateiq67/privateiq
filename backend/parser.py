import requests
from bs4 import BeautifulSoup
import re

def fetch_and_parse_filing(document_metadata_url, api_key):
    headers = {"Authorization": api_key}
    
    try:
        # 1. Get the download link
        meta_res = requests.get(document_metadata_url, headers=headers)
        if meta_res.status_code != 200: return None
        
        meta_data = meta_res.json()
        resources = meta_data.get('resources', {})
        
        # 2. Find the digital file (xhtml or xml)
        content_url = None
        if 'application/xhtml+xml' in resources:
            content_url = resources['application/xhtml+xml']['content_url']
        elif 'application/xml' in resources:
            content_url = resources['application/xml']['content_url']
        else:
            return {"parsing_status": "pdf_only"}

        # 3. Download the file
        doc_res = requests.get(content_url, headers={"Authorization": api_key})
        if doc_res.status_code != 200: return None
        
        # 4. Parse Tags using BeautifulSoup
        soup = BeautifulSoup(doc_res.content, 'lxml')
        
        def find_val(possible_tags):
            for t in possible_tags:
                # Find tag ending with the name (handles namespaces like uk-gaap: or ifrs:)
                element = soup.find(lambda x: x.name and x.name.endswith(t))
                if element:
                    text = element.text.strip()
                    if not text: continue
                    
                    # Clean the number (remove commas, handle brackets as negative)
                    is_negative = "(" in text or "-" in text
                    clean = re.sub(r'[^\d.]', '', text)
                    try:
                        val = float(clean)
                        return -val if is_negative else val
                    except:
                        continue
            return None

        # --- EXPANDED DICTIONARY ---
        # This checks for UK GAAP and IFRS tag names
        return {
            "parsing_status": "success",
            "revenue": find_val([
                'TurnoverRevenue', 'Turnover', 'Revenue', 'GrossIncome', 'Sales'
            ]),
            "op_profit": find_val([
                'OperatingProfitLoss', 'OperatingProfit', 'ProfitLossFromOperatingActivities', 'ProfitLoss'
            ]),
            "net_assets": find_val([
                'NetAssetsLiabilities', 'NetAssets', 'TotalEquity', 'Equity', 'ShareholderFunds'
            ]),
            "cash": find_val([
                'CashBankOnHand', 'CashAndCashEquivalents', 'Cash', 'Bank'
            ])
        }

    except Exception as e:
        print(f"Parser Error: {e}")
        return None