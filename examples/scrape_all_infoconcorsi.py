"""
Harvester Multi-Page Crawler: Scrape ALL pagination pages of Infoconcorsi Edises
Target: https://infoconcorsi.edises.it/titolo-di-studio/laurea-magistrale?slqualification=113

Features:
- Dynamic pagination discovery (traverses all pages 1..N until completion)
- Rate limiting (polite 1.2s delay between requests)
- Real-time schema validation with dead-letter quarantine
- Multi-tier Sieve persistence (raw page responses, staged records, curated unified catalog in JSON + CSV)
- Comprehensive statistics & progress tracking
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from bs4 import BeautifulSoup
from harvester import (
    check_robots,
    fetch_with_retry,
    persist_sieve_layout,
    validate_records,
)

BASE_URL = "https://infoconcorsi.edises.it"
START_URL = "https://infoconcorsi.edises.it/titolo-di-studio/laurea-magistrale?slqualification=113"

CONCORSO_SCHEMA = {
    "type": "object",
    "properties": {
        "titolo": {"type": "string", "minLength": 3},
        "ente": {"type": "string", "minLength": 2},
        "posti": {"type": ["integer", "null"]},
        "scadenza": {"type": "string"},
        "url": {"type": "string", "format": "uri"},
        "descrizione": {"type": "string"},
        "pagina_origine": {"type": "integer"},
    },
    "required": ["titolo", "ente", "scadenza", "url"]
}


def extract_concorsi_from_page(html: str, page_num: int, base_url: str = BASE_URL) -> list[dict]:
    """Extract concorsi from table-striped2 or mobile table fallback."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # Strategy 1: Desktop table (.table-striped2)
    table = soup.find("table", class_=lambda c: c and "table-striped2" in c)
    if table:
        rows = table.find_all("tr")
        i = 1 if rows and rows[0].find("th") else 0

        while i < len(rows):
            main_row = rows[i]
            tds = main_row.find_all("td")

            if len(tds) == 4:
                scadenza_text = tds[0].get_text(strip=True)
                titolo_td = tds[1]
                link = titolo_td.find("a")
                titolo = link.get_text(strip=True) if link else titolo_td.get_text(strip=True)
                href = urljoin(base_url, link.get("href")) if link and link.get("href") else ""
                ente = tds[2].get_text(strip=True)
                posti_raw = tds[3].get_text(strip=True)

                try:
                    posti = int(re.sub(r"[^\d]", "", posti_raw)) if posti_raw else None
                except ValueError:
                    posti = None

                # Optional detail row
                descrizione = ""
                if i + 1 < len(rows) and len(rows[i + 1].find_all("td")) == 1:
                    desc_td = rows[i + 1].find("td")
                    desc_clone = BeautifulSoup(str(desc_td), "html.parser")
                    for a in desc_clone.find_all("a"):
                        a.decompose()
                    descrizione = desc_clone.get_text(" ", strip=True)
                    i += 1

                date_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", scadenza_text)
                scadenza_clean = date_match.group(0) if date_match else scadenza_text

                records.append({
                    "titolo": titolo,
                    "ente": ente,
                    "posti": posti,
                    "scadenza": scadenza_clean,
                    "url": href,
                    "descrizione": descrizione,
                    "pagina_origine": page_num,
                })
            i += 1

    return records


def find_max_page_number(html: str) -> int:
    """Identify the total number of pages from the pagination bar."""
    soup = BeautifulSoup(html, "html.parser")
    page_numbers = []
    for a in soup.select(".pagination a, .edises--pagination a"):
        href = a.get("href", "")
        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            page_numbers.append(int(match.group(1)))
        text = a.get_text(strip=True)
        if text.isdigit():
            page_numbers.append(int(text))

    return max(page_numbers) if page_numbers else 1


def crawl_all_pages(output_dir: str = "./data", delay: float = 1.2):
    base_dir = Path(output_dir).resolve()
    for layer in ("raw", "staged", "curated", "quarantine"):
        (base_dir / layer).mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("HARVESTER MULTI-PAGE CRAWLER")
    print(f"Target Base: {START_URL}")
    print("=" * 75)

    # 1. Check robots.txt
    print("\n[Step 1] Checking robots.txt policy...")
    if not check_robots(START_URL):
        print("  Blocked by robots.txt policy. Aborting crawl.")
        return

    print("  Robots.txt: ALLOWED.\n")

    # 2. Fetch page 1 and determine max pages
    print("[Step 2] Discovering pagination boundaries from Page 1...")
    p1_resp = fetch_with_retry(START_URL)
    if p1_resp.get("status") != 200:
        print(f"  Failed to fetch page 1 (Status: {p1_resp.get('status')})")
        return

    max_pages = find_max_page_number(p1_resp["content"])
    print(f"  Detected Total Pages: {max_pages} pages")

    all_valid_records = []
    all_quarantined_records = []
    unique_urls = set()

    # 3. Iterate through all pages
    for page_num in range(1, max_pages + 1):
        page_url = f"{START_URL}&page={page_num}" if page_num > 1 else START_URL

        print(f"\n--- [Page {page_num:02d}/{max_pages:02d}] Fetching {page_url} ---")
        
        # If page 1, we already fetched it
        resp = p1_resp if page_num == 1 else fetch_with_retry(page_url, delay=delay)
        
        if resp.get("status") != 200:
            print(f"  Warning: HTTP {resp.get('status')} on page {page_num}. Skipping.")
            continue

        records = extract_concorsi_from_page(resp["content"], page_num)
        print(f"  Extracted: {len(records)} concorsi")

        valid, quarantined = validate_records(records, CONCORSO_SCHEMA)
        
        # Deduplicate on URL
        new_valid = 0
        for r in valid:
            if r["url"] not in unique_urls:
                unique_urls.add(r["url"])
                all_valid_records.append(r)
                new_valid += 1

        all_quarantined_records.extend(quarantined)

        print(f"  Valid: {len(valid)} ({new_valid} new unique) | Quarantined: {len(quarantined)}")

        # Save raw page response to Sieve raw/
        persist_sieve_layout(str(base_dir), page_url, resp, valid, quarantined)

        # Politeness delay
        if page_num < max_pages:
            time.sleep(delay)

    # 4. Save Curated Unified Dataset (Sieve curated layer)
    print("\n" + "=" * 75)
    print(f"[Step 3] Generating Curated Unified Catalog ({len(all_valid_records)} concorsi)...")
    print("=" * 75)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    
    # 4a. Curated JSON
    curated_json_path = base_dir / "curated" / f"concorsi_laurea_magistrale_{timestamp}.json"
    latest_json_path = base_dir / "curated" / "concorsi_laurea_magistrale_latest.json"
    
    catalog_payload = {
        "source": START_URL,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "total_pages_scraped": max_pages,
        "total_records": len(all_valid_records),
        "total_quarantined": len(all_quarantined_records),
        "concorsi": all_valid_records,
    }
    
    curated_json_path.write_text(json.dumps(catalog_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    latest_json_path.write_text(json.dumps(catalog_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved Curated JSON: {curated_json_path}")

    # 4b. Curated CSV
    curated_csv_path = base_dir / "curated" / f"concorsi_laurea_magistrale_{timestamp}.csv"
    latest_csv_path = base_dir / "curated" / "concorsi_laurea_magistrale_latest.csv"

    if all_valid_records:
        fieldnames = ["titolo", "ente", "posti", "scadenza", "url", "descrizione", "pagina_origine"]
        with open(curated_csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_valid_records)
        with open(latest_csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_valid_records)
        print(f"  Saved Curated CSV:  {curated_csv_path}")

    print("\n" + "=" * 75)
    print("CRAWL COMPLETE SUMMARY")
    print(f"  Total Pages Crawled:       {max_pages}")
    print(f"  Total Unique Concorsi:     {len(all_valid_records)}")
    print(f"  Total Quarantined Records: {len(all_quarantined_records)}")
    print("=" * 75)

    return catalog_payload


if __name__ == "__main__":
    out_path = str(Path(__file__).parent.parent / "data")
    crawl_all_pages(output_dir=out_path, delay=1.2)
