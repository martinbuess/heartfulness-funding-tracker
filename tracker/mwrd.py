"""Collector for MWRD (Metropolitan Water Reclamation District of Greater Chicago)
contract announcements. Public web page, no login; new bids post on Wednesdays.
"""

import datetime
import html
import re

from tracker.text import clean, dollars, fetch

BASE_URL = "https://apps.mwrd.org/ContractAnnouncements/"
DETAIL_URL = BASE_URL + "BidDetails.aspx?contractID={id}"

_ROW = re.compile(r"(?s)<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>(.*?)</tr>")
_ID = re.compile(r"BidDetails\.aspx\?contractID=(\d+)")


def _date(text):
    """'9/16/2026 12:00:00 AM' -> '2026-09-16'."""
    try:
        return datetime.datetime.strptime(text.split()[0], "%m/%d/%Y").date().isoformat()
    except (ValueError, IndexError):
        return ""


def parse_list(page):
    """Rows of the announcements table as dicts."""
    table = page[page.find('id="GridView1"'):]
    rows = []
    for number, title, posted, opening, rest in _ROW.findall(table):
        found = _ID.search(rest)
        if not found:
            continue
        rows.append({
            "id": found.group(1),
            "number": html.unescape(clean(number)),
            "title": html.unescape(clean(title)),
            "posted": _date(clean(posted)),
            "opening": _date(clean(opening)),
        })
    return rows


def parse_detail(page):
    """Label -> value pairs from a contract's General Information page."""
    text = html.unescape(clean(re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", page)))
    labels = ["Contract Number", "Contract Description", "Estimated Cost", "Bid Deposit",
              "Pre-Bid Walkthrough", "Pre-Bid Technical Conference", "Advertise Date",
              "Bid Opening Date/Time", "Notes", "Number of Addenda"]
    pattern = "(" + "|".join(re.escape(l) for l in labels) + "):"
    parts = re.split(pattern, text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def normalize(row, detail):
    summary = " ".join(f"{k}: {detail[k]}" for k in ("Estimated Cost", "Pre-Bid Technical Conference", "Notes") if detail.get(k))
    return {
        "source": "mwrd",
        "source_id": row["number"],
        "title": row["title"].title(),
        "funder": "Metropolitan Water Reclamation District of Greater Chicago",
        "funder_code": "MWRD",
        "listing_type": "Contract (RFP)" if "RFP" in row["number"] else "Contract (bid)",
        "status": "posted",
        "post_date": row["posted"],
        "close_date": row["opening"],
        "award_floor": "",
        "award_ceiling": dollars(detail.get("Estimated Cost")),
        "total_funding": "",
        # Open to any vendor registered with the District.
        "eligibility": "Any vendor",
        "topics": "",
        "location": "Chicago area, IL",
        "link": DETAIL_URL.format(id=row["id"]),
        "summary": summary[:600],
    }


def collect(today, page=None, details=None):
    """Return open MWRD bids in the common format.

    Pass page (the announcements HTML) and details (contractID -> detail HTML)
    to skip the download, e.g. in tests.
    """
    if page is None:
        page = fetch(BASE_URL, timeout=120).decode("utf-8", errors="replace")
    rows = [r for r in parse_list(page) if r["opening"] >= today.isoformat()]
    out = []
    for row in rows:
        if details is not None:
            detail_page = details.get(row["id"], "")
        else:
            try:
                detail_page = fetch(DETAIL_URL.format(id=row["id"]), timeout=60).decode("utf-8", errors="replace")
            except OSError:
                detail_page = ""  # the list row alone is still useful
        out.append(normalize(row, parse_detail(detail_page)))
    return out
