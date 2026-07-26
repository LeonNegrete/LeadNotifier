# Hotel Interior Design Lead Scraper

Daily-running scraper that reads Spanish hospitality/design trade press RSS
feeds, uses Gemini to classify+extract renovation/fit-out leads for hotels
**and cruise ships**, stores them in a SQLite file versioned in this repo,
sends you a **daily email digest**, and gives you a local CLI to review
leads in more detail (`git pull` model).

## How it works

1. **GitHub Actions** runs `pipeline/main.py` every morning (cron in
   `.github/workflows/daily-scrape.yml`).
2. It fetches feeds listed in `feeds.yaml`, sends each recent article to
   Gemini for classification, and inserts anything relevant into `leads.db`.
3. If `leads.db` or `last_run.txt` changed, the Action commits and pushes
   them back to this repo.
4. It sends you an email — either listing the new leads found, or a plain
   "nothing today" heartbeat so you know the pipeline actually ran.
5. You run `python cli/review.py` locally whenever you want to check leads —
   it pulls the latest DB, shows you everything with `lead_status = 'New'`,
   and lets you mark items reviewed and push that status back.

## One-time setup

1. **Create a GitHub repo** and push this project to it.
2. **Get a free Gemini API key**: https://aistudio.google.com/apikey — and
   bookmark https://aistudio.google.com/rate-limit, which shows your
   project's actual live rate limits (not published in general docs).
3. **Add it as a repo secret**: repo → Settings → Secrets and variables →
   Actions → New repository secret → name it `GEMINI_API_KEY`.
4. **Set up the daily email** (uses Gmail — free, no new service to sign
   up for):
   - You need 2-Step Verification turned on for the Google account you
     want to send from: https://myaccount.google.com/security
   - Generate an App Password: https://myaccount.google.com/apppasswords
     → create one for "Mail" → copy the 16-character password it gives you
     (this is NOT your regular Gmail password — don't use that one, it
     won't work with SMTP).
   - Add two more repo secrets: `GMAIL_ADDRESS` (the Gmail address you're
     sending from) and `GMAIL_APP_PASSWORD` (the 16-character password from
     the step above).
   - By default the digest emails that same address (i.e. you email
     yourself). To send somewhere else instead, add an optional
     `NOTIFY_EMAIL` secret with the destination address.
5. **Enable Actions** if it's not already (Settings → Actions → General →
   allow all actions).
6. Locally: `pip install -r requirements.txt`
7. Clone the repo locally (this is where you'll run the CLI from).

## Running it

- **Manual test run of the pipeline** (instead of waiting for the daily
  cron): go to the Actions tab → "Daily Lead Scrape" → "Run workflow".
- **Review leads locally**:
  ```
  cd hotel-lead-scraper
  python cli/review.py
  ```

## `feeds.yaml`

Currently 9 feeds: Hosteltur's renovation/interiorismo/openings tags (highest
signal), a hotel real-estate investment outlet (Brains RE — covers
conversions and acquisitions, an even earlier signal than "reforma" news),
and cruise trade press. A few are marked `verified: false` — I confirmed the
underlying content is on-target but couldn't execute a live HTTP request to
verify the exact feed URL resolves; the first real run will surface any that
404 or fail to parse (they just get skipped and logged, they won't break the
run). Worth periodically revisiting the notes at the bottom of the file for
design/architecture press that's identified but not yet added.

## Deliberately out of scope

- **Building permits.** Spain doesn't have a unified national permit feed —
  it's per-municipality, mostly not machine-readable. Not worth the
  engineering time until the RSS-based version is proven out. If you want
  it later, treat it as "pick 3-5 target cities and write one scraper per
  city hall."
- **Contact enrichment.** This tool only tells you *which property* to look
  at and *why* — finding the actual decision-maker's phone number is a
  separate downstream step, intentionally not built here.

## Email digest

`pipeline/notifier.py` sends one email per run — a list of new leads if any
were found, otherwise a short "ran fine, nothing new" message. It never
raises an exception on failure (a broken email shouldn't cost you the day's
scraped data or fail the whole Action) — it just logs the error and the run
continues normally. If you'd rather only get emailed when there's actually
something new (skip the "nothing today" heartbeat), that's a one-line change
in `notifier.send_daily_email` — return early if `not new_leads`.

## A known risk with Gemini specifically

Google has been retiring/replacing Gemini model IDs quickly and sometimes
without much warning (we hit this directly: `gemini-2.5-flash` started
404ing before its officially announced shutdown date — turned out its free
quota had been quietly cut to 20 requests/day, which we'd already blown
through during testing). `pipeline/classifier.py` is currently pinned to
`gemini-3.5-flash-lite`. If the pipeline ever starts failing with 404s
again, that's what's happening — check
https://ai.google.dev/gemini-api/docs/models for the current model ID and
update `MODEL` in `classifier.py`. It'll fail fast and print a clear message
telling you this exact thing when it happens, rather than silently retrying.

**Confirmed live limits as of 2026-07-26** (from
https://aistudio.google.com/rate-limit — this is account-specific and can
change without notice, so re-check there if things start failing again):
`gemini-3.5-flash-lite` gets **15 RPM / 500 RPD** on the free tier. At the
current pacing (`MIN_SECONDS_BETWEEN_CALLS = 6.5`, ~9.2 requests/minute)
and realistic daily volume (~40-80 articles/day across the 9 feeds in
`feeds.yaml`), there's comfortable headroom on both — capacity shouldn't be
the recurring problem going forward, only future model/quota churn might be.

If this becomes a recurring headache anyway, switching providers (e.g.
Groq, which has much more stable model naming) is a legitimate option —
`classifier.py` is the only file that would need to change.

## Database schema

See `pipeline/db.py` for the full schema. Main table is `leads`, with a
`run_log` table tracking each day's scan (article count, leads found) —
that's what powers `last_run.txt`. There's a `property_type` column
(Hotel / Resort / Cruise Ship / Other) so you can tell at a glance what
kind of lead you're looking at in the CLI. `init_db()` migrates existing
databases automatically (adds the column if it's missing) — you don't need
to do anything by hand when pulling this update.

## Notes on scale

SQLite-in-Git works fine at this volume (single writer, low frequency). If
this ever exceeds ~100k rows, or you add a second person writing to the DB
concurrently, that's the point to migrate to a real Postgres instance — the
schema translates directly, only the connection in `pipeline/db.py` changes.
Not a v1 concern.
