"""One row per call: merges copies of the same call published by different sources.

fundsforNGOs, Terra Viva Grants and the hand-kept calendar often list the same
call (the Global EbA Fund, IKI, Keidanren, ...). Each copy has its own ID, so
without merging the call shows up twice and a decision on one copy doesn't
carry over to the other.

Two listings are treated as the same call when their deadlines agree (equal,
within 2 days, or one of them not given) and either:
  - they have the same funder and their titles share most of their distinctive
    words (the words left after removing the funder's name and generic words like
    "call", "grants", "apply"), or one title has no distinctive words left; or
  - their titles and funders share at least half their meaningful words (70% for
    two posts from the same source, which are usually different calls).
Two EU topics are never merged: each topic ID is a separate call.

The merged row is the best-scoring copy (then the most complete: deadline, link,
labelled fields), with any missing deadline, funder, amount or link filled in from
the other copies. It
lists the other copies in "also_listed" (source and link) and their IDs in
"alias_ids", so the Google Sheet can find a decision made on any copy. Recently
closed copies from the archive are included as aliases too, so a re-posted call
keeps the decision made on the earlier post. The merged row keeps the earliest
first_seen date, so a call is not flagged NEW again when a second source posts it.
"""

import datetime
import re

GENERIC = {
    "a", "an", "and", "the", "of", "for", "to", "in", "on", "by", "with", "at", "from", "its", "is", "now", "new",
    "call", "calls", "proposal", "proposals", "application", "applications", "apply", "open", "opens", "cfa", "cfas",
    "rfp", "rfps", "rfa", "rfas", "eoi", "eois", "nomination", "nominations", "invites", "inviting", "submit",
    "grant", "grants", "program", "programme", "programs", "programmes", "funding", "fund", "funds", "opportunity",
    "opportunities", "scheme", "round", "cycle", "size", "edition", "annual", "letters", "inquiry", "expression",
    "expressions", "interest", "2024", "2025", "2026", "2027", "2028", "1st", "2nd", "3rd", "4th", "5th", "6th",
    "7th", "8th", "9th", "10th", "first", "second", "third", "fourth", "fifth", "up",
}
SOURCE_RANK = {"fundsforngos": 3, "terraviva": 2, "eu-funding": 1, "grants.gov": 1, "calendar": 0}
ARCHIVE_DAYS = 180


def words(text):
    text = re.sub(r"\([^)]*\)", " ", (text or "").lower()).replace("’", "'")
    return {w for w in re.findall(r"[a-z0-9]+", re.sub(r"'s\b", "", text)) if len(w) > 1 and w not in GENERIC}


def funder_key(funder):
    if not funder or funder.startswith("("):
        return ""
    return " ".join(sorted(words(funder)))


def _deadlines_agree(a, b):
    if not a or not b:
        return True
    try:
        gap = abs((datetime.date.fromisoformat(a) - datetime.date.fromisoformat(b)).days)
    except ValueError:
        return a == b
    return gap <= 2


def distinct(a, b):
    """Listings that are certainly different calls: two EU topics have different topic IDs."""
    return a["source"] == b["source"] == "eu-funding" and a["source_id"] != b["source_id"]


def same_call(a, b):
    if a["source"] == b["source"] and a["source_id"] == b["source_id"]:
        return True
    if distinct(a, b):
        return False
    if not _deadlines_agree(a.get("close_date", ""), b.get("close_date", "")):
        return False
    fa, fb = funder_key(a.get("funder", "")), funder_key(b.get("funder", ""))
    if fa and fa == fb:
        funder_words = words(a["funder"])
        da, db = words(a["title"]) - funder_words, words(b["title"]) - funder_words
        if not da or not db:
            return True
        shared = da & db
        return bool(shared) and len(shared) >= 0.6 * min(len(da), len(db))
    ta = words(a["title"]) | words(a.get("funder", ""))
    tb = words(b["title"]) | words(b.get("funder", ""))
    shared = ta & tb
    # Two posts from the same source are usually different calls (e.g. categories of one award),
    # so they need near-identical titles; copies from different sources need half their words.
    need = 0.7 if a["source"] == b["source"] else 0.5
    return len(shared) >= 3 and len(shared) >= need * len(ta | tb)


def _completeness(row):
    # The best-scoring copy wins; among equals, the most complete one.
    return (int(row.get("fit_score") or 0), bool(row.get("close_date")), bool(row.get("link")), row.get("details", "").startswith("structured"),
            bool(row.get("funder")), SOURCE_RANK.get(row["source"], 0))


def _label(row):
    names = {"fundsforngos": "fundsforNGOs", "terraviva": "Terra Viva Grants", "calendar": "Calendar",
             "eu-funding": "EU Funding & Tenders", "grants.gov": "Grants.gov"}
    return f"{names.get(row['source'], row['source'])}: {row.get('link') or row['title']}"


def merge(matches, archived=(), today=None):
    """Matches with copies of the same call merged. Archived rows only add aliases and dates."""
    groups = []
    for row in matches:
        for group in groups:
            if any(same_call(row, other) for other in group) and not any(distinct(row, o) for o in group):
                group.append(row)
                break
        else:
            groups.append([row])
    cutoff = ((today or datetime.date.today()) - datetime.timedelta(days=ARCHIVE_DAYS)).isoformat()
    recent = [r for r in archived if (r.get("closed_on") or r.get("last_seen") or "") >= cutoff]
    out = []
    for group in groups:
        primary = max(group, key=_completeness)
        others = [r for r in group if r is not primary]
        old = [r for r in recent if any(same_call(r, g) for g in group)
               and f"{r['source']}:{r['source_id']}" not in {f"{g['source']}:{g['source_id']}" for g in group}]
        merged = dict(primary)
        merged["first_seen"] = min(r.get("first_seen") or "9999" for r in group + old)
        merged["also_listed"] = "; ".join(_label(r) for r in others)
        merged["alias_ids"] = "; ".join(f"{r['source']}:{r['source_id']}" for r in others + old)
        # Fill gaps in the primary from the other copies.
        for field in ("close_date", "deadline", "funder", "amount", "link"):
            if not merged.get(field) or merged.get(field) == "Not set":
                for r in others:
                    if r.get(field) and r.get(field) != "Not set":
                        merged[field] = r[field]
                        break
        out.append(merged)
    return out
