"""Collector for NYC City Record Online solicitations (NYC Open Data, no API key).

The City Record dataset holds every city notice; we keep procurement
solicitations whose due date has not passed.
"""

import json
import urllib.parse

from tracker.text import clean, dollars, fetch

API_URL = "https://data.cityofnewyork.us/resource/dg92-zbpx.json"
NOTICE_URL = "https://a856-cityrecord.nyc.gov/RequestDetail/{id}"


def download(today):
    query = {
        "$where": f"type_of_notice_description='Solicitation' AND due_date >= '{today.isoformat()}'",
        "$order": "due_date",
        "$limit": "5000",
    }
    url = API_URL + "?" + urllib.parse.urlencode(query)
    return json.loads(fetch(url, timeout=120))


def normalize(row):
    method = row.get("selection_method_description", "")
    summary = clean(row.get("additional_description_1"))
    return {
        "source": "nyc-city-record",
        "source_id": row.get("request_id", ""),
        "title": clean(row.get("short_title")),
        "funder": f"NYC {row.get('agency_name', '')}".strip(),
        "funder_code": "NYC",
        "listing_type": f"Contract ({method})" if method else "Contract",
        "status": "posted",
        "post_date": (row.get("start_date") or "")[:10],
        "close_date": (row.get("due_date") or "")[:10],
        "award_floor": "",
        "award_ceiling": dollars(row.get("contract_amount")),
        "total_funding": "",
        # City solicitations are open to any registered vendor.
        "eligibility": "Any vendor",
        "topics": row.get("category_description", ""),
        "location": "New York City",
        "link": NOTICE_URL.format(id=row.get("request_id", "")),
        "summary": summary[:600],
    }


def collect(today, rows=None):
    """Return open NYC solicitations in the common format.

    Pass rows (the API's JSON records) to skip the download, e.g. in tests.
    """
    if rows is None:
        rows = download(today)
    return [normalize(r) for r in rows if (r.get("due_date") or "")[:10] >= today.isoformat()]
