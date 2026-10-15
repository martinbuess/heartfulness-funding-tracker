"""Collector for fundsforNGOs, an aggregator of grant calls for NGOs worldwide.

fundsforNGOs publishes each call as a post on a WordPress site, and WordPress
offers every site's posts as a public list (/wp-json/wp/v2/posts). This reads
the newest posts plus one page for each search word in profile.toml, and
turns each post into a listing. Deadlines, amounts and eligibility are read
from the post text, so they are best-effort: the sheet marks them "verify".

Posts drop off the newest-posts list after a few days even though the call is
still open, so run.py keeps this source's listings until their deadline passes
(see FEED_SOURCES in run.py).
"""

import datetime
import html
import json
import re
import urllib.parse

from tracker.text import clean, deadline_in, fetch

SOURCE = "fundsforngos"
FIELDS = "id,date,link,title,content"


def _text(item, key):
    value = item.get(key)
    return html.unescape(clean(value.get("rendered", ""))) if isinstance(value, dict) else ""


def _labelled(text, label):
    """The words after a label such as "Donor Name:" up to the next label or sentence end."""
    m = re.search(rf"{label}\s*:\s*(.{{2,120}}?)(?=\s+[A-Z][A-Za-z ]{{2,25}}:|\.\s|$)", text)
    return m.group(1).strip() if m else ""


def _eligibility(text):
    """Sentences about who may apply, up to 600 characters."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked = [s for s in sentences if re.search(r"eligib|who can apply|applicants? (must|should)|open to", s, re.I)]
    return " ".join(picked)[:600]


def normalize(item, today):
    title = _text(item, "title")
    body = _text(item, "content")
    due = deadline_in(body) or deadline_in(title)
    posted = (item.get("date") or "")[:10]
    funder = _labelled(body, "Donor Name") or _labelled(body, "Donor")
    lowered = title.lower()
    if any(w in lowered for w in ("award", "prize", "challenge", "competition")):
        kind = "Prize or award"
    else:
        kind = "Grant"
    return {
        "source": SOURCE,
        "source_id": str(item.get("id", "")),
        "title": title,
        "funder": funder,
        "funder_code": "",
        "listing_type": kind,
        "status": "posted",
        "post_date": posted,
        "close_date": due.isoformat() if due else "",
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "",
        "eligibility_notes": _eligibility(body),
        "topics": "",
        "location": _labelled(body, "Countries") or _labelled(body, "Country"),
        "link": item.get("link", ""),
        "summary": re.sub(r"^\s*Deadline\s*:?\s*\S+\s*", "", body)[:600],
    }


def _url(api, page=1, search=""):
    query = {"per_page": "100", "page": str(page), "_fields": FIELDS, "orderby": "date", "order": "desc"}
    if search:
        query["search"] = search
    return api + "?" + urllib.parse.urlencode(query)


def download(settings):
    """Every post from the newest pages and the search pages, without repeats."""
    api = settings.get("api", "https://www2.fundsforngos.org/wp-json/wp/v2/posts")
    urls = [_url(api, page) for page in range(1, settings.get("latest_pages", 2) + 1)]
    urls += [_url(api, search=word) for word in settings.get("searches", [])]
    items = {}
    for url in urls:
        data = json.loads(fetch(url, timeout=120).decode("utf-8", "replace"))
        if not isinstance(data, list):
            raise RuntimeError(f"unexpected answer from {url}: {str(data)[:120]}")
        for item in data:
            items[item.get("id")] = item
    return list(items.values())


def collect(today, settings, items=None):
    """Return open calls in the common format. Pass items (parsed posts) to skip the download."""
    if items is None:
        items = download(settings)
    rows = [normalize(item, today) for item in items]
    return [r for r in rows if not r["close_date"] or r["close_date"] >= today.isoformat()]


def still_open(row, today, keep_days):
    """For listings no longer in the feed: open until the deadline, or keep_days after first seen."""
    if row["close_date"]:
        return row["close_date"] >= today.isoformat()
    first = row.get("first_seen") or today.isoformat()
    return first >= (today - datetime.timedelta(days=keep_days)).isoformat()
