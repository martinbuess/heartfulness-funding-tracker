"""Collector for City of Cleveland bids (public web pages, no login).

Two pages: invitations to bid, and requests for qualifications or proposals.
Each listing is a collapsible block whose text gives the division (e.g. Division
of Water) and the deadline: "opened at Noon on" for large bids, "Closing Date"
for small bids and RFPs. The RFP page keeps old, closed listings, so a listing
with no date it can read is left out.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

BASE = "https://www.clevelandohio.gov/city-hall/departments/finance/"
PAGES = {
    "invitations-bid": "Contract (bid)",
    "request-qualificationsproposal": "Contract (RFP)",
}

_ITEM = re.compile(r'(?s)<span class="ms-2 h3">(.*?)</span>.*?<div id="(collapse_\d+)".*?<div class="accordion-body">(.*?)</div>')
_DIVISION = re.compile(r"FOR THE (DIVISION OF [A-Z ,&'-]+?|DEPARTMENT OF [A-Z ,&'-]+?)(?: FOR THE| AS |,|\.)", re.IGNORECASE)
_DEPT = re.compile(r"(?:Dept/Div|Department):\s*(.+?)\s+(?:Contact|Requestor)", re.IGNORECASE)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = rf"(?:[A-Za-z]+day,?\s+)?({_MONTHS})\s+(\d{{1,2}}),?\s*(\d{{4}})"
# Tried in order, so a "Question Submission Deadline" never wins over the real one.
_DUE = [re.compile(label + r"[^:]{0,20}:\s*" + _DATE, re.IGNORECASE)
        for label in (r"Closing Date", r"opened at Noon on", r"due date")]
# City Hall and the utilities building are on Lakeside Avenue; left in, every
# listing would match the keyword "lake".
_ADDRESS = re.compile(r"\b\d+\s+Lakeside\s+Ave(?:nue)?\b\.?(?:\s+E\b\.?)?", re.IGNORECASE)
_NUMBER = re.compile(r"^(\d+(?:-\d+)?)\s+-\s+(.+)$")


def due_date(text):
    for pattern in _DUE:
        found = pattern.search(text)
        if found:
            month, day, year = found.groups()
            try:
                return datetime.datetime.strptime(f"{month.title()} {day} {year}", "%B %d %Y").date().isoformat()
            except ValueError:
                return ""
    return ""


def _division(text):
    found = _DIVISION.search(text)
    if found:
        name = found.group(1)
    else:
        found = _DEPT.search(text)
        if not found:
            return ""
        name = found.group(1).strip(" .")
        if name.isupper():  # "Department: PUBLIC UTILITIES"
            return "Department of " + name.title().replace(" And ", " and ")
        return name
    return name.title().replace(" Of ", " of ").replace(" And ", " and ")


def parse(page):
    items = []
    for title, anchor, body in _ITEM.findall(page):
        text = _ADDRESS.sub("", html.unescape(clean(body)))
        title = html.unescape(clean(title))
        numbered = _NUMBER.match(title)
        items.append({
            "number": numbered.group(1) if numbered else "",
            "title": numbered.group(2).strip() if numbered else title.strip(),
            "anchor": anchor,
            "division": _division(text),
            "due": due_date(text),
            "text": text,
        })
    return items


def normalize(item, page_name, listing_type):
    rfi = "request for information" in item["title"].lower()
    funder = "City of Cleveland" + (f" {item['division']}" if item["division"] else "")
    return {
        "source": "cleveland",
        "source_id": item["number"] or item["anchor"],
        "title": item["title"],
        "funder": funder,
        "funder_code": "CLE",
        "listing_type": "Contract (request for information)" if rfi else listing_type,
        "status": "posted",
        "post_date": "",
        "close_date": item["due"],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": item["division"],
        "location": "Cleveland, OH",
        "link": f"{BASE}{page_name}#{item['anchor']}",
        "summary": item["text"][:600],
    }


def collect(today, pages=None):
    """Return open City of Cleveland bids and RFPs in the common format.

    Pass pages (page name -> HTML) to skip the download, e.g. in tests.
    """
    rows = []
    for page_name, listing_type in PAGES.items():
        if pages is not None:
            page = pages.get(page_name, "")
        else:
            page = fetch(BASE + page_name, timeout=120).decode("utf-8", errors="replace")
        for item in parse(page):
            row = normalize(item, page_name, listing_type)
            if row["close_date"] and row["close_date"] >= today.isoformat():
                rows.append(row)
    return rows
