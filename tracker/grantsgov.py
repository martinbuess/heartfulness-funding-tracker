"""Collector for Grants.gov, using its free daily XML extract (no API key).

The extract holds every federal grant opportunity ever posted. We keep only
the ones still open (or forecast) and reshape them into the common format.
"""

import datetime
import io
import xml.etree.ElementTree as ET
import zipfile

from tracker.text import clean, fetch

# Grants.gov publishes the daily extract to this public bucket.
EXTRACT_URL = "https://prod-grants-gov-chatbot.s3.amazonaws.com/extracts/GrantsDBExtract{day}v2.zip"
LISTING_URL = "https://www.grants.gov/search-results-detail/{id}"
NS = "{http://apply.grants.gov/system/OpportunityDetail-V1.0}"

# Codes from the Grants.gov XML extract user guide.
APPLICANT_TYPES = {
    "00": "State governments",
    "01": "County governments",
    "02": "City or township governments",
    "04": "Special district governments",
    "05": "Independent school districts",
    "06": "Public and state controlled institutions of higher education",
    "07": "Native American tribal governments (federally recognized)",
    "08": "Public housing authorities",
    "11": "Native American tribal organizations (other than federally recognized)",
    "12": "Nonprofits with 501(c)(3) status",
    "13": "Nonprofits without 501(c)(3) status",
    "20": "Private institutions of higher education",
    "21": "Individuals",
    "22": "For-profit organizations other than small businesses",
    "23": "Small businesses",
    "25": "Others (see listing)",
    "99": "Unrestricted",
}
CATEGORIES = {
    "ACA": "Affordable Care Act",
    "AG": "Agriculture",
    "AR": "Arts",
    "BC": "Business and Commerce",
    "CD": "Community Development",
    "CP": "Consumer Protection",
    "DPR": "Disaster Prevention and Relief",
    "ED": "Education",
    "ELT": "Employment, Labor and Training",
    "EN": "Energy",
    "ENV": "Environment",
    "FN": "Food and Nutrition",
    "HL": "Health",
    "HO": "Housing",
    "HU": "Humanities",
    "IIJ": "Infrastructure Investment and Jobs Act",
    "IS": "Information and Statistics",
    "ISS": "Income Security and Social Services",
    "LJL": "Law, Justice and Legal Services",
    "NR": "Natural Resources",
    "O": "Other",
    "OZ": "Opportunity Zone Benefits",
    "RA": "Recovery Act",
    "RD": "Regional Development",
    "ST": "Science and Technology",
    "T": "Transportation",
}
INSTRUMENTS = {
    "G": "Grant",
    "CA": "Cooperative agreement",
    "PC": "Procurement contract",
    "O": "Other",
}


def download_extract(today, days_back=3):
    """Return the XML bytes of the newest extract, trying a few days back."""
    for offset in range(days_back + 1):
        day = (today - datetime.timedelta(days=offset)).strftime("%Y%m%d")
        url = EXTRACT_URL.format(day=day)
        try:
            data = fetch(url)
        except Exception as exc:  # missing file or network hiccup: try the day before
            print(f"grants.gov: no extract at {url} ({exc})")
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".xml"))
            print(f"grants.gov: using {name}")
            return zf.read(name)
    raise RuntimeError("grants.gov: no extract found in the last few days")


def _date(value):
    try:
        return datetime.datetime.strptime(value, "%m%d%Y").date()
    except (TypeError, ValueError):
        return None


def _money(value):
    value = (value or "").strip()
    return value if value.isdigit() and value != "0" else ""


def parse_records(xml_source):
    """Yield one dict per opportunity in the extract (file path or file object)."""
    for _, el in ET.iterparse(xml_source):
        tag = el.tag.replace(NS, "")
        if not tag.startswith(("OpportunitySynopsisDetail", "OpportunityForecastDetail")):
            continue
        record = {}
        for child in el:
            key = child.tag.replace(NS, "")
            text = (child.text or "").strip()
            if key in ("EligibleApplicants", "CategoryOfFundingActivity", "FundingInstrumentType"):
                record.setdefault(key, []).append(text)
            else:
                record[key] = text
        record["_kind"] = "forecast" if "Forecast" in tag else "posted"
        el.clear()
        yield record


def is_open(record, today):
    close = _date(record.get("CloseDate"))
    archive = _date(record.get("ArchiveDate"))
    if record["_kind"] == "posted":
        if close:
            return close >= today
        return bool(archive and archive >= today)
    # Forecasts often have no dates yet; keep them until archived.
    return not archive or archive >= today


def normalize(record):
    """Reshape one raw record into the common listing format."""
    close = _date(record.get("CloseDate"))
    post = _date(record.get("PostDate"))
    instruments = [INSTRUMENTS.get(c, c) for c in record.get("FundingInstrumentType", [])]
    return {
        "source": "grants.gov",
        "source_id": record.get("OpportunityID", ""),
        "title": clean(record.get("OpportunityTitle")),
        "funder": record.get("AgencyName", ""),
        "funder_code": record.get("AgencyCode", ""),
        "listing_type": "; ".join(instruments) or "Grant",
        "status": record["_kind"],
        "post_date": post.isoformat() if post else "",
        "close_date": close.isoformat() if close else "",
        "award_floor": _money(record.get("AwardFloor")),
        "award_ceiling": _money(record.get("AwardCeiling")),
        "total_funding": _money(record.get("EstimatedTotalProgramFunding")),
        "eligibility": "; ".join(APPLICANT_TYPES.get(c, c) for c in record.get("EligibleApplicants", [])),
        "eligibility_notes": clean(record.get("AdditionalInformationOnEligibility"))[:600],
        "topics": "; ".join(CATEGORIES.get(c, c) for c in record.get("CategoryOfFundingActivity", [])),
        "location": "National",
        "link": LISTING_URL.format(id=record.get("OpportunityID", "")),
        "summary": clean(record.get("Description"))[:600],
    }


def collect(today, xml_source=None):
    """Return open Grants.gov listings in the common format.

    Pass xml_source (a path or file object) to skip the download, e.g. in tests.
    """
    if xml_source is None:
        xml_source = io.BytesIO(download_extract(today))
    listings = {}
    for record in parse_records(xml_source):
        if is_open(record, today):
            row = normalize(record)
            # The extract can hold a forecast and a synopsis for one id; keep the posted one.
            if row["source_id"] not in listings or row["status"] == "posted":
                listings[row["source_id"]] = row
    return list(listings.values())
