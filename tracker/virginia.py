"""Collector for Virginia eVA open solicitations (state agencies, universities
and localities). Uses the same public search the eVA opportunities page uses.
"""

import json
import urllib.parse

from tracker.text import clean, fetch

SEARCH_URL = "https://mvendor.cgieva.com/Vendor/public/solrconnect.jsp"
DETAIL_URL = "https://mvendor.cgieva.com/Vendor/public/{page}?"
LIST_URL = "https://mvendor.cgieva.com/Vendor/public/AllOpportunities.jsp"


def download():
    # The site's search proxy rejects date-range filters, so past deadlines are dropped in collect().
    query = [("q", "*:*"), ("fq", "status:Open"), ("rows", "5000"), ("wt", "json")]
    return json.loads(fetch(SEARCH_URL + "?" + urllib.parse.urlencode(query), timeout=180))


def _link(doc):
    # Built the same way as the eVA site's own "View" links.
    if doc.get("app") == "IV":
        return DETAIL_URL.format(page="IVDetails.jsp") + urllib.parse.urlencode({
            "PageTitle": "SO Details", "rfp_id_lot": doc.get("internalid", ""), "rfp_id_round": doc.get("version", ""),
        })
    if doc.get("app") == "QQ":
        return DETAIL_URL.format(page="QQDetails.jsp") + urllib.parse.urlencode({
            "PageTitle": "QQ Details", "REQUEST_ID": doc.get("internalid", ""),
        })
    pages = {"VBO": ("VBODetails.jsp", "VBOSODetails.jsp"), "ADV": ("ADVSODetails.jsp", "ADVSODetails.jsp")}
    if doc.get("app") not in pages:
        return LIST_URL
    page, details = pages[doc["app"]]
    return DETAIL_URL.format(page=page) + urllib.parse.urlencode({
        "PageTitle": "SO Details", "DOC_CD": doc.get("doccd", ""), "Details_Page": details,
        "DEPT_CD": doc.get("docdeptcd", ""), "BID_INTRNL_NO": doc.get("internalid", ""),
        "BID_NO": doc.get("externalid", ""), "BID_VERS_NO": doc.get("version", ""),
    })


def normalize(doc):
    kind = doc.get("doccddesc", "")
    return {
        "source": "eva-virginia",
        "source_id": doc.get("id", ""),
        "title": clean(doc.get("shortdesc")),
        "funder": doc.get("agencyname", ""),
        "funder_code": "VA",
        "listing_type": f"Contract ({kind})" if kind else "Contract",
        "status": "posted",
        "post_date": (doc.get("pubdate") or "")[:10],
        "close_date": (doc.get("closedate") or "")[:10],
        "award_floor": "",
        "award_ceiling": "",
        "total_funding": "",
        "eligibility": "Any vendor",
        # eVA's own category (Construction, Goods, Professional Services, ...) comes first.
        "topics": "; ".join(([f"Category: {doc['category']}"] if doc.get("category") else []) + (doc.get("commdesc") or [])),
        "location": f"{doc['workloc']}, VA" if doc.get("workloc") else "Virginia",
        "link": _link(doc),
        "summary": clean(doc.get("longdesc"))[:600],
    }


def collect(today, data=None):
    """Return open eVA solicitations in the common format.

    Pass data (the search JSON) to skip the download, e.g. in tests.
    """
    if data is None:
        data = download()
    docs = (data.get("response") or {}).get("docs") or []
    rows = [normalize(d) for d in docs if d.get("status") == "Open"]
    return [r for r in rows if r["close_date"] >= today.isoformat()]
