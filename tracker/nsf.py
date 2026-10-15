"""Collector for NSF's SBIR/STTR (America's Seed Fund) deadlines, from the NSF
"upcoming due dates" RSS feed (deadlines in the next 30 days).

Only the small-business programs are kept: NSF's other programs already come
in through Grants.gov, but the SBIR/STTR solicitations don't.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

FEED_URL = "https://www.nsf.gov/rss/rss_www_funding_upcoming.xml"
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DEADLINE = re.compile(rf"(?:Deadline Date|Window|Due Date)[^:]*:\s*({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})")
_SMALL_BUSINESS = re.compile(r"\b(SBIR|STTR|Small Business Innovation|Small Business Technology Transfer)\b")


def _tag(item, name):
    found = re.search(rf"(?s)<{name}>(.*?)</{name}>", item)
    if not found:
        return ""
    return re.sub(r"(?s)^<!\[CDATA\[(.*)\]\]>$", r"\1", found.group(1).strip())


def parse(feed):
    """Items from the feed. Parsed with patterns, not an XML parser, because
    the feed has unescaped ampersands in titles."""
    items = []
    for item in re.findall(r"(?s)<item>(.*?)</item>", feed):
        description = _tag(item, "description")
        deadline = _DEADLINE.search(html.unescape(clean(description)))
        due = ""
        if deadline:
            due = datetime.datetime.strptime(" ".join(deadline.groups()), "%B %d %Y").date().isoformat()
        program = re.search(r"Program Guidelines:\s*([A-Z]+)\s(\d{2}-\d+)", description)  # "NSF 26-511", often with a no-break space
        items.append({
            "title": html.unescape(_tag(item, "title")),
            "link": _tag(item, "link"),
            "due": due,
            "program": " ".join(program.groups()) if program else "",
            "text": html.unescape(clean(description)).replace("This is an NSF Upcoming Due Dates item.", "").strip(),
        })
    return items


def normalize(item):
    return {
        "source": "nsf-sbir",
        "source_id": item["program"] or item["link"],
        "title": item["title"],
        "funder": "National Science Foundation",
        "funder_code": "NSF",
        "listing_type": "Grant",
        "status": "posted",
        "post_date": "",
        "close_date": item["due"],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Small businesses",
        "topics": "SBIR/STTR",
        "location": "National",
        "link": item["link"],
        "summary": item["text"][:600],
    }


def collect(today, feed=None):
    """Return NSF SBIR/STTR deadlines in the common format.

    Pass feed (the RSS text) to skip the download, e.g. in tests.
    """
    if feed is None:
        feed = fetch(FEED_URL, timeout=60).decode("utf-8", errors="replace")
    return [normalize(i) for i in parse(feed)
            if _SMALL_BUSINESS.search(i["title"]) and (not i["due"] or i["due"] >= today.isoformat())]
