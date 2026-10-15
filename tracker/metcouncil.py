"""Collector for Metropolitan Council (Minneapolis-St. Paul) contracting
opportunities. Public web page, no login. Its Environmental Services division
runs the region's wastewater system; Metro Transit and other divisions post here too.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

PAGE_URL = "https://metrocouncil.org/About-Us/What-We-Do/DoingBusiness/Contracting-Opportunities.aspx"
SITE = "https://metrocouncil.org"
DIVISIONS = {
    "ES": "Metropolitan Council Environmental Services",
    "Transit": "Metro Transit",
    "MTS": "Metropolitan Council Transportation Services",
    "RA": "Metropolitan Council",
    "CD": "Metropolitan Council Community Development",
    "LRT": "Metro Transit Light Rail",
}
TYPES = {"RFI": "Contract (request for information)", "RFP": "Contract (RFP)", "RFQ": "Contract (quote)",
         "IFB": "Contract (bid)", "D/B": "Contract (design-build)", "PSD": "Contract (prequalification)"}


def _date(text):
    try:
        return datetime.datetime.strptime(text.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return ""


def parse(page):
    page = re.sub(r"(?s)<!--.*?-->", "", page)  # a commented-out "posted" column
    rows = []
    for table in re.findall(r"(?s)<table.*?</table>", page):
        if "Due Date" not in table:
            continue
        for tr in re.findall(r"(?s)<tr.*?</tr>", table):
            cells = re.findall(r"(?s)<td[^>]*>(.*?)</td>", tr)
            if len(cells) != 6:
                continue
            division, number, title, issued, due, kind = cells
            link = re.search(r'href="([^"]+)"', number)
            rows.append({
                "division": clean(division),
                "number": html.unescape(clean(number)),
                "title": re.sub(r"^NEW\s+|\s+Meeting Announcement$", "", html.unescape(clean(title))),
                "issued": _date(clean(issued)),
                "due": _date(clean(due)),
                "type": clean(kind),
                "link": SITE + html.unescape(link.group(1)) if link else PAGE_URL,
            })
    return rows


def normalize(row):
    return {
        "source": "metcouncil",
        "source_id": row["number"],
        "title": row["title"],
        "funder": DIVISIONS.get(row["division"], "Metropolitan Council"),
        "funder_code": f"METC-{row['division']}",
        "listing_type": TYPES.get(row["type"], "Contract"),
        "status": "posted",
        "post_date": row["issued"],
        "close_date": row["due"],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": row["division"],
        "location": "Minneapolis-St. Paul, MN",
        "link": row["link"],
        "summary": "",
    }


def collect(today, page=None):
    """Return open Met Council solicitations in the common format.

    Pass page (the HTML) to skip the download, e.g. in tests.
    """
    if page is None:
        page = fetch(PAGE_URL, timeout=120).decode("utf-8", errors="replace")
    return [normalize(r) for r in parse(page) if r["due"] >= today.isoformat()]
