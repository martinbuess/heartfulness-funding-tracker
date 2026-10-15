"""Collector for SAM.gov contract opportunities (public daily file, no API key).

SAM.gov publishes every active federal contract notice as one CSV each day.
We keep solicitations whose response deadline has not passed, plus early
notices (presolicitations and sources sought) that have no deadline yet.
"""

import csv
import io

from tracker.text import clean, fetch

CSV_URL = (
    "https://sam.gov/api/prod/fileextractservices/v1/api/download/"
    "Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv?privacy=Public"
)

# Notices about contracts already awarded or not open to bids.
SKIP_TYPES = {
    "Award Notice",
    "Justification",
    "Justification and Approval (J&A)",
    "Sale of Surplus Property",
    "Consolidate/(Substantially) Bundle",
}
EARLY_TYPES = {"Presolicitation", "Sources Sought"}


def download():
    # The file is Windows-1252, not UTF-8.
    return fetch(CSV_URL, timeout=600).decode("cp1252", errors="replace")


def _location(row):
    place = ", ".join(p for p in (row.get("PopCity", "").strip(), row.get("PopState", "").strip()) if p)
    return place or "National"


def normalize(row):
    set_aside = row.get("SetASide", "").strip()
    if not set_aside or set_aside == "No Set aside used":
        # Open to any registered vendor, including small businesses.
        set_aside = "Any vendor"
    return {
        "source": "sam.gov",
        "source_id": row.get("NoticeId", ""),
        "title": clean(row.get("Title")),
        "funder": (row.get("Sub-Tier") or row.get("Department/Ind.Agency") or "").title(),
        "funder_code": f"SAM-{row.get('CGAC', '')}",
        "listing_type": f"Contract ({row.get('Type', '')})",
        "status": "forecast" if row.get("BaseType") in EARLY_TYPES else "posted",
        "post_date": (row.get("PostedDate") or "")[:10],
        "close_date": (row.get("ResponseDeadLine") or "")[:10],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": set_aside,
        "topics": f"NAICS {row.get('NaicsCode', '')}; PSC {row.get('ClassificationCode', '')}",
        "location": _location(row),
        "link": row.get("Link", ""),
        "summary": clean(row.get("Description"))[:600],
    }


def collect(today, csv_text=None):
    """Return open SAM.gov contract opportunities in the common format.

    Pass csv_text to skip the download, e.g. in tests.
    """
    if csv_text is None:
        csv_text = download()
    today = today.isoformat()
    latest = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("Active") != "Yes" or row.get("Type") in SKIP_TYPES:
            continue
        deadline = (row.get("ResponseDeadLine") or "")[:10]
        if deadline:
            if deadline < today:
                continue
        elif row.get("BaseType") not in EARLY_TYPES or (row.get("ArchiveDate") or "") < today:
            continue
        # Each amendment or follow-up notice is its own row; keep the newest one
        # per solicitation number (or per title and agency when there is none).
        key = row.get("Sol#", "").strip().lower() or (row.get("Title", "").strip().lower(), row.get("Sub-Tier", ""))
        if key not in latest or row.get("PostedDate", "") > latest[key].get("PostedDate", ""):
            latest[key] = row
    return [normalize(row) for row in latest.values()]
