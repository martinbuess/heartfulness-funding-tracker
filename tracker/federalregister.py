"""Collector for funding and prize notices in the Federal Register (public API, no key).

An early-warning source: agencies announce funding rounds, prize competitions
and calls for proposals here, sometimes before or outside Grants.gov.
Keeps notices from the last 30 days; each links to the full notice.
"""

import datetime
import json
import urllib.parse

from tracker.text import clean, fetch

API_URL = "https://www.federalregister.gov/api/v1/documents.json"
TERMS = [
    "funding opportunity", "request for applications", "inviting applications",
    "solicitation of applications", "request for proposals", "prize competition",
    "challenge competition",
]
# Paperwork notices mention a funding program without announcing one.
NOT_OPPORTUNITIES = ("agency information collection", "proposed information collection",
                     "proposed data collection", "information collection request")
WINDOW_DAYS = 30


def download(today):
    since = today - datetime.timedelta(days=WINDOW_DAYS)
    query = [
        ("per_page", "1000"),
        ("order", "newest"),
        ("conditions[type][]", "NOTICE"),
        ("conditions[publication_date][gte]", since.isoformat()),
        ("conditions[term]", " | ".join(f'"{t}"' for t in TERMS)),
    ]
    return json.loads(fetch(API_URL + "?" + urllib.parse.urlencode(query), timeout=120))


def normalize(doc):
    agencies = [a.get("name") or a.get("raw_name") or "" for a in doc.get("agencies") or []]
    return {
        "source": "federalregister",
        "source_id": doc.get("document_number", ""),
        "title": clean(doc.get("title")),
        # The most specific agency is listed last.
        "funder": agencies[-1] if agencies else "",
        "funder_code": "FR",
        "listing_type": "Notice",
        "status": "posted",
        "post_date": doc.get("publication_date", ""),
        "close_date": "",  # deadlines are in the notice text
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Others (see listing)",
        "topics": "; ".join(agencies),
        "location": "National",
        "link": doc.get("html_url", ""),
        "summary": clean(doc.get("abstract"))[:600],
    }


def collect(today, data=None):
    """Return recent funding and prize notices in the common format.

    Pass data (the API's parsed JSON) to skip the download, e.g. in tests.
    """
    if data is None:
        data = download(today)
    docs = [d for d in data.get("results") or []
            if not any(p in d.get("title", "").lower() for p in NOT_OPPORTUNITIES)]
    return [normalize(d) for d in docs]
