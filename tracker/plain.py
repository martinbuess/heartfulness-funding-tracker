"""Plain-language columns that read the same whatever the source.

Every source names things its own way ("Contract (Combined Synopsis/Solicitation)",
"Cooperative agreement; Grant", "Others (see listing)"). These columns put each
listing into a few simple buckets so founders can sort and filter in one go.
The source's own wording stays in the original columns.
"""

import html
import re


def add(rows):
    for row in rows:
        row.update(describe(row))
    return rows


def describe(row):
    return {
        "kind": kind(row),
        "stage": stage(row),
        "deadline": row["close_date"] or "Not set",
        "amount": amount(row),
        "who_can_apply": who_can_apply(row),
        "short_summary": short_summary(row["summary"]),
    }


def kind(row):
    t = row["listing_type"].lower()
    if "prize" in t:
        return "Prize"
    if t.startswith("contract"):
        return "Contract"
    if "grant" in t or "cooperative agreement" in t:
        return "Grant"
    if "loan" in t:
        return "Loan"
    if "accelerator" in t:
        return "Accelerator"
    if "pitch" in t:
        return "Pitch competition"
    if "pilot" in t:
        return "Pilot"
    if t == "notice":
        return "Funding notice"
    return "Other"


_INFO = ("sources sought", "request for information", "(rfi)", "special notice")
_SOON = ("presolicitation", "pre-solicitation")


def stage(row):
    """Open: you can apply now. Coming soon: announced, not open yet.
    Info request: the buyer is asking questions, a chance to get known before a bid."""
    t = row["listing_type"].lower()
    if any(w in t for w in _INFO):
        return "Info request"
    if row["status"] == "forecast" or any(w in t for w in _SOON):
        return "Coming soon"
    return "Open"


def amount(row):
    if row["award_ceiling"]:
        return "Up to " + _money(row["award_ceiling"])
    if row["total_funding"]:
        return _money(row["total_funding"]) + " total"
    return ""


def _money(value):
    try:
        n = float(value)
    except ValueError:
        return value
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.0f}"


def who_can_apply(row):
    e = row["eligibility"].lower()
    if "small business set aside" in e or "small business set-aside" in e:
        return "Small businesses only"
    if "any vendor" in e or "any company" in e or "unrestricted" in e:
        return "Any company"
    if "business" in e or "for-profit" in e:
        return "Companies eligible"
    if "see listing" in e:
        return "Check listing"
    return "Not companies"


def short_summary(text, limit=280):
    text = re.sub(r"\s+", " ", html.unescape(html.unescape(text))).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    if end > limit // 2:
        return cut[: end + 1]
    return cut[: cut.rfind(" ")] + " ..."
