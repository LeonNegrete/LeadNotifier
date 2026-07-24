"""
Orchestrator: fetch -> classify -> dedupe+store -> log.
This is the entrypoint the GitHub Action runs daily.
"""

import sys
from pipeline import db, fetcher, classifier


def run():
    db.init_db()
    conn = db.get_connection()

    print("Fetching articles from feeds...")
    articles, fetch_errors = fetcher.fetch_recent_articles()
    print(f"  {len(articles)} candidate articles found.")
    for err in fetch_errors:
        print(f"  [feed error] {err}")

    new_lead_count = 0
    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] Classifying: {article['title'][:70]}")
        result = classifier.classify_article(article)
        if result is None:
            continue

        inserted = db.insert_lead(conn, result)
        if inserted:
            new_lead_count += 1
            print(f"  -> NEW LEAD: {result.get('property_name')} ({result.get('location')})")

    notes = "; ".join(fetch_errors) if fetch_errors else ""
    db.log_run(conn, articles_scanned=len(articles), new_leads=new_lead_count, notes=notes)
    conn.commit()
    conn.close()

    print(f"\nDone. {new_lead_count} new lead(s) out of {len(articles)} articles scanned.")

    # Write a plain-text status file so `git pull` gives an at-a-glance summary
    # without needing to query the DB (see README for why this exists).
    with open("last_run.txt", "w", encoding="utf-8") as f:
        f.write(f"articles_scanned={len(articles)}\n")
        f.write(f"new_leads={new_lead_count}\n")

    return new_lead_count


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"FATAL: {e}")
        sys.exit(1)
