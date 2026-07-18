'''
Downloads the full global list of OpenAQ station locations for a given
parameter (e.g. PM2.5 or O3), paging through /v3/locations until all
results are collected, and saves them into one combined JSON file in
the same shape as a single-page response (so it works with the same
loading pattern used for india_stations.json).
 
To switch between PM2.5 and O3, edit PARAMETER_ID and OUTPUT_FILE below
and run the script again.
'''
 
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dotenv import load_dotenv
import os
 
API_BASE = "https://api.openaq.org/v3"
 
# 2 = pm25, 10 = o3
PARAMETER_ID = 10
OUTPUT_FILE = "data/global_o3_stations.json"
 
PAGE_LIMIT = 1000
SECONDS_BETWEEN_REQUESTS = 1.1
 
 
def fetch_page(parameter_id, api_key, page):
    params = urllib.parse.urlencode({
        "parameters_id": parameter_id,
        "limit": PAGE_LIMIT,
        "page": page,
    })
    url = f"{API_BASE}/locations?{params}"
    req = urllib.request.Request(url, headers = {"X-API-Key": api_key})
 
    try:
        with urllib.request.urlopen(req, timeout = 30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("Rate limited - waiting 60s before retrying...")
            time.sleep(60)
            with urllib.request.urlopen(req, timeout = 30) as resp:
                return json.load(resp)
        raise
 
 
def main():
    load_dotenv()
    
    api_key = os.getenv("OPENAQ_API_KEY")
 
    print(f"Fetching all global locations for parameter_id = {PARAMETER_ID}...")
 
    all_results = []
    page = 1
 
    while True:
        data = fetch_page(PARAMETER_ID, api_key, page)
        results = data.get("results", [])
        all_results.extend(results)
 
        print(f"page {page}: got {len(results)} locations")
 
        if len(results) < PAGE_LIMIT:
            break  # last page reached
 
        page += 1
        time.sleep(SECONDS_BETWEEN_REQUESTS)
 
    output = {
        "meta": {
            "name": "openaq-api",
            "found": len(all_results),
        },
        "results": all_results,
    }
 
    with open(OUTPUT_FILE, "w", encoding = "utf-8") as f:
        json.dump(output, f, ensure_ascii = False)
 
if __name__ == "__main__":
    main()