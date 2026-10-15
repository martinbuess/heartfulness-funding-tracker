"""The data pool: one CSV of open listings, refreshed per source each run."""

import csv
import os

from tracker.schema import FIELDS


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(path, rows, extra=()):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["close_date"] or "9999-99-99", r["source"], r["source_id"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS + list(extra), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def closed(previous, source, fresh):
    """Rows of this source that were open before but are missing from the fresh pull."""
    still_open = {r["source_id"] for r in fresh}
    return [r for r in previous if r["source"] == source and r["source_id"] not in still_open]


def archive(path, rows):
    """Add closed listings to the archive, keeping one row per listing."""
    kept = {(r["source"], r["source_id"]): r for r in load(path)}
    for row in rows:
        kept[(row["source"], row["source_id"])] = row
    save(path, kept.values())
    return len(kept)


def merge(previous, source, fresh, today):
    """Replace one source's rows with a fresh pull, keeping first_seen dates.

    Rows from other sources are left as they were, so one failing collector
    never wipes the rest of the pool. Listings missing from the fresh pull
    have closed and drop out.
    """
    first_seen = {r["source_id"]: r["first_seen"] for r in previous if r["source"] == source}
    kept = [r for r in previous if r["source"] != source]
    stamp = today.isoformat()
    for row in fresh:
        row["first_seen"] = first_seen.get(row["source_id"], stamp)
        row["last_seen"] = stamp
    return kept + fresh
