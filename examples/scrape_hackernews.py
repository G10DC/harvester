"""
Example: Scrape Hacker News front page titles and links.

Usage:
    python examples/scrape_hackernews.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from harvester import run_harvest

# Schema: each record must have a title (string) and optionally a link
SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "tag":  {"type": "string"},
    },
    "required": ["text"]
}

if __name__ == "__main__":
    result = run_harvest(
        url="https://news.ycombinator.com",
        selector="span.titleline > a",
        schema=SCHEMA,
        output_dir="./data",
        delay=2.0,
    )
    print(f"\nHarvested {result.get('records_valid', 0)} Hacker News titles.")
