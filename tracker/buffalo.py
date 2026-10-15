"""Collector for Buffalo Sewer Authority bid and RFP posts (WordPress RSS feed,
no login). Posts have no deadline field, so the date is read from the notice
text ("... on Thursday, July 9, 2026 ..."). The feed carries the latest 10 posts.
"""

import datetime
import email.utils
import html
import re
import xml.etree.ElementTree as ET

from tracker.text import clean, fetch

FEED_URL = "https://buffalosewer.org/category/vendor-opportunities/feed/"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
# Posts without a date in the text (RFPs whose dates are in the PDF) are kept
# this many days after posting, marked "Not set".
UNDATED_DAYS = 45

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
# 'July 9, 2026', 'DECEMBER 17, 2025', and the site's 'April, 27, 2026'.
_DATE = re.compile(rf"\b({_MONTHS}),?\s+(\d{{1,2}}),?\s+(\d{{4}})", re.IGNORECASE)
_RFP = re.compile(r"\b(RFP|RFQ|request for (proposals?|qualifications))\b", re.IGNORECASE)
_BID = re.compile(r"\b(bids?|RFP|RFQ|proposals?|qualifications)\b", re.IGNORECASE)


def due_date(text):
    """The first date in the notice, which is when bids are due (pre-bid meetings come after)."""
    found = _DATE.search(text)
    if not found:
        return ""
    month, day, year = found.groups()
    try:
        return datetime.datetime.strptime(f"{month} {day} {year}", "%B %d %Y").date().isoformat()
    except ValueError:
        return ""


def parse(feed):
    root = ET.fromstring(feed)
    items = []
    for item in root.iter("item"):
        body = item.findtext(CONTENT) or item.findtext("description") or ""
        text = html.unescape(clean(re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", body)))
        posted = email.utils.parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
        items.append({
            "title": html.unescape(item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "guid": (item.findtext("guid") or "").strip(),
            "posted": posted,
            "text": text,
            "topics": [c.text.strip() for c in item.findall("category") if c.text],
        })
    return items


def normalize(item):
    title = re.sub(r"^(advertisement to bid|invitation to bid|rfp|rfq)\s*:\s*", "", item["title"], flags=re.IGNORECASE)
    rfp = _RFP.search(item["title"])
    return {
        "source": "buffalo-sewer",
        "source_id": item["guid"].rsplit("=", 1)[-1] or item["link"],
        "title": title.strip() or item["title"],
        "funder": "Buffalo Sewer Authority",
        "funder_code": "BSA",
        "listing_type": "Contract (RFP)" if rfp else "Contract (bid)",
        "status": "posted",
        "post_date": item["posted"],
        "close_date": due_date(item["text"]),
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": "; ".join(item["topics"]),
        "location": "Buffalo, NY",
        "link": item["link"],
        "summary": item["text"][:600],
    }


def collect(today, feed=None):
    """Return open Buffalo Sewer Authority bids and RFPs in the common format.

    Pass feed (the RSS bytes) to skip the download, e.g. in tests.
    """
    if feed is None:
        feed = fetch(FEED_URL, timeout=60)
    rows = []
    cutoff = (today - datetime.timedelta(days=UNDATED_DAYS)).isoformat()
    for item in parse(feed):
        if not _BID.search(item["title"]):
            continue  # meeting recordings and news
        row = normalize(item)
        if row["close_date"] >= today.isoformat() or (not row["close_date"] and row["post_date"] >= cutoff):
            rows.append(row)
    return rows
