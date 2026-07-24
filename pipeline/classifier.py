"""
AI Engine: sends each candidate article to Gemini (free tier) and asks for a
binary classification + structured extraction in one call.

Uses Gemini because it has the most generous free tier for this kind of
low-volume daily batch job (tens of articles/day). Swap MODEL / the API call
below if you'd rather use another provider — the rest of the pipeline only
cares about the dict this module returns.
"""

import os
import json
import time
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-2.0-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

TARGET_COUNTRY = "Spain"

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


def classify_article(article: dict, retries: int = 2) -> dict | None:
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
        try:
            resp = requests.post(
                f"{API_URL}?key={GEMINI_API_KEY}",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)

            if not parsed.get("is_relevant"):
                return None

            parsed["source_url"] = article.get("url")
            return parsed

        except (requests.RequestException, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"  [classifier error] '{article.get('title', '')[:60]}': {e}")
            return None
