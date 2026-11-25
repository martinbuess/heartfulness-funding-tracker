"""Check a call against the funder's own page, when the listing links to it.

Terra Viva Grants posts link to the funder's announcement. For calls that made it into the
tracker with a fit of 3 or more, the daily run reads that page (at most MAX_PER_RUN pages,
each one at most once a week, and only if the site's robots.txt allows it) and looks for
the same wording the watched pages use: "applications are open", "applications are closed",
and dates ahead.

  - The funder's page says applications are closed, with no date ahead: the call is set
    aside ("call closed: the funder's page says applications are closed").
  - It says applications are open: "confirmed on the funder's page" is added to the evidence.
  - Anything else (no clear wording, or the page can't be read) changes nothing; the sheet
    keeps "Verify" for the call's status.

fundsforNGOs posts carry no link to the funder in their feed, and fundsforNGOs' own pages
refuse automated readers, so those can't be checked this way.
"""

import datetime

from tracker import watch
from tracker.text import fetch

MAX_PER_RUN = 15
RECHECK_DAYS = 7
MIN_FIT = 3


def due(row, today):
    if not row.get("official_link") or int(row.get("fit_score") or 0) < MIN_FIT:
        return False
    last = (row.get("primary_check") or "")[:10]
    return not last or last <= (today - datetime.timedelta(days=RECHECK_DAYS)).isoformat()


def check(rows, today, get=None):
    """Check due rows against their funder's page. Returns how many were set to Closed."""
    get = get or (lambda url: fetch(url, timeout=45).decode("utf-8", "replace"))
    closed = 0
    for row in [r for r in rows if due(r, today)][:MAX_PER_RUN]:
        stamp = today.isoformat()
        try:
            _, signal, next_date, _ = watch.read(get(row["official_link"]), today)
        except Exception as exc:  # down, blocked by robots.txt, refusing automated readers
            row["primary_check"] = f"{stamp}: funder's page could not be read ({str(exc)[:80]})"
            continue
        if signal == "Says closed" and not next_date:
            row["call_status"] = "Closed"
            row["status_evidence"] = "the funder's page says applications are closed"
            row["primary_check"] = f"{stamp}: says closed"
            closed += 1
        elif signal == "Says open":
            row["primary_check"] = f"{stamp}: says open" + (f", next date {next_date}" if next_date else "")
            if "confirmed on the funder's page" not in row.get("status_evidence", ""):
                row["status_evidence"] = (row.get("status_evidence", "") + "; confirmed on the funder's page").lstrip("; ")
        else:
            row["primary_check"] = f"{stamp}: no clear open/closed wording" + (
                f", next date {next_date}" if next_date else "")
    return closed
