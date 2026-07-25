# Hotel Interior Design Lead Scraper

Daily-running scraper that reads Spanish hospitality/design trade press RSS
feeds, uses Gemini to classify+extract renovation/fit-out leads for hotels
**and cruise ships**, stores them in a SQLite file versioned in this repo,
and gives you a local CLI to review them (`git pull` model — no push
notifications in v1, that's planned for v2 as a daily email).

## How it works

1. **GitHub Actions** runs `pipeline/main.py` every morning (cron in
   `.github/workflows/daily-scrape.yml`).
2. It fetches feeds listed in `feeds.yaml`, sends each recent article to
   Gemini for classification, and inserts anything relevant into `leads.db`.
3. If `leads.db` or `last_run.txt` changed, the Action commits and pushes
   them back to this repo.
4. You run `python cli/review.py` locally whenever you want to check leads —
   it pulls the latest DB, shows you everything with `lead_status = 'New'`,
   and lets you mark items reviewed and push that status back.

## One-time setup

1. **Create a GitHub repo** and push this project to it.
2. **Get a free Gemini API key**: https://aistudio.google.com/apikey — and
   bookmark https://aistudio.google.com/rate-limit, which shows your
   project's actual live rate limits (not published in general docs).
3. **Add it as a repo secret**: repo → Settings → Secrets and variables →
   Actions → New repository secret → name it `GEMINI_API_KEY`.
4. **Enable Actions** if it's not already (Settings → Actions → General →
   allow all actions).
5. Locally: `pip install -r requirements.txt`
6. Clone the repo locally (this is where you'll run the CLI from).

## Running it

- **Manual test run of the pipeline** (instead of waiting for the daily
  cron): go to the Actions tab → "Daily Lead Scrape" → "Run workflow".
- **Review leads locally**:
  ```
  cd hotel-lead-scraper
  python cli/review.py
  ```

## Before this is actually useful: fill out `feeds.yaml`

I seeded it with a couple of confirmed-working Hosteltur feeds and a few
educated guesses at standard WordPress `/feed` URLs for other publications —
those are marked `verified: false`. Open each one in a browser first to
confirm it's a real feed before relying on it. The file has notes on good
categories of sources to add (architecture/design press, regional trade
journals) — this list is the single biggest lever on lead quality, so it's
worth 30 minutes of manual curation rather than treating it as done.

## Deliberately out of scope for v1

- **Building permits.** Spain doesn't have a unified national permit feed —
  it's per-municipality, mostly not machine-readable. Not worth the
  engineering time until the RSS-based version is proven out. If you want
  it later, treat it as "pick 3-5 target cities and write one scraper per
  city hall."
- **Push notifications.** v1 is pull-only (`git pull` + CLI). A daily email
  digest is the planned v2 (e.g. via a free transactional email API,
  triggered at the end of the Action if `new_leads > 0`).
- **Contact enrichment.** This tool only tells you *which property* to look
  at and *why* — finding the actual decision-maker's phone number is a
  separate downstream step, intentionally not built here.

## A known risk with Gemini specifically

Google has been retiring/replacing Gemini model IDs quickly and sometimes
without much warning (we hit this directly: `gemini-2.5-flash` started
404ing before its officially announced shutdown date). `pipeline/classifier.py`
is currently pinned to `gemini-3.5-flash-lite`. If the pipeline ever starts
failing with 404s again, that's what's happening — check
https://ai.google.dev/gemini-api/docs/models for the current model ID and
update `MODEL` in `classifier.py`. It'll fail fast and print a clear message
telling you this exact thing when it happens, rather than silently retrying.

If this becomes a recurring headache, switching providers (e.g. Groq, which
has much more stable model naming) is a legitimate option — `classifier.py`
is the only file that would need to change.

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
