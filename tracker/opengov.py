"""Collector for public agency portals on OpenGov Procurement (no login for open projects).

Starts with the Northeast Ohio Regional Sewer District (Cleveland area).
Many cities and utilities use OpenGov, so more portals can be added to PORTALS.
"""

import html
import json
import re

from tracker.text import clean, fetch

# portal code -> (short code, location)
PORTALS = {
    "neorsd": ("NEORSD", "Cleveland area, OH"),
}
DATA_URL = "https://api.procurement.opengov.com/api/v1/government/{portal}/project/public"
LINK_URL = "https://procurement.opengov.com/portal/{portal}/projects/{id}"
PAGE_SIZE = 100


def normalize(portal, project):
    code, location = PORTALS[portal]
    title = (project.get("title") or "").strip()
    kind = (project.get("template") or {}).get("title", "").strip()
    rfi = "request for information" in f"{title} {kind}".lower()
    department = ((project.get("department") or {}).get("name") or "").strip()
    # Inline spans split words mid-way ("contrac</span><span>t"), so drop them before cleaning.
    summary = html.unescape(clean(re.sub(r"</?span[^>]*>", "", project.get("summary") or "")))
    org = ((project.get("government") or {}).get("organization") or {})
    return {
        "source": "opengov",
        "source_id": f"{portal}-{project['id']}",
        "title": title,
        "funder": org.get("name") or code,
        "funder_code": code,
        "listing_type": "Contract (request for information)" if rfi else "Contract (bid)",
        "status": "forecast" if project.get("comingSoon") else "posted",
        "post_date": (project.get("releaseProjectDate") or "")[:10],
        # Deadlines are daytime UTC, so the date part is the local date too.
        "close_date": (project.get("proposalDeadline") or "")[:10],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": "; ".join(t for t in (department, kind.title()) if t),
        "location": location,
        "link": LINK_URL.format(portal=portal, id=project["id"]),
        "summary": summary[:600],
    }


def _pages(portal):
    page = 1
    while True:
        body = json.dumps({"filters": [{"type": "status", "value": "open"}], "limit": PAGE_SIZE, "page": page})
        data = json.loads(fetch(DATA_URL.format(portal=portal), timeout=60, data=body.encode(),
                                headers={"Content-Type": "application/json"}))
        rows = data.get("rows") or []
        yield data
        if len(rows) < PAGE_SIZE or page * PAGE_SIZE >= (data.get("count") or 0):
            return
        page += 1


def collect(today, payloads=None):
    """Return open projects from every portal in the common format.

    Pass payloads (portal -> list of parsed JSON pages) to skip the download, e.g. in tests.
    """
    rows = []
    for portal in PORTALS:
        pages = payloads[portal] if payloads is not None else _pages(portal)
        for data in pages:
            for project in data.get("rows") or []:
                if project.get("status") != "open" or project.get("isPaused"):
                    continue
                row = normalize(portal, project)
                if not row["close_date"] or row["close_date"] >= today.isoformat():
                    rows.append(row)
    return rows
