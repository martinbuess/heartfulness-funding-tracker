"""The hand-kept calendar of yearly programs (accelerators, prizes, grants).

These programs open once or twice a year on pages with no feed, so people keep
their dates in a "Calendar" tab of the Google Sheet instead of scraping them.
Each run reads that tab, keeps a copy in data/calendar.csv (so the history is
in the repo, and the run still works if the sheet can't be reached), and turns
rows that are open or coming up into listings.
"""

import csv
import datetime
import io
import os
import re

from tracker.text import fetch

MIRROR_PATH = "data/calendar.csv"
COLUMNS = ["program", "run_by", "kind", "opens", "closes", "rolling", "amount", "who_can_apply",
           "location", "usual_window", "link", "about", "last_checked", "notes"]
# A row nobody has checked for this long is flagged on the sheet's About tab.
STALE_DAYS = 90


def parse(text):
    """Calendar rows from CSV text, with tidy keys; blank rows dropped."""
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [(f or "").strip().lower().replace(" ", "_") for f in reader.fieldnames or []]
    rows = []
    for row in reader:
        row = {k: (v or "").strip() for k, v in row.items() if k}
        if row.get("program"):
            rows.append(row)
    return rows


def _valid(text):
    """True if the text is a calendar (a missing tab can come back as another tab)."""
    first = text.splitlines()[0].lower() if text.strip() else ""
    return "program" in first and "closes" in first


def read_mirror(path=MIRROR_PATH):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def load(url, path=MIRROR_PATH):
    """Read the sheet tab and refresh the mirror; fall back to the mirror if the sheet fails."""
    if url:
        try:
            text = fetch(url, timeout=60).decode("utf-8-sig")
        except OSError as exc:
            print(f"calendar: sheet not reachable ({exc}); using {path}")
        else:
            if _valid(text):
                rows = parse(text)
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(rows)
                return rows
            print(f"calendar: sheet has no Calendar tab yet; using {path}")
    return read_mirror(path)


def _date(text):
    """Accept 2026-11-13 or 11/13/2026; blank when neither."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _rolling(row):
    return row.get("rolling", "").lower() in ("yes", "y", "true", "x")


def normalize(row, today):
    opens, closes = _date(row.get("opens", "")), _date(row.get("closes", ""))
    # The id keeps the round's year, so editing a date inside a round doesn't make a new listing.
    round_ = (opens or closes)[:4] or "rolling"
    about = " ".join(t for t in (row.get("about", ""), f"Usual window: {row['usual_window']}." if row.get("usual_window") else "",
                                 row.get("notes", "")) if t)
    return {
        "source": "calendar",
        "source_id": f"{_slug(row['program'])}-{round_}",
        "title": row["program"],
        "funder": row.get("run_by", ""),
        "funder_code": "",
        "listing_type": row.get("kind", "") or "Program",
        "status": "forecast" if opens and opens > today.isoformat() else "posted",
        "post_date": opens,
        "close_date": closes,
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": row.get("who_can_apply", ""),
        "topics": "Hand-kept calendar",
        "location": row.get("location", ""),
        "link": row.get("link", ""),
        "summary": " ".join(filter(None, [row.get("amount", "") and f"{row['amount']}.", about]))[:600],
    }


def is_listed(row, today):
    """Open or upcoming rounds go into the pool: rolling programs, and rounds whose
    close date hasn't passed."""
    closes = _date(row.get("closes", ""))
    return _rolling(row) or (closes and closes >= today.isoformat())


def checks(today, rows):
    """(program, what to do) for rows that need a person to look at them."""
    out = []
    stale = (today - datetime.timedelta(days=STALE_DAYS)).isoformat()
    for row in rows:
        if not is_listed(row, today):
            closes = _date(row.get("closes", ""))
            out.append((row["program"], "Round closed; add next round's dates" if closes else "Add this round's dates"))
        elif (_date(row.get("last_checked", "")) or "") < stale:
            out.append((row["program"], f"Not checked in {STALE_DAYS} days; confirm the dates"))
    return out


def collect(today, url="", rows=None, path=MIRROR_PATH):
    """Return the calendar's open and upcoming rounds in the common format.

    Pass rows (parsed calendar rows) to skip reading the sheet, e.g. in tests.
    """
    if rows is None:
        rows = load(url, path)
    return [normalize(r, today) for r in rows if is_listed(r, today)]
