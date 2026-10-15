"""Collector for City of Chicago eProcurement solicitations (public abstracts
page, no login). Covers bids run through eProcurement, including the
Department of Water Management. Bids posted only in the weekly PDF are not covered.
"""

import datetime
import html
import re

from tracker.text import clean, fetch

ABSTRACTS_URL = "https://eprocurement.cityofchicago.org/OA_HTML/OA.jsp?OAFunc=PON_ABSTRACT_PAGE"

_CELL = re.compile(r'<span id="N13:(\w+):(\d+)"[^>]*>([^<]*)</span>')


def _date(text):
    """'30-NOV-2026 11:00:00' -> '2026-11-30'."""
    try:
        return datetime.datetime.strptime(text.split()[0].title(), "%d-%b-%Y").date().isoformat()
    except (ValueError, IndexError):
        return ""


def decode(raw):
    """The page says UTF-8, but titles pasted from Word arrive as Windows-1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse(page):
    rows = {}
    for field, index, value in _CELL.findall(page):
        rows.setdefault(int(index), {})[field] = html.unescape(value).strip()
    return [rows[i] for i in sorted(rows)]


def normalize(row):
    market = row.get("COC_PROTECTED_MARKETS", "")
    eligibility = "Any vendor"
    if "target market" in market.lower():
        # Target Market bids are reserved for City-certified small, minority or women-owned firms.
        eligibility = "Any vendor; Target Market set-aside (City-certified MBE/WBE firms only)"
    goals = row.get("COC_COMPLIANCE_GOALS", "")
    summary = "; ".join(p for p in (
        f"Spec {row['COC_SPEC_NUMBER']}" if row.get("COC_SPEC_NUMBER") else "",
        f"Compliance goals: {goals}" if goals and goals.upper() not in ("NA", "NONE") else "",
        f"Questions due {_date(row.get('COC_DEADLINE_FOR_QUESTION', ''))}" if row.get("COC_DEADLINE_FOR_QUESTION") else "",
    ) if p)
    event = row.get("EVENT", "")
    department = row.get("CocDepartmentName", "").title()
    if not department.startswith("Chicago"):
        department = f"Chicago {department}".strip()
    return {
        "source": "chicago-eprocurement",
        "source_id": row.get("NEGOTIATION_NUM", ""),
        "title": clean(row.get("TITLE")),
        "funder": department,
        "funder_code": "CHI",
        "listing_type": f"Contract ({event})" if event else "Contract",
        "status": "posted",
        "post_date": _date(row.get("PREVIEW_DATE", "")),
        "close_date": _date(row.get("CLOSE_DATE", "")),
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": eligibility,
        "topics": event,
        "location": "Chicago, IL",
        "link": ABSTRACTS_URL,
        "summary": summary[:600],
    }


def collect(today, page=None):
    """Return open Chicago solicitations in the common format.

    The page lists the newest due dates first, so every open bid is on it.
    Pass page (the abstracts HTML) to skip the download, e.g. in tests.
    """
    if page is None:
        page = decode(fetch(ABSTRACTS_URL, timeout=120))
    rows = [normalize(r) for r in parse(page)]
    return [r for r in rows if r["close_date"] >= today.isoformat()]
