"""Aggregator feeds: RSS feeds of sites that publish grant calls (fundsforNGOs, Terra Viva Grants).

Each feed item is one call. This reads the feed once a day (an RSS feed is meant
to be read by programs; nothing else on the site is fetched), and turns each
item into a listing. Deadlines, amounts and eligibility are read from the item
text, so they are best-effort: the sheet marks them "verify".

A feed only shows its newest items, so run.py keeps each listing until its
deadline passes, or for keep_days when no deadline is given.

Which feeds to read is set in profile.toml under [[aggregators]].
"""

import datetime
import email.utils
import html
import re

from tracker.text import clean, deadline_in, fetch


def _tag(item, name):
    match = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", item, re.S)
    value = match.group(1).strip() if match else ""
    return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", value, flags=re.S)


def parse(text):
    """Items of an RSS feed: id, title, link, posted date and text."""
    items = []
    for raw in re.findall(r"<item\b[^>]*>(.*?)</item>", text, re.S):
        link = clean(_tag(raw, "link"))
        guid = clean(_tag(raw, "guid")) or link
        # WordPress ids look like https://site/?p=12345; keep just the number so ids stay stable.
        found = re.search(r"[?&]p=(\d+)", guid)
        posted = ""
        try:
            posted = email.utils.parsedate_to_datetime(_tag(raw, "pubDate")).date().isoformat()
        except (TypeError, ValueError):
            pass
        body = _tag(raw, "content:encoded") or _tag(raw, "description")
        items.append({"id": found.group(1) if found else guid, "title": html.unescape(clean(_tag(raw, "title"))),
                      "link": link, "posted": posted, "text": html.unescape(clean(body))})
    return items


def _labelled(text, label):
    """The words after a label such as "Donor Name:" up to the next label or sentence end."""
    m = re.search(rf"{label}\s*:\s*(.{{2,120}}?)(?=\s+[A-Z][A-Za-z ]{{2,25}}:|\.\s|$)", text)
    return m.group(1).strip() if m else ""


def _eligibility(text):
    """Sentences about who may apply, up to 600 characters."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked = [s for s in sentences if re.search(r"eligib|who can apply|applicants? (must|should)|open to", s, re.I)]
    return " ".join(picked)[:600]


def normalize(item, source):
    title, body = item["title"], item["text"]
    due = deadline_in(body) or deadline_in(title)
    lowered = title.lower()
    kind = "Prize or award" if any(w in lowered for w in ("award", "prize", "challenge", "competition")) else "Grant"
    return {
        "source": source,
        "source_id": item["id"],
        "title": title,
        "funder": _labelled(body, "Donor Name") or _labelled(body, "Donor") or _labelled(body, "Funder"),
        "funder_code": "",
        "listing_type": kind,
        "status": "posted",
        "post_date": item["posted"],
        "close_date": due.isoformat() if due else "",
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "",
        "eligibility_notes": _eligibility(body),
        "topics": "",
        "location": _labelled(body, "Countries") or _labelled(body, "Country"),
        "link": item["link"],
        "summary": re.sub(r"^\s*Deadline\s*:?\s*\S+\s*", "", body)[:600],
    }


def collect(today, feed, text=None):
    """Open calls from one feed, in the common format. Pass text (the feed) to skip the download."""
    if text is None:
        text = fetch(feed["url"], timeout=120).decode("utf-8", "replace")
    items = parse(text)
    if not items:
        raise RuntimeError(f"no items in the feed (got {text[:120]!r})")
    skip = [w.lower() for w in feed.get("skip_title_words", [])]
    rows = [normalize(item, feed["source"]) for item in items if not any(w in item["title"].lower() for w in skip)]
    return [r for r in rows if not r["close_date"] or r["close_date"] >= today.isoformat()]


def still_open(row, today, keep_days):
    """For listings no longer in the feed: open until the deadline, or keep_days after first seen."""
    if row["close_date"]:
        return row["close_date"] >= today.isoformat()
    first = row.get("first_seen") or today.isoformat()
    return first >= (today - datetime.timedelta(days=keep_days)).isoformat()
