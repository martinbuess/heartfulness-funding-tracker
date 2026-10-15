"""The common listing format every source is normalized into."""

FIELDS = [
    "source",          # where the listing came from, e.g. "grants.gov"
    "source_id",       # the source's own id, used to update rows day to day
    "title",
    "funder",          # agency, state department or city
    "funder_code",
    # Plain-language columns, the same for every source (see tracker/plain.py)
    "kind",            # Grant, Contract, Prize, Loan, Funding notice
    "stage",           # Open, Coming soon, Info request
    "deadline",        # close date, or "Not set"
    "amount",          # e.g. "Up to $500K"
    "who_can_apply",   # NGOs eligible, Anyone, Check listing (and "partner may be needed")
    "short_summary",   # first sentences of the summary
    # The source's own fields
    "listing_type",    # grant, cooperative agreement, contract, prize, ...
    "status",          # posted or forecast
    "post_date",       # YYYY-MM-DD
    "close_date",      # YYYY-MM-DD, blank for rolling or forecast
    "award_floor",     # dollars, blank when not given
    "award_ceiling",
    "total_funding",
    "eligibility",     # source's applicant types, "; " separated
    "eligibility_notes",  # source's own words on who may apply, when it gives them
    "topics",          # source's categories, "; " separated
    "location",        # where the applicant or work must be; "National" for federal
    "link",            # the original listing page
    "summary",         # first part of the description
    # How well the listing fits FBH (filled in by tracker/fit.py for matches)
    "fbh_area",        # which FBH program area(s) it matches
    "geography",       # India named, International (check India), Unclear, ...
    "eligibility_check",  # "Confirmed: ..." facts from the listing; "Verify: ..." assumptions to check
    "amount_usd",      # rough size in US dollars, for the size rule
    "in_pipeline",     # "Yes" when the funder is on our watch list
    "fit_score",       # 1 (weak) to 5 (strong)
    "fit_reason",      # why it scored what it did
    "first_seen",      # date this pool first saw the listing
    "last_seen",       # most recent date it was still open
]
