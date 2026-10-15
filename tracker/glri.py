"""Collector for the Great Lakes Restoration Initiative's funding page.

The page lists a few open opportunities (title and link only) and a table of
yearly programs with the agency, a description and when each is usually
announced. Only the open list becomes listings; the table fills in the agency
and description for an open program it also names. Links to Grants.gov are
skipped because Grants.gov is already a source.
"""

import html
import re
import urllib.parse

from tracker.text import clean, fetch

PAGE_URL = "https://glri.us/funding/funding-opportunities"

# Funder names for links that the yearly table doesn't describe.
_FUNDERS = {
    "fs.usda.gov": "USDA Forest Service",
    "nfwf.org": "National Fish and Wildlife Foundation",
    "lakeerie.ohio.gov": "Ohio Lake Erie Commission",
    "ohio.gov": "State of Ohio",
    "noaa.gov": "NOAA",
    "fws.gov": "U.S. Fish and Wildlife Service",
    "epa.gov": "U.S. EPA",
    "glc.org": "Great Lakes Commission",
}

_LINK = re.compile(r'(?s)<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>')


def _text(fragment):
    return html.unescape(clean(fragment)).strip()


def _key(title):
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _funder(link):
    host = urllib.parse.urlsplit(link).hostname or ""
    host = host.removeprefix("www.")
    for domain, name in _FUNDERS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host


def parse(page):
    """The open opportunities, each with the yearly table's details when it has a row for it."""
    start = page.find("Open Funding Opportunities")
    if start < 0:
        raise ValueError("GLRI page layout changed: no 'Open Funding Opportunities' heading")
    open_list = page[start:page.find("</ul>", start)]

    programs = {}
    for cells in re.findall(r"(?s)<tr>(.*?)</tr>", page):
        tds = re.findall(r"(?s)<td[^>]*>(.*?)</td>", cells)
        if len(tds) < 4:
            continue
        programs[_key(_text(tds[0]))] = {
            "agency": _text(tds[1]),
            "description": _text(tds[2]),
            "announced": _text(tds[3]),
        }

    items = []
    for link, title in _LINK.findall(open_list):
        link = html.unescape(link)
        if "grants.gov" in link:
            continue
        title = _text(title)
        items.append({"title": title, "link": link, **programs.get(_key(title), {})})
    return items


def normalize(item):
    summary = item.get("description") or "Listed as open on the Great Lakes Restoration Initiative funding page."
    if item.get("announced"):
        summary += f" Usually announced: {item['announced']}."
    return {
        "source": "glri",
        "source_id": item["link"],
        "title": item["title"],
        "funder": item.get("agency") or _funder(item["link"]),
        "funder_code": "GLRI",
        "listing_type": "Grant",
        "status": "posted",
        "post_date": "",
        "close_date": "",  # the page gives no deadlines; see the link
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Others (see listing)",
        "topics": "Great Lakes Restoration Initiative",
        "location": "Great Lakes",
        "link": item["link"],
        "summary": summary[:600],
    }


def collect(today, page=None):
    """Return the GLRI page's open opportunities in the common format.

    Pass the page's HTML to skip the download, e.g. in tests.
    """
    if page is None:
        page = fetch(PAGE_URL, timeout=60).decode("utf-8", errors="replace")
    return [normalize(i) for i in parse(page)]
