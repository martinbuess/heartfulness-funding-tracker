"""Daily run: pull every source, refresh the pool, write the profile matches.

    python -m tracker.run                 # normal daily run
    python -m tracker.run --xml FILE      # use a local Grants.gov extract
"""

import argparse
import datetime

import collections
import csv
import os

from tracker import (bonfire, buffalo, california, chicago, cleveland, federalregister, glri, grantsgov, illinois,
                     leads, massachusetts, metcouncil, mmsd, mwrd, nsf, nyc, opengov, plain, pool, prizes, profile,
                     programs, samgov, sbir, virginia)

POOL_PATH = "data/listings.csv"
MATCHES_PATH = "data/matches.csv"
FILTERED_PATH = "data/filtered_out.csv"
SUMMARY_PATH = "data/summary.csv"
# How many days in a row each source has failed, so a one-day outage doesn't fail the run.
STREAK_PATH = "data/failures.csv"
# The run fails (and GitHub sends its failure email) once a source has failed this many days running.
FAIL_AFTER_DAYS = 3
# Closed water listings, one file per year so each stays well under GitHub's file limit.
ARCHIVE_PATH = "data/archive/{year}.csv"

# How each source is described in data/summary.csv (and the sheet's About tab).
ABOUT = {
    "grants.gov": ("Grants.gov", "Federal", "All federal grants and cooperative agreements, including forecasts"),
    "sam.gov": ("SAM.gov", "Federal", "Federal contract opportunities in R&D, environmental, sensors, data, inspection, engineering and drones"),
    "federalregister": ("Federal Register", "Federal", "Funding and prize notices published by agencies"),
    "grants.ca.gov": ("California Grants Portal", "State (CA)", "California state grants and loans"),
    "illinois-gata": ("Illinois GATA", "State (IL)", "Illinois state funding opportunities"),
    "commbuys": ("Massachusetts COMMBUYS", "State (MA)", "Massachusetts state and local bids, plus some grants"),
    "eva-virginia": ("Virginia eVA", "State (VA)", "Virginia state and local solicitations"),
    "nyc-city-record": ("NYC City Record", "City (New York)", "New York City solicitations"),
    "chicago-eprocurement": ("Chicago eProcurement", "City (Chicago)", "City of Chicago bids"),
    "mwrd": ("MWRD (Chicago)", "Water agency", "Metropolitan Water Reclamation District bids"),
    "bonfire": ("Great Lakes Water Authority", "Water agency", "Detroit-area regional water authority bids"),
    "opengov": ("NEORSD (Cleveland)", "Water agency", "Northeast Ohio Regional Sewer District bids"),
    "mmsd": ("MMSD (Milwaukee)", "Water agency", "Milwaukee Metropolitan Sewerage District bids, RFPs and RFIs"),
    "buffalo-sewer": ("Buffalo Sewer Authority", "Water agency", "Buffalo Sewer Authority bids and RFPs"),
    "cleveland": ("City of Cleveland", "City (Cleveland)", "City bids and RFPs, including the Division of Water"),
    "metcouncil": ("Met Council (Minneapolis)", "Water agency", "Metropolitan Council bids, RFPs and RFIs, including regional wastewater"),
    "sbir.gov": ("SBIR.gov topics", "Federal", "Open and upcoming SBIR/STTR research topics from every agency, including Defense"),
    "nsf-sbir": ("NSF SBIR/STTR", "Federal", "NSF small-business research deadlines in the next 30 days"),
    "glri": ("Great Lakes Restoration Initiative", "Federal", "Open opportunities listed on the GLRI funding page (Grants.gov links skipped)"),
    "prizes": ("Army xTech, Bureau of Reclamation", "Prizes", "Open prize competitions"),
    "calendar": ("Calendar (hand-kept)", "Programs", "Yearly accelerators, prizes and grants kept in the sheet's Calendar tab"),
}


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

    sources = [
        ("grants.gov", lambda: grantsgov.collect(today, xml_source=args.xml)),
        ("grants.ca.gov", lambda: california.collect(today)),
        ("nyc-city-record", lambda: nyc.collect(today)),
        ("sam.gov", lambda: samgov.collect(today)),
        ("federalregister", lambda: federalregister.collect(today)),
        ("mwrd", lambda: mwrd.collect(today)),
        ("chicago-eprocurement", lambda: chicago.collect(today)),
        ("bonfire", lambda: bonfire.collect(today)),
        ("opengov", lambda: opengov.collect(today)),
        ("mmsd", lambda: mmsd.collect(today)),
        ("buffalo-sewer", lambda: buffalo.collect(today)),
        ("cleveland", lambda: cleveland.collect(today)),
        ("metcouncil", lambda: metcouncil.collect(today)),
        ("sbir.gov", lambda: sbir.collect(today)),
        ("nsf-sbir", lambda: nsf.collect(today)),
        ("illinois-gata", lambda: illinois.collect(today)),
        ("commbuys", lambda: massachusetts.collect(today)),
        ("eva-virginia", lambda: virginia.collect(today)),
        ("glri", lambda: glri.collect(today)),
        ("prizes", lambda: prizes.collect(today)),
        ("calendar", lambda: programs.collect(today, url=calendar_url)),
    ]
    failed = []
    closed = []
    for name, collect in sources:
        try:
            fresh = collect()
        except Exception as exc:
            # Keep yesterday's rows for this source and carry on with the rest.
            print(f"{name}: FAILED ({exc}); keeping previous listings")
            failed.append(name)
            continue
        gone = pool.closed(rows, name, fresh)
        if not fresh and len(gone) >= 10:
            # A big source that suddenly returns nothing has more likely broken than closed everything.
            print(f"{name}: FAILED (no listings returned); keeping previous listings")
            failed.append(name)
            continue
        closed += gone
        rows = pool.merge(rows, name, fresh, today)
        print(f"{name}: {len(fresh)} open listings")

    # Leads: calls posted on incubator and water-cluster news feeds. A feed that
    # is down only means no new leads from it today, so it doesn't fail the run.
    fresh_leads, leads_failed = leads.collect(today, prof)
    lead_rows = leads.merge(leads.load(), fresh_leads, today)
    leads.save(lead_rows)
    print(f"leads: {len(fresh_leads)} calls in the feeds today, {len(lead_rows)} in {leads.PATH}")

    plain.add(rows)
    pool.save(POOL_PATH, rows)
    dropped = []
    matches = profile.apply(prof, rows, dropped)
    to_archive = profile.on_topic(prof, closed)
    archive_path = ARCHIVE_PATH.format(year=today.year)
    archived = pool.archive(archive_path, to_archive)
    print(f"archive: {len(to_archive)} water listings closed today, {archived} in {archive_path}")
    pool.save(MATCHES_PATH, matches)
    pool.save(FILTERED_PATH, [dict(row, filtered_reason=reason) for row, reason in dropped],
              extra=["filtered_reason"])
    streaks = update_streaks(STREAK_PATH, failed)
    save_summary(SUMMARY_PATH, today, rows, matches, dropped, failed,
                 programs.checks(today, programs.read_mirror()), lead_rows, leads_failed, streaks)
    print(f"pool: {len(rows)} listings, {len(matches)} match {args.profile}, "
          f"{len(dropped)} more set aside as not biddable (see {FILTERED_PATH})")
    broken = [name for name in failed if streaks[name] >= FAIL_AFTER_DAYS]
    if broken:
        raise SystemExit(f"sources failed {FAIL_AFTER_DAYS} days in a row: {', '.join(broken)}")
    if failed:
        print(f"sources failed today (not yet {FAIL_AFTER_DAYS} days in a row): {', '.join(failed)}")


def update_streaks(path, failed):
    """Days in a row each failed source has failed, counting today. Saved for the next run."""
    previous = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            previous = {row["source"]: int(row["days"]) for row in csv.DictReader(f)}
    streaks = {name: previous.get(name, 0) + 1 for name in failed}
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "days"])
        writer.writerows(sorted(streaks.items()))
    return streaks


def save_summary(path, today, rows, matches, dropped, failed, calendar_checks=(), lead_rows=(), leads_failed=(),
                 streaks=None):
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
            note = (f"Failed {days} days in a row; showing the last listings it gave. " if days > 1
                    else "Failed today; showing yesterday's listings. ")
        out.append(["source", label, level, pool_by[source], match_by[source], drop_by[source], note + covers])
    for name, n in collections.Counter(r["kind"] for r in matches).most_common():
        out.append(["kind", name, "", "", n, "", ""])
    for name, n in collections.Counter(r["stage"] for r in matches).most_common():
        out.append(["stage", name, "", "", n, "", ""])
    for name, n in collections.Counter(r["who_can_apply"] for r in matches).most_common():
        out.append(["who", name, "", "", n, "", ""])
    labels = {"construction bid": "Construction bids", "set-aside": "Certification-only set-asides",
              "off-topic bid": "Off-topic bids (supplies, grounds, building services)",
              "not open to businesses": "Grants closed to companies"}
    reasons = collections.Counter(labels.get(reason.split(":")[0], reason) for _, reason in dropped)
    for name, n in reasons.most_common():
        out.append(["set_aside", name, "", "", "", n, ""])
    new_today = sum(1 for r in matches if r["first_seen"] == today.isoformat())
    out.append(["new", "New matches today", "", "", new_today, "", ""])
    # Calendar rows a person should update (shown on the About tab).
    for program, todo in calendar_checks:
        out.append(["calendar_check", program, "", "", "", "", todo])
    # Leads tab: how many are new today, and any feed that could not be read.
    out.append(["leads", "New leads today", "", "", sum(1 for r in lead_rows if r["first_seen"] == today.isoformat()),
                "", f"{len(lead_rows)} leads in the last year"])
    for name in leads_failed:
        out.append(["leads_failed", name, "", "", "", "", "Feed could not be read today"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)


if __name__ == "__main__":
    main()
