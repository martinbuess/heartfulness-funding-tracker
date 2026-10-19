# Forests by Heartfulness Funding Tracker

A free, self-running list of open grant opportunities for [Forests by Heartfulness](https://heartfulness.org/) (FBH), the environmental initiative of the Heartfulness Institute. Adapted from Gaurav Shikhar Gandhi's [GLIA Funding Tracker](https://github.com/gauravshikhargandhi-web/glia-funding-tracker).

Every day a GitHub job reads public funding sources, keeps the calls that fit FBH's four program areas, named as in the FBH summary deck:

1. **Ecological restoration & biodiversity**: native afforestation, hill greening, degraded forest and landscape restoration, endangered native species, nurseries, urban forests
2. **Water & watershed restoration**: lakes and ponds, rainwater harvesting, groundwater recharge, watersheds, climate resilience
3. **Carbon & climate solutions**: biochar, soil carbon, carbon sequestration, nature-based carbon removal
4. **Regenerative agriculture & rural livelihoods**: agroforestry, soil health, horticulture, rural incomes

Each call is also matched to FBH's projects (the **Best-fit FBH projects** column): Shivgarh landscape restoration, Peddaveedu pond & water security, village-scale biochar, agroforestry livelihoods, the Gachibowli urban rainforest, and the endangered native trees & nursery network. Edit them under `[[projects]]` in `profile.toml`.

## What's in it

| File | What it holds |
| --- | --- |
| [`data/opportunities.csv`](data/opportunities.csv) | **The main result.** Open opportunities that fit FBH, best fit first, with plain column names. This is what the Google Sheet shows. |
| [`data/matches.csv`](data/matches.csv) | The same listings with every column the sources give |
| [`data/filtered_out.csv`](data/filtered_out.csv) | Listings on FBH's topics that a rule removed (another country only, US only, procurement, start-ups only, for individuals, under $10K), with the reason in the last column. Check it now and then. |
| [`data/listings.csv`](data/listings.csv) | Every open listing read today, relevant or not |
| [`data/archive/`](data/archive) | Relevant listings that closed or passed their deadline, with the date, one file per year. Nothing is deleted. |
| [`data/calendar.csv`](data/calendar.csv) | Yearly programs with no feed, kept by hand (see below) |
| [`data/watch.csv`](data/watch.csv) | The watched funder pages: whether each changed, what it says about applications, and the next date it mentions |
| [`data/summary.csv`](data/summary.csv) | Today's counts and each source's status (feeds the sheet's About tab) |
| [`profile.toml`](profile.toml) | **The settings**: keywords for each program area, places, who can apply, size limits, and the funders in our pipeline |

## How each opportunity is scored

| Column | What it means |
| --- | --- |
| Fit (1-5) | Topic: an FBH area word in the title (2) or description (1), or 0 when the call's main focus is outside FBH (marine, coastal, redwoods, animal welfare… see `off_focus` in `profile.toml`). Place: India listed or named (2), open internationally (1). Applicants: NGOs named as eligible (1). Size: US$50,000 or more (1), under (−1). Pipeline funder (1). Then capped: at most 3 when the call doesn't say where the work can happen, at most 2 for off-focus calls and EU consortium calls. "Why this score" starts with the sum. |
| Best-fit FBH projects | FBH projects whose words appear in the call, best match first, with the words that matched (`[[projects]]` in `profile.toml`) |
| FBH area | Which of the four program areas matched |
| Geography | India named, International (check India), or Unclear |
| Who can apply | NGOs eligible, Anyone, Check listing; "partner may be needed" when a consortium is mentioned |
| Eligibility: confirmed vs. to verify | "Confirmed" lists what the listing itself says. "Verify" lists our assumptions to check before applying. |
| Why this score | The words that matched, the place, who can apply and the size, in one sentence |
| Flag | NEW (first seen in the last 7 days), Closing soon (deadline within 21 days), Coming soon, or Source down today |
| Last verified | The last day the tracker saw the listing still open at its source |

Rules that **remove** a listing (it goes to `filtered_out.csv`, never silently): the work is for another named country or the US only; it's a procurement contract, consultancy or tender; it's only for companies or start-ups; it's for individuals (scholarships, fellowships, courses); the stated amount is under US$10,000. Listings with unclear eligibility are **kept** and marked "Verify".

Remember that grants from outside India need FCRA registration to receive.

## Sources

| Source | How | Status |
| --- | --- | --- |
| [fundsforNGOs](https://www2.fundsforngos.org/) | Automatic: its RSS feed (newest 25 posts), once a day. The labelled "Opportunity at a Glance" fields (funding organization, eligible countries, grant size, deadline) are read first. Roundup posts are split into their separate calls. Each call is kept until its deadline (or 120 days with no deadline). | Live |
| [Terra Viva Grants](https://www.terravivagrants.org/) Funding News | Automatic: its RSS feed, once a day. Open calls for agriculture, environment and natural resources in developing countries. | Live |
| [EU Funding & Tenders portal](https://ec.europa.eu/info/funding-tenders/opportunities/portal/) | Automatic: the portal's public search, one search per FBH topic word. Indian organisations can usually join EU calls only as consortium partners, so these are marked "verify". | Live |
| [Grants.gov](https://www.grants.gov) daily extract | Automatic. Only grants open to nonprofits **and** stating that foreign organisations may apply (for example the US Fish & Wildlife Service's Asian elephant fund). | Live |
| Watched funder pages (Wipro Foundation, Global EbA Fund, GEF Small Grants, Darwin Initiative, CEPF, India Water Portal, IKI, Keidanren, Global Food System Challenge, Mohamed bin Zayed Fund) | Automatic: each page's call-related sentences are compared with the day before; a change is flagged on the **Watched pages** tab for a person to look at. Edit the list under `[[watch.pages]]` in `profile.toml`. | Live |
| Calendar of yearly programs | By hand, in `data/calendar.csv` (from the Calendar tab of the pipeline sheet) | Live |
| HCL Foundation (HCLTech Grant), Whitley Award | Their sites ask automated readers not to visit, so they are in the calendar for manual checks | Manual |
| UN Partner Portal | Calls are visible only after logging in | Manual |
| Devex Funding, DevelopmentAid, Candid, Instrumentl | Paid or behind a login | Not used |

Every download first checks the site's robots.txt and skips anything the site asks automated readers not to fetch. If a source fails, the others still update, that source's previous listings are kept and flagged "Source down today", and the About tab says so. After 3 failed days in a row the run shows as failed in the Actions tab and GitHub emails you. `data/failures.csv` keeps the count.

## Calendar of yearly programs

Some funders open once a year on pages with no feed. Keep them in `data/calendar.csv` (edit it on GitHub with the pencil icon), one row per program per round. Dates are YYYY-MM-DD. Rows that are open or rolling ("yes" in the rolling column) always appear in the results. The About tab lists rows that need dates or haven't been checked in 90 days.

## The Google Sheet and the weekly review

[`sheet/refresh.gs`](sheet/refresh.gs) adds "Tracker –" tabs to the pipeline Google Sheet and refreshes them daily. It never changes your own tabs, except when you choose **Funding tracker → Add selected call to Pipeline**. Setup steps are at the top of the file.

| Tab | What it is for |
| --- | --- |
| **To review** | Open calls (fit 3+) you haven't decided on yet, best first. Your weekly inbox. |
| **Shortlist** | Calls marked Pursue, Contact funder or Clarify, soonest deadline first |
| **All open** | Every open call with its decision, including fit 1–2 |
| **Deadlines** | Everything not discarded that has a date, soonest first |
| **Watched pages** | Funder pages that changed (open them) |
| **Set aside** | What the rules removed, with the reason. Skim monthly. |
| **Decisions** | Every decision you've made, kept permanently. The daily refresh never clears it. |
| **Dashboard** | Start here: headline numbers, deadlines in the next 30 days (red within a week), the best calls waiting for a decision, your shortlist, funder pages that changed, open calls by FBH area and project, and source health |

Pick a **Decision** in column A (Pursue, Contact funder, Clarify, Later, Discard) and a few words in **My notes**. It is saved straight away, and the Shortlist, Deadlines and Dashboard update a few seconds later. Decided calls stay (shaded) in To review until the next full refresh, so rows don't jump while you work; **Funding tracker → Refresh now** clears them out at once.

**When it runs:** the GitHub job collects new calls every day at 12:00 UTC, and the sheet pulls them in every day at 13:00 UTC (and whenever you choose Refresh now).

## Changing what it looks for

Everything is in [`profile.toml`](profile.toml): open it on GitHub, click the pencil icon, edit the word lists, and click **Commit changes**. The next daily run uses the new settings. To run it straight away: **Actions** tab → **Daily refresh** → **Run workflow**.

## Run it on your computer

Needs Python 3.11 or newer and nothing else.

```
python -m tracker.run
python -m unittest discover -s tests -t .
```
