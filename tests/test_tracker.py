import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from tracker import fit, fundsforngos, grantsgov, leads, plain, pool, profile, programs, run, text

HERE = os.path.dirname(__file__)
SAMPLE = os.path.join(HERE, "sample_extract.xml")
TODAY = datetime.date(2026, 10, 5)
PROFILE = profile.load(os.path.join(HERE, "..", "profile.toml"))


def _ffn_rows(today=datetime.date(2026, 10, 15)):
    with open(os.path.join(HERE, "sample_fundsforngos.json"), encoding="utf-8") as f:
        items = json.load(f)
    return plain.add(fundsforngos.collect(today, {}, items=items))


class GrantsGovTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in grantsgov.collect(TODAY, xml_source=SAMPLE)}

    def test_keeps_open_and_forecast_only(self):
        self.assertEqual(set(self.rows), {"100", "102", "103", "200", "201"})

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


class FundsForNgosTest(unittest.TestCase):
    def setUp(self):
        self.rows = {r["source_id"]: r for r in _ffn_rows()}

    def test_reads_posts_and_drops_passed_deadlines(self):
        self.assertEqual(len(self.rows), 12)
        self.assertNotIn("12", self.rows)  # Telangana lake call closed on 1 Sep 2026

    def test_normalizes_fields(self):
        row = self.rows["1"]
        self.assertEqual(row["close_date"], "2026-11-30")
        self.assertEqual(row["funder"], "Example Climate Foundation")
        self.assertEqual(row["link"], "https://www2.fundsforngos.org/?p=1")
        self.assertIn("registered non-profit organisations in India", row["eligibility_notes"])
        self.assertFalse(row["summary"].startswith("Deadline"))
        self.assertEqual(self.rows["8"]["listing_type"], "Prize or award")
        self.assertEqual(self.rows["10"]["close_date"], "")  # rolling

    def test_left_feed_but_still_open(self):
        today = datetime.date(2026, 10, 15)
        self.assertTrue(fundsforngos.still_open({"close_date": "2026-11-01"}, today, 120))
        self.assertFalse(fundsforngos.still_open({"close_date": "2026-10-14"}, today, 120))
        self.assertTrue(fundsforngos.still_open({"close_date": "", "first_seen": "2026-08-01"}, today, 120))
        self.assertFalse(fundsforngos.still_open({"close_date": "", "first_seen": "2026-05-01"}, today, 120))


class FbhProfileTest(unittest.TestCase):
    def setUp(self):
        self.dropped = []
        self.matches = {r["source_id"]: r for r in profile.apply(PROFILE, _ffn_rows(), self.dropped)}
        self.reasons = {r["source_id"]: why for r, why in self.dropped}

    def test_strong_fits_score_high(self):
        self.assertEqual(self.matches["1"]["fit_score"], "5")  # biochar, India, NGOs, $150K
        self.assertEqual(self.matches["4"]["fit_score"], "5")  # wetlands, developing countries, EUR
        self.assertIn("Biochar & carbon removal", self.matches["1"]["fbh_area"])
        self.assertEqual(self.matches["1"]["geography"], "India named")
        self.assertTrue(self.matches["1"]["eligibility_check"].startswith("Confirmed: NGOs"))

    def test_unclear_eligibility_is_kept_and_marked_verify(self):
        row = self.matches["10"]
        self.assertEqual(row["geography"], "Unclear")
        self.assertIn("Verify: NGO eligibility not stated", row["eligibility_check"])
        self.assertIn("partner may be needed", self.matches["4"]["who_can_apply"])

    def test_rules_set_aside_with_reasons(self):
        self.assertTrue(self.reasons["2"].startswith("geography: for Kenya"))
        self.assertTrue(self.reasons["3"].startswith("for companies or start-ups"))
        self.assertTrue(self.reasons["5"].startswith("for individuals"))
        self.assertTrue(self.reasons["6"].startswith("procurement"))
        self.assertTrue(self.reasons["7"].startswith("too small"))
        self.assertTrue(self.reasons["9"].startswith("geography: US-based"))

    def test_off_topic_is_skipped(self):
        for source_id in ("11", "13"):  # health in Bangladesh, shipping report
            self.assertNotIn(source_id, self.matches)
            self.assertNotIn(source_id, self.reasons)

    def test_best_fit_first(self):
        scores = [int(r["fit_score"]) for r in profile.apply(PROFILE, _ffn_rows())]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_watchlist_funder_shows_status(self):
        prof = dict(PROFILE, watchlist={"no_bonus_statuses": ["Discarded"], "funders": [
            {"name": "Example Climate Foundation", "status": "Contacted", "match": ["Example Climate Foundation"]},
            {"name": "Nature Fund", "status": "Discarded", "match": ["Nature-based Solutions Fund"]}]})
        rows = {r["source_id"]: r for r in profile.apply(prof, _ffn_rows())}
        self.assertEqual(rows["1"]["in_pipeline"], "Example Climate Foundation: Contacted")
        self.assertIn("in our pipeline", rows["1"]["fit_reason"])
        self.assertEqual(rows["10"]["in_pipeline"], "Nature Fund: Discarded")
        self.assertEqual(rows["10"]["fit_score"], "2")  # no bonus for a discarded funder

    def test_pipeline_names_match_whole_words_only(self):
        rules = fit.Rules(PROFILE)
        hits = lambda text: [name for name, _, p in rules.watchlist if p.search(text)]
        self.assertIn("Tata Trusts", hits("A call from Tata Trusts for water NGOs"))
        self.assertEqual(hits("Restoring forests in the Amazon basin near San Francisco"), [])

    def test_grants_gov_keeps_only_foreign_eligible_nonprofit_grants(self):
        rows = plain.add(grantsgov.collect(TODAY, xml_source=SAMPLE))
        dropped = []
        matches = {r["source_id"]: r for r in profile.apply(PROFILE, rows, dropped)}
        self.assertEqual(set(matches), {"200"})
        self.assertEqual(matches["200"]["geography"], "International (check India)")
        self.assertEqual(matches["200"]["amount"], "Up to $200K")
        reasons = {r["source_id"]: why for r, why in dropped}
        self.assertTrue(reasons["201"].startswith("geography: US federal grant"))


class MoneyAndDatesTest(unittest.TestCase):
    RATES = {"USD": 1.0, "EUR": 1.1, "INR": 0.0114, "GBP": 1.3}

    def test_amounts(self):
        def usd(text):
            return round(max(fit.amounts(text, self.RATES))[0])
        self.assertEqual(usd("Grants of up to USD 150,000."), 150000)
        self.assertEqual(usd("A prize pool of $1 million."), 1000000)
        self.assertEqual(usd("Up to INR 50 lakh."), 57000)
        self.assertEqual(usd("Between EUR 100,000 and EUR 500,000"), 550000)
        self.assertEqual(usd("Grants of £25k"), 32500)
        self.assertEqual(fit.amounts("Founded in 2019 with 40 projects", self.RATES), [])

    def test_deadlines(self):
        self.assertEqual(text.deadline_in("Deadline: 15-Sep-2026 Donor"), datetime.date(2026, 9, 15))
        self.assertEqual(text.deadline_in("Applications are due by September 30, 2026."), datetime.date(2026, 9, 30))
        self.assertEqual(text.deadline_in("Closing date: 1st December 2026"), datetime.date(2026, 12, 1))
        self.assertIsNone(text.deadline_in("Founded on 1 May 2001. Rolling applications."))


class CalendarTest(unittest.TestCase):
    SHEET = (
        "Program,Run by,Kind,Opens,Closes,Rolling,Amount,Who can apply,Location,Usual window,Link,About,Last checked,Notes\n"
        "Darwin Initiative,Defra,Grant,2026-10-01,2026-12-01,,Up to £600K,NGOs,India eligible,Autumn,https://x,Biodiversity.,2026-10-01,\n"
        "Rolling Fund,Some Trust,Grant,,,yes,,NGOs,India,Rolling,https://z,,2026-10-01,\n"
        "No Dates Yet,Foundation,Grant,,,,,,,,https://w,,2026-10-01,\n"
        "Old Round,Foundation,Grant,,2026-09-01,,,,,,https://v,,2026-10-01,\n"
        ",,,,,,,,,,,,,\n")

    def setUp(self):
        self.rows = programs.parse(self.SHEET)
        self.listed = {r["title"]: r for r in programs.collect(TODAY, rows=self.rows)}

    def test_lists_open_and_rolling_rounds(self):
        self.assertEqual(set(self.listed), {"Darwin Initiative", "Rolling Fund"})

    def test_calendar_rows_always_count_and_get_scored(self):
        matches = profile.apply(PROFILE, plain.add(list(self.listed.values())))
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(r["fit_score"] for r in matches))

    def test_checks_flag_rows_needing_dates(self):
        self.assertEqual(dict(programs.checks(TODAY, self.rows)), {
            "No Dates Yet": "Add this round's dates", "Old Round": "Round closed; add next round's dates"})

    def test_repo_calendar_file_parses(self):
        rows = programs.read_mirror(os.path.join(HERE, "..", "data", "calendar.csv"))
        self.assertTrue(rows)
        self.assertGreaterEqual(len(rows), 15)
        self.assertTrue(all(r["program"] and (not r["link"] or r["link"].startswith("https://")) for r in rows))

    def test_sheet_column_names_are_understood(self):
        rows = programs.parse("Program,Run by,Link,Opens,Closes,Cadence,Amount (USD),Criteria,Comments\n"
                              "IKI Medium Grants,IKI,https://x,2026-10-13 00:00:00,2027-01-12,Yearly,€300k,Climate,Lead needed\n")
        row = programs.collect(TODAY, rows=rows)[0]
        self.assertEqual((row["post_date"], row["close_date"]), ("2026-10-13", "2027-01-12"))
        self.assertIn("€300k", row["summary"])


class RunTest(unittest.TestCase):
    def test_flags(self):
        today = datetime.date(2026, 10, 15)
        row = {"source": "fundsforngos", "first_seen": "2026-10-14", "close_date": "2026-10-30", "stage": "Open"}
        self.assertEqual(run.flag(row, today, []), "NEW, Closing soon")
        row = dict(row, first_seen="2026-09-01", close_date="2027-01-01")
        self.assertEqual(run.flag(row, today, []), "Open")
        self.assertEqual(run.flag(row, today, ["fundsforngos"]), "Source down today (not re-checked)")

    def test_feed_listings_stay_until_deadline(self):
        today = datetime.date(2026, 10, 15)
        previous = [{"source": "fundsforngos", "source_id": "1", "close_date": "2026-11-01", "first_seen": "2026-10-01"},
                    {"source": "fundsforngos", "source_id": "2", "close_date": "2026-10-01", "first_seen": "2026-09-01"},
                    {"source": "grants.gov", "source_id": "9", "close_date": "", "first_seen": "2026-09-01"}]
        fresh = [{"source": "fundsforngos", "source_id": "3", "close_date": ""}]
        kept = run._keep_until_deadline(previous, "fundsforngos", fresh, today, 120)
        self.assertEqual([r["source_id"] for r in kept], ["3", "1"])

    def test_opportunities_file(self):
        rows = profile.apply(PROFILE, _ffn_rows())
        for r in rows:
            r["first_seen"] = r["last_seen"] = "2026-10-15"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "opportunities.csv")
            run.save_opportunities(path, rows, datetime.date(2026, 10, 15), [])
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        self.assertTrue(lines[0].startswith("Flag,Fit (1-5),FBH area,Funder,Grant / program"))
        self.assertEqual(len(lines), len(rows) + 1)


class ArchiveTest(unittest.TestCase):
    def test_closed_listings_are_archived_once_with_date(self):
        rows = profile.on_topic(PROFILE, _ffn_rows())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "archive", "2026.csv")
            self.assertEqual(pool.archive(path, rows[:2], datetime.date(2026, 10, 15)), 2)
            self.assertEqual(pool.archive(path, rows[:2], datetime.date(2026, 10, 16)), 2)
            self.assertEqual({r["closed_on"] for r in pool.load(path)}, {"2026-10-15"})


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


class LeadsTest(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 8)

    def setUp(self):
        # Fixed word lists, so these tests check the feed reader, not today's settings.
        self.calls = leads._words(["apply", "applications open", "call for"])
        self.title_calls = leads._words(["prize", "challenge", "award", "deadline"])
        water = ["water", "stormwater", "river"]
        self.topics = {"water": leads._words(water), "climate": leads._words(water + ["climate"])}

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


