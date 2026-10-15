"""Collector for SBIR.gov's topic search: every agency's open and upcoming
SBIR/STTR research topics (Defense, Energy, NSF, NASA and others).

SBIR.gov's data API refuses automated requests, but its public topic search
page (www.sbir.gov/topics) is plain HTML, ten topics per page. Most Defense
topics reach us only this way. Topics are kept when they match the water
keywords like any other listing.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

BASE = "https://www.sbir.gov"
SEARCH_URL = BASE + "/topics?status=1&page={page}"
# Safety stop: about 350 topics are open or upcoming at a time, ten per page.
MAX_PAGES = 80
AGENCIES = {
    "DOD": "Department of Defense", "DOE": "Department of Energy", "NSF": "National Science Foundation",
    "NASA": "NASA", "HHS": "Department of Health and Human Services", "USDA": "Department of Agriculture",
    "EPA": "Environmental Protection Agency", "DHS": "Department of Homeland Security",
    "DOC": "Department of Commerce", "DOT": "Department of Transportation", "ED": "Department of Education",
}
# Agencies that award SBIR/STTR as grants; the rest (Defense, NASA, EPA, ...) award contracts.
GRANT_AGENCIES = {"NSF", "DOE", "USDA", "HHS"}
_DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def _date(text):
    try:
        return datetime.datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return ""


def parse(page):
    """Topics on one search results page."""
    topics = []
    blocks = re.split(r'<h3 class="margin-top-2[^"]*">', page)[1:]
    for block in blocks:
        link = re.search(r'<a href="(/topics/(\d+))">(.*?)</a>', block, re.S)
        if not link:
            continue
        found = lambda label: re.search(rf"<b>{label}:</b>\s*{_DATE}", block)
        dates = {label: _date(m.group(1)) if (m := found(label)) else ""
                 for label in ("Release Date", "Open Date", "Close Date")}
        badge = re.search(r'<span class="[^"]*radius-sm[^"]*">\s*([^<]+?)\s*</span>', block)
        agency = re.search(r'alt="Seal of the Agency:\s*([A-Z]+)"', block)
        summary = re.search(r'<p class="measure-6">(.*?)</p>', block, re.S)
        tags = re.findall(r'<p class="[^"]*bg-base-dark[^"]*">\s*([^<]+?)\s*</p>', block)
        topics.append({
            "id": link.group(2),
            "link": BASE + link.group(1),
            "title": html.unescape(clean(link.group(3))),
            "badge": badge.group(1) if badge else "",
            "agency": agency.group(1) if agency else "",
            "summary": html.unescape(clean(summary.group(1))) if summary else "",
            "tags": tags,
            **dates,
        })
    return topics


def normalize(topic, today):
    code = topic["agency"]
    not_open_yet = topic["Open Date"] and topic["Open Date"] > today.isoformat()
    programs = [t for t in topic["tags"] if t in ("SBIR", "STTR")]
    return {
        "source": "sbir.gov",
        "source_id": topic["id"],
        "title": topic["title"],
        "funder": AGENCIES.get(code, code),
        "funder_code": code,
        "listing_type": ("Grant" if code in GRANT_AGENCIES else "Contract") + f" ({' / '.join(programs or ['SBIR'])} topic)",
        "status": "forecast" if not_open_yet else "posted",
        "post_date": topic["Release Date"],
        "close_date": topic["Close Date"],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Small businesses",
        "topics": "; ".join(["SBIR/STTR"] + ([f"Opens {topic['Open Date']}"] if not_open_yet else [])),
        "location": "National",
        "link": topic["link"],
        "summary": topic["summary"][:600],
    }


def collect(today, pages=None):
    """Return open and upcoming SBIR/STTR topics in the common format.

    Pass pages (a list of result-page HTML) to skip the download, e.g. in tests.
    """
    if pages is None:
        pages = _download()
    seen, rows = set(), []
    for page in pages:
        for topic in parse(page):
            if topic["id"] in seen:
                continue
            seen.add(topic["id"])
            if topic["Close Date"] and topic["Close Date"] < today.isoformat():
                continue
            rows.append(normalize(topic, today))
    return rows


def _download():
    pages, seen = [], set()
    for number in range(MAX_PAGES):
        page = fetch(SEARCH_URL.format(page=number), timeout=60).decode("utf-8", errors="replace")
        ids = {t["id"] for t in parse(page)}
        if not ids or ids <= seen:
            break  # past the last page
        seen |= ids
        pages.append(page)
    return pages
