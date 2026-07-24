"""
Fetcher: pulls RSS feeds listed in feeds.yaml, keeps only articles published
in the last N hours, and returns a flat list of {title, url, summary, source} dicts.

Deliberately does NOT do permit-office scraping (see project notes) — every
municipality in Spain publishes permits differently, and that's a v2+ problem,
not a v1 one. This only handles RSS, which is uniform and reliable to parse.
"""

import yaml
import feedparser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import mktime

FEEDS_PATH = Path(__file__).resolve().parent.parent / "feeds.yaml"
LOOKBACK_HOURS = 30  # slightly over 24h as a buffer against skipped/late runs


def load_feeds():
    with open(FEEDS_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("feeds", [])


def _entry_datetime(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return datetime.fromtimestamp(mktime(val), tz=timezone.utc)
    return None


def fetch_recent_articles(lookback_hours: int = LOOKBACK_HOURS):
    feeds = load_feeds()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    articles = []
    errors = []

    for feed in feeds:
        url = feed["url"]
        try:
            parsed = feedparser.parse(url)
            if parsed.bozo and not parsed.entries:
                errors.append(f"{feed['name']}: failed to parse ({parsed.bozo_exception})")
                continue

            for entry in parsed.entries:
                pub_date = _entry_datetime(entry)
                # If a feed doesn't expose a date, include it anyway rather than
                # silently dropping it — better a false positive than a missed lead.
                if pub_date is not None and pub_date < cutoff:
                    continue

                articles.append(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", ""),
                        "source": feed["name"],
                        "published": pub_date.isoformat() if pub_date else None,
                    }
                )
        except Exception as e:
            errors.append(f"{feed['name']}: {e}")

    return articles, errors
