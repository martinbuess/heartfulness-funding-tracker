"""Watched pages: funders' "apply" pages that have no feed.

Many funders in the FBH pipeline (HCLTech Grant, Wipro Foundation, GEF Small
Grants, ...) announce calls only on a page of their own website. Reading such
pages field by field breaks whenever the layout changes, so instead each run:

  1. downloads the page (only if the site's robots.txt allows it),
  2. keeps the sentences that talk about calls: apply, deadline, call for
     proposals, applications open or closed, and dates,
  3. compares them with the last run. If they changed, the page is flagged
     CHANGED, so a person can open it and see what's new.

It also reports whether the page says applications are open or closed, and the
next future date it mentions. Results go to data/watch.csv and the sheet's
"Tracker – Watched pages" tab. A page that can't be read is reported there; it
never fails the whole run.
"""

import csv
import datetime
import hashlib
import html
import os
import re

from tracker.text import Blocked, dates, fetch

PATH = "data/watch.csv"
COLUMNS = ["name", "funder", "status", "signal", "next_date", "last_changed", "last_checked", "link", "snippet",
           "fingerprint", "note"]
# Pages flagged CHANGED for this many days after a change.
CHANGED_DAYS = 7

_CALL = re.compile(r"\b(apply|applications?|call for|proposals?|deadline|last date|due|closes?|closed|"
                   r"opens?|open now|accepting|submission|eligib|grant cycle|round)\b", re.IGNORECASE)
_OPEN = re.compile(r"applications? (are )?(now )?open|now accepting|apply now|apply (here|online|today)|"
                   r"call for (proposals|applications) (is )?(now )?open|open for applications", re.IGNORECASE)
_CLOSED = re.compile(r"applications? (are |is )?(now )?closed|closed for (applications|this)|no open calls?|"
                     r"not accepting|call (is |has )?closed|currently closed", re.IGNORECASE)


def page_text(page):
    """Visible text of an HTML page, without scripts, styles, menus and footers."""
    page = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>", " ", page)
    page = re.sub(r"(?s)<!--.*?-->", " ", page)
    page = re.sub(r"(?i)<(br|p|div|li|h\d|tr|section|article)\b[^>]*>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def call_lines(text):
    """The sentences that talk about calls or dates, in page order, without repeats."""
    seen, out = set(), []
    for line in text.splitlines():
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if len(sentence) > 400 or len(sentence) < 8:
                continue
            if _CALL.search(sentence) or dates(sentence):
                key = sentence.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(sentence)
    return out


def read(page_html, today):
    """(fingerprint, signal, next date, snippet) for one page's HTML."""
    text = page_text(page_html)
    lines = call_lines(text)
    joined = " ".join(lines)
    fingerprint = hashlib.sha1(joined.lower().encode()).hexdigest()[:12]
    opened, closed = _OPEN.search(joined), _CLOSED.search(joined)
    signal = ("Says closed" if closed and not opened else "Says open" if opened and not closed
              else "Open and closed both mentioned" if opened else "No signal")
    future = sorted(d for d in dates(joined) if d >= today)
    return fingerprint, signal, future[0].isoformat() if future else "", joined[:400]


def load(path=PATH):
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["link"]: row for row in csv.DictReader(f)}


def save(rows, path=PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def check(pages, today, previous, get=None):
    """Check every page. Returns (rows for data/watch.csv, names of pages that failed)."""
    get = get or (lambda url: fetch(url, timeout=60).decode("utf-8", "replace"))
    rows, failed = [], []
    stamp = today.isoformat()
    for page in pages:
        old = previous.get(page["url"], {})
        row = {"name": page["name"], "funder": page.get("funder", ""), "link": page["url"],
               "note": page.get("note", ""), "last_changed": old.get("last_changed", ""),
               "fingerprint": old.get("fingerprint", ""), "signal": old.get("signal", ""),
               "next_date": old.get("next_date", ""), "snippet": old.get("snippet", ""),
               "last_checked": old.get("last_checked", "")}
        try:
            fingerprint, signal, next_date, snippet = read(get(page["url"]), today)
        except Blocked as exc:
            row["status"] = f"Not read: {exc}"
            failed.append(page["name"])
        except Exception as exc:  # down, moved or refusing automated readers
            row["status"] = f"Could not be read today ({str(exc)[:120]}); showing the last check"
            failed.append(page["name"])
        else:
            if not old.get("fingerprint"):
                row["status"] = "First check (baseline saved)"
            elif fingerprint != old["fingerprint"]:
                row["status"] = "CHANGED: open the page to see what's new"
                row["last_changed"] = stamp
            elif row["last_changed"] >= (today - datetime.timedelta(days=CHANGED_DAYS)).isoformat():
                row["status"] = f"CHANGED on {row['last_changed']}: open the page to see what's new"
            else:
                row["status"] = "No change"
            row.update(fingerprint=fingerprint, signal=signal, next_date=next_date, snippet=snippet,
                       last_checked=stamp)
        rows.append(row)
    return rows, failed
