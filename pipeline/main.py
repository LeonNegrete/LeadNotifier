"""
Orchestrator: fetch -> classify -> dedupe+store -> log.
This is the entrypoint the GitHub Action runs daily.
"""

import sys
from pipeline import db, fetcher, classifier, notifier


def run():
    db.init_db()
    conn = db.get_connection()

    print("Fetching articles from feeds...")
    articles, fetch_errors = fetcher.fetch_recent_articles()
    print(f"  {len(articles)} candidate articles found.")
    for err in fetch_errors:
        print(f"  [feed error] {err}")

    new_leads_this_run = []
    consecutive_rate_limits = 0
    RATE_LIMIT_ABORT_THRESHOLD = 3  # 3 in a row means this is a quota problem, not noise

    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] Classifying: {article['title'][:70]}")
        try:
            result = classifier.classify_article(article)
            consecutive_rate_limits = 0
        except classifier.ModelNotFoundError as e:
            print(f"\n[config error] {e}\nStopping here — this won't fix itself by retrying.")
            break
        except classifier.RateLimitedError:
            consecutive_rate_limits += 1
            if consecutive_rate_limits >= RATE_LIMIT_ABORT_THRESHOLD:
                print(
                    f"\n{RATE_LIMIT_ABORT_THRESHOLD} rate-limit failures in a row — "
                    "this looks like a quota problem (daily cap, not per-minute), "
                    "so stopping here instead of grinding through the rest of the "
                    f"{len(articles) - i} remaining articles. What was found so far is still saved."
                )
                break
            continue

        if result is None:
            continue

        inserted = db.insert_lead(conn, result)
        if inserted:
            new_leads_this_run.append(result)
            print(f"  -> NEW LEAD: {result.get('property_name')} ({result.get('location')})")

    new_lead_count = len(new_leads_this_run)

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

    notifier.send_daily_email(new_leads_this_run, len(articles), fetch_errors)

    return new_lead_count


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"FATAL: {e}")
        sys.exit(1)
