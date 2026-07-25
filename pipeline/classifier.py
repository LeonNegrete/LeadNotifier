"""
AI Engine: sends each candidate article to Gemini (free tier) and asks for a
binary classification + structured extraction in one call.

Model note (updated 2026-07-25): pinned to gemini-3.5-flash-lite. Google has
shipped several Gemini generations in quick succession recently, and at least
one prior pin (gemini-2.5-flash) started 404ing before its officially
announced shutdown date. Flash-Lite tiers also tend to get more generous
RPM/RPD than full Flash, which helps here. If this model starts 404ing too,
check https://ai.google.dev/gemini-api/docs/models for the current GA Flash
or Flash-Lite model ID and swap MODEL below — that's the fix, not the pacing.
"""

import os
import json
import time
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-3.5-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

TARGET_COUNTRY = "Spain"


class RateLimitedError(Exception):
    """Raised when Gemini returns 429 after retries are exhausted."""
    pass


class ModelNotFoundError(Exception):
    """Raised when the model ID itself is invalid/retired (404). Retrying won't help."""
    pass


# Exact free-tier RPM isn't published without an AI Studio login (see
# https://aistudio.google.com/rate-limit for your project's live numbers) —
# this pacing is a conservative default, not a documented guarantee.
MIN_SECONDS_BETWEEN_CALLS = 6.5
MAX_BACKOFF_SECONDS = 20
_last_call_at = 0.0

PROMPT_TEMPLATE = """You are a lead-qualification filter for a hospitality interior design sales team.

Read the article below (title + summary). Decide if it describes a REAL, SPECIFIC
renovation, construction, fit-out, or interior design project for a hotel, resort,
or other hospitality property located in {country}.

Do NOT count: general industry trend pieces, opinion columns, financial/earnings
news with no physical renovation mentioned, or articles about a single property
that is just opening/operating with no renovation or design work mentioned.

Respond with ONLY a JSON object (no markdown fences, no preamble), matching this
exact shape:

{{
  "is_relevant": true or false,
  "property_name": "string or null",
  "location": "string or null (city/province/region)",
  "project_stage": "one of: Permit Granted, Under Renovation, Pre-opening, Planned, Unknown",
  "interior_studio": "string or null (design/architecture firm, if named)",
  "investor_chain": "string or null (hotel group / ownership, if named)",
  "summary": "one sentence in English summarizing the project"
}}

If is_relevant is false, all other fields should be null.

Article title: {title}
Article summary: {summary}
"""


def _wait_for_rate_limit():
    """Enforce a minimum gap between calls so we don't blow through the free-tier RPM cap."""
    global _last_call_at
    elapsed = time.monotonic() - _last_call_at
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_at = time.monotonic()


def classify_article(article: dict, retries: int = 1) -> dict | None:
    """Returns an extraction dict if relevant, or None if not relevant / failed."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")

    prompt = PROMPT_TEMPLATE.format(
        country=TARGET_COUNTRY,
        title=article.get("title", ""),
        summary=article.get("summary", ""),
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    }

    for attempt in range(retries + 1):
        _wait_for_rate_limit()
        try:
            resp = requests.post(
                f"{API_URL}?key={GEMINI_API_KEY}",
                json=payload,
                timeout=30,
            )

            if resp.status_code == 404:
                # Model ID itself is wrong/retired — no amount of retrying fixes this.
                # Fail immediately rather than burning the retry budget on it.
                raise ModelNotFoundError(
                    f"Model '{MODEL}' returned 404 — it's likely been retired. "
                    "Check https://ai.google.dev/gemini-api/docs/models for the "
                    "current model ID and update MODEL in classifier.py."
                )

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait_s = min(float(retry_after), MAX_BACKOFF_SECONDS) if retry_after else MAX_BACKOFF_SECONDS
                if attempt < retries:
                    print(f"  [rate limited] waiting {wait_s:.0f}s before retry...")
                    time.sleep(wait_s)
                    continue
                print(f"  [classifier error] '{article.get('title', '')[:60]}': rate limited (429)")
                raise RateLimitedError()

            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)

            if not parsed.get("is_relevant"):
                return None

            parsed["source_url"] = article.get("url")
            return parsed

        except (RateLimitedError, ModelNotFoundError):
            raise
        except (requests.RequestException, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  [classifier error] '{article.get('title', '')[:60]}': {e}")
            return None
