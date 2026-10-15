"""Collector for MMSD (Milwaukee Metropolitan Sewerage District) procurement
opportunities. Public listing page, no login. It lists the District's own bids
and the RFPs it also posts on Bonfire; construction bids live on QuestCDN and
are not covered.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

LIST_URL = "https://mmsd.diversitycompliance.com/FrontEnd/proposalsearchpublic.asp?tn=mmsd&xid=8146"
DETAIL_URL = "https://mmsd.diversitycompliance.com/FrontEnd/ProposalSearchPublicDetail.asp?XID=8518&TN=mmsd&PID={id}"

_TILE = re.compile(
    r"(?s)<a class='RecordTile' href=\"javascript: ViewDetail\('(\w+)'\)\">.*?"
    r"<div class='Label'>Due</div>(.*?)</div>.*?<div class='Status'[^>]*>(.*?)</div>(.*?)</div>")
# Statuses of listings still taking bids; closed ones say Closed or Awarded.
OPEN_STATUSES = {"open", "due soon"}


def _date(text):
    """'10/8/2026 2:00 pm US/Central' -> '2026-10-08'."""
    try:
        return datetime.datetime.strptime(text.split()[0], "%m/%d/%Y").date().isoformat()
    except (ValueError, IndexError):
        return ""


def parse(page):
    rows = []
    for rid, due, status, name in _TILE.findall(page):
        name = html.unescape(clean(name))
        number, _, title = name.partition(" - ")
        if not title:
            number, title = "", name
        rows.append({"id": rid, "due": _date(clean(due)), "status": clean(status).lower(),
                     "number": number.strip(), "title": title.strip()})
    return rows


def normalize(row):
    rfi = "request for information" in row["title"].lower()
    return {
        "source": "mmsd",
        "source_id": row["number"] or row["id"],
        "title": row["title"],
        "funder": "Milwaukee Metropolitan Sewerage District",
        "funder_code": "MMSD",
        "listing_type": "Contract (request for information)" if rfi else "Contract",
        "status": "posted",
        "post_date": "",
        "close_date": row["due"],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": "",
        "location": "Milwaukee area, WI",
        "link": DETAIL_URL.format(id=row["id"]),
        "summary": f"Reference {row['number']}" if row["number"] else "",
    }


def collect(today, page=None):
    """Return open MMSD listings in the common format.

    Pass page (the listing HTML) to skip the download, e.g. in tests.
    """
    if page is None:
        # The page is Windows-1252 (en dashes in titles).
        page = fetch(LIST_URL, timeout=120).decode("cp1252", errors="replace")
    return [normalize(r) for r in parse(page)
            if r["status"] in OPEN_STATUSES and r["due"] >= today.isoformat()]
