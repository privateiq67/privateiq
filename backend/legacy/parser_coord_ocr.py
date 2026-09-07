import requests
import fitz  # PyMuPDF
import re
import os
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import shutil

# --- SMART TESSERACT CONFIGURATION ---
# 1. Try to find Tesseract in the System Path (Works on Cloud/Linux)
tesseract_cmd = shutil.which("tesseract")

# 2. If not found, check the manual Windows path (Works on your PC)
if not tesseract_cmd:
    possible_windows_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(possible_windows_path):
        tesseract_cmd = possible_windows_path

# 3. Apply the configuration
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    print(f"   [Config] Tesseract found at: {tesseract_cmd}")
else:
    print("   [WARNING] Tesseract not found! OCR will fail.")

def fetch_and_parse_filing(document_metadata_url, api_key):
    try:
        # 1. DOWNLOAD
        print(f"   [1] Fetching Metadata...")
        meta_res = requests.get(document_metadata_url, auth=(api_key, ''))
        if meta_res.status_code != 200: return {"parsing_status": "metadata_failed"}
        
        resources = meta_res.json().get('resources', {})
        content_url = None
        if 'application/xhtml+xml' in resources: content_url = resources['application/xhtml+xml'].get('content_url')
        if not content_url: content_url = f"{document_metadata_url}/content"
        
        doc_res = requests.get(content_url, auth=(api_key, ''), headers={"Accept": "application/pdf"})
        if doc_res.status_code != 200: return {"parsing_status": "download_failed"}

        print("   [2] Starting Universal Coordinate Analysis...")
        
        extracted_data = {}

        with fitz.open(stream=doc_res.content, filetype="pdf") as doc:
            # Scan up to 60 pages
            for page_idx, page in enumerate(doc):
                if page_idx > 60: break

                # --- STEP A: GET WORDS WITH COORDINATES (HYBRID) ---
                # We normalize everything to: (x0, y0, text)
                # x0 is percentage of page width (0.0 to 1.0)
                
                page_words = [] # List of {'text': str, 'x': float, 'y': float}
                
                # 1. Try Digital Extraction
                words_raw = page.get_text("words")
                width = page.rect.width
                height = page.rect.height

                if len(words_raw) > 10:
                    # Digital PDF
                    for w in words_raw:
                        page_words.append({
                            'text': w[4],
                            'x': w[0] / width, # Normalize 0-1
                            'y': w[1]
                        })
                else:
                    # 2. Image/Scan Fallback (Critical for Cloud/Scans)
                    # We use image_to_data to get coordinates from pixels
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    try:
                        ocr_data = pytesseract.image_to_data(img, output_type=Output.DICT)
                        n_boxes = len(ocr_data['text'])
                        img_width, img_height = img.size
                        
                        for i in range(n_boxes):
                            txt = ocr_data['text'][i].strip()
                            if len(txt) > 0:
                                page_words.append({
                                    'text': txt,
                                    'x': ocr_data['left'][i] / img_width, # Normalize 0-1
                                    'y': ocr_data['top'][i] # Pixel Y is fine for sorting
                                })
                    except: continue

                if not page_words: continue

                # --- STEP B: CHECK FOR TARGET PAGE ---
                full_text = " ".join([w['text'] for w in page_words]).lower()
                is_pnl = "comprehensive income" in full_text or "profit and loss" in full_text
                is_bs = "balance sheet" in full_text or "financial position" in full_text
                
                if not (is_pnl or is_bs): continue

                print(f"   [TARGET] Financials on Page {page_idx+1}")

                # --- STEP C: DETECT SCALE ---
                scale = 1
                if "millions" in full_text or "£m" in full_text: scale = 1000000
                elif "thousands" in full_text or "£'000" in full_text or "£000" in full_text: scale = 1000
                print(f"      [Scale] x{scale}")

                # --- STEP D: CLUSTER INTO ROWS ---
                # Sort by Y position
                page_words.sort(key=lambda w: w['y'])
                
                rows = []
                if page_words:
                    current_row = [page_words[0]]
                    for w in page_words[1:]:
                        # If within 15px vertical tolerance
                        if abs(w['y'] - current_row[-1]['y']) < 15: 
                            current_row.append(w)
                        else:
                            rows.append(current_row)
                            current_row = [w]
                    rows.append(current_row)

                # --- STEP E: ANALYZE ROWS ---
                for row in rows:
                    # Sort left-to-right
                    row.sort(key=lambda w: w['x'])
                    
                    row_text = " ".join([w['text'] for w in row]).lower()
                    
                    # EXTRACT NUMBERS FROM THE RIGHT SIDE (> 50% Width)
                    candidates = []
                    for w in row:
                        # FILTER: Right side only (X > 0.5)
                        # This kills the "Note" column which is usually at 0.1 - 0.4
                        if w['x'] < 0.5: continue
                        
                        matches = re.findall(r'(\(?-?[\d,]+\.?\d*\)?)', w['text'])
                        for m in matches:
                            clean = m.replace(',', '').replace('(', '-').replace(')', '')
                            try:
                                val = float(clean)
                                # Filter Years/Notes
                                if abs(val) < 50: continue
                                if 2018 < val < 2030: continue
                                candidates.append({'val': val, 'x': w['x']})
                            except: continue

                    if not candidates: continue
                    
                    # Sort candidates left-to-right
                    candidates.sort(key=lambda c: c['x'])
                    best_val = candidates[0]['val'] * scale

                    # MAPPING
                    if ("turnover" in row_text or "revenue" in row_text) and "is_revenue" not in extracted_data:
                        extracted_data["is_revenue"] = best_val

                    if "operating" in row_text and ("profit" in row_text or "loss" in row_text) and "is_ebit" not in extracted_data:
                        extracted_data["is_ebit"] = best_val

                    if "profit" in row_text and ("financial year" in row_text or "for the year" in row_text) and "before" not in row_text:
                        if "is_net_income" not in extracted_data:
                            extracted_data["is_net_income"] = best_val
                    
                    # Balance Sheet Matches
                    if "net assets" in row_text and "current" not in row_text:
                        extracted_data["bs_total_assets"] = best_val
                        
                    if "creditors" in row_text and "within one year" in row_text:
                         extracted_data["bs_curr_liab"] = abs(best_val)

                    if "creditors" in row_text and "more than one year" in row_text:
                         extracted_data["bs_total_liab"] = abs(best_val)
                    
                    if "current assets" in row_text and "less" not in row_text and "net" not in row_text:
                        if "bs_curr_assets" not in extracted_data:
                             extracted_data["bs_curr_assets"] = best_val

            return {
                "parsing_status": "success",
                "is_revenue": extracted_data.get("is_revenue"),
                "is_ebit": extracted_data.get("is_ebit"),
                "is_net_income": extracted_data.get("is_net_income"),
                "bs_total_assets": extracted_data.get("bs_total_assets"),
                "bs_curr_assets": extracted_data.get("bs_curr_assets"),
                "bs_curr_liab": extracted_data.get("bs_curr_liab"),
                "bs_total_liab": extracted_data.get("bs_total_liab"),
                "cf_operations": None, "cf_investing": None, "cf_financing": None
            }

    except Exception as e:
        print(f"   [CRITICAL PARSER ERROR] {e}")
        return None