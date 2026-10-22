"""Aggregator feeds: RSS feeds of sites that publish grant calls (fundsforNGOs, Terra Viva Grants).

Each feed item is one call. This reads the feed once a day (an RSS feed is meant
to be read by programs; nothing else on the site is fetched), and turns each
item into a listing.

Most fundsforNGOs posts carry an "Opportunity at a Glance" block of labelled
fields (Funding organization, Eligible countries, Grant size, Deadline, ...).
Those labelled fields are read first, because they are far more reliable than
guessing from the running text. When a post has no such block, the funder,
deadline and amount are guessed from the text and the sheet marks them "verify".

Roundup posts (fundsforNGOs "/listing/" pages) list many separate calls, each
with its own deadline and link. Each call in a roundup becomes its own listing.

A feed only shows its newest items, so run.py keeps each listing until its
deadline passes, or for keep_days when no deadline is given.

Which feeds to read is set in profile.toml under [[aggregators]].
"""

import datetime
import email.utils
import html
import re

from tracker.text import clean, dates, deadline_in, fetch

# --- the "Opportunity at a Glance" block ---------------------------------------

# Field labels, grouped by what they tell us. Matched case-insensitively and
# followed by a colon. Longer labels are tried first.
LABELS = {
    "funder": ["funder/organizer", "funder/organiser", "funder / organizer", "funding organizations", "funding organisations", "funding organization(s)", "funding organisation(s)",
               "funding organization", "funding organisation", "funding agency", "funding body", "provider",
               "donor name", "donor", "funder", "organizer", "organiser", "organizing body", "hosted by", "host",
               "implementing organization", "implementing agency", "sponsor", "awarding body", "offered by"],
    "name": ["funding opportunity name", "opportunity name", "programme name", "program name"],
    "type": ["opportunity type", "grant type", "funding type", "type"],
    "amount": ["grant size (small)", "grant size (large)", "grant size", "grant amount", "grant value",
               "funding amount", "funding available", "award amount", "award value", "prize money", "prize",
               "total funding", "total budget", "budget", "funding", "award", "amount"],
    "countries": ["eligible countries", "eligible country", "eligible locations", "eligible location",
                  "eligible regions", "eligible region", "eligible geographies", "eligible geography",
                  "geographic focus", "geographical focus", "geographic scope", "geographical scope",
                  "geographic coverage", "project location scope", "project location", "location", "countries",
                  "region"],
    "applicants": ["eligible applicants", "eligible applicant", "who can apply", "applicant type", "eligibility"],
    "deadline": ["deadline for pre-proposals", "deadline for proposals", "deadline for applications",
                 "application deadline", "submission deadline", "submission window (online)", "submission window",
                 "closing date", "due date", "deadline"],
    "other": ["opening date", "official launch of the call", "launch date", "project duration", "duration",
              "application format", "eligible priorities", "focus areas", "focus area", "thematic areas",
              "thematic area", "regional implementation team (rit)", "language", "contact", "website",
              "funding period", "number of grants", "co-financing", "cofinancing"],
}
_ALL = sorted(((label, group) for group, labels in LABELS.items() for label in labels), key=lambda x: -len(x[0]))
_GROUP = {label: group for label, group in _ALL}
# A label may carry a note in brackets, e.g. "Eligible priorities (overall call focus):".
_LABEL = re.compile(r"(?<![\w(])(" + "|".join(re.escape(label) for label, _ in _ALL) + r")(?:\s*\([^)]{1,40}\))?\s*:",
                    re.IGNORECASE)
# Headings that end the glance block.
_END = re.compile(r"\b(About the (Opportunity|Program|Programme|Grant|Fund|Call)|Who Is Eligible|Eligibility Criteria|"
                  r"Ineligible|How to Apply|Application Process|Selection Criteria|Key Dates|For more information)\b",
                  re.IGNORECASE)
_NOT_GIVEN = re.compile(r"^\s*(not specified|not stated|not mentioned|n/?a|tbd|tba|none)\b", re.IGNORECASE)


def glance(text):
    """The labelled fields of an "Opportunity at a Glance" block, as {group: value}.

    Only the first value of each group is kept ("Grant size (small)" and
    "Grant size (large)" are joined). Values saying "Not specified" are dropped.
    """
    start = re.search(r"at a glance", text, re.IGNORECASE)
    block = text[start.end():] if start else text
    found = list(_LABEL.finditer(block))
    if len(found) < 2:  # one stray "Deadline:" in running text is not a block
        return {}
    fields = {}
    for i, match in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(block)
        value = block[match.end():end]
        # A value ends where running text starts again, e.g. "Donor Name: X. The Foundation invites ...".
        value = re.split(r"\.\s+(?=(?:The|This|These|It|Its|Applications?|Grants?|Funding|Proposals?|Projects?)\b)",
                         value)[0]
        stop = _END.search(value)
        value = " ".join((value[:stop.start()] if stop else value).split())[:300].strip(" .;,")
        group = _GROUP[match.group(1).lower()]
        if not value or _NOT_GIVEN.match(value):
            continue
        if group == "amount" and "amount" in fields and value not in fields["amount"]:
            fields["amount"] += f"; {value}"
        elif group != "amount" or "amount" not in fields:
            fields.setdefault(group, value)
    return fields


# --- guessing from the running text -------------------------------------------

_INVITES = re.compile(
    r"^(?:the\s+)?(.{3,90}?)\s+(?:\([A-Z]{2,10}\)\s+)?(?:is\s+(?:now\s+)?(?:inviting|accepting|offering|seeking|calling|"
    r"launching|announcing|opening|providing)|are\s+(?:now\s+)?(?:inviting|accepting|offering|seeking|calling)|"
    r"invites?|announces?|has\s+(?:launched|opened|announced)|have\s+(?:launched|opened|announced)|"
    r"opens?|launche[sd]|seeks?|welcomes?|calls\s+for)\b", re.IGNORECASE)


def guess_funder(title, text, title_separator=""):
    """Funder from the title ("X — Y", "... by X") or the first sentence ("The X invites ...")."""
    if title_separator and title_separator in title:
        return title.split(title_separator)[0].strip()
    by = re.search(r"\b(?:by|from)\s+(?:the\s+)?([A-Z][\w&'’.-]*(?:\s+(?:[A-Z][\w&'’.-]*|of|for|and|&|the|de|du))*)\s*$",
                   title)
    if by and len(by.group(1)) > 4:
        return by.group(1)
    found = _INVITES.match(text.strip())
    if found:
        name = found.group(1).strip(" ,")
        # Keep only names, not sentence starts like "This program" or "Applications".
        if name[:1].isupper() and not re.match(r"(this|these|applications?|proposals?|grants?|funding)\b", name, re.I):
            return re.split(r",| in partnership with | together with ", name)[0].strip()
    return ""


def _clean_funder(name):
    return re.sub(r"^the\s+", "", name, flags=re.IGNORECASE).strip(" .,;")


# --- RSS ------------------------------------------------------------------------


def _tag(item, name):
    match = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", item, re.S)
    value = match.group(1).strip() if match else ""
    return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", value, flags=re.S)


def parse(text):
    """Items of an RSS feed: id, title, link, posted date, text, and the raw HTML body."""
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
                      "link": link, "posted": posted, "text": html.unescape(clean(body)), "html": html.unescape(body)})
    return items


def _eligibility_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    picked = [s for s in sentences if re.search(r"eligib|who can apply|applicants? (must|should)|open to", s, re.I)]
    return " ".join(picked)[:600]


def _kind(title):
    lowered = title.lower()
    return "Prize or award" if any(w in lowered for w in ("award", "prize", "challenge", "competition")) else "Grant"


def normalize(item, source, title_separator=""):
    title, body = item["title"], item["text"]
    fields = glance(body)
    window = dates(fields.get("deadline", ""))
    due = (window[-1] if window else None) or deadline_in(body) or deadline_in(title)
    funder = _clean_funder(fields.get("funder", "")) or guess_funder(title, body, title_separator)
    summary = re.sub(r"^\s*Deadline\s*:?\s*\S+\s*", "", body)
    # Keep the summary to the description before the glance block (the block's fields have their own columns).
    cut = re.search(r"Opportunity at a Glance", summary, re.IGNORECASE)
    return {
        "source": source,
        "source_id": item["id"],
        "title": title,
        "funder": funder[:120],
        "funder_code": "",
        "listing_type": fields.get("type", "") or _kind(title),
        "status": "posted",
        "post_date": item["posted"],
        "close_date": due.isoformat() if due else "",
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "amount_text": fields.get("amount", ""),
        "eligibility": fields.get("applicants", ""),
        "eligibility_notes": (fields.get("applicants", "") + " " + _eligibility_sentences(body)).strip()[:600],
        "topics": "",
        "location": fields.get("countries", ""),
        "link": item["link"],
        "summary": (summary[:cut.start()] if cut and cut.start() > 80 else summary)[:900],
        "details": "structured" if fields else "",
    }


# --- roundups -----------------------------------------------------------------

_ANCHOR = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.IGNORECASE)


def is_roundup(item):
    return "/listing/" in item["link"]


def roundup_calls(item, source):
    """The separate calls listed in a roundup post: title, own link, deadline and blurb."""
    calls, seen = [], set()
    anchors = [(m.start(), m.end(), m.group(1), clean(html.unescape(m.group(2)))) for m in _ANCHOR.finditer(item["html"])]
    titled = [a for a in anchors if len(a[3]) > 15 and "/listing/" not in a[2] and not a[3].lower().startswith("more")]
    for i, (start, end, href, title) in enumerate(titled):
        if href in seen:
            continue
        stop = titled[i + 1][0] if i + 1 < len(titled) else len(item["html"])
        after = html.unescape(clean(item["html"][end:stop]))
        due = deadline_in(after[:200])
        if not due:
            continue  # sidebar cards and "related" links have no deadline
        seen.add(href)
        blurb = re.sub(r"^\s*Deadline\s*:?\s*[\w ,-]+?\d{4}\s*", "", after).split("…[")[0].split("[ more")[0]
        slug = href.rstrip("/").rsplit("/", 1)[-1][:80]
        calls.append({
            "source": source, "source_id": f"roundup:{slug}", "title": title, "funder": guess_funder(title, blurb),
            "funder_code": "", "listing_type": _kind(title), "status": "posted", "post_date": item["posted"],
            "close_date": due.isoformat(), "award_floor": "", "award_ceiling": "", "total_funding": "",
            "amount_text": "", "eligibility": "", "eligibility_notes": _eligibility_sentences(blurb), "topics": "",
            "location": "", "link": href, "summary": blurb.strip()[:600],
            "details": f"from roundup: {item['title'][:80]}",
        })
    return calls


# --- collecting -----------------------------------------------------------------


def collect(today, feed, text=None):
    """Open calls from one feed, in the common format. Pass text (the feed) to skip the download."""
    if text is None:
        text = fetch(feed["url"], timeout=120).decode("utf-8", "replace")
    items = parse(text)
    if not items:
        raise RuntimeError(f"no items in the feed (got {text[:120]!r})")
    # A feed shows only its newest posts (25 on fundsforNGOs). On busy days more than that are
    # published, so older pages of the same feed are read too (WordPress: ?paged=2, 3, ...).
    # A missing extra page only means fewer posts today; it never fails the source.
    seen = {item["id"] for item in items}
    for page in range(2, feed.get("pages", 1) + 1):
        joiner = "&" if "?" in feed["url"] else "?"
        try:
            more = parse(fetch(f"{feed['url']}{joiner}paged={page}", timeout=120).decode("utf-8", "replace"))
        except Exception as exc:
            print(f"{feed['source']}: page {page} not read ({exc})")
            break
        more = [item for item in more if item["id"] not in seen]
        if not more:
            break
        seen.update(item["id"] for item in more)
        items += more
    skip = [w.lower() for w in feed.get("skip_title_words", [])]
    separator = feed.get("title_separator", "")
    rows = []
    for item in items:
        if any(w in item["title"].lower() for w in skip):
            continue
        if is_roundup(item):
            rows += roundup_calls(item, feed["source"])
        else:
            rows.append(normalize(item, feed["source"], separator))
    # A call posted on its own and also listed in a roundup: keep the full post.
    by_link = {}
    for row in rows:
        if row["link"] not in by_link or not row["details"].startswith("from roundup"):
            by_link[row["link"]] = row
    return [r for r in by_link.values() if not r["close_date"] or r["close_date"] >= today.isoformat()]


def reread(row, title_separator=""):
    """Fill the labelled fields of a listing saved by an older version, from its saved text."""
    # Older versions cut the summary mid-block and repeated the block in the notes, so read
    # the block from whichever field holds it whole.
    notes, summary = row.get("eligibility_notes", ""), row.get("summary", "")
    text = notes if re.search(r"at a glance", notes, re.IGNORECASE) else summary
    fields = glance(text)
    window = dates(fields.get("deadline", ""))
    if window and not row.get("close_date"):
        row["close_date"] = window[-1].isoformat()
    row["funder"] = (row.get("funder") or _clean_funder(fields.get("funder", ""))
                     or guess_funder(row["title"], summary, title_separator))[:120]
    row["location"] = row.get("location") if row.get("location") and not _NOT_GIVEN.match(row["location"]) \
        else fields.get("countries", "")
    row["amount_text"] = row.get("amount_text") or fields.get("amount", "")
    if fields.get("applicants") and not row.get("eligibility"):
        row["eligibility"] = fields["applicants"]
    cut = re.search(r"Opportunity at a Glance", row.get("summary", ""), re.IGNORECASE)
    if cut and cut.start() > 80:
        row["summary"] = row["summary"][:cut.start()]
    row["details"] = "structured (re-read)" if fields else "re-read"
    return row


def still_open(row, today, keep_days):
    """For listings no longer in the feed: open until the deadline, or keep_days after first seen."""
    if row["close_date"]:
        return row["close_date"] >= today.isoformat()
    first = row.get("first_seen") or today.isoformat()
    return first >= (today - datetime.timedelta(days=keep_days)).isoformat()
