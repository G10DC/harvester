# Harvester

Professional web scraping and structured data extraction engine for the G10DC Antigravity ecosystem.

## Core Principles

- **Polite**: Respects `robots.txt`, rate-limits every request, identifies itself via User-Agent
- **Validated**: Every extracted record is schema-checked before persistence — unvalidated data goes to quarantine
- **Idempotent**: Same URL + same content = same output, no duplicates on re-run
- **Provenance-tagged**: Every record carries source URL, fetch timestamp, HTTP status, content hash
- **Composable**: Delegates persistence to `sieve`, trust boundaries to `warden`, OCR to `scribe`, egress to `sentinel`

## Quick Start

```bash
pip install requests beautifulsoup4 jsonschema
python scripts/harvester.py --url "https://example.com" --selector "div.item" --output ./data
```

## Ecosystem Integration

| Concern | Delegated To |
|---|---|
| Data persistence layout | `sieve` |
| Trust boundary for LLM processing | `warden` |
| OCR from images/PDFs | `scribe` |
| Egress domain filtering | `sentinel` |
| Test generation | `forge` |
| Change reports | `beacon` |
| Code minimalism | `bonsai` |
| Audit trail | `keel` |

## License

MIT
