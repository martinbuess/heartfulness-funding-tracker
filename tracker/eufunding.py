"""Collector for the EU Funding & Tenders portal, using its public search service (no key or login).

The portal's own search page asks this service for open and forthcoming calls;
we ask the same questions, once per search word in profile.toml under
[eu_funding], and keep calls whose deadline hasn't passed.

Most EU calls fund consortia led by European organisations. Indian
organisations can usually join as partners, but India is not automatically
eligible for EU funding in most programmes, so every EU listing carries that
note and is marked "verify".
"""

import datetime
import json
import urllib.parse

from tracker.text import clean, fetch

SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text={text}&pageSize=100&pageNumber=1"
TOPIC_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{id}"
# The portal's codes: call types (1 topic, 2 call for proposals, 8 cascade funding) and statuses.
TYPES = ["1", "2", "8"]
FORTHCOMING, OPEN = "31094501", "31094502"
NOTE = ("EU programme: proposals usually come from a consortium led by an EU-based organisation. India is not "
        "automatically eligible for EU funding in most programmes; check the call's eligible countries.")


def _form(query):
    boundary = "----fbhtracker"
    parts = ""
    for name, value in (("query", query), ("languages", ["en"])):
        parts += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"blob\"\r\n"
                  f"Content-Type: application/json\r\n\r\n{json.dumps(value)}\r\n")
    return (parts + f"--{boundary}--\r\n").encode(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def search(text):
    query = {"bool": {"must": [{"terms": {"type": TYPES}}, {"terms": {"status": [FORTHCOMING, OPEN]}}]}}
    body, headers = _form(query)
    url = SEARCH_URL.format(text=urllib.parse.quote(text))
    return json.loads(fetch(url, timeout=120, data=body, headers=headers)).get("results", [])


def _first(meta, key):
    value = meta.get(key)
    return value[0] if isinstance(value, list) and value else (value or "")


def _budget(meta):
    """(largest single grant, total budget) in euros, from the portal's budget table; blank when absent."""
    try:
        overview = json.loads(_first(meta, "budgetOverview"))
    except (TypeError, ValueError):
        return "", ""
    biggest, total = 0.0, 0.0
    for actions in (overview.get("budgetTopicActionMap") or {}).values():
        for action in actions:
            biggest = max(biggest, float(action.get("maxContribution") or 0))
            total += sum(float(v or 0) for v in (action.get("budgetYearMap") or {}).values())
    return (f"{biggest:.0f}" if biggest else ""), (f"{total:.0f}" if total else "")


def normalize(result, today, eur_to_usd):
    meta = result.get("metadata") or {}
    identifier = _first(meta, "identifier")
    deadlines = sorted(d[:10] for d in meta.get("deadlineDate") or [] if d)
    upcoming = [d for d in deadlines if d >= today.isoformat()]
    biggest, total = _budget(meta)
    title = clean(_first(meta, "title"))
    call = clean(_first(meta, "callTitle"))
    url = result.get("url", "")
    if "/portal/screen/" not in url:
        url = TOPIC_URL.format(id=identifier)
    usd = lambda eur: f"{float(eur) * eur_to_usd:.0f}" if eur else ""
    return {
        "source": "eu-funding",
        "source_id": identifier,
        "title": title,
        "funder": "European Commission",
        "funder_code": "EU",
        "listing_type": "Grant",
        "status": "forecast" if _first(meta, "status") == FORTHCOMING else "posted",
        "post_date": (_first(meta, "startDate") or "")[:10],
        "close_date": upcoming[0] if upcoming else "",
        "award_floor": "",
        "award_ceiling": usd(biggest),
        "total_funding": usd(total),
        "eligibility": "",
        "eligibility_notes": NOTE,
        "topics": identifier,
        "location": "",
        "link": url,
        "summary": ((f"Programme: {call}. " if call and call != title else "")
                    + clean(_first(meta, "descriptionByte") or result.get("summary") or ""))[:600],
    }, deadlines


def collect(today, settings, results=None):
    """Open and forthcoming EU calls matching the search words. Pass results to skip the download."""
    if results is None:
        results = {}
        for word in settings.get("searches", []):
            for result in search(word):
                results[_first(result.get("metadata") or {}, "identifier")] = result
        results = list(results.values())
    rate = settings.get("eur_to_usd", 1.10)
    rows = []
    for result in results:
        row, deadlines = normalize(result, today, rate)
        # Keep calls with a deadline still ahead, or none announced yet.
        if row["source_id"] and (row["close_date"] or not deadlines):
            rows.append(row)
    return rows
