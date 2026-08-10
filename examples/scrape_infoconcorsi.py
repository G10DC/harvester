"""
Harvester Live Test: Scrape Infoconcorsi Edises (Concorsi per Laurea Magistrale)
Target: https://infoconcorsi.edises.it/titolo-di-studio/laurea-magistrale?slqualification=113

Demonstrates:
1. robots.txt compliance
2. Rate-limited & timeout-protected fetch
3. Table parsing & normalization
4. JSON Schema validation
5. Sieve raw/staged persistence
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from bs4 import BeautifulSoup
from harvester import check_robots, fetch_with_retry, persist_sieve_layout, validate_records

TARGET_URL = "https://infoconcorsi.edises.it/titolo-di-studio/laurea-magistrale?slqualification=113"

# JSON Schema for Concorso record
CONCORSO_SCHEMA = {
    "type": "object",
    "properties": {
        "titolo": {"type": "string", "minLength": 3},
        "ente": {"type": "string", "minLength": 2},
        "posti": {"type": ["integer", "null"]},
        "scadenza": {"type": "string", "pattern": r"^\d{2}/\d{2}/\d{4}$"},
        "url": {"type": "string", "format": "uri"},
        "descrizione": {"type": "string"},
    },
    "required": ["titolo", "ente", "scadenza", "url"]
}


def extract_concorsi(html: str, base_url: str = TARGET_URL) -> list[dict]:
    """Parse Infoconcorsi desktop table (table-striped2)."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # Find the main desktop table
    table = soup.find("table", class_=lambda c: c and "table-striped2" in c)
    if not table:
        return []

    rows = table.find_all("tr")
    i = 0
    # Skip header row if present
    if rows and rows[0].find("th"):
        i = 1

    while i < len(rows):
        main_row = rows[i]
        tds = main_row.find_all("td")

        # Standard concorso row has 4 columns: [Scadenza, Titolo, Ente, Posti]
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

            # Look ahead to next row for detailed description if present
            descrizione = ""
            if i + 1 < len(rows) and len(rows[i + 1].find_all("td")) == 1:
                desc_td = rows[i + 1].find("td")
                # Remove "vedi tutto" link text from description
                desc_clone = BeautifulSoup(str(desc_td), "html.parser")
                for a in desc_clone.find_all("a"):
                    a.decompose()
                descrizione = desc_clone.get_text(" ", strip=True)
                i += 1  # consumed detail row

            # Clean deadline date (extract DD/MM/YYYY)
            date_match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", scadenza_text)
            scadenza_clean = date_match.group(0) if date_match else scadenza_text

            records.append({
                "titolo": titolo,
                "ente": ente,
                "posti": posti,
                "scadenza": scadenza_clean,
                "url": href,
                "descrizione": descrizione,
            })

        i += 1

    return records


def run_infoconcorsi_harvest(output_dir: str = "./data"):
    print("=" * 70)
    print(f"HARVESTER LIVE RUN — {TARGET_URL}")
    print("=" * 70)

    # 1. Robots compliance
    print("\n[1/4] Verifying robots.txt policy...")
    if not check_robots(TARGET_URL):
        print("  Blocked by robots.txt. Aborting.")
        return

    print("  Robots.txt: ALLOWED.")

    # 2. Fetch with exponential backoff & size guard
    print("\n[2/4] Fetching page content with rate limiting...")
    response = fetch_with_retry(TARGET_URL, max_retries=3, delay=1.0)
    if response.get("status") != 200:
        print(f"  Fetch failed: HTTP {response.get('status')} - {response.get('error')}")
        return

    print(f"  Fetch success: HTTP 200 ({len(response['content'])} bytes, SHA-256: {response['content_hash'][:16]}...)")

    # 3. Extract & Validate records
    print("\n[3/4] Extracting structured concorsi and validating schema...")
    records = extract_concorsi(response["content"])
    print(f"  Extracted {len(records)} concorsi from table.")

    valid, quarantined = validate_records(records, CONCORSO_SCHEMA)
    print(f"  Schema validation: {len(valid)} VALID, {len(quarantined)} QUARANTINED.")

    # 4. Sieve persistence (raw / staged / quarantine)
    print(f"\n[4/4] Persisting data via Sieve multi-tier layout to '{output_dir}'...")
    result = persist_sieve_layout(output_dir, TARGET_URL, response, valid, quarantined)

    print(f"  Sieve Raw File:    {result['raw']}")
    print(f"  Sieve Staged Items: {result['staged_records']}")
    print(f"  Sieve Quarantined:  {result['quarantined_records']}")

    print("\n" + "=" * 70)
    print("SAMPLE EXTRACTED CONCORSI:")
    print("=" * 70)
    for idx, r in enumerate(valid[:5], 1):
        print(f"\n{idx:02d}. {r['titolo']}")
        print(f"    Ente:        {r['ente']}")
        print(f"    Posti:       {r['posti'] if r['posti'] is not None else 'N/D'}")
        print(f"    Scadenza:    {r['scadenza']}")
        print(f"    URL Bando:   {r['url']}")
        if r['descrizione']:
            print(f"    Descrizione: {r['descrizione'][:120]}...")

    return {
        "url": TARGET_URL,
        "valid_count": len(valid),
        "quarantined_count": len(quarantined),
        "raw_file": result["raw"]
    }


if __name__ == "__main__":
    out = str(Path(__file__).parent.parent / "data")
    run_infoconcorsi_harvest(output_dir=out)
