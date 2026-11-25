"""Is this listing an actionable funding call? Screening before a listing can enter the tracker.

Every listing is put in one of these groups, from the evidence in the listing itself:

  Open      a specific call that is accepting applications now: a call for proposals,
            RFP, prize, challenge, EOI ..., or a stated application deadline still ahead
  Upcoming  a specific call that has been announced but is not open yet (an opening
            date ahead, "coming soon", a Grants.gov forecast, an EU "forthcoming" topic)
  Rolling   a specific program that says it accepts applications or LOIs on a rolling
            or ongoing basis
  Closed    the listing says applications are closed
  Not a call   general fundraising information: articles listing grantmakers, donor
            profiles, advice, case studies, past grants, winners announced, ...
  Unconfirmed  nothing in the listing shows that applications are open, upcoming or rolling

Only Open, Upcoming and Rolling listings go into the tracker. The others are set aside
with the reason (Tracker – Set aside in the sheet, data/filtered_out.csv on GitHub).

Rules kept on purpose:
  - A post's publication date is never read as an opening date.
  - No deadline is never read as "rolling": rolling needs the listing to say so.
  - A funder being active in a field, or having funded similar work, is not a call.
  - Nothing is invented: when a listing doesn't state a deadline, amount or funder, the
    tracker leaves it blank and the sheet says "Verify".

Structured sources (Grants.gov, the EU portal, the hand-kept calendar) state their status
in a field, so they are classified from that field. Aggregator posts (fundsforNGOs, Terra
Viva Grants) are classified from their title and text. fundsforNGOs' feed only carries a
teaser of each post and its pages refuse automated readers, so its posts are judged on the
title and teaser alone.
"""

import datetime
import re

from tracker.text import dates, deadline_in

ACTIONABLE = ("Open", "Upcoming", "Rolling")

# fundsforNGOs sections that only hold articles, never calls.
ARTICLE_SECTIONS = ("/articles-searching-grants-and-donors/", "/grant-writing/", "/proposal-writing/",
                    "/fundraising-", "/ngo-management/", "/how-to-")

# Titles of general information, not calls. Checked only when the title doesn't announce a call.
_INFO_TITLE = re.compile(
    r"^\d+\s+(?:\w+\s+){0,4}?(grantmakers?|donors?|donor agencies|funders?|foundations?|funding (?:routes|sources|options|ideas)"
    r"|places|ways|tips|grants to explore|organi[sz]ations|sources|resources|mistakes|questions|lessons|steps|things)\b"
    r"|^(who funds|where (?:small )?(?:ngos|organi[sz]ations|you) can find|how (?:to|can|do|does|ngos)|what (?:do|does|is|are|"
    r"ngos|indian ngos|should)|why |beyond |after the |can an? |is your |are you |inside |meet |the (?:farmer|story|case)"
    r"|top \d+|best \d+|a guide|guide to|lessons from)"
    r"|\b(case study|cheat sheet|explained|explainer|checklist|toolkit|template|interview|profile of|donor profile"
    r"|what (?:\w+ ){0,4}reveal|winners? announced|announces? (?:the |its |\d{4} |new ){0,2}(?:winners|grantees|recipients|awardees|grant recipients|laureates)"
    r"|recipients announced|grantees announced|shortlist announced|awarded to|webinar recap|annual report)\b",
    re.IGNORECASE)
_QUESTION = re.compile(r"\?\s*(\(|$)")

# Evidence that applications are open now.
_OPEN = re.compile(
    r"\bcalls? for (proposals|applications|nominations|concept notes|expressions? of interest|letters of (inquiry|intent)"
    r"|submissions|entries|projects|innovations|solutions|grant applications|participants|partners|proposal)"
    r"|\brequests? for (proposals|applications|concept notes|expressions of interest)"
    r"|\b(rfps?|rfas?|cfps?|cfas?|eois?|lois?)\b(?!\s*template)"
    r"|\bapplications? (?:are |is )?(?:now )?(?:open|invited|welcome|being accepted)"
    r"|\bopen(?:ed)? for (applications|proposals|nominations|submissions)"
    r"|\b(?:now |is |are )?accepting (applications|proposals|nominations|submissions|letters|concept notes|entries)"
    r"|\b(?:invites?|inviting|welcomes?|seeks?|seeking|calls? on) (?:\w+ ){0,5}?(applications|proposals|nominations"
    r"|submissions|concept notes|letters of (?:inquiry|intent)|expressions of interest|entries|eligible|ngos|organi[sz]ations"
    r"|civil society|non-?profits|applicants|innovators)"
    r"|\bapply (now|for|by|before|online|here|today|through)\b|^apply\b|\bhow to apply\b"
    r"|\bopen call\b|\bnominations? (?:are )?open|\bsubmit (?:your |a |an )?(proposals?|applications?|concept notes?|nominations?"
    r"|letters? of (?:inquiry|intent)|entries|projects?)"
    r"|\bsubmission (window|deadline)|\bapplication (window|deadline|period)|\bdeadline\s*:"
    r"|^(?:\w+ )?calls? for\b|\bentries (?:are )?(?:now )?open|\bapplications? (?:are |is )?(?:now )?accepted"
    r"|\b(?:opens|launches|has (?:opened|launched)) (?:its |a |the |new |\d{4} )?(?:\w+ ){0,4}?(grants?|calls?|funding"
    r"|fund|program(?:me)?|competition|challenge|prize|awards?|applications)"
    r"|\binvit\w* (?:\w+ ){0,6}?to (?:apply|submit|participate|take part|enter|nominate)"
    r"|\bis (?:now )?open (?:from|until|till|for applications|to (?:all|applicants|ngos|organi[sz]ations))",
    re.IGNORECASE)
# Evidence that a call is announced but not open yet (needs a date ahead, or "coming soon").
_UPCOMING = re.compile(
    r"\b(will (?:open|launch|be (?:open|launched|announced|available))|opens? (?:on|from|in)|opening (?:date|on)"
    r"|applications? (?:will )?open (?:on|from|in)|to be launched|expected to open|launch(?:es)? (?:on|in)"
    r"|official launch)\b", re.IGNORECASE)
_SOON = re.compile(r"\b(coming soon|opening soon|forthcoming call|upcoming call|pre-?announcement|save the date)\b",
                   re.IGNORECASE)
# Evidence of rolling applications (it must be said; no deadline is not enough).
_ROLLING = re.compile(
    r"\b(rolling basis|on a rolling|rolling (?:applications|deadlines?|intake|submissions|admissions|call)"
    r"|accepted (?:at )?any ?time|(?:applications|proposals|letters of inquiry|lois) (?:are )?accepted (?:throughout|all) "
    r"(?:the|year)|year[- ]round|throughout the year|ongoing basis|on an ongoing|open[- ]ended call|no (?:fixed )?deadline"
    r"|open until (?:further notice|funds)|continuous(?:ly)? (?:open|accepting)|accepts? (?:applications|proposals|"
    r"letters of inquiry|lois|unsolicited proposals) (?:on a rolling|at any time|year-round|continuously))\b",
    re.IGNORECASE)
_CLOSED = re.compile(
    r"\b(applications? (?:are |is )?(?:now )?closed|(?:call|round|submissions?) (?:is |are |has |have )?(?:now )?"
    r"(?:been )?closed|no longer accepting|closed for (?:applications|submissions|this (?:year|round|cycle))"
    r"|not (?:currently )?accepting (?:applications|proposals|unsolicited))\b", re.IGNORECASE)


def _quote(match, text, width=70):
    start = max(0, match.start() - 15)
    return "“" + " ".join(text[start:match.end() + width - 15].split()).strip(" ,.;") + "…”"


def classify(row, text=None, today=None):
    """(status, evidence) for a listing. text defaults to its title and summary."""
    today = today or datetime.date.today()
    source = row["source"]
    close = row.get("close_date", "")
    if source == "grants.gov":
        if row.get("status") == "forecast":
            return "Upcoming", "Grants.gov forecast (not yet posted for applications)"
        return "Open", "posted on Grants.gov" + (f", closes {close}" if close else "")
    if source == "eu-funding":
        if row.get("status") == "forecast":
            return "Upcoming", "EU portal lists the topic as forthcoming" + (f"; deadline {close}" if close else "")
        return "Open", "EU portal lists the topic as open" + (f"; deadline {close}" if close else "")
    if source == "calendar":
        if row.get("status") == "forecast":
            return "Upcoming", f"calendar: opens {row.get('post_date', '')}"
        if not close:
            return "Rolling", "calendar: marked as a rolling program"
        return "Open", f"calendar: open, closes {close}"

    title = row["title"]
    body = text if text is not None else f"{row.get('summary', '')} {row.get('eligibility_notes', '')}"
    link = row.get("link", "")
    open_in_title = _OPEN.search(title)
    if any(section in link for section in ARTICLE_SECTIONS):
        return "Not a call", "fundsforNGOs article section (donor lists and advice, not calls)"
    if not open_in_title:
        info = _INFO_TITLE.search(title) or _QUESTION.search(title)
        if info:
            return "Not a call", f"the title reads as an article, not a call: {_quote(info, title, 40)}"
    closed = _CLOSED.search(body)
    if closed and not open_in_title:
        return "Closed", f"the listing says {_quote(closed, body)}"
    future = [d for d in dates(body) if d > today]
    upcoming = _UPCOMING.search(body) or _UPCOMING.search(title)
    if upcoming:
        near = dates((body if _UPCOMING.search(body) else title)[upcoming.start():upcoming.end() + 60])
        if near and near[0] > today:
            return "Upcoming", f"opens {near[0].isoformat()}: {_quote(upcoming, body if _UPCOMING.search(body) else title)}"
    soon = _SOON.search(title) or _SOON.search(body)
    if soon:
        return "Upcoming", f"{_quote(soon, title if _SOON.search(title) else body)}"
    rolling = _ROLLING.search(body) or _ROLLING.search(title)
    if rolling:
        return "Rolling", f"{_quote(rolling, body if _ROLLING.search(body) else title)}"
    if not close:
        stated = deadline_in(body) or deadline_in(title)
        if stated and stated < today:
            return "Closed", f"the deadline it states, {stated.isoformat()}, has passed"
        close = stated.isoformat() if stated else ""
    if close and close >= today.isoformat():
        return "Open", f"application deadline {close} stated in the listing"
    found = open_in_title or _OPEN.search(body)
    if found:
        where = title if open_in_title else body
        return "Open", f"{_quote(found, where)}"
    if future and source == "terraviva":
        # Terra Viva Funding News posts are calls; a date ahead in one is its deadline or opening.
        return "Open", f"Terra Viva call with a date ahead ({future[0].isoformat()}); check the deadline"
    return "Unconfirmed", "nothing in the listing says applications are open, upcoming or rolling"


def reason(status, evidence):
    """The set-aside reason for a listing that is not actionable."""
    label = {"Not a call": "not a funding call", "Closed": "call closed",
             "Unconfirmed": "not confirmed as an open call"}[status]
    return f"{label}: {evidence}"
