"""
Local CLI: git pull -> show new leads -> mark reviewed -> git push.

Run this from the repo root: python cli/review.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import db


def run_git(args, check=True):
    result = subprocess.run(["git"] + args, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  [git error] {result.stderr.strip()}")
    return result


def sync_pull():
    print("Pulling latest leads from repo...")
    result = run_git(["pull"], check=False)
    if result.returncode != 0:
        print(f"  Warning: git pull had issues:\n{result.stderr}")
    else:
        print("  Up to date.")


def print_last_run_summary():
    status_file = Path(__file__).resolve().parent.parent / "last_run.txt"
    if status_file.exists():
        print("\nLast pipeline run:")
        print("  " + status_file.read_text().replace("\n", "  |  ").strip(" |"))


def show_leads(leads):
    if not leads:
        print("\nNo new leads. All caught up.")
        return

    print(f"\n{len(leads)} new lead(s):\n" + "=" * 60)
    for lead in leads:
        print(f"[{lead['id']}] {lead.get('property_name') or 'Unnamed property'}")
        print(f"    Location:        {lead.get('location') or '-'}")
        print(f"    Stage:           {lead.get('project_stage') or '-'}")
        print(f"    Interior studio: {lead.get('interior_studio') or '-'}")
        print(f"    Chain/Investor:  {lead.get('investor_chain') or '-'}")
        print(f"    Summary:         {lead.get('summary') or '-'}")
        print(f"    Source:          {lead.get('source_url') or '-'}")
        print(f"    Detected:        {lead.get('detection_date') or '-'}")
        print("-" * 60)


def prompt_mark_reviewed(leads):
    if not leads:
        return
    answer = input(
        "\nMark all of these as 'Reviewed' now? [y/N] (do this once you've noted/exported them): "
    ).strip().lower()
    if answer != "y":
        print("Left as 'New' — they'll show up again next time.")
        return

    conn = db.get_connection()
    db.mark_reviewed(conn, [lead["id"] for lead in leads])
    conn.commit()
    conn.close()
    print("Marked as reviewed.")


def sync_push():
    answer = input("\nPush these status updates back to the repo? [y/N] ").strip().lower()
    if answer != "y":
        print("Skipped push. Remember to push later so your team stays in sync.")
        return

    run_git(["add", "leads.db"])
    result = run_git(["commit", "-m", "Mark leads reviewed via CLI"], check=False)
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        print(f"  [git error] {result.stderr.strip()}")
        return
    run_git(["push"])
    print("Pushed.")


def main():
    sync_pull()
    print_last_run_summary()

    conn = db.get_connection()
    leads = db.get_new_leads(conn)
    conn.close()

    show_leads(leads)
    prompt_mark_reviewed(leads)
    sync_push()


if __name__ == "__main__":
    main()
