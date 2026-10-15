# Forests by Heartfulness Funding Tracker

A free, self-running list of open grant opportunities for [Forests by Heartfulness](https://heartfulness.org/) (FBH), the environmental initiative of the Heartfulness Institute. Adapted from Gaurav Shikhar Gandhi's [GLIA Funding Tracker](https://github.com/gauravshikhargandhi-web/glia-funding-tracker).

Every day a GitHub job reads public funding sources, keeps the calls that fit FBH's four program areas and can be carried out in India, gives each one a fit score from 1 to 5 with the reasons, and saves the results. A Google Sheet picks them up an hour later.

FBH's four program areas, as the tracker understands them:

1. **Ecological restoration & biodiversity**: native afforestation, forest and landscape restoration, biodiversity, habitats
2. **Water & watershed**: lakes, check dams, groundwater recharge, watersheds, climate resilience
3. **Agroforestry & regenerative agriculture**: farmer livelihoods, soil health, agroecology
4. **Biochar & carbon removal**: biochar, soil carbon, carbon sequestration, nature-based carbon removal

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
| Fit (1-5) | Points for: an FBH area word in the title (2) or description (1); India named (2) or open internationally (1); NGOs named as eligible (1); size known and US$50,000 or more (1, or −1 when under $50K); funder already in our pipeline (1). Capped at 5. |
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
| [fundsforNGOs](https://www2.fundsforngos.org/) | Automatic: its RSS feed (newest 25 posts), once a day. Each call is kept until its deadline (or 120 days with no deadline), so coverage builds up day by day. | Live |
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

## The Google Sheet

[`sheet/refresh.gs`](sheet/refresh.gs) adds these tabs to an existing Google Sheet and refreshes them daily: **Tracker – About**, **New this week**, **Open opportunities**, **Deadlines**, **Watched pages**, **Leads** and **Set aside**. It only writes to tabs whose names start with "Tracker", so your own tabs are never touched. Setup steps are at the top of the file.

For a quick read-only view instead, put this in cell A1 of any sheet:

```
=IMPORTDATA("https://raw.githubusercontent.com/martinbuess/heartfulness-funding-tracker/main/data/opportunities.csv")
```

## Changing what it looks for

Everything is in [`profile.toml`](profile.toml): open it on GitHub, click the pencil icon, edit the word lists, and click **Commit changes**. The next daily run uses the new settings. To run it straight away: **Actions** tab → **Daily refresh** → **Run workflow**.

## Run it on your computer

Needs Python 3.11 or newer and nothing else.

```
python -m tracker.run
python -m unittest discover -s tests -t .
```
