"""How well a listing fits FBH, and why.

For each listing this works out, from the settings in profile.toml:

  fbh_area           which of FBH's four program areas it matches
  geography          India named / International (check India) / Unclear / restricted elsewhere
  who_can_apply      NGOs eligible / Check listing / Partnership needed
  eligibility_check  "Confirmed: ..." for facts the listing states, "Verify: ..." for our assumptions
  amount_usd         rough size in US dollars, used for the size rule
  fit_score          1 (weak) to 5 (strong)
  fit_reason         a plain sentence explaining the score

It also says when a listing should be set aside (reason text), so the rules in
profile.py can move it to data/filtered_out.csv instead of the sheet.
"""

import re

# --- word matching -----------------------------------------------------------


def prefix_words(words):
    """Match any of the words at the start of a word, ignoring capitals."""
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")",
                      re.IGNORECASE)


def whole_words(words):
    """Match any of the words as whole words ("India" but not "Indiana")."""
    words = [w for w in words if w]
    if not words:
        return None
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![\w-])",
                      re.IGNORECASE)


def regex(patterns):
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def _found(pattern, text):
    return sorted({m.group(0).lower() for m in pattern.finditer(text)}) if pattern else []


# --- money -------------------------------------------------------------------

_SYMBOLS = {"us$": "USD", "usd": "USD", "$": "USD", "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
            "£": "GBP", "gbp": "GBP", "inr": "INR", "rs": "INR", "rs.": "INR", "₹": "INR", "rupees": "INR",
            "chf": "CHF", "aud": "AUD", "a$": "AUD", "cad": "CAD", "c$": "CAD", "sek": "SEK", "nok": "NOK",
            "dkk": "DKK", "jpy": "JPY", "¥": "JPY", "dollars": "USD", "pounds": "GBP"}
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "millions": 1e6, "bn": 1e9,
          "billion": 1e9, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7}
_CUR = r"(US\$|USD|EUR|GBP|INR|CHF|AUD|CAD|SEK|NOK|DKK|JPY|Rs\.?|A\$|C\$|\$|€|£|₹|¥)"
_NUM = r"(\d{1,3}(?:[,.]\d{2,3})+|\d+(?:\.\d+)?)"
_SC = r"(k|thousand|million|millions|mn|m|billion|bn|lakhs?|lac|crores?|cr)?"
_BEFORE = re.compile(_CUR + r"\s?" + _NUM + r"\s*" + _SC + r"(?![a-z])", re.IGNORECASE)
_AFTER = re.compile(_NUM + r"\s*" + _SC + r"\s*(USD|EUR|GBP|INR|CHF|euros?|dollars|pounds|rupees)(?![a-z])",
                    re.IGNORECASE)


def _number(text):
    # "1,250,000" or "1.250.000" are thousands separators; "2.5" is a decimal.
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", text):
        return float(re.sub(r"[,.]", "", text))
    return float(text.replace(",", ""))


def amounts(text, usd_per):
    """Every money figure in the text, as (US dollars, original text)."""
    found = []
    for pattern, order in ((_BEFORE, "cur-num-scale"), (_AFTER, "num-scale-cur")):
        for m in pattern.finditer(text or ""):
            if order == "cur-num-scale":
                cur, num, scale = m.groups()
            else:
                num, scale, cur = m.groups()
            code = _SYMBOLS.get(cur.lower(), cur.upper())
            try:
                value = _number(num) * _SCALE.get((scale or "").lower(), 1)
            except ValueError:
                continue
            rate = usd_per.get(code)
            if rate and value * rate >= 1000:  # smaller figures are usually fees or costs, not grant sizes
                found.append((value * rate, m.group(0).strip()))
    return found


def size(row, usd_per):
    """(rough US dollars, how it was found). Blank when no amount is given."""
    for field in ("award_ceiling", "total_funding"):
        if row.get(field):
            try:
                return float(row[field]), ""
            except ValueError:
                pass
    found = amounts(f"{row['title']} {row['summary']}", usd_per)
    if not found:
        return None, ""
    usd, text = max(found)
    return usd, text


# --- the fit -------------------------------------------------------------------


class Rules:
    """The profile's words, compiled once."""

    def __init__(self, profile):
        self.areas = {name: prefix_words(words) for name, words in profile.get("areas", {}).items()}
        f = profile.get("filter", {})
        self.general = prefix_words(f.get("general_keywords", []))
        geo = profile.get("geography", {})
        self.india = whole_words(geo.get("india", []))
        self.international = whole_words(geo.get("international", []))
        # "Asia" counts as international, but not inside "Southeast Asia" or "Central Asia".
        self.other = whole_words(geo.get("other_places", []))
        self.us_only = regex(geo.get("us_only_patterns", []))
        self.gg_foreign = regex(geo.get("grants_gov_foreign_patterns", []))
        app = profile.get("applicants", {})
        self.nonprofit = prefix_words(app.get("nonprofit", []))
        self.partnership = prefix_words(app.get("partnership", []))
        self.us_charity = prefix_words(app.get("us_charity_words", []))
        s = profile.get("size", {})
        self.priority_min = s.get("priority_min_usd", 50000)
        self.minimum = s.get("minimum_usd", 10000)
        self.usd_per = s.get("usd_per", {"USD": 1.0})
        watch = profile.get("watchlist", {})
        self.no_bonus = {s.lower() for s in watch.get("no_bonus_statuses", [])}
        self.watchlist = []
        for entry in watch.get("funders", []):
            if isinstance(entry, str):  # a plain name is also accepted
                entry = {"name": entry, "match": [entry]}
            pattern = whole_words(entry.get("match") or [entry["name"]])
            if pattern:
                self.watchlist.append((entry["name"], entry.get("status", ""), pattern))


def areas(row, rules):
    """(areas matched in the title, areas matched anywhere, words found)."""
    title, text = row["title"], f"{row['title']} {row['summary']}"
    in_title, anywhere, words = [], [], []
    for name, pattern in rules.areas.items():
        hits = _found(pattern, text)
        if hits:
            anywhere.append(name)
            words += hits[:2]
            if pattern.search(title):
                in_title.append(name)
    return in_title, anywhere, words


def _embassy(funder):
    """The country in "U.S. Mission to Cambodia" or "U.S. Embassy in Ghana"; blank for other funders."""
    m = re.search(r"(?:mission to|embassy (?:in|to)|bureau of) (.+)", funder or "", re.IGNORECASE)
    return m.group(1) if m else ""


def _place(text):
    return text if text.isupper() else text.title()


def _strip_subregions(text):
    return re.sub(r"\b(south[- ]?east|central|east|west|north) asia", "subregion", text, flags=re.IGNORECASE)


def geography(row, rules):
    """(label, points, reason to set aside or "")."""
    # The EU note is our own words (it mentions India), so it isn't read as the call's geography.
    notes = "" if row["source"] == "eu-funding" else row.get("eligibility_notes", "")
    text = f"{row['title']} {row['summary']} {notes} {row.get('location', '')}"
    if rules.india and rules.india.search(text):
        return "India named", 2, ""
    if rules.us_only and rules.us_only.search(text):
        return "US only", 0, "US-based work or applicants only"
    # A place named in the title or the funder (e.g. "U.S. Mission to Cambodia") without India.
    # A title that also says "global" or "Asia" (e.g. "Africa and Asia") is not restricted.
    title_places = _found(rules.other, f"{row['title']} {_embassy(row['funder'])}")
    title_intl = rules.international and rules.international.search(_strip_subregions(row["title"]))
    # "US" in capitals (e.g. "Pilot Program (US)"); lower-case "us" is just a word.
    if re.search(r"\bUS\b", row["title"]):
        title_places.append("US")
    if title_places and not title_intl:
        return "Elsewhere", 0, f"for {', '.join(_place(p) for p in title_places[:3])}, not India"
    if row["source"] == "grants.gov":
        # Federal grants are for US applicants unless the listing says foreign organisations may apply.
        notes = f"{row['summary']} {row.get('eligibility_notes', '')}"
        if rules.gg_foreign and rules.gg_foreign.search(notes):
            return "International (check India)", 1, ""
        return "US only", 0, "US federal grant with no mention of foreign applicants"
    if row["source"] == "eu-funding":
        return "EU call (India usually as partner only)", 0, ""
    if rules.international and rules.international.search(_strip_subregions(text)):
        return "International (check India)", 1, ""
    places = _found(rules.other, text[:400])
    if places:
        return f"Unclear (mentions {', '.join(p.title() for p in places[:2])})", 0, ""
    return "Unclear", 0, ""


def applicants(row, rules):
    """(who_can_apply, points, confirmed facts, things to verify)."""
    confirmed, verify = [], []
    elig = row.get("eligibility", "").lower()
    text = f"{row['summary']} {row.get('eligibility_notes', '')}"
    points = 0
    if "nonprofit" in elig or (rules.nonprofit and rules.nonprofit.search(f"{row['title']} {text}")):
        who, points = "NGOs eligible", 1
        confirmed.append("NGOs/nonprofits named as eligible")
    elif "unrestricted" in elig:
        who, points = "Anyone", 1
        confirmed.append("open to any applicant")
    else:
        who = "Check listing"
        verify.append("NGO eligibility not stated")
    if rules.partnership and rules.partnership.search(text):
        who += "; partner may be needed"
        verify.append("may need a partner or consortium")
    if rules.us_charity and rules.us_charity.search(text):
        verify.append("mentions US 501(c)(3) status (equivalency or fiscal sponsor may be needed)")
    return who, points, confirmed, verify


def _money(usd):
    if usd >= 1e6:
        return f"${usd / 1e6:.1f}M".replace(".0M", "M")
    return f"${usd / 1e3:.0f}K"


def assess(row, rules):
    """Fill the fit columns. Returns a reason to set the listing aside, or ""."""
    in_title, anywhere, words = areas(row, rules)
    general = _found(rules.general, f"{row['title']} {row['summary']}")
    geo, geo_points, geo_out = geography(row, rules)
    who, app_points, confirmed, verify = applicants(row, rules)
    usd, usd_text = size(row, rules.usd_per)

    if geo_out:
        return f"geography: {geo_out}"
    if usd is not None and usd < rules.minimum:
        return f"too small: about {_money(usd) if usd >= 1000 else f'${usd:.0f}'} (under {_money(rules.minimum)})"

    program = 2 if in_title else (1 if anywhere else 0)
    if usd is None:
        size_points, size_note = 0, "amount not published"
    elif usd >= rules.priority_min:
        size_points, size_note = 1, f"about {_money(usd)}"
    else:
        size_points, size_note = -1, f"smaller grant, about {_money(usd)}"
    if usd_text:
        size_note += f" (from \"{usd_text}\"; may be the total budget)"
    funder_text = f"{row['funder']} {row['title']} {row['summary']}"
    pipeline = next(((name, status) for name, status, pattern in rules.watchlist if pattern.search(funder_text)), None)
    bonus = 1 if pipeline and pipeline[1].lower() not in rules.no_bonus else 0

    score = max(1, min(5, program + geo_points + app_points + size_points + bonus))

    if geo == "India named":
        confirmed.append("India named")
    elif geo.startswith("International"):
        verify.append("India eligibility (open internationally)")
    else:
        verify.append("India eligibility (not stated)")
    if usd is None:
        verify.append("grant size")

    area_label = "; ".join(anywhere) or ("General environment / climate" if general else "")
    match = ", ".join(words[:4] or general[:3])
    where = "title" if in_title else "description"
    reason = [f"Matches {match} ({where})" if match else "Hand-picked program",
              geo, who, size_note]
    if pipeline:
        reason.append(f"{pipeline[0]} is in our pipeline ({pipeline[1] or 'no status'})")
    row.update({
        "fbh_area": area_label,
        "geography": geo,
        "who_can_apply": who,
        "eligibility_check": "; ".join(filter(None, [
            "Confirmed: " + ", ".join(confirmed) if confirmed else "",
            "Verify: " + ", ".join(verify) if verify else ""])),
        "amount_usd": f"{usd:.0f}" if usd is not None else "",
        "in_pipeline": f"{pipeline[0]}: {pipeline[1] or 'no status'}" if pipeline else "",
        "fit_score": str(score),
        "fit_reason": ". ".join(reason) + ".",
    })
    if not row.get("amount") and usd is not None:
        row["amount"] = (usd_text or "Up to " + _money(usd))
    return ""
