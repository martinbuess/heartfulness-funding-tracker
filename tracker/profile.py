"""Which listings fit FBH, using the settings in profile.toml.

A listing is kept when it mentions an FBH program area (or a broad
environment/climate word) and no rule rules it out. Listings removed by a rule
are returned with the reason so they can be checked in data/filtered_out.csv;
nothing is dropped silently except plainly off-topic listings.
"""

import tomllib

from tracker import fit

# Sources picked by a person: every listing counts, and no rule sets it aside.
HAND_PICKED = ("calendar",)


def load(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


class _Filter:
    def __init__(self, profile):
        rules = profile.get("filter", {})
        self.fit = fit.Rules(profile)
        topic_words = [w for words in profile.get("areas", {}).values() for w in words]
        self.topic = fit.prefix_words(topic_words + rules.get("general_keywords", []))
        self.exclude = fit.whole_words(rules.get("exclude_keywords", []))
        self.skip_funders = tuple(rules.get("exclude_funder_codes", []))
        self.individual = fit.prefix_words(rules.get("individual_title_words", []))
        self.procurement = fit.whole_words(rules.get("procurement_title_words", []))
        self.business = fit.prefix_words(rules.get("business_title_words", []))
        self.not_eligible = fit.regex(rules.get("not_eligible_patterns", []))

    def on_topic(self, row):
        if row["source"] in HAND_PICKED:
            return True
        if self.skip_funders and row.get("funder_code", "").startswith(self.skip_funders):
            return False
        text = f"{row['title']} {row['summary']}"
        if not (self.topic and self.topic.search(text)):
            return False
        return not (self.exclude and self.exclude.search(text))

    def set_aside(self, row):
        """Why FBH could not apply, or "" if nothing says so."""
        title = row["title"]
        listing_type = row.get("listing_type", "").lower()
        if "procurement" in listing_type or listing_type.startswith("contract"):
            return "procurement: a contract to supply services, not a grant"
        found = self.procurement.search(title) if self.procurement else None
        if found:
            return f"procurement: \"{found.group(0)}\" in the title"
        found = self.individual.search(title) if self.individual else None
        if found:
            return f"for individuals or events: \"{found.group(0)}\" in the title"
        elig = row.get("eligibility", "").lower()
        if row["source"] == "grants.gov" and not any(w in elig for w in ("nonprofit", "unrestricted", "see listing")):
            return "not open to nonprofits (Grants.gov applicant types)"
        notes = f"{row.get('eligibility_notes', '')} {row['summary']}"
        found = self.not_eligible.search(notes) if self.not_eligible else None
        if found:
            return f"not open to nonprofits: \"{found.group(0)}\""
        found = self.business.search(title) if self.business else None
        if found and not (self.fit.nonprofit and self.fit.nonprofit.search(f"{title} {notes}")):
            return f"for companies or start-ups: \"{found.group(0)}\" in the title"
        return ""


def apply(profile, rows, dropped=None):
    """Return the rows that fit FBH, with the fit columns filled in.

    Pass a list as dropped to collect (row, reason) for listings that were on
    topic but set aside by a rule.
    """
    f = _Filter(profile)
    matches = []
    for row in rows:
        if not f.on_topic(row):
            continue
        hand_picked = row["source"] in HAND_PICKED
        reason = "" if hand_picked else f.set_aside(row)
        if not reason:
            reason = fit.assess(row, f.fit)
            if hand_picked:
                reason = ""
        if reason:
            if dropped is not None:
                dropped.append((row, reason))
            continue
        matches.append(row)
    matches.sort(key=lambda r: (-int(r["fit_score"] or 0), r["close_date"] or "9999"))
    return matches


def on_topic(profile, rows):
    """Rows that mention an FBH area, before any eligibility rule. Used for the archive."""
    f = _Filter(profile)
    return [r for r in rows if f.on_topic(r)]
