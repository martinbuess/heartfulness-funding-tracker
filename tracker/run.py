"""Daily run: pull every source, refresh the pool, score the FBH matches.

    python -m tracker.run                 # normal daily run
    python -m tracker.run --xml FILE      # use a local Grants.gov extract
"""

import argparse
import collections
import csv
import datetime
import os

from tracker import eufunding, feeds, grantsgov, leads, plain, pool, profile, programs, watch

POOL_PATH = "data/listings.csv"
MATCHES_PATH = "data/matches.csv"
OPPORTUNITIES_PATH = "data/opportunities.csv"
FILTERED_PATH = "data/filtered_out.csv"
SUMMARY_PATH = "data/summary.csv"
# How many days in a row each source has failed, so a one-day outage doesn't fail the run.
STREAK_PATH = "data/failures.csv"
# The run fails (and GitHub sends its failure email) once a source has failed this many days running.
FAIL_AFTER_DAYS = 3
# Closed and expired FBH-relevant listings, one file per year.
ARCHIVE_PATH = "data/archive/{year}.csv"
# Listings first seen this many days ago or less are marked NEW.
NEW_DAYS = 7
# Deadlines this close are marked "Closing soon".
SOON_DAYS = 21

# How each source is described in data/summary.csv (and the sheet's About tab).
# Aggregator feeds from profile.toml are added to this at the start of each run.
ABOUT = {
    "eu-funding": ("EU Funding & Tenders", "Multilateral", "Open and upcoming EU calls on FBH topics (India usually only as a consortium partner)"),
    "grants.gov": ("Grants.gov", "US federal", "US federal grants; only those open to foreign or international applicants are kept"),
    "calendar": ("Calendar (hand-kept)", "Programs", "Yearly programs with no feed, kept by hand in data/calendar.csv"),
}

# The columns of data/opportunities.csv, the file the Google Sheet shows, in order.
OPPORTUNITY_COLUMNS = [
    ("flag", "Flag"), ("fit_score", "Fit (1-5)"), ("funder", "Funder"), ("title", "Grant / program"),
    ("deadline", "Deadline"), ("amount", "Amount"), ("fbh_topics", "Fits these FBH topics"), ("fbh_area", "FBH area"),
    ("geography", "Geography"), ("who_can_apply", "Who can apply"),
    ("eligibility_check", "Eligibility: confirmed vs. to verify"), ("fit_reason", "Why this score"), ("link", "Link"),
    ("in_pipeline", "In pipeline"), ("kind", "Kind"), ("source_label", "Source"), ("last_seen", "Last verified"),
    ("first_seen", "First seen"), ("short_summary", "Summary"), ("uid", "ID"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", help="local Grants.gov extract instead of downloading")
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    parser.add_argument("--profile", default="profile.toml")
    args = parser.parse_args()

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    rows = pool.load(POOL_PATH)
    prof = profile.load(args.profile)
    calendar_url = prof.get("calendar", {}).get("sheet_csv", "")
    aggregators = {feed["source"]: feed for feed in prof.get("aggregators", [])}
    for source, feed in aggregators.items():
        ABOUT.setdefault(source, (feed["name"], "Aggregator", feed.get("about", "")))

    sources = [(source, lambda feed=feed: feeds.collect(today, feed)) for source, feed in aggregators.items()]
    sources += [
        ("eu-funding", lambda: eufunding.collect(today, prof.get("eu_funding", {}))),
        ("grants.gov", lambda: grantsgov.collect(today, xml_source=args.xml)),
        ("calendar", lambda: programs.collect(today, url=calendar_url)),
    ]
    failed = []
    closed = []
    for name, collect in sources:
        try:
            fresh = collect()
        except Exception as exc:
            # Keep the previous rows for this source and carry on with the rest.
            print(f"{name}: FAILED ({exc}); keeping previous listings")
            failed.append(name)
            continue
        if name in aggregators:
            fresh = _keep_until_deadline(rows, name, fresh, today, aggregators[name].get("keep_days", 120),
                                         aggregators[name].get("title_separator", ""))
        gone = pool.closed(rows, name, fresh)
        if not fresh and len(gone) >= 10:
            # A big source that suddenly returns nothing has more likely broken than closed everything.
            print(f"{name}: FAILED (no listings returned); keeping previous listings")
            failed.append(name)
            continue
        closed += gone
        rows = pool.merge(rows, name, fresh, today)
        print(f"{name}: {len(fresh)} open listings")

    # Listings whose deadline has passed (for example from a source that failed today) are expired.
    expired = [r for r in rows if r["close_date"] and r["close_date"] < today.isoformat()]
    if expired:
        rows = [r for r in rows if not (r["close_date"] and r["close_date"] < today.isoformat())]
        closed += expired

    # Leads: calls posted on funder news feeds. A feed that is down only means no
    # new leads from it today, so it doesn't fail the run.
    fresh_leads, leads_failed = leads.collect(today, prof)
    lead_rows = leads.merge(leads.load(), fresh_leads, today)
    leads.save(lead_rows)

    # Watched pages: funders' apply pages with no feed. A page that can't be read
    # is reported on the sheet; it doesn't fail the run.
    watch_rows, watch_failed = watch.check(prof.get("watch", {}).get("pages", []), today, watch.load())
    watch.save(watch_rows)
    print(f"watched pages: {len(watch_rows)} checked, "
          f"{sum(r['status'].startswith('CHANGED') for r in watch_rows)} changed, {len(watch_failed)} not read")

    plain.add(rows)
    pool.save(POOL_PATH, rows)
    dropped = []
    matches = profile.apply(prof, rows, dropped)
    to_archive = profile.on_topic(prof, closed)
    archive_path = ARCHIVE_PATH.format(year=today.year)
    archived = pool.archive(archive_path, to_archive, today)
    print(f"archive: {len(to_archive)} relevant listings closed or expired today, {archived} in {archive_path}")
    pool.save(MATCHES_PATH, matches)
    save_opportunities(OPPORTUNITIES_PATH, matches, today, failed)
    pool.save(FILTERED_PATH, [dict(row, filtered_reason=reason) for row, reason in dropped],
              extra=["filtered_reason"])
    streaks = update_streaks(STREAK_PATH, failed)
    save_summary(SUMMARY_PATH, today, rows, matches, dropped, failed,
                 programs.checks(today, programs.read_mirror()), lead_rows, leads_failed, streaks, len(to_archive),
                 watch_rows)
    print(f"pool: {len(rows)} listings, {len(matches)} fit FBH, "
          f"{len(dropped)} more set aside by a rule (see {FILTERED_PATH})")
    broken = [name for name in failed if streaks[name] >= FAIL_AFTER_DAYS]
    if broken:
        raise SystemExit(f"sources failed {FAIL_AFTER_DAYS} days in a row: {', '.join(broken)}")
    if failed:
        print(f"sources failed today (not yet {FAIL_AFTER_DAYS} days in a row): {', '.join(failed)}")


def _keep_until_deadline(previous, source, fresh, today, keep_days, separator=""):
    """Add back this source's earlier listings that left the feed but are still open.

    Listings saved before the feed reader understood labelled fields are read
    again from their saved text, and old whole-roundup listings are dropped
    (each call in a roundup is now its own listing).
    """
    seen = {r["source_id"] for r in fresh}
    links = {r["link"] for r in fresh}
    kept = []
    for row in previous:
        if row["source"] != source or row["source_id"] in seen or row["link"] in links or "/listing/" in row["link"]:
            continue
        row = dict(row)
        if not row.get("details"):
            row = feeds.reread(row, separator)
        if feeds.still_open(row, today, keep_days):
            kept.append(row)
            links.add(row["link"])
    return fresh + kept


def flag(row, today, failed):
    """A short label for the sheet: NEW, Closing soon, Coming soon, Source down."""
    flags = []
    if row["source"] in failed:
        flags.append("Source down today (not re-checked)")
    if row.get("first_seen", "") >= (today - datetime.timedelta(days=NEW_DAYS)).isoformat():
        flags.append("NEW")
    if row["close_date"] and row["close_date"] <= (today + datetime.timedelta(days=SOON_DAYS)).isoformat():
        flags.append("Closing soon")
    if row.get("stage") == "Coming soon":
        flags.append("Coming soon")
    return ", ".join(flags) or "Open"


def save_opportunities(path, matches, today, failed):
    """The sheet-ready file: friendly column names, best fit first."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in OPPORTUNITY_COLUMNS])
        for row in matches:
            row = dict(row, flag=flag(row, today, failed), source_label=ABOUT.get(row["source"], (row["source"],))[0],
                       uid=f"{row['source']}:{row['source_id']}", funder=row["funder"] or "(see link)")
            writer.writerow([row.get(key, "") for key, _ in OPPORTUNITY_COLUMNS])


def update_streaks(path, failed):
    """Days in a row each failed source has failed, counting today. Saved for the next run."""
    previous = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            previous = {row["source"]: int(row["days"]) for row in csv.DictReader(f)}
    streaks = {name: previous.get(name, 0) + 1 for name in failed}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "days"])
        writer.writerows(sorted(streaks.items()))
    return streaks


def save_summary(path, today, rows, matches, dropped, failed, calendar_checks=(), lead_rows=(), leads_failed=(),
                 streaks=None, archived_today=0, watch_rows=()):
    """A small table of today's counts, for the sheet's About tab."""
    pool_by = collections.Counter(r["source"] for r in rows)
    match_by = collections.Counter(r["source"] for r in matches)
    drop_by = collections.Counter(r["source"] for r, _ in dropped)
    out = [["section", "name", "level", "open", "matches", "set_aside", "detail"],
           ["run", "Last refresh", "", "", "", "", today.isoformat()],
           ["total", "All sources", "", len(rows), len(matches), len(dropped), f"{len(ABOUT)} sources"]]
    for source, (label, level, covers) in ABOUT.items():
        days = (streaks or {}).get(source, 1)
        note = ""
        if source in failed:
            note = (f"FAILED {days} days in a row; showing the last listings it gave. " if days > 1
                    else "FAILED today; showing yesterday's listings. ")
        out.append(["source", label, level, pool_by[source], match_by[source], drop_by[source], note + covers])
    for score in "54321":
        out.append(["score", f"Fit {score}", "", "", sum(1 for r in matches if r["fit_score"] == score), "", ""])
    areas = collections.Counter(a for r in matches for a in r["fbh_area"].split("; ") if a)
    for name, n in areas.most_common():
        out.append(["area", name, "", "", n, "", ""])
    reasons = collections.Counter(reason.split(":")[0] for _, reason in dropped)
    for name, n in reasons.most_common():
        out.append(["set_aside", name, "", "", "", n, ""])
    new_since = (today - datetime.timedelta(days=NEW_DAYS)).isoformat()
    out.append(["new", "New in the last 7 days", "", "", sum(1 for r in matches if r["first_seen"] >= new_since), "", ""])
    out.append(["archived", "Closed or expired today", "", "", archived_today, "", "moved to data/archive/"])
    for program, todo in calendar_checks:
        out.append(["calendar_check", program, "", "", "", "", todo])
    out.append(["leads", "New leads today", "", "", sum(1 for r in lead_rows if r["first_seen"] == today.isoformat()),
                "", f"{len(lead_rows)} leads in the last year"])
    for name in leads_failed:
        out.append(["leads_failed", name, "", "", "", "", "Feed could not be read today"])
    out.append(["watch", "Watched pages changed", "", len(watch_rows),
                sum(r["status"].startswith("CHANGED") for r in watch_rows),
                sum(not r["status"].startswith(("CHANGED", "No change", "First")) for r in watch_rows),
                "Tracker – Watched pages tab"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)


if __name__ == "__main__":
    main()
