"""Ingest news/documents into the Qdrant stock_news collection.

Usage (from the lm/ directory):
  python scripts/ingest_news.py                # load bundled sample articles
  python scripts/ingest_news.py --file my.json # load your own articles

JSON file format: a list of objects with keys
  ticker (required), title, text (required), source, date
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="JSON file with articles to ingest")
    args = parser.parse_args()

    from app.services.news_ingest import SAMPLES, ingest_articles

    if args.file:
        articles = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        articles = SAMPLES
        print("No --file given, ingesting bundled sample articles.")

    stored = ingest_articles(articles)
    for ticker in stored:
        print(f"  stored [{ticker}]")
    print(f"\nDone: {len(stored)} documents in Qdrant.")


if __name__ == "__main__":
    main()
