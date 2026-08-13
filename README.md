# Harvester

[![CI](https://github.com/G10DC/harvester/actions/workflows/ci.yml/badge.svg)](https://github.com/G10DC/harvester/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)

**Harvester** is a professional, resilient web scraping and structured data extraction engine built for the **G10DC Antigravity AI Skill Ecosystem**.

It combines polite crawling policies (mandatory `robots.txt` enforcement, exponential backoff, rate limiting) with strict **JSON Schema validation**, **SSRF safety guards**, and multi-tier **Sieve data persistence**.

---

## ⚡ Key Features

- 🛡️ **Polite & Compliant**: Enforces `robots.txt` parsing with explicit 10s timeouts; rate-limits consecutive domain requests.
- 🔒 **Zero-Trust Security**: Validates target schemes (`http`/`https` only) to block SSRF, streaming response caps (10MB) to prevent memory exhaustion (DoS).
- 📐 **Schema-First Extraction**: Every scraped record is validated against a strict JSON Schema; malformed records are routed to a `quarantine/` dead-letter store without crashing the crawl.
- 📦 **Sieve 4-Tier Persistence Layout**:
  - `raw/`: Write-once, immutable HTTP response payloads (tagged with SHA-256 content hashes).
  - `staged/`: Schema-validated, typed structured items.
  - `curated/`: Unified, deduplicated catalog outputs in JSON & UTF-8-SIG CSV.
  - `quarantine/`: Isolation log for records failing schema checks.
- 🔁 **Resilient Multi-Page Pagination**: Traverses multi-page listings dynamically with deduplication and state preservation.
- 🧩 **Ecosystem Delegation**: Designed to compose cleanly with sibling skills rather than reinventing functionality.

---

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/G10DC/harvester.git
cd harvester
pip install -r requirements.txt
pip install -e .
```

### CLI Usage

```bash
# Basic single-page scrape
python scripts/harvester.py --url "https://news.ycombinator.com" --selector "span.titleline > a" --output ./data

# With custom schema validation and rate limiting
python scripts/harvester.py --url "https://example.com/items" --selector "div.card" --schema schema.json --delay 2.0
```

---

## 📂 Ready-to-Run Examples

| Example Script | Description |
|---|---|
| [`scripts/scrape_doveconviene.py`](scripts/scrape_doveconviene.py) | **DoveConviene Harvester Pro**: Dynamic flyer discovery across Italian supermarket chains/cities, LD+JSON/window.DCFlyer extraction, Sieve JSON/CSV/SQLite persistence, price comparison & interactive search CLI. |
| [`examples/scrape_doveconviene_quickstart.py`](examples/scrape_doveconviene_quickstart.py) | Quickstart guide demonstrating DoveConviene crawler, SQLite queries, and price comparison matrix. |
| [`examples/scrape_all_infoconcorsi.py`](examples/scrape_all_infoconcorsi.py) | **Full multi-page crawler**: traverses all pagination pages with Sieve curated JSON & CSV export. |
| [`examples/scrape_hackernews.py`](examples/scrape_hackernews.py) | Scrapes frontpage Hacker News titles with schema validation. |
| [`examples/scrape_infoconcorsi.py`](examples/scrape_infoconcorsi.py) | Single-page extraction of public competition notices from *Infoconcorsi Edises*. |

### 🛒 DoveConviene Harvester Pro Usage

```bash
# 1. Harvest active supermarket and discount flyers (Lidl, Conad, Eurospin, Coop, Unieuro...)
python scripts/scrape_doveconviene.py harvest --categories iper-e-super discount --limit 10

# 2. Search for offers across all scraped flyers
python scripts/scrape_doveconviene.py search "nutella"
python scripts/scrape_doveconviene.py search "birra" --max-price 2.00

# 3. Compare prices across supermarkets (finds lowest, average, and highest prices)
python scripts/scrape_doveconviene.py compare "caffè"

# 4. Launch the Interactive Terminal Search CLI
python scripts/scrape_doveconviene.py interactive
```

---

## 🧪 Testing & Verification

The test suite runs 100% offline and deterministic using Python's native `unittest` and `pytest`:

```bash
python -m unittest discover -s tests -v
```

```text
Ran 17 tests in 0.030s — 100% OK (All Passed)
├── TestSecurityAndURLValidation (SSRF & schema guards)
├── TestRobotsCompliance (Allow, Deny, Timeout, Invalid URLs)
├── TestFetchWithRetry (200 OK, 429 backoff, max size cap)
├── TestExtractRecords (Field map, text stripping)
├── TestValidation (Schema partitioning & quarantine)
├── TestPersistSieveLayout (raw/staged/quarantine directory hierarchy)
└── TestRunHarvestEndToEnd (Pipeline orchestration)
```

---

## 🌐 Ecosystem Integration

| Concern | Delegated Skill | Architecture Rule |
|---|---|---|
| Multi-tier data persistence | `sieve` | `raw/` → `staged/` → `curated/` separation |
| Untrusted data isolation & prompt guard | `warden` | `separateInstructionData` before LLM processing |
| OCR from scanned/image pages | `scribe` | Preprocessed lossy-channel OCR pipeline |
| Sandbox outbound network firewall | `sentinel` | Domain allowlisting & secret leak filtering |
| Test & mutation verification | `forge` | Synthetic test generation & mutation coverage |
| Delta diffs & change alerting | `beacon` | Natural-language digest of data modifications |
| Code minimalism & standard library reuse | `bonsai` | Stdlib-first, Pathlib native platform features |
| Tamper-evident audit logging | `keel` | Cryptographic hash-chained audit trails |

---

## 📄 License

[MIT License](LICENSE) © 2026 G10DC
