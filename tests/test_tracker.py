import datetime
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from tracker import run
from tracker import (bonfire, buffalo, california, chicago, cleveland, federalregister, glri, grantsgov, illinois, leads,
                     massachusetts, metcouncil, mmsd, mwrd, nsf, nyc, opengov, plain, pool, prizes, profile, programs, samgov, sbir, text, virginia)

HERE = os.path.dirname(__file__)
SAMPLE = os.path.join(HERE, "sample_extract.xml")
TODAY = datetime.date(2026, 10, 5)


class GrantsGovTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in grantsgov.collect(TODAY, xml_source=SAMPLE)}

    def test_keeps_open_and_forecast_only(self):
        self.assertEqual(set(self.rows), {"100", "102", "103"})

    def test_normalizes_fields(self):
        row = self.rows["100"]
        self.assertEqual(row["close_date"], "2026-12-15")
        self.assertEqual(row["award_ceiling"], "250000")
        self.assertEqual(row["eligibility"], "Small businesses")
        self.assertEqual(row["topics"], "Environment")
        self.assertEqual(row["listing_type"], "Grant")
        self.assertEqual(row["summary"], "Pilots that monitor shoreline & harbor structures.")
        self.assertEqual(row["link"], "https://www.grants.gov/search-results-detail/100")

    def test_forecast_status(self):
        self.assertEqual(self.rows["103"]["status"], "forecast")
        self.assertEqual(self.rows["103"]["close_date"], "")


class CaliforniaTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "sample_california.csv"), encoding="utf-8") as f:
            self.rows = {r["source_id"]: r for r in california.collect(TODAY, csv_text=f.read())}

    def test_keeps_active_only(self):
        self.assertEqual(set(self.rows), {"192465", "190509"})

    def test_normalizes_fields(self):
        row = self.rows["192465"]
        self.assertEqual(row["close_date"], "2026-11-25")
        self.assertEqual((row["award_floor"], row["award_ceiling"]), ("1", "750000"))
        self.assertEqual(row["total_funding"], "15000000")
        self.assertEqual(row["eligibility"], "Business")
        self.assertEqual(row["location"], "California")
        self.assertTrue(row["link"].startswith("http"))

    def test_ongoing_deadline_is_blank(self):
        self.assertEqual(self.rows["190509"]["close_date"], "")


class NycTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "sample_nyc.json"), encoding="utf-8") as f:
            self.rows = nyc.collect(TODAY, rows=json.load(f))

    def test_keeps_future_due_dates_only(self):
        self.assertEqual([r["source_id"] for r in self.rows], ["20260903027"])

    def test_normalizes_fields(self):
        row = self.rows[0]
        self.assertEqual(row["close_date"], "2026-10-08")
        self.assertEqual(row["funder"], "NYC Environmental Protection")
        self.assertEqual(row["listing_type"], "Contract (Request for Proposals)")
        self.assertEqual(row["summary"], "Sensors for sewer overflow monitoring.")
        self.assertEqual(row["link"], "https://a856-cityrecord.nyc.gov/RequestDetail/20260903027")



def _read(name, encoding="utf-8"):
    with open(os.path.join(HERE, name), encoding=encoding) as f:
        return f.read()


class MwrdTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in mwrd.collect(
            TODAY, page=_read("sample_mwrd.html"), details={"2904": _read("sample_mwrd_detail.html")})}

    def test_keeps_bids_not_yet_opened(self):
        self.assertEqual(set(self.rows), {"23-890-1S", "25-RFP-20"})

    def test_normalizes_fields(self):
        row = self.rows["23-890-1S"]
        self.assertEqual(row["title"], "Rehabilitation Of Local Sewers")
        self.assertEqual((row["post_date"], row["close_date"]), ("2026-09-16", "2026-10-27"))
        self.assertEqual(row["award_ceiling"], "2706674")
        self.assertIn("LABOR AGREEMENT", row["summary"])
        self.assertTrue(row["link"].endswith("contractID=2904"))
        self.assertEqual(self.rows["25-RFP-20"]["listing_type"], "Contract (RFP)")


class ChicagoTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "sample_chicago.html"), "rb") as f:
            page = chicago.decode(f.read())
        self.rows = {r["source_id"]: r for r in chicago.collect(TODAY, page=page)}

    def test_keeps_open_only(self):
        self.assertEqual(set(self.rows), {"70287", "72293"})

    def test_normalizes_fields(self):
        row = self.rows["70287"]
        self.assertEqual(row["funder"], "Chicago Department Of Water Management")
        self.assertEqual((row["post_date"], row["close_date"]), ("2026-09-14", "2026-10-14"))
        self.assertEqual(row["eligibility"], "Any vendor")
        self.assertEqual(self.rows["72293"]["funder"], "Chicago Department Of Aviation")
        self.assertEqual(self.rows["72293"]["title"], "AED\u2019s and Support Materials")

    def test_flags_target_market_set_aside(self):
        self.assertIn("Target Market", self.rows["72293"]["eligibility"])


class BonfireTest(unittest.TestCase):
    def test_keeps_open_and_normalizes(self):
        rows = bonfire.collect(TODAY, payloads={"glwater": json.loads(_read("sample_bonfire.json"))})
        self.assertEqual([r["source_id"] for r in rows], ["glwater-252183"])
        self.assertEqual(rows[0]["close_date"], "2026-10-16")
        self.assertEqual(rows[0]["funder"], "Great Lakes Water Authority")
        self.assertEqual(rows[0]["link"], "https://glwater.bonfirehub.com/opportunities/252183")


class OpenGovTest(unittest.TestCase):
    def setUp(self):
        payload = json.loads(_read("sample_opengov.json"))
        self.rows = {r["source_id"]: r for r in opengov.collect(TODAY, payloads={"neorsd": [payload]})}

    def test_keeps_open_and_coming_soon(self):
        self.assertEqual(set(self.rows), {"neorsd-307121", "neorsd-279486", "neorsd-300761", "neorsd-2"})

    def test_normalizes_fields(self):
        row = self.rows["neorsd-279486"]
        self.assertEqual(row["title"], "Rubbish Removal and Recycling Services")
        self.assertEqual(row["funder"], "Northeast Ohio Regional Sewer District")
        self.assertEqual(row["close_date"], "2026-11-02")
        self.assertEqual(row["post_date"], "2026-10-06")
        self.assertEqual(row["topics"], "Technical Services Group; Standard Bid")
        self.assertEqual(row["link"], "https://procurement.opengov.com/portal/neorsd/projects/279486")
        self.assertIn("requirement contract awarded", row["summary"])  # split spans rejoined

    def test_coming_soon_request_for_information(self):
        row = dict(self.rows["neorsd-2"])
        self.assertEqual((row["status"], row["close_date"]), ("forecast", ""))
        self.assertEqual(plain.stage(row), "Info request")


class MmsdTest(unittest.TestCase):
    def setUp(self):
        page = _read("sample_mmsd.html", encoding="cp1252")
        self.rows = {r["source_id"]: r for r in mmsd.collect(TODAY, page=page)}

    def test_keeps_open_listings_only(self):
        self.assertEqual(set(self.rows), {"J06106C10", "J06105D01", "P-3388"})

    def test_normalizes_fields(self):
        row = self.rows["J06105D01"]
        self.assertEqual(row["title"], "Engineering Services \u2013 Electrical Distribution System Equipment "
                                       "Replacements at Jones Island Water Reclamation Facility")
        self.assertEqual(row["close_date"], "2026-10-22")
        self.assertEqual(row["funder"], "Milwaukee Metropolitan Sewerage District")
        self.assertTrue(row["link"].endswith("PID=B9BC41590DD445AB7D4E91B8423EFA255C6EC00A76B4B31B"))
        self.assertEqual(self.rows["P-3388"]["listing_type"], "Contract (request for information)")


class BuffaloTest(unittest.TestCase):
    def setUp(self):
        self.feed = _read("sample_buffalo.xml").encode()

    def test_reads_deadline_from_notice_text(self):
        rows = {r["source_id"]: r for r in buffalo.collect(datetime.date(2026, 6, 10), feed=self.feed)}
        # The meeting recording is skipped; the dateless RFP is kept as recent.
        self.assertEqual(set(rows), {"10332", "9668"})
        row = rows["9668"]
        self.assertEqual(row["title"], "Colorado Avenue \u2013 CSO053 SPP 337 Modifications")
        self.assertEqual(row["close_date"], "2026-07-09")
        self.assertEqual(row["post_date"], "2026-06-04")
        self.assertEqual(row["listing_type"], "Contract (bid)")
        self.assertEqual(rows["10332"]["listing_type"], "Contract (RFP)")
        self.assertEqual(rows["10332"]["close_date"], "")

    def test_old_posts_drop_out(self):
        self.assertEqual(buffalo.collect(TODAY, feed=self.feed), [])

    def test_odd_date_formats(self):
        self.assertEqual(buffalo.due_date("on Monday April, 27, 2026, for the"), "2026-04-27")
        self.assertEqual(buffalo.due_date("at 10:00 A.M. local time on DECEMBER 17, 2025"), "2025-12-17")


class ClevelandTest(unittest.TestCase):
    def setUp(self):
        pages = {"invitations-bid": _read("sample_cleveland_itb.html"),
                 "request-qualificationsproposal": _read("sample_cleveland_rfq.html")}
        self.rows = {r["source_id"]: r for r in cleveland.collect(datetime.date(2026, 10, 8), pages=pages)}

    def test_keeps_open_dated_listings(self):
        # 98-26 closed; the CDBG RFP gives no year, so it is left out.
        self.assertEqual(set(self.rows), {"109-26", "112-26", "510", "collapse_301"})

    def test_large_bid(self):
        row = self.rows["109-26"]
        self.assertEqual(row["title"], "Pipe Repair Clamps and Couplings")
        self.assertEqual(row["funder"], "City of Cleveland Division of Water")
        self.assertEqual(row["close_date"], "2026-10-22")
        self.assertEqual(row["link"], cleveland.BASE + "invitations-bid#collapse_101")
        self.assertEqual(self.rows["112-26"]["funder"], "City of Cleveland Department of Public Works")

    def test_drops_city_hall_address(self):
        # "Lakeside Avenue" would otherwise match the keyword "lake" on every listing.
        self.assertNotIn("Lakeside", self.rows["112-26"]["summary"])
        self.assertIn("Cleveland City Hall", self.rows["112-26"]["summary"])

    def test_small_bid_closing_date(self):
        self.assertEqual(self.rows["510"]["close_date"], "2026-10-14")
        self.assertEqual(self.rows["510"]["title"], "MANHOLE RISERS & LIDS")

    def test_rfp_uses_closing_date_and_keeps_dashed_title(self):
        row = self.rows["collapse_301"]
        self.assertEqual(row["title"], "Central Recreation Center - Expansion")
        self.assertEqual(row["close_date"], "2026-11-29")
        self.assertEqual(row["listing_type"], "Contract (RFP)")
        self.assertIn("Division of Architecture", row["funder"])


class MetCouncilTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in metcouncil.collect(datetime.date(2026, 10, 8),
                                                                    page=_read("sample_metcouncil.html"))}

    def test_keeps_open_rows(self):
        self.assertEqual(set(self.rows), {"26P276"})

    def test_normalizes_fields(self):
        row = self.rows["26P276"]
        self.assertEqual(row["title"], "Interceptor 1-MS-100 Condition Assessment")
        self.assertEqual(row["funder"], "Metropolitan Council Environmental Services")
        self.assertEqual(row["listing_type"], "Contract (request for information)")
        self.assertEqual(row["post_date"], "2026-10-01")
        self.assertEqual(row["close_date"], "2026-10-30")
        self.assertEqual(row["link"], "https://metrocouncil.org/getdoc/abc/26P276.aspx")


class NsfTest(unittest.TestCase):
    def test_keeps_only_small_business_programs(self):
        rows = nsf.collect(datetime.date(2026, 10, 8), feed=_read("sample_nsf.xml"))
        self.assertEqual([r["source_id"] for r in rows], ["NSF 26-511"])
        self.assertEqual(rows[0]["close_date"], "2026-11-04")
        self.assertEqual(rows[0]["eligibility"], "Small businesses")
        self.assertNotIn("Upcoming Due Dates item", rows[0]["summary"])


class SbirTest(unittest.TestCase):
    def test_open_and_upcoming_topics(self):
        today = datetime.date(2026, 10, 9)
        rows = sbir.collect(today, pages=[_read("sample_sbir.html"), _read("sample_sbir.html")])
        # The closed topic is dropped and the repeated page adds nothing.
        self.assertEqual([r["source_id"] for r in rows], ["12958", "13022"])
        water, navy = rows
        self.assertEqual(water["funder"], "Environmental Protection Agency")
        self.assertEqual(water["status"], "posted")
        self.assertEqual(water["close_date"], "2026-11-20")
        self.assertEqual(water["listing_type"], "Contract (SBIR topic)")
        self.assertIn("drinking water & distribution", water["summary"])
        self.assertEqual(water["link"], "https://www.sbir.gov/topics/12958")
        # Released but not open until Oct 28: shown as coming soon.
        self.assertEqual(navy["status"], "forecast")
        self.assertEqual(navy["funder_code"], "DOD")
        self.assertEqual(navy["listing_type"], "Contract (STTR topic)")
        self.assertIn("Opens 2026-10-28", navy["topics"])


class FederalRegisterTest(unittest.TestCase):
    def test_drops_paperwork_notices_and_normalizes(self):
        rows = federalregister.collect(TODAY, data=json.loads(_read("sample_federalregister.json")))
        self.assertEqual([r["source_id"] for r in rows], ["2026-20001"])
        self.assertEqual(rows[0]["funder"], "National Oceanic and Atmospheric Administration")
        self.assertEqual(rows[0]["summary"], "NOAA invites applications for sensor pilots.")
        self.assertEqual(rows[0]["eligibility"], "Others (see listing)")



class IllinoisTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in illinois.collect(TODAY, page=_read("sample_illinois.html"))}

    def test_keeps_open_and_no_end_date(self):
        self.assertEqual(set(self.rows), {"0f9fad21-8730", "4339"})

    def test_normalizes_fields(self):
        row = self.rows["0f9fad21-8730"]
        self.assertEqual(row["title"], "Lake Michigan Monitoring")
        self.assertEqual(row["funder"], "Illinois Department of Natural Resources")
        self.assertEqual((row["award_floor"], row["award_ceiling"]), ("15000", "75000"))
        self.assertEqual(row["close_date"], "")
        self.assertEqual(row["link"], "https://il.amplifund.com/Public/Opportunities/Details/0f9fad21-8730")
        nofo = self.rows["4339"]
        self.assertEqual((nofo["post_date"], nofo["close_date"]), ("2026-08-31", "2026-10-19"))
        self.assertTrue(nofo["link"].endswith("nofo=4339"))


class MassachusettsTest(unittest.TestCase):
    def test_pages_are_combined_deduped_and_filtered(self):
        pages = [_read("sample_commbuys_p1.html"), _read("sample_commbuys_p2.xml")]
        rows = {r["source_id"]: r for r in massachusetts.collect(TODAY, pages=pages)}
        self.assertEqual(set(rows), {"BD-1", "BD-2"})
        self.assertEqual(rows["BD-1"]["listing_type"], "Grant")
        self.assertEqual(rows["BD-1"]["close_date"], "2026-11-06")
        self.assertEqual(rows["BD-2"]["funder"], "City of Fitchburg")
        self.assertIn("docId=BD-2", rows["BD-2"]["link"])


class VirginiaTest(unittest.TestCase):
    def test_keeps_open_future_and_normalizes(self):
        rows = virginia.collect(TODAY, data=json.loads(_read("sample_virginia.json")))
        self.assertEqual([r["source_id"] for r in rows], ["VBO:IFB:A123:1"])
        row = rows[0]
        self.assertEqual((row["post_date"], row["close_date"]), ("2026-09-01", "2026-11-01"))
        self.assertEqual(row["summary"], "Furnish sensors .")
        self.assertEqual(row["topics"], "Water Testing Equipment")
        self.assertEqual(row["location"], "Virginia Beach, VA")
        self.assertIn("VBODetails.jsp", row["link"])
        self.assertIn("BID_INTRNL_NO=1", row["link"])

    def test_local_government_bids_link_to_their_own_page(self):
        link = virginia._link({"app": "IV", "internalid": "128282", "version": "1"})
        self.assertEqual(link, "https://mvendor.cgieva.com/Vendor/public/IVDetails.jsp?"
                               "PageTitle=SO+Details&rfp_id_lot=128282&rfp_id_round=1")


class GlriTest(unittest.TestCase):
    def test_reads_open_list_and_fills_details_from_yearly_table(self):
        rows = glri.collect(TODAY, page=_read("sample_glri.html"))
        self.assertEqual([r["title"] for r in rows], [
            "Community Forest Grant in Lake Superior Basin", "Lake Erie Community Grant Program",
            "Southeast Michigan Resilience Fund"])
        self.assertEqual(rows[0]["funder"], "USDA Forest Service")
        self.assertEqual(rows[2]["funder"], "DOI-USFWS and the National Fish and Wildlife Foundation")
        self.assertIn("stormwater", rows[2]["summary"])
        self.assertIn("Usually announced: Fall.", rows[2]["summary"])
        self.assertEqual(rows[1]["source_id"], rows[1]["link"])

    def test_skips_grants_gov_links(self):
        page = _read("sample_glri.html").replace(
            "https://lakeerie.ohio.gov/funding-oportunities/protection-fund/lake+erie+community+grant",
            "https://www.grants.gov/search-results-detail/123")
        self.assertEqual(len(glri.collect(TODAY, page=page)), 2)

    def test_changed_layout_fails_loudly(self):
        with self.assertRaises(ValueError):
            glri.collect(TODAY, page="<html>moved</html>")


class PrizesTest(unittest.TestCase):
    def test_reads_open_xtech_cards_and_skips_empty_usbr_page(self):
        rows = prizes.collect(TODAY, xtech_page=_read("sample_xtech.html"), usbr_page=_read("sample_usbr_none.html"))
        self.assertEqual([r["source_id"] for r in rows], ["xtechsearch10"])
        row = rows[0]
        self.assertEqual(row["title"], "xTech|Search 10")
        self.assertEqual((row["post_date"], row["close_date"]), ("2026-09-10", "2026-10-19"))
        self.assertIn("unmanned vessel", row["summary"])

    def test_usbr_page_with_a_competition_is_listed(self):
        page = _read("sample_usbr_none.html").replace(
            "There are currently no prize competitions accepting submissions.", "Halt the Hitchhiker Phase 2 is open.")
        rows = prizes.parse_usbr(page, TODAY)
        self.assertEqual(len(rows), 1)
        self.assertIn("Halt the Hitchhiker", rows[0]["summary"])
        self.assertEqual(rows[0]["source_id"], prizes.parse_usbr(page, TODAY)[0]["source_id"])


class CalendarTest(unittest.TestCase):
    SHEET = (
        "Program,Run by,Kind,Opens,Closes,Rolling,Amount,Who can apply,Location,Usual window,Link,About,Last checked,Notes\n"
        "Imagine H2O,Imagine H2O,Accelerator,2026-10-12,2026-11-20,,,Any company,Global,Oct to Nov,https://x,Water accelerator.,2026-10-01,\n"
        "BREW 2.0,The Water Council,Accelerator,,11/13/2026,,,Any company,,,https://y,,2026-06-01,\n"
        "Great Lakes Protection Fund,GLPF,Grant,,,yes,,Any company,,Rolling,https://z,,2026-10-01,\n"
        "Cleantech Open,Cleantech Open,Accelerator,,,,,Any company,,Feb to Apr,https://w,,2026-10-01,\n"
        "Tech Challenge,The Water Council,Prize,,2026-10-02,,Up to $10K,Any company,,,https://v,,2026-10-01,\n"
        ",,,,,,,,,,,,,\n")

    def setUp(self):
        self.rows = programs.parse(self.SHEET)
        self.listed = {r["title"]: r for r in programs.collect(TODAY, rows=self.rows)}

    def test_lists_open_upcoming_and_rolling_rounds(self):
        self.assertEqual(set(self.listed), {"Imagine H2O", "BREW 2.0", "Great Lakes Protection Fund"})
        row = self.listed["Imagine H2O"]
        self.assertEqual((row["status"], row["post_date"], row["close_date"]), ("forecast", "2026-10-12", "2026-11-20"))
        self.assertEqual(row["source_id"], "imagine-h2o-2026")
        self.assertEqual(self.listed["BREW 2.0"]["close_date"], "2026-11-13")  # US-style date accepted
        self.assertEqual(self.listed["Great Lakes Protection Fund"]["source_id"], "great-lakes-protection-fund-rolling")

    def test_plain_columns_and_profile_keep_every_program(self):
        rows = plain.add(list(self.listed.values()))
        by = {r["title"]: r for r in rows}
        self.assertEqual(by["Imagine H2O"]["kind"], "Accelerator")
        self.assertEqual(by["Imagine H2O"]["stage"], "Coming soon")
        self.assertEqual(by["Imagine H2O"]["who_can_apply"], "Any company")
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        self.assertEqual(len(profile.apply(prof, rows)), 3)  # no water words needed

    def test_checks_flag_rows_needing_dates(self):
        found = dict(programs.checks(TODAY, self.rows))
        self.assertEqual(found, {
            "BREW 2.0": "Not checked in 90 days; confirm the dates",
            "Cleantech Open": "Add this round's dates",
            "Tech Challenge": "Round closed; add next round's dates",
        })

    def test_missing_tab_falls_back_to_mirror(self):
        self.assertFalse(programs._valid("title,funder\nSomething else,x\n"))
        self.assertTrue(programs._valid(self.SHEET))

    def test_repo_calendar_file_parses(self):
        rows = programs.read_mirror(os.path.join(HERE, "..", "data", "calendar.csv"))
        self.assertGreaterEqual(len(rows), 10)
        self.assertTrue(all(r["program"] and r["link"].startswith("https://") for r in rows))


class PoolTest(unittest.TestCase):
    def test_merge_keeps_first_seen_and_other_sources(self):
        previous = [
            {"source": "grants.gov", "source_id": "100", "first_seen": "2026-09-01"},
            {"source": "grants.gov", "source_id": "999", "first_seen": "2026-08-01"},
            {"source": "nyc", "source_id": "A", "first_seen": "2026-09-15"},
        ]
        fresh = [{"source": "grants.gov", "source_id": "100"}, {"source": "grants.gov", "source_id": "200"}]
        merged = {r["source_id"]: r for r in pool.merge(previous, "grants.gov", fresh, TODAY)}
        self.assertEqual(set(merged), {"100", "200", "A"})  # 999 closed and dropped
        self.assertEqual(merged["100"]["first_seen"], "2026-09-01")
        self.assertEqual(merged["200"]["first_seen"], "2026-10-05")
        self.assertEqual(merged["100"]["last_seen"], "2026-10-05")


class ProfileTest(unittest.TestCase):
    def test_default_profile_filters_by_keyword_and_eligibility(self):
        rows = grantsgov.collect(TODAY, xml_source=SAMPLE)
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        ids = {r["source_id"] for r in profile.apply(prof, rows)}
        # 102 is water-related but open to universities only.
        self.assertEqual(ids, {"100", "103"})

    def test_default_profile_keeps_matching_city_solicitations(self):
        with open(os.path.join(HERE, "sample_nyc.json"), encoding="utf-8") as f:
            rows = nyc.collect(datetime.date(2026, 7, 1), rows=json.load(f))
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        ids = {r["source_id"] for r in profile.apply(prof, rows)}
        self.assertEqual(ids, {"20260903027"})  # the locks bid has no water keywords

    def test_default_profile_keeps_every_water_agency_bid(self):
        rows = mwrd.collect(TODAY, page=_read("sample_mwrd.html"), details={})
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        dropped = []
        ids = {r["source_id"] for r in profile.apply(prof, rows, dropped)}
        self.assertEqual(ids, {"25-RFP-20"})  # the CMMS software RFP has no water words
        # The sewer rehabilitation bid matches as a water-agency bid but is construction.
        self.assertEqual([row["source_id"] for row, _ in dropped], ["23-890-1S"])

    def test_default_profile_keeps_only_allowed_contract_codes(self):
        with open(os.path.join(HERE, "sample_samgov.csv"), encoding="cp1252") as f:
            rows = samgov.collect(TODAY, csv_text=f.read())
        construction = dict(rows[0], source_id="c1", topics="NAICS 237110; PSC Y1ND")
        boat_part = dict(rows[0], source_id="c2", topics="NAICS 336612; PSC 2040")
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        ids = {r["source_id"] for r in profile.apply(prof, rows + [construction, boat_part])}
        self.assertEqual(ids, {"s6", "s2"})

    def test_who_can_bid_rules_drop_and_record_reasons(self):
        base = {k: "" for k in pool.FIELDS}
        base.update(title="Stormwater monitoring", summary="water quality", eligibility="Any vendor",
                    funder="City", listing_type="Contract (bid)")
        rows = [
            dict(base, source_id="keep"),
            dict(base, source_id="setaside", eligibility="Total Small Business; 8(a) Set-Aside"),
            dict(base, source_id="build", title="Water Main Replacement Phase 2"),
            dict(base, source_id="grant", title="Water Main Replacement Planning Grant",
                 listing_type="Grant", eligibility="Others (see listing)"),
            dict(base, source_id="category", title="Stormwater pond retrofit", topics="Category: Construction"),
            dict(base, source_id="locating", title="Locating Underground Water & Sanitary Sewer",
                 topics="Category: Construction"),
            dict(base, source_id="noprofit", listing_type="Grant", eligibility="Others (see listing)",
                 eligibility_notes="For-profit organizations are not eligible to apply."),
            dict(base, source_id="seelisting", listing_type="Grant", eligibility="Others (see listing)",
                 eligibility_notes="See the full announcement for details."),
        ]
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        dropped = []
        ids = {r["source_id"] for r in profile.apply(prof, rows, dropped)}
        self.assertEqual(ids, {"keep", "grant", "seelisting", "locating"})
        reasons = {row["source_id"]: reason for row, reason in dropped}
        self.assertEqual(reasons["setaside"], "set-aside: 8(a)")
        self.assertEqual(reasons["build"], "construction bid: water main replacement")
        self.assertEqual(reasons["category"], "construction bid: Category: Construction")
        self.assertNotIn("locating", reasons)
        self.assertTrue(reasons["noprofit"].startswith("not open to businesses"))

    def test_off_topic_utility_bids_are_set_aside(self):
        base = {k: "" for k in pool.FIELDS}
        base.update(eligibility="Any vendor", funder="Northeast Ohio Regional Sewer District",
                    listing_type="Contract (bid)")
        rows = [
            dict(base, source_id="rubbish", title="Rubbish Removal and Recycling Services"),
            dict(base, source_id="chlorine", title="Sodium Hypochlorite Solution at all Wastewater Treatment Plants"),
            dict(base, source_id="itsm", title="Request for Information: IT Service Management Platform"),
            dict(base, source_id="tech", title="Landscape drainage monitoring"),  # technical words win
            dict(base, source_id="grant", title="Landscape restoration grant", listing_type="Grant"),
        ]
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        dropped = []
        ids = {r["source_id"] for r in profile.apply(prof, rows, dropped)}
        self.assertEqual(ids, {"itsm", "tech", "grant"})
        reasons = {row["source_id"]: reason for row, reason in dropped}
        self.assertEqual(reasons, {"rubbish": "off-topic bid: rubbish", "chlorine": "off-topic bid: hypochlorite"})



class PlainTest(unittest.TestCase):
    def row(self, **fields):
        base = {k: "" for k in pool.FIELDS}
        base.update(fields)
        return plain.describe(base)

    def test_grant_with_ceiling_and_see_listing(self):
        got = self.row(listing_type="Cooperative agreement; Grant", status="posted", close_date="2026-11-01",
                       award_ceiling="1657690", eligibility="Others (see listing)",
                       summary="Study salinity &amp;amp; flow. More detail follows.")
        self.assertEqual(got["kind"], "Grant")
        self.assertEqual(got["stage"], "Open")
        self.assertEqual(got["deadline"], "2026-11-01")
        self.assertEqual(got["amount"], "Up to $1.7M")
        self.assertEqual(got["who_can_apply"], "Check listing")
        self.assertEqual(got["short_summary"], "Study salinity & flow. More detail follows.")

    def test_contract_stages_and_set_asides(self):
        sought = self.row(listing_type="Contract (Sources Sought)", status="forecast",
                          eligibility="Small Business Set Aside - Total")
        self.assertEqual((sought["kind"], sought["stage"], sought["who_can_apply"]),
                         ("Contract", "Info request", "Small businesses only"))
        presol = self.row(listing_type="Contract (Presolicitation)", status="forecast", eligibility="Any vendor")
        self.assertEqual((presol["stage"], presol["deadline"], presol["who_can_apply"]),
                         ("Coming soon", "Not set", "Any company"))

    def test_total_funding_and_long_summary(self):
        got = self.row(listing_type="Grant", total_funding="3500000", eligibility="Business; Nonprofit",
                       summary="word " * 100)
        self.assertEqual(got["amount"], "$3.5M total")
        self.assertEqual(got["who_can_apply"], "Companies eligible")
        self.assertTrue(got["short_summary"].endswith(" ...") and len(got["short_summary"]) <= 284)


class ArchiveTest(unittest.TestCase):
    def test_closed_water_listings_are_archived_once(self):
        import tempfile
        base = {k: "" for k in pool.FIELDS}
        previous = [dict(base, source="mwrd", source_id="1", title="Sewer flow monitoring", funder="City"),
                    dict(base, source="mwrd", source_id="2", title="Office chairs", funder="City"),
                    dict(base, source="mwrd", source_id="3", title="Stormwater study", funder="City"),
                    dict(base, source="nyc", source_id="1", title="Wastewater sensors", funder="City")]
        fresh = [dict(base, source="mwrd", source_id="3", title="Stormwater study", funder="City")]
        gone = pool.closed(previous, "mwrd", fresh)
        self.assertEqual([r["source_id"] for r in gone], ["1", "2"])
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        water = profile.on_topic(prof, gone)
        self.assertEqual([r["title"] for r in water], ["Sewer flow monitoring"])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "archive", "2026.csv")
            self.assertEqual(pool.archive(path, water), 1)
            self.assertEqual(pool.archive(path, water), 1)  # the same listing is not added twice


class LeadsTest(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 8)

    def setUp(self):
        prof = profile.load(os.path.join(HERE, "..", "profile.toml"))
        self.calls = leads._words(prof["leads"]["call_words"])
        self.title_calls = leads._words(prof["leads"]["call_title_words"])
        water = prof["filter"]["keywords"]
        self.topics = {"water": leads._words(water),
                       "climate": leads._words(water + prof["leads"]["climate_words"])}

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_rss_keeps_recent_calls(self):
        posts = leads.parse_rss(self._read("sample_leads.xml"))
        self.assertEqual(len(posts), 3)
        rows = leads.pick(posts, {"name": "Sample"}, self.calls, self.title_calls, self.topics, self.TODAY)
        # The member profile has no call words; the 2025 post is old news.
        self.assertEqual([r["title"] for r in rows], ["Applications Open: Stormwater Sensor Challenge"])
        self.assertEqual(rows[0]["deadline"], "2026-11-20")
        self.assertEqual(rows[0]["posted"], "2026-10-05")
        self.assertIn("apply", rows[0]["why"])

    def test_standing_feed_keeps_every_program(self):
        posts = leads.parse_wp(self._read("sample_leads_wp.json"))
        feed = {"name": "Awards", "standing": True}
        rows = leads.pick(posts, feed, self.calls, self.title_calls, self.topics, self.TODAY)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["why"], "award")  # from the title
        self.assertEqual(rows[1]["why"], "apply, prize")

    def test_needs_water(self):
        posts = leads.parse_wp(self._read("sample_leads_wp.json"))
        feed = {"name": "Awards", "standing": True, "needs": "water"}
        rows = leads.pick(posts, feed, self.calls, self.title_calls, self.topics, self.TODAY)
        self.assertEqual([r["title"] for r in rows], ["The Gas Utility Innovator Award"])

    def test_skips_closed_calls(self):
        posts = [{"title": "Entries open for a water award", "link": "x", "posted": "2026-07-15",
                  "text": "Deadline Date: September 30, 2026. Apply online."}]
        self.assertEqual(leads.pick(posts, {"name": "S"}, self.calls, self.title_calls, self.topics, self.TODAY), [])

    def test_skips_winner_news(self):
        posts = [{"title": "Tech Challenge Spotlight: Aqua Alarm", "link": "x", "posted": "2026-10-01", "text": ""}]
        skip = leads._words(["spotlight"])
        self.assertEqual(leads.pick(posts, {"name": "S"}, self.calls, self.title_calls, self.topics,
                                    self.TODAY, skip), [])

    def test_deadline_ignores_past_dates(self):
        self.assertEqual(leads.deadline("Deadline: Sept 3, 2026.", self.TODAY), "closed")
        self.assertEqual(leads.deadline("No dates here.", self.TODAY), "")
        self.assertEqual(leads.deadline("Applications close Dec. 1st, 2026", self.TODAY), "2026-12-01")

    def test_merge_keeps_first_seen_and_drops_old(self):
        old = [{"first_seen": "2026-10-01", "posted": "2026-09-30", "link": "a", "title": "A"},
               {"first_seen": "2025-01-01", "posted": "2025-01-01", "link": "b", "title": "B"},
               {"first_seen": "2025-02-01", "posted": "2021-11-15", "link": "d", "title": "Still listed"}]
        fresh = [{"posted": "2026-09-30", "link": "a", "title": "A (edited)"},
                 {"posted": "2026-10-07", "link": "c", "title": "C"},
                 {"posted": "2021-11-15", "link": "e", "title": "Old award page, new to us"},
                 {"posted": "2021-11-15", "link": "d", "title": "Still listed"}]
        rows = leads.merge(old, fresh, self.TODAY)
        # b is gone from the feeds and over a year old; d and e are old posts still in a feed.
        self.assertEqual(sorted(r["link"] for r in rows), ["a", "c", "d", "e"])
        rows = [r for r in rows if r["link"] in ("a", "c")]
        self.assertEqual([r["link"] for r in rows], ["c", "a"])
        self.assertEqual(rows[1]["first_seen"], "2026-10-01")
        self.assertEqual(rows[1]["title"], "A (edited)")


class FailureStreakTest(unittest.TestCase):
    def test_streaks_count_days_in_a_row(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "failures.csv")
            self.assertEqual(run.update_streaks(path, ["mmsd"]), {"mmsd": 1})
            self.assertEqual(run.update_streaks(path, ["mmsd", "chicago"]), {"mmsd": 2, "chicago": 1})
            # A day without failure resets the count.
            self.assertEqual(run.update_streaks(path, ["chicago"]), {"chicago": 2})
            self.assertEqual(run.update_streaks(path, ["mmsd", "chicago"]), {"mmsd": 1, "chicago": 3})


class TextTest(unittest.TestCase):
    def _fetch_with(self, *results):
        """Run text.fetch against a fake site that gives these results in turn."""
        calls = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_open(request, timeout):
            calls.append(request.full_url)
            result = results[len(calls) - 1]
            if isinstance(result, Exception):
                raise result
            return Response(result)

        with mock.patch.object(text._opener, "open", fake_open), mock.patch.object(text.time, "sleep"):
            return text.fetch("https://example.com/x"), calls

    def _error(self, code):
        return urllib.error.HTTPError("https://example.com/x", code, "error", {}, None)

    def test_fetch_retries_a_server_error_once(self):
        body, calls = self._fetch_with(self._error(500), b"ok")
        self.assertEqual(body, b"ok")
        self.assertEqual(len(calls), 2)

    def test_fetch_gives_up_after_second_server_error(self):
        with self.assertRaises(urllib.error.HTTPError):
            self._fetch_with(self._error(503), self._error(503))

    def test_fetch_does_not_retry_client_errors(self):
        with self.assertRaises(urllib.error.HTTPError):
            self._fetch_with(self._error(404), b"never reached")

    def test_drop_default_port(self):
        self.assertEqual(text.drop_default_port("https://s3.amazonaws.com:443/b/f.csv?X-Amz-Signature=abc"),
                         "https://s3.amazonaws.com/b/f.csv?X-Amz-Signature=abc")
        self.assertEqual(text.drop_default_port("https://example.com:8443/x"), "https://example.com:8443/x")
        self.assertEqual(text.drop_default_port("https://example.com/x"), "https://example.com/x")


class SamGovTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "sample_samgov.csv"), encoding="cp1252") as f:
            self.rows = {r["source_id"]: r for r in samgov.collect(TODAY, csv_text=f.read())}

    def test_keeps_open_solicitations_and_early_notices(self):
        # s3 is an award, s4 is past its deadline, s5 has no deadline and is not an early notice,
        # and s6 is a later amendment of s1, so it replaces s1.
        self.assertEqual(set(self.rows), {"s6", "s2"})

    def test_normalizes_fields(self):
        row = self.rows["s6"]
        self.assertEqual(row["title"], "Stormwater sensor network pilot - Amendment 1")
        self.assertEqual(row["funder"], "National Oceanic And Atmospheric Administration")
        self.assertEqual(row["listing_type"], "Contract (Solicitation)")
        self.assertEqual(row["close_date"], "2026-11-05")
        self.assertEqual(row["eligibility"], "Small Business Set Aside - Total")
        self.assertEqual(row["topics"], "NAICS 334519; PSC 6665")
        self.assertEqual(row["location"], "Ann Arbor, MI")
        self.assertEqual(row["summary"], "Deploy sensors & telemetry.")

    def test_early_notice_without_deadline(self):
        row = self.rows["s2"]
        self.assertEqual(row["status"], "forecast")
        self.assertEqual(row["close_date"], "")
        self.assertEqual(row["eligibility"], "Any vendor")
        self.assertEqual(row["location"], "National")


if __name__ == "__main__":
    unittest.main()
