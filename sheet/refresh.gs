/**
 * GLIA funding tracker: keeps this Google Sheet in sync with the GitHub data.
 *
 * Setup (once, or again whenever this file changes):
 *   1. In the sheet: Extensions > Apps Script. Delete what is there, paste this file, click Save.
 *   2. Pick "setUp" in the function menu at the top and click Run. Approve the permissions
 *      Google asks for (it needs to read the URLs below and write to this sheet).
 *   3. Reload the sheet. A "Funding tracker" menu appears with "Refresh now".
 *
 * After that the sheet refreshes itself every day shortly after the GitHub job,
 * and you can click Funding tracker > Refresh now any time. Each refresh rewrites
 * the "Matches", "Leads" and "About" tabs, so don't type into those three tabs.
 *
 * "Leads" lists calls for startups (awards, prizes, open applications) found on
 * incubator and water-cluster news feeds, newest first. It fills itself; nobody
 * has to approve anything.
 *
 * The "Calendar" tab is the opposite: people type into it and the script never
 * overwrites it. The first refresh creates it from the repo's data/calendar.csv;
 * after that the GitHub job reads it every morning. Dates are YYYY-MM-DD.
 * The sheet must stay shared as "Anyone with the link can view" for the job to read it.
 */

// Swap in your own GitHub username and repository if you run your own copy.
const REPO = 'gauravshikhargandhi-web/glia-funding-tracker';
const DATA_URL = 'https://raw.githubusercontent.com/' + REPO + '/main/data/';
const MATCHES_TAB = 'Matches';
const ABOUT_TAB = 'About';
const CALENDAR_TAB = 'Calendar';
const LEADS_TAB = 'Leads';

function refreshNow() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const matches = fetchCsv('matches.csv');
  const sheet = ss.getSheetByName(MATCHES_TAB) || ss.insertSheet(MATCHES_TAB);
  sheet.clearContents();
  sheet.getRange(1, 1, matches.length, matches[0].length).setValues(matches);
  sheet.setFrozenRows(1);
  writeLeads(ss, fetchCsv('leads.csv'));
  writeAbout(ss, fetchCsv('summary.csv'));
  ensureCalendar(ss);
  ss.toast((matches.length - 1) + ' listings loaded', 'Funding tracker', 5);
}

function fetchCsv(name) {
  // The timestamp skips GitHub's cache so we always get the latest file.
  const url = DATA_URL + name + '?t=' + Date.now();
  const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    throw new Error('Could not download ' + url + ' (HTTP ' + response.getResponseCode() + ')');
  }
  return Utilities.parseCsv(response.getContentText());
}

function writeLeads(ss, rows) {
  // leads.csv columns: first_seen, posted, deadline, source, title, link, why, summary
  const sheet = ss.getSheetByName(LEADS_TAB) || ss.insertSheet(LEADS_TAB);
  sheet.clearContents();
  sheet.getRange(1, 1, rows.length, rows[0].length).setNumberFormat('@').setValues(rows);
  sheet.getRange(1, 1, 1, rows[0].length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(5, 380);
  sheet.setColumnWidth(8, 420);
}

function ensureCalendar(ss) {
  // Created once from the repo copy; never overwritten, because people edit it.
  if (ss.getSheetByName(CALENDAR_TAB)) return;
  const rows = fetchCsv('calendar.csv');
  const sheet = ss.insertSheet(CALENDAR_TAB);
  // Plain text everywhere, so Sheets doesn't turn dates into its own format.
  sheet.getRange(1, 1, 500, rows[0].length).setNumberFormat('@');
  sheet.getRange(1, 1, rows.length, rows[0].length).setValues(rows).setVerticalAlignment('top');
  sheet.getRange(1, 1, 1, rows[0].length).setFontWeight('bold');
  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(1);
  sheet.setColumnWidth(1, 240);
  sheet.setColumnWidth(12, 420);
}

function writeAbout(ss, summary) {
  // summary.csv columns: section, name, level, open, matches, set_aside, detail
  const rowsIn = section => summary.slice(1).filter(r => r[0] === section);
  const one = section => rowsIn(section)[0] || [];
  const total = one('total');
  const num = n => Number(n || 0).toLocaleString('en-US');
  const breakdown = section => rowsIn(section).map(r => r[1] + ': ' + num(r[4] || r[5])).join(', ');

  const out = [];
  const headers = [];
  const add = (...cells) => out.push(cells);
  const heading = text => { headers.push(out.length + 1); add(text); };

  add('GLIA Funding Tracker');
  add('Last refreshed ' + (one('run')[6] || '') + '. This tab updates itself with every refresh.');
  add('');
  heading('WHAT IT IS');
  add('A free, automatic pool of grants, contracts, bids and prize competitions for water and water-adjacent startups. ' +
      'Every morning it pulls public sources, cleans them into one table, and picks out the listings that fit our cohort.');
  add('');
  heading('AT A GLANCE');
  add('Open listings in the pool', num(total[3]));
  add('Matches (Matches tab)', num(total[4]), breakdown('kind'));
  add('New matches since yesterday', num(one('new')[4]));
  add('New leads today (Leads tab)', num(one('leads')[4]), one('leads')[6] || '');
  add('Stage of the matches', '', breakdown('stage'));
  add('Who can apply to the matches', '', breakdown('who'));
  add('Set aside as not biddable', num(total[5]), breakdown('set_aside') + ' (kept in data/filtered_out.csv, not deleted)');
  add('Sources', total[6] || '', 'Federal, state, city and water-agency portals, plus prize pages');
  add('Cost to run', '$0', 'Public sources only; no paid data, logins or scraping of gated sites');
  add('');
  heading('SOURCES');
  headers.push(out.length + 1);
  add('Source', 'Level', 'Open today', 'Matches', 'Set aside', 'What it covers');
  rowsIn('source').forEach(r => add(r[1], r[2], num(r[3]), num(r[4]), num(r[5]), r[6]));
  add('');
  const leadsFailed = rowsIn('leads_failed');
  if (leadsFailed.length) {
    add('Leads feeds that could not be read today: ' + leadsFailed.map(r => r[1]).join(', '));
    add('');
  }
  const checks = rowsIn('calendar_check');
  if (checks.length) {
    heading('CALENDAR: NEEDS AN UPDATE');
    add('Update these rows in the Calendar tab (dates as YYYY-MM-DD, and today\'s date in last_checked).');
    checks.forEach(r => add(r[1], r[6]));
    add('');
  }
  heading('HOW MATCHING WORKS');
  add('1. Water keywords', 'Water and water-adjacent terms (stormwater, wastewater, PFAS, coastal, aquaculture, flood, ...). The list grows as new terms show up.');
  add('2. Water agencies', 'Every bid from a water agency counts, even without water words.');
  add('3. Who can apply', 'Keeps listings open to businesses, small businesses, or anyone. Grants that say "see listing" are kept.');
  add('4. Who can win', 'Drops construction bids (contracts only, never grants) and set-asides that need a certification (veteran-owned, 8(a), HUBZone, women-owned). Technical bids (monitoring, testing, sensors, SCADA, data) are always kept.');
  add('5. Noise', 'Drops off-topic uses of "water" (water heaters, water damage, bottled water, lifeguards) federal building repair and facility jobs, and bids for supplies, chemicals, grounds and building services (rubbish, elevators, landscaping).');
  add('6. Calendar', 'Programs in the Calendar tab always count. Open rounds and rolling programs show in Matches; rounds that have not opened yet show as Coming soon.');
  add('');
  heading('READING THE LEADS TAB');
  add('What it is', 'Posts from incubator, water-cluster and funder news feeds that look like a call: apply, award, prize, challenge, deadline. Some are news, not calls; open the link to check.');
  add('deadline', 'A deadline date found in the post, when there is one');
  add('why', 'The words that made the post count as a lead');
  add('Adding a feed', 'Add a block under [leads] in profile.toml on GitHub');
  add('');
  heading('READING THE MATCHES TAB');
  add('kind', 'Grant, Contract, Prize, Accelerator, Pitch competition, Pilot, Loan or Funding notice');
  add('stage', 'Open: apply now. Coming soon: announced, not open yet. Info request: the buyer is asking questions, a chance to get known before a bid.');
  add('deadline', 'Closing date, or "Not set" for rolling and forecast listings');
  add('who_can_apply', 'Any company, Companies eligible, Small businesses only, or Check listing (the funder explains eligibility in the full listing)');
  add('first_seen', 'The date this tracker first saw the listing; sort by it to see what is new');
  add('');
  heading('WHERE WE COVER');
  add('Federal', 'Nationwide');
  add('States', 'California, Illinois, Massachusetts, Virginia (cohort home states). Michigan and New York state portals block automated access, so they are not covered yet.');
  add('Cities', 'New York and Chicago. Detroit\'s city portal requires a login; the regional water authority is covered instead.');
  add('');
  heading('FEATURES');
  add('Refreshes itself', 'Runs every day at 8am Eastern on GitHub; this sheet pulls the new data an hour later.');
  add('Each source runs on its own', 'If one website is down, the rest still update and yesterday\'s listings for that source are kept.');
  add('Keeps history', 'Water listings that close move to a yearly archive (data/archive/) instead of disappearing, so future cohorts can see what funders offer and when.');
  add('Nothing is lost silently', 'Listings removed as not biddable are kept in a review file with the reason.');
  add('Built to hand off', 'Each startup can copy the project for free and tune its own keywords and filters in one settings file.');
  add('');
  add('Full data', 'https://github.com/' + REPO);

  const width = 6;
  const grid = out.map(r => r.concat(Array(width - r.length).fill('')).slice(0, width));
  const sheet = ss.getSheetByName(ABOUT_TAB) || ss.insertSheet(ABOUT_TAB, 0);
  sheet.clear();
  sheet.getRange(1, 1, grid.length, width).setValues(grid).setVerticalAlignment('top');
  sheet.getRange(1, 1).setFontSize(16).setFontWeight('bold');
  headers.forEach(row => sheet.getRange(row, 1, 1, width).setFontWeight('bold'));
  sheet.setColumnWidth(1, 260);
  sheet.setColumnWidths(2, 4, 110);
  sheet.setColumnWidth(6, 520);
}

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Funding tracker').addItem('Refresh now', 'refreshNow').addToUi();
}

function setUp() {
  // One daily refresh, an hour after the GitHub job (12:00 UTC).
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('refreshNow').timeBased().everyDays(1).atHour(13).inTimezone('Etc/UTC').create();
  refreshNow();
}
