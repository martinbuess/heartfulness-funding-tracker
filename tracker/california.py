"""Collector for the California Grants Portal open dataset (no API key).

grants.ca.gov publishes every state grant and loan as one CSV, refreshed daily.
We keep active and forecasted listings.
"""

import csv
import io
import re

from tracker.text import clean, dollars, fetch

CSV_URL = (
    "https://data.ca.gov/dataset/e1b1c799-cdd4-4219-af6d-93b79747fffb/resource/"
    "111c8c88-21f6-453c-ae2c-b4785a0624f5/download/california-grants-portal-data.csv"
)


def download():
    return fetch(CSV_URL).decode("utf-8-sig")


def _amount_range(text):
    """'Between $50,000.00 and $12,500,000.00' -> ('50000', '12500000')."""
    found = re.findall(r"\$[\d,]+(?:\.\d+)?", text or "")
    if len(found) >= 2:
        return dollars(found[0]), dollars(found[1])
    return "", dollars(found[0]) if found else ""


def _deadline(text):
    match = re.match(r"\d{4}-\d{2}-\d{2}", text or "")
    return match.group(0) if match else ""


def normalize(row):
    floor, ceiling = _amount_range(row.get("EstAmounts"))
    summary = clean(row.get("Purpose")) or clean(row.get("Description"))
    return {
        "source": "grants.ca.gov",
        "source_id": row.get("PortalID", ""),
        "title": clean(row.get("Title")),
        "funder": row.get("AgencyDept", ""),
        "funder_code": "CA",
        "listing_type": row.get("Type", "") or "Grant",
        "status": "forecast" if row.get("Status") == "forecasted" else "posted",
        "post_date": _deadline(row.get("OpenDate")),
        "close_date": _deadline(row.get("ApplicationDeadline")),
        "award_floor": floor,
        "award_ceiling": ceiling,
        "total_funding": dollars(row.get("EstAvailFunds")),
        "eligibility": row.get("ApplicantType", ""),
        "topics": row.get("Categories", ""),
        "location": "California",
        "link": row.get("GrantURL") or row.get("AgencyURL", ""),
        "summary": summary[:600],
    }


def collect(today, csv_text=None):
    """Return open California listings in the common format.

    Pass csv_text to skip the download, e.g. in tests.
    """
    if csv_text is None:
        csv_text = download()
    listings = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("Status") not in ("active", "forecasted"):
            continue
        listing = normalize(row)
        if listing["close_date"] and listing["close_date"] < today.isoformat():
            continue
        listings.append(listing)
    return listings
