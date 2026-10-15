"""Collector for federal prize competitions that have no feed.

Reads each agency's own prize page: Army xTech competitions (cards marked
open), and the Bureau of Reclamation's water prize page (listed only when it
shows a competition accepting submissions). Prize notices in the Federal
Register are picked up by the federalregister collector.
"""

import datetime
import hashlib
import html
import re

from tracker.text import clean, fetch

XTECH_URL = "https://xtech.army.mil/competitions/"
USBR_URL = "https://www.usbr.gov/research/challenges/accepting.html"

_CARD = re.compile(r'(?s)<li[^>]*class="[^"]*competition-open-wrapper[^"]*"[^>]*>(.*?)</li>')


def _element(card, number):
    found = re.search(rf'(?s)element-{number}(?:-a)?\b[^>]*>(.*?)</div>', card)
    return html.unescape(clean(found.group(1))).strip("​ ") if found else ""


def _ymd(text):
    try:
        return datetime.datetime.strptime(text.strip(), "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def parse_xtech(page):
    rows = []
    for card in _CARD.findall(page):
        link = re.search(r'href="(https://xtech\.army\.mil/competition/[^"]+)"', card)
        if not link:
            continue
        rows.append({
            "source": "prizes",
            "source_id": link.group(1).rstrip("/").split("/")[-1],
            "title": _element(card, 1),
            "funder": "U.S. Army (xTech)",
            "funder_code": "PRIZE-ARMY",
            "listing_type": "Prize competition",
            "status": "posted",
            "post_date": _ymd(_element(card, 14)),
            "close_date": _ymd(_element(card, 15)),
            "award_floor": "",
            "award_ceiling": "",
            "total_funding": "",
            # xTech competitions are generally open to U.S. small businesses.
            "eligibility": "Small businesses (see listing)",
            "topics": "",
            "location": "National",
            "link": link.group(1),
            "summary": _element(card, 5)[:600],
        })
    return rows


def parse_usbr(page, today):
    text = html.unescape(clean(re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", page)))
    main = text[text.find("Accepting Submissions", text.find("About")):]
    main = main[:main.find("More Information about the Bureau")].strip()
    if not main or "currently no prize competitions" in main.lower():
        return []
    return [{
        "source": "prizes",
        # A new id whenever the page changes, so first_seen flags new competitions.
        "source_id": "usbr-" + hashlib.md5(main.encode()).hexdigest()[:8],
        "title": "Bureau of Reclamation water prize competition accepting submissions",
        "funder": "Bureau of Reclamation",
        "funder_code": "PRIZE-USBR",
        "listing_type": "Prize competition",
        "status": "posted",
        "post_date": "",
        "close_date": "",
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Others (see listing)",
        "topics": "",
        "location": "National",
        "link": USBR_URL,
        "summary": main[:600],
    }]


def collect(today, xtech_page=None, usbr_page=None):
    """Return open prize competitions in the common format.

    Pass the pages' HTML to skip the downloads, e.g. in tests.
    """
    if xtech_page is None:
        xtech_page = fetch(XTECH_URL, timeout=120).decode("utf-8", errors="replace")
    if usbr_page is None:
        usbr_page = fetch(USBR_URL, timeout=60).decode("utf-8", errors="replace")
    rows = parse_xtech(xtech_page) + parse_usbr(usbr_page, today)
    return [r for r in rows if not r["close_date"] or r["close_date"] >= today.isoformat()]
