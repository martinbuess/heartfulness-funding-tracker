"""Leads: calls for startups posted by incubators, water clusters and funders.

Awards like the Nicor Gas Illinois Innovator Award are announced on incubator
and water-cluster websites, not on government portals. Many of those sites
have a free news feed (RSS or WordPress). Each run reads the feeds, keeps the
posts that look like a call (apply, award, challenge, prize, pitch, deadline,
...) and writes them to data/leads.csv for the sheet's Leads tab. Nobody has to
approve anything: leads stay in the file for a year, newest first.

Which feeds to read and which words count as a call live in profile.toml
under [leads], so each founder can tune their own copy.
"""

import csv
import datetime
import email.utils
import html
import json
import os
import re

from tracker.text import clean, fetch

PATH = "data/leads.csv"
COLUMNS = ["first_seen", "posted", "deadline", "source", "title", "link", "why", "summary"]
# Posts older than this when first read are old news, not open calls.
MAX_AGE_DAYS = 120
# Leads no feed shows any more drop out of the file a year after they were first seen.
KEEP_DAYS = 365

_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec")
_DEADLINE = re.compile(
    r"(?:deadline|due|closes?|close date|apply by|applications? (?:are )?(?:due|close)|submit by|until)"
    r"[^.]{0,40}?\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.IGNORECASE)


def _words(words):
    if not words:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")", re.IGNORECASE)


def parse_rss(text):
    """Posts from an RSS feed: title, link, posted date and text."""
    posts = []
    for item in re.findall(r"<item\b[^>]*>(.*?)</item>", text, re.S):
        def tag(name):
            match = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", item, re.S)
            value = match.group(1) if match else ""
            return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", value.strip(), flags=re.S)
        posted = ""
        if tag("pubDate"):
            try:
                posted = email.utils.parsedate_to_datetime(tag("pubDate")).date().isoformat()
            except (TypeError, ValueError):
                pass
        body = tag("content:encoded") or tag("description")
        posts.append({"title": html.unescape(clean(tag("title"))), "link": clean(tag("link")),
                      "posted": posted, "text": html.unescape(clean(body))})
    return posts


def parse_wp(text):
    """Posts from a WordPress REST list (/wp-json/wp/v2/...)."""
    posts = []
    for item in json.loads(text):
        rendered = lambda key: (item.get(key) or {}).get("rendered", "") if isinstance(item.get(key), dict) else ""
        body = rendered("content") or rendered("excerpt")
        posts.append({"title": html.unescape(clean(rendered("title"))), "link": item.get("link", ""),
                      "posted": (item.get("date") or "")[:10], "text": html.unescape(clean(body))})
    return posts


def deadline(text, today):
    """The first deadline in the text that is today or later.

    Returns "closed" when the text gives deadlines and all of them have passed,
    and blank when it gives none.
    """
    passed = False
    for match in _DEADLINE.finditer(text):
        month, day, year = match.groups()
        try:
            date = datetime.datetime.strptime(f"{month[:3]} {day} {year}", "%b %d %Y").date()
        except ValueError:
            continue
        if date >= today:
            return date.isoformat()
        passed = True
    return "closed" if passed else ""


def pick(posts, feed, call_words, title_words, topics, today, skip=None):
    """The posts from one feed that look like a call for startups.

    feed["needs"] says which topic words a post must also have: "water" for
    feeds that cover every industry, "climate" for general startup hubs, blank
    for water and climate groups. Feeds marked "standing" list open programs
    (like Evergreen's award pages), so every post counts, however old.
    """
    found = []
    oldest = (today - datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()
    need = topics.get(feed.get("needs", ""))
    for post in posts:
        standing = feed.get("standing", False)
        if not standing and post["posted"] and post["posted"] < oldest:
            continue
        if skip and skip.search(post["title"]):
            continue
        text = post["title"] + " " + post["text"]
        calls = {m.lower() for m in call_words.findall(text)} if call_words else set()
        # Words like "prize" or "challenge" turn up in plain news stories, so
        # they only count in a title.
        calls = sorted(calls | ({m.lower() for m in title_words.findall(post["title"])} if title_words else set()))
        if standing:
            calls = calls or ["open program"]
        if not calls:
            continue
        # The topic has to be near the top, not in a passing mention further down.
        hits = sorted({m.lower() for m in need.findall(text[:400])}) if need else []
        if need and not hits:
            continue
        due = deadline(text, today)
        if due == "closed":
            continue
        found.append({
            "posted": post["posted"],
            "deadline": due,
            "source": feed["name"],
            "title": post["title"],
            "link": post["link"],
            "why": ", ".join(calls[:4] + hits[:3]),
            "summary": post["text"][:300],
        })
    return found


def collect(today, profile):
    """Read every feed. Returns (leads, failed feed names)."""
    settings = profile.get("leads", {})
    call_words = _words(settings.get("call_words", []))
    title_words = _words(settings.get("call_title_words", []))
    skip = _words(settings.get("skip_title_words", []))
    water = profile.get("filter", {}).get("keywords", [])
    topics = {"water": _words(water), "climate": _words(water + settings.get("climate_words", []))}
    leads, failed = [], []
    for feed in settings.get("feeds", []):
        try:
            text = fetch(feed["url"], timeout=60).decode("utf-8", "replace")
            posts = parse_wp(text) if feed.get("format") == "wordpress" else parse_rss(text)
        except Exception as exc:
            print(f"leads: {feed['name']} FAILED ({exc})")
            failed.append(feed["name"])
            continue
        if not posts:
            # Every feed has posts; none at all means the site sent something else.
            print(f"leads: {feed['name']} FAILED (no posts; got {text[:120]!r})")
            failed.append(feed["name"])
            continue
        picked = pick(posts, feed, call_words, title_words, topics, today, skip)
        print(f"leads: {feed['name']}: {len(posts)} posts, {len(picked)} look like calls")
        leads += picked
    return leads, failed


def load(path=PATH):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def merge(old, fresh, today):
    """Add today's leads to the saved ones (matched by link).

    A saved lead that no feed shows any more drops out a year after it was
    first seen. Leads still in a feed stay, however old the post (Evergreen's
    award pages were first posted years ago and are still open).
    """
    by_link = {row["link"]: row for row in old}
    for row in fresh:
        saved = by_link.get(row["link"])
        by_link[row["link"]] = dict(row, first_seen=saved["first_seen"] if saved else today.isoformat())
    cutoff = (today - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    current = {row["link"] for row in fresh}
    rows = [r for r in by_link.values() if r["link"] in current or r["first_seen"] >= cutoff]
    return sorted(rows, key=lambda r: (r["first_seen"], r["posted"]), reverse=True)


def save(rows, path=PATH):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
