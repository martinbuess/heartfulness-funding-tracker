/**
 * Forests by Heartfulness funding tracker: copies the GitHub results into this Google Sheet.
 *
 * It only ever writes to tabs whose names start with "Tracker" (listed below). Your own tabs
 * (pipeline, outreach, calendar, overview, ...) are never read or changed.
 *
 * Setup (once, or again whenever this file changes):
 *   1. In the sheet: Extensions > Apps Script. Delete what is there, paste this file, click Save.
 *   2. Pick "setUp" in the function menu at the top and click Run. Approve the permissions
 *      Google asks for (it needs to download the results from GitHub and write to this sheet).
 *   3. Reload the sheet. A "Funding tracker" menu appears with "Refresh now".
 *
 * After that the sheet refreshes itself every day about an hour after the GitHub job, and
 * you can click Funding tracker > Refresh now at any time. Each refresh rewrites the Tracker
 * tabs, so don't type into them: copy a row into your pipeline tab to work on it.
 */

const REPO = 'martinbuess/heartfulness-funding-tracker';
const DATA_URL = 'https://raw.githubusercontent.com/' + REPO + '/main/data/';
const TABS = {
  about: 'Tracker – About',
  fresh: 'Tracker – New this week',
  open: 'Tracker – Open opportunities',
  deadlines: 'Tracker – Deadlines',
  leads: 'Tracker – Leads',
  setAside: 'Tracker – Set aside',
};
const NEW_DAYS = 7;

function refreshNow() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const all = fetchCsv('opportunities.csv');
  const header = all[0];
  const rows = all.slice(1);
  const col = name => header.indexOf(name);
  const cutoff = isoDaysAgo(NEW_DAYS);

  // All open opportunities, best fit first (the file is already in that order).
  writeTable(ss, TABS.open, all);
  // New this week.
  writeTable(ss, TABS.fresh, [header].concat(rows.filter(r => r[col('First seen')] >= cutoff)));
  // Deadlines: only rows with a date, soonest first, with the most useful columns.
  const keep = ['Deadline', 'Flag', 'Fit (1-5)', 'Funder', 'Grant / program', 'Amount', 'FBH area', 'Link'];
  const dated = rows.filter(r => /^\d{4}-\d{2}-\d{2}$/.test(r[col('Deadline')]))
    .sort((a, b) => a[col('Deadline')].localeCompare(b[col('Deadline')]))
    .map(r => keep.map(k => r[col(k)]));
  writeTable(ss, TABS.deadlines, [keep].concat(dated));
  writeTable(ss, TABS.leads, fetchCsv('leads.csv'));
  writeSetAside(ss, fetchCsv('filtered_out.csv'));
  writeAbout(ss, fetchCsv('summary.csv'));
  ss.toast(rows.length + ' open opportunities loaded', 'Funding tracker', 5);
}

function isoDaysAgo(days) {
  const d = new Date(Date.now() - days * 86400000);
  return Utilities.formatDate(d, 'Etc/UTC', 'yyyy-MM-dd');
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

function tab(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name, ss.getSheets().length);
}

function writeTable(ss, name, rows) {
  const sheet = tab(ss, name);
  sheet.clear();
  if (!rows.length || !rows[0].length) return;
  const width = rows[0].length;
  const grid = rows.map(r => r.concat(Array(width).fill('')).slice(0, width));
  // Plain text, so Sheets doesn't reformat dates or amounts.
  sheet.getRange(1, 1, grid.length, width).setNumberFormat('@').setValues(grid)
    .setVerticalAlignment('top').setWrap(false);
  sheet.getRange(1, 1, 1, width).setFontWeight('bold').setBackground('#e6f0e3');
  sheet.setFrozenRows(1);
  const header = rows[0];
  const widths = { 'Grant / program': 340, 'Funder': 180, 'Why this score': 420, 'Summary': 420, 'title': 340,
                   'Eligibility: confirmed vs. to verify': 320, 'FBH area': 200, 'Link': 220, 'summary': 420 };
  header.forEach((h, i) => { if (widths[h]) sheet.setColumnWidth(i + 1, widths[h]); });
  const score = header.indexOf('Fit (1-5)');
  if (score >= 0 && grid.length > 1) {
    const range = sheet.getRange(2, score + 1, grid.length - 1, 1);
    const rule = (text, colour) => SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(text).setBackground(colour).setRanges([range]).build();
    sheet.setConditionalFormatRules([rule('5', '#b7e1a1'), rule('4', '#d9efc9'), rule('3', '#fff2cc')]);
  }
}

function writeSetAside(ss, rows) {
  // Listings on topic but removed by a rule, with the reason: check now and then that nothing useful was cut.
  if (!rows.length) return writeTable(ss, TABS.setAside, rows);
  const h = rows[0];
  const keep = ['filtered_reason', 'title', 'funder', 'deadline', 'amount', 'link', 'source', 'first_seen'];
  const idx = keep.map(k => h.indexOf(k));
  writeTable(ss, TABS.setAside, rows.map(r => idx.map(i => (i >= 0 ? r[i] : ''))));
}

function writeAbout(ss, summary) {
  // summary.csv columns: section, name, level, open, matches, set_aside, detail
  const rowsIn = section => summary.slice(1).filter(r => r[0] === section);
  const one = section => rowsIn(section)[0] || [];
  const total = one('total');
  const out = [];
  const bold = [];
  const add = (...cells) => out.push(cells);
  const heading = text => { bold.push(out.length + 1); add(text); };

  add('Forests by Heartfulness – funding tracker');
  add('Last refreshed ' + (one('run')[6] || '') + '. This tab updates itself; the Tracker tabs are rewritten every day.');
  add('');
  heading('AT A GLANCE');
  add('Open opportunities that fit FBH', total[4] || '0', 'Tracker – Open opportunities (best fit first)');
  add('New in the last 7 days', one('new')[4] || '0', 'Tracker – New this week');
  add('Closed or expired today', one('archived')[4] || '0', 'Kept in data/archive/ on GitHub, never deleted');
  add('Set aside by a rule', total[5] || '0', 'Tracker – Set aside, with the reason for each');
  rowsIn('score').forEach(r => add(r[1], r[4]));
  add('');
  heading('BY FBH AREA');
  rowsIn('area').forEach(r => add(r[1], r[4]));
  add('');
  heading('SOURCES (check this when numbers look odd)');
  bold.push(out.length + 1);
  add('Source', 'Type', 'Open today', 'Fit FBH', 'Set aside', 'Status / what it covers');
  rowsIn('source').forEach(r => add(r[1], r[2], r[3], r[4], r[5], r[6]));
  rowsIn('leads_failed').forEach(r => add(r[1], 'Leads feed', '', '', '', 'Could not be read today'));
  add('');
  const checks = rowsIn('calendar_check');
  if (checks.length) {
    heading('CALENDAR ROWS THAT NEED AN UPDATE');
    checks.forEach(r => add(r[1], '', '', '', '', r[6]));
    add('');
  }
  heading('HOW TO READ THE SCORE');
  add('5', 'Strong: FBH area in the title, India or international, NGOs named as eligible, size known and $50K+');
  add('4', 'Good: most of the above, one thing to check');
  add('3', 'Possible: worth opening the link');
  add('1–2', 'Weak or unclear: eligibility, place or topic not stated');
  add('Confirmed vs. Verify', 'Confirmed = the listing says so. Verify = our assumption; check before applying.');
  add('Flag', 'NEW (first seen in the last 7 days), Closing soon (deadline within 21 days), Source down (not re-checked today)');
  add('Last verified', 'The last day the tracker saw the listing still open at its source');
  add('');
  add('Settings and full data', 'https://github.com/' + REPO);

  const width = 6;
  const grid = out.map(r => r.concat(Array(width).fill('')).slice(0, width));
  const sheet = tab(ss, TABS.about);
  sheet.clear();
  sheet.getRange(1, 1, grid.length, width).setNumberFormat('@').setValues(grid).setVerticalAlignment('top');
  sheet.getRange(1, 1).setFontSize(16).setFontWeight('bold');
  bold.forEach(row => sheet.getRange(row, 1, 1, width).setFontWeight('bold'));
  sheet.setColumnWidth(1, 300);
  sheet.setColumnWidths(2, 4, 100);
  sheet.setColumnWidth(6, 520);
}

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Funding tracker').addItem('Refresh now', 'refreshNow').addToUi();
}

function setUp() {
  // One daily refresh, an hour after the GitHub job (12:00 UTC). Removes only this script's own timers.
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'refreshNow')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('refreshNow').timeBased().everyDays(1).atHour(13).inTimezone('Etc/UTC').create();
  refreshNow();
}
