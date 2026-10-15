"""Collector for public agency portals on Bonfire (no login for open listings).

Starts with the Great Lakes Water Authority (Detroit area water and sewer).
Many cities and utilities use Bonfire, so more portals can be added to PORTALS.
"""

import json

from tracker.text import fetch

# portal subdomain -> (agency name, short code, location)
PORTALS = {
    "glwater": ("Great Lakes Water Authority", "GLWA", "Detroit area, MI"),
}
DATA_URL = "https://{portal}.bonfirehub.com/PublicPortal/getOpenPublicOpportunitiesSectionData"
LINK_URL = "https://{portal}.bonfirehub.com/opportunities/{id}"


def normalize(portal, project):
    name, code, location = PORTALS[portal]
    return {
        "source": "bonfire",
        "source_id": f"{portal}-{project['ProjectID']}",
        "title": project.get("ProjectName", "").strip(),
        "funder": name,
        "funder_code": code,
        "listing_type": "Contract",
        "status": "posted",
        "post_date": "",
        "close_date": (project.get("DateClose") or "")[:10],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        "topics": "",
        "location": location,
        "link": LINK_URL.format(portal=portal, id=project["ProjectID"]),
        "summary": f"Reference {project['ReferenceID'].strip()}" if project.get("ReferenceID") else "",
    }


def collect(today, payloads=None):
    """Return open opportunities from every portal in the common format.

    Pass payloads (portal -> parsed JSON) to skip the download, e.g. in tests.
    """
    rows = []
    for portal in PORTALS:
        if payloads is not None:
            data = payloads[portal]
        else:
            data = json.loads(fetch(DATA_URL.format(portal=portal), timeout=60))
        projects = (data.get("payload") or {}).get("projects") or {}
        for project in projects.values():
            row = normalize(portal, project)
            if row["close_date"] >= today.isoformat():
                rows.append(row)
    return rows
