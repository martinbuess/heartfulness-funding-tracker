"""Collector for Illinois state grant opportunities (GATA Catalog of State
Financial Assistance, public page, no login).
"""

import datetime
import html
import re
import urllib.parse

from tracker.text import clean, dollars, fetch

LIST_URL = "https://omb.illinois.gov/public/gata/csfa/OpportunityList.aspx"
NOFO_URL = "https://omb.illinois.gov/public/gata/csfa/Opportunity.aspx?nofo={id}"

# Agency codes on the list -> names. Unknown codes are shown as given.
AGENCIES = {
    "DNR": "Department of Natural Resources",
    "DCEO": "Department of Commerce and Economic Opportunity",
    "EPA": "Environmental Protection Agency",
    "IEMAOHS": "Emergency Management Agency and Office of Homeland Security",
    "DOT": "Department of Transportation",
    "AGE": "Department on Aging",
    "BHE": "Board of Higher Education",
    "ICCB": "Community College Board",
    "IFA": "Finance Authority",
    "OSFM": "Office of the State Fire Marshal",
    "SBEL": "State Board of Elections",
    "DCFS": "Department of Children and Family Services",
    "DHS": "Department of Human Services",
    "IAC": "Arts Council",
    "ICJIA": "Criminal Justice Information Authority",
    "LETSB": "Law Enforcement Training and Standards Board",
}

_ROW = re.compile(r"(?s)<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>")


def _date(text):
    """'10/19/2026' -> '2026-10-19'; blank for 'No end date'."""
    try:
        return datetime.datetime.strptime(text.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return ""


def parse(page):
    rows = []
    for title_cell, agency, dates, award in _ROW.findall(page):
        href = re.search(r"href='([^']+)'", title_cell)
        if not href:
            continue
        href = html.unescape(href.group(1))
        if href.startswith("GMS.aspx"):
            # NOFOs run through AmpliFund link straight to the AmpliFund page.
            link = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get("url", [""])[0]
            source_id = link.rstrip("/").split("/")[-1]
        else:
            source_id = re.search(r"nofo=(\d+)", href).group(1) if "nofo=" in href else href
            link = NOFO_URL.format(id=source_id)
        start, _, end = clean(dates).partition(" - ")
        low, _, high = clean(award).partition(" - ")
        rows.append({
            "id": source_id,
            "title": html.unescape(clean(re.sub(r"<i[^>]*>.*?</i>", "", title_cell))),
            "agency": html.unescape(clean(agency)),
            "start": _date(start),
            "end": _date(end),
            "floor": dollars(low),
            "ceiling": dollars(high),
            "link": link,
        })
    return rows


def normalize(row):
    return {
        "source": "illinois-gata",
        "source_id": row["id"],
        "title": row["title"],
        "funder": "Illinois " + AGENCIES.get(row["agency"].split(" (")[0], row["agency"]),
        "funder_code": "IL-" + row["agency"].split(" (")[0],
        "listing_type": "Grant",
        "status": "posted",
        "post_date": row["start"],
        "close_date": row["end"],
        "award_floor": row["floor"],
        "award_ceiling": row["ceiling"],
        "total_funding": "",
        # The list does not say who may apply; each NOFO does.
        "eligibility": "Others (see listing)",
        "topics": "",
        "location": "Illinois",
        "link": row["link"],
        "summary": "",
    }


def collect(today, page=None):
    """Return open Illinois NOFOs in the common format.

    Pass page (the opportunity list HTML) to skip the download, e.g. in tests.
    """
    if page is None:
        page = fetch(LIST_URL, timeout=120).decode("utf-8", errors="replace")
    rows = [normalize(r) for r in parse(page)]
    return [r for r in rows if not r["close_date"] or r["close_date"] >= today.isoformat()]
