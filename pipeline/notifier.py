"""
Daily email notifier — sends a summary of the day's run (new leads found,
or a plain "nothing today" heartbeat) via Gmail SMTP.

Uses Gmail because it's genuinely free (well under the 500 emails/day
sending limit for a regular Gmail account at this volume of 1/day) and
needs no third-party signup, domain verification, or extra API key — just
an "App Password" on the Google account you likely already have from the
Gemini API key setup. See README for how to generate one.
"""

import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
# Defaults to emailing yourself; set NOTIFY_EMAIL as a separate secret if you
# ever want the digest to go somewhere else (e.g. a shared team inbox).
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL") or GMAIL_ADDRESS


def _format_lead(lead: dict) -> str:
    type_tag = f" ({lead['property_type']})" if lead.get("property_type") else ""
    lines = [
        f"• {lead.get('property_name') or 'Unnamed property'}{type_tag}",
        f"    Location:  {lead.get('location') or '-'}",
        f"    Stage:     {lead.get('project_stage') or '-'}",
        f"    Studio:    {lead.get('interior_studio') or '-'}",
        f"    Chain:     {lead.get('investor_chain') or '-'}",
        f"    Summary:   {lead.get('summary') or '-'}",
        f"    Source:    {lead.get('source_url') or '-'}",
    ]
    return "\n".join(lines)


def build_email_body(new_leads: list, articles_scanned: int, feed_errors: list) -> tuple[str, str]:
    """Returns (subject, body)."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if new_leads:
        subject = f"[LeadNotifier] {len(new_leads)} new lead(s) — {date_str}"
        lead_block = "\n\n".join(_format_lead(l) for l in new_leads)
        body = (
            f"{len(new_leads)} new lead(s) found today, out of {articles_scanned} articles scanned.\n\n"
            f"{lead_block}\n\n"
            "Review and mark these in the CLI (python cli/review.py) once you've acted on them."
        )
    else:
        subject = f"[LeadNotifier] No new leads today — {date_str}"
        body = f"Ran fine, scanned {articles_scanned} articles, nothing new matched today. No action needed."

    if feed_errors:
        body += "\n\n---\nFeed errors this run (non-fatal, other feeds still ran):\n" + "\n".join(f"- {e}" for e in feed_errors)

    return subject, body


def send_daily_email(new_leads: list, articles_scanned: int, feed_errors: list) -> bool:
    """Sends the daily digest. Returns True on success, False on failure (never raises —
    a broken email shouldn't fail the whole pipeline run or lose the day's scraped data)."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("  [notifier] GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set — skipping email.")
        return False

    subject, body = build_email_body(new_leads, articles_scanned, feed_errors)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [NOTIFY_EMAIL], msg.as_string())
        print(f"  [notifier] Email sent to {NOTIFY_EMAIL}.")
        return True
    except Exception as e:
        print(f"  [notifier] Failed to send email: {e}")
        return False
