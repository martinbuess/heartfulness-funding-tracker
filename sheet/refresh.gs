/**
 * Forests by Heartfulness funding tracker: copies the GitHub results into this Google Sheet
 * and keeps your review decisions.
 *
 * It only writes to tabs whose names start with "Tracker". Your own tabs are never changed,
 * except when you choose Funding tracker > "Add selected call to Pipeline", which adds one
 * row to your Pipeline tab (or a note to that funder's existing row, if you agree).
 *
 * Setup (once, or again whenever this file changes):
 *   1. In the sheet: Extensions > Apps Script. Delete what is there, paste this file, click Save.
 *   2. Pick "setUp" in the function menu at the top and click Run. Approve the permissions
 *      Google asks for (it needs to download the results from GitHub and write to this sheet).
 *   3. Reload the sheet. A "Funding tracker" menu appears.
 *
 * How the review works:
 *   - "Tracker – To review" lists open calls you haven't decided on yet (fit 3 and up), best first.
 *   - Pick a Decision in column A (Pursue, Contact funder, Clarify, Later, Discard) and add a few
 *     words in "My notes" (for Discard, say why: "coastal focus", "not India"...).
 *   - Every decision is saved straight away in "Tracker – Decisions", which the daily refresh
 *     never clears. Decided calls leave To review at the next refresh.
 *   - "Tracker – Shortlist" shows everything marked Pursue, Contact funder or Clarify, by deadline.
 *   - "Tracker – All open" shows every open call with its decision, including fit 1-2.
 * You can change a decision in any of these tabs, or in the Decisions tab itself.
 */

const REPO = 'martinbuess/heartfulness-funding-tracker';
const DATA_URL = 'https://raw.githubusercontent.com/' + REPO + '/main/data/';
const PIPELINE_TAB = 'Pipeline';
const TABS = {
  about: 'Tracker – About',
  review: 'Tracker – To review',
  shortlist: 'Tracker – Shortlist',
  all: 'Tracker – All open',
  deadlines: 'Tracker – Deadlines',
  watch: 'Tracker – Watched pages',
  setAside: 'Tracker – Set aside',
  decisions: 'Tracker – Decisions',
};
// Tabs from earlier versions of this script, removed on refresh.
const OLD_TABS = ['Tracker – New this week', 'Tracker – Open opportunities', 'Tracker – Leads'];
const DECISIONS = ['Pursue', 'Contact funder', 'Clarify', 'Later', 'Discard'];
const ACTIVE = ['Pursue', 'Contact funder', 'Clarify'];
const SHADE = { 'Pursue': '#d9efc9', 'Contact funder': '#d9efc9', 'Clarify': '#fff2cc', 'Later': '#eeeeee',
                'Discard': '#eeeeee' };
const STORE_HEADER = ['ID', 'Decision', 'My notes', 'Decided on', 'Funder', 'Grant / program', 'Deadline', 'Link',
                      'Still open?'];
// Calls scoring below this stay out of To review (they are still in All open).
const REVIEW_MIN_SCORE = 3;
const VIEWS = [TABS.review, TABS.shortlist, TABS.all];

function refreshNow() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const all = fetchCsv('opportunities.csv');
  const header = all[0];
  const rows = all.slice(1);
  const col = name => header.indexOf(name);
  const decisions = readDecisions(ss);
  markStillOpen(ss, decisions, new Set(rows.map(r => r[col('ID')])));

  const viewHeader = ['Decision', 'My notes'].concat(header);
  const withDecision = rows.map(r => {
    const d = decisions[r[col('ID')]] || {};
    return [d.decision || '', d.notes || ''].concat(r);
  });
  const score = r => Number(r[2 + col('Fit (1-5)')] || 0);
  const deadline = r => r[2 + col('Deadline')];
  const byDeadline = (a, b) => (deadline(a) || '9999').localeCompare(deadline(b) || '9999');

  const review = withDecision.filter(r => !r[0] && score(r) >= REVIEW_MIN_SCORE);
  const shortlist = withDecision.filter(r => ACTIVE.indexOf(r[0]) >= 0).sort(byDeadline);
  writeView(ss, TABS.review, viewHeader, review);
  writeView(ss, TABS.shortlist, viewHeader, shortlist);
  writeView(ss, TABS.all, viewHeader, withDecision);

  const keep = ['Decision', 'Deadline', 'Flag', 'Fit (1-5)', 'Funder', 'Grant / program', 'Amount',
                'Best-fit FBH projects', 'Link'];
  const dated = withDecision.filter(r => r[0] !== 'Discard' && /^\d{4}-\d{2}-\d{2}$/.test(deadline(r)))
    .sort(byDeadline).map(r => keep.map(k => r[viewHeader.indexOf(k)]));
  writeTable(ss, TABS.deadlines, [keep].concat(dated));
  writeWatch(ss, fetchCsv('watch.csv'));
  writeSetAside(ss, fetchCsv('filtered_out.csv'));

  const counts = { review: review.length, newReview: review.filter(r => /NEW/.test(r[2 + col('Flag')])).length,
                   below: withDecision.filter(r => !r[0] && score(r) < REVIEW_MIN_SCORE).length };
  DECISIONS.forEach(d => { counts[d] = withDecision.filter(r => r[0] === d).length; });
  writeAbout(ss, fetchCsv('summary.csv'), counts);
  OLD_TABS.forEach(name => { const s = ss.getSheetByName(name); if (s) ss.deleteSheet(s); });
  ss.toast(review.length + ' calls to review, ' + shortlist.length + ' on the shortlist', 'Funding tracker', 6);
}

// --- decisions ----------------------------------------------------------------------------

function storeSheet(ss) {
  let sheet = ss.getSheetByName(TABS.decisions);
  if (!sheet) {
    sheet = ss.insertSheet(TABS.decisions, ss.getSheets().length);
    sheet.getRange(1, 1, 1, STORE_HEADER.length).setValues([STORE_HEADER]).setFontWeight('bold')
      .setBackground('#e6f0e3');
    sheet.setFrozenRows(1);
    sheet.getRange('A:I').setNumberFormat('@');
    sheet.setColumnWidth(3, 320);
    sheet.setColumnWidth(6, 340);
  }
  sheet.getRange(2, 2, Math.max(sheet.getMaxRows() - 1, 1), 1).setDataValidation(dropdown());
  return sheet;
}

function readDecisions(ss) {
  const sheet = storeSheet(ss);
  const last = sheet.getLastRow();
  const out = {};
  if (last < 2) return out;
  sheet.getRange(2, 1, last - 1, 4).getValues().forEach((r, i) => {
    if (r[0]) out[r[0]] = { decision: String(r[1]), notes: String(r[2]), date: r[3], row: i + 2 };
  });
  return out;
}

function saveDecision(ss, rec) {
  const sheet = storeSheet(ss);
  const last = sheet.getLastRow();
  const ids = last >= 2 ? sheet.getRange(2, 1, last - 1, 1).getValues().map(r => String(r[0])) : [];
  const at = ids.indexOf(rec.id);
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  const values = [rec.id, rec.decision, rec.notes, today, rec.funder, rec.title, rec.deadline, rec.link, 'open'];
  if (at >= 0) {
    sheet.getRange(at + 2, 1, 1, values.length).setValues([values]);
  } else {
    sheet.getRange(last + 1, 1, 1, values.length).setValues([values]);
  }
}

function markStillOpen(ss, decisions, openIds) {
  const sheet = storeSheet(ss);
  const last = sheet.getLastRow();
  if (last < 2) return;
  const ids = sheet.getRange(2, 1, last - 1, 1).getValues();
  sheet.getRange(2, 9, last - 1, 1).setValues(ids.map(r => [r[0] ? (openIds.has(String(r[0])) ? 'open' :
                                                                   'closed or expired') : '']));
}

function dropdown() {
  return SpreadsheetApp.newDataValidation().requireValueInList(DECISIONS, true).setAllowInvalid(false).build();
}

/** Saves a decision as soon as you pick it in a Tracker view, and shades the row. */
function onEdit(e) {
  const sheet = e.range.getSheet();
  const name = sheet.getName();
  if (name === TABS.decisions) {
    if (e.range.getColumn() <= 3 && e.range.getLastColumn() >= 2 && e.range.getRow() > 1) {
      const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
      sheet.getRange(e.range.getRow(), 4, e.range.getNumRows(), 1).setValue(today);
    }
    return;
  }
  if (VIEWS.indexOf(name) < 0 || e.range.getColumn() > 2 || e.range.getLastRow() < 2) return;
  const width = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, width).getValues()[0];
  const at = h => header.indexOf(h);
  const first = Math.max(2, e.range.getRow());
  const rows = sheet.getRange(first, 1, e.range.getLastRow() - first + 1, width).getValues();
  rows.forEach((r, i) => {
    if (!r[at('ID')]) return;
    saveDecision(e.source, { id: r[at('ID')], decision: r[0], notes: r[1], funder: r[at('Funder')],
                             title: r[at('Grant / program')], deadline: r[at('Deadline')], link: r[at('Link')] });
    sheet.getRange(first + i, 1, 1, width).setBackground(SHADE[r[0]] || null);
  });
}

// --- adding a call to the Pipeline tab ------------------------------------------------------

function addToPipeline() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const sheet = ss.getActiveSheet();
  const row = sheet.getActiveRange().getRow();
  if (VIEWS.indexOf(sheet.getName()) < 0 || row < 2) {
    ui.alert('Click on a call in To review, Shortlist or All open first, then choose this again.');
    return;
  }
  const width = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, width).getValues()[0];
  const r = sheet.getRange(row, 1, 1, width).getValues()[0];
  const get = h => String(r[header.indexOf(h)] || '');
  const funder = get('Funder') === '(see link)' ? '' : get('Funder');
  const call = get('Grant / program') + (get('Deadline') && get('Deadline') !== 'Not set' ? ' (deadline ' +
               get('Deadline') + ')' : '');
  const pipe = ss.getSheetByName(PIPELINE_TAB);
  if (!pipe) {
    ui.alert('There is no tab called "' + PIPELINE_TAB + '" in this sheet.');
    return;
  }
  const ph = pipe.getRange(1, 1, 1, pipe.getLastColumn()).getValues()[0].map(String);
  const find = re => ph.findIndex(h => re.test(h));
  const cOrg = find(/^organi[sz]ation/i), cStatus = find(/^status/i), cNext = find(/^next/i),
        cComments = find(/^comment/i);
  if (cOrg < 0) {
    ui.alert('Could not find an "Organization" column in the ' + PIPELINE_TAB + ' tab.');
    return;
  }
  const orgs = pipe.getLastRow() > 1 ? pipe.getRange(2, cOrg + 1, pipe.getLastRow() - 1, 1).getValues()
    .map(x => String(x[0]).toLowerCase()) : [];
  const match = funder ? orgs.findIndex(o => o && (o.indexOf(funder.toLowerCase()) >= 0 ||
                                                   funder.toLowerCase().indexOf(o) >= 0)) : -1;
  const note = 'Open call: ' + call + ' ' + get('Link');
  if (match >= 0) {
    const answer = ui.alert(funder + ' is already in the Pipeline (row ' + (match + 2) + ').',
                            'Add this call to that row\'s Comments?', ui.ButtonSet.YES_NO);
    if (answer !== ui.Button.YES) return;
    const cell = pipe.getRange(match + 2, (cComments >= 0 ? cComments : cOrg) + 1);
    cell.setValue((cell.getValue() ? cell.getValue() + '\n' : '') + note);
  } else {
    const values = Array(ph.length).fill('');
    values[cOrg] = funder || get('Grant / program');
    if (cStatus >= 0) values[cStatus] = 'TBD';
    if (cNext >= 0) values[cNext] = 'Review open call: ' + call;
    if (cComments >= 0) values[cComments] = get('Link') + ' | Tracker fit ' + get('Fit (1-5)') + ': ' +
                                             get('Best-fit FBH projects');
    pipe.appendRow(values);
  }
  if (!r[0]) {
    sheet.getRange(row, 1).setValue('Pursue');
  }
  saveDecision(ss, { id: get('ID'), decision: r[0] || 'Pursue', notes: String(r[1] || ''), funder: funder,
                     title: get('Grant / program'), deadline: get('Deadline'), link: get('Link') });
  sheet.getRange(row, 1, 1, width).setBackground(SHADE['Pursue']);
  ss.toast('Added to ' + PIPELINE_TAB, 'Funding tracker', 4);
}

// --- writing tabs ---------------------------------------------------------------------------

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

function writeView(ss, name, header, rows) {
  writeTable(ss, name, [header].concat(rows));
  const sheet = ss.getSheetByName(name);
  const n = Math.max(rows.length, 1);
  sheet.getRange(2, 1, n, 1).setDataValidation(dropdown());
  sheet.getRange(1, 1, 1, 2).setBackground('#cfe2f3');
  sheet.setColumnWidth(1, 120);
  sheet.setColumnWidth(2, 220);
  sheet.setFrozenColumns(2);
  rows.forEach((r, i) => { if (SHADE[r[0]]) sheet.getRange(i + 2, 1, 1, header.length).setBackground(SHADE[r[0]]); });
}

function writeTable(ss, name, rows) {
  const sheet = tab(ss, name);
  sheet.clear();
  sheet.getRange(1, 1, sheet.getMaxRows(), sheet.getMaxColumns()).clearDataValidations();
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
                   'Eligibility: confirmed vs. to verify': 320, 'Best-fit FBH projects': 240, 'Link': 220,
                   'Geography': 220, 'summary': 420 };
  header.forEach((h, i) => { if (widths[h]) sheet.setColumnWidth(i + 1, widths[h]); });
  const score = header.indexOf('Fit (1-5)');
  if (score >= 0 && grid.length > 1) {
    const range = sheet.getRange(2, score + 1, grid.length - 1, 1);
    const rule = (text, colour) => SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(text).setBackground(colour).setRanges([range]).build();
    sheet.setConditionalFormatRules([rule('5', '#b7e1a1'), rule('4', '#d9efc9'), rule('3', '#fff2cc')]);
  }
}

function writeWatch(ss, rows) {
  // Funders' apply pages with no feed: changed pages first, then the ones that couldn't be read.
  if (!rows.length) return writeTable(ss, TABS.watch, rows);
  const h = rows[0];
  const keep = [['status', 'Status'], ['name', 'Page'], ['signal', 'What the page says'],
                ['next_date', 'Next date mentioned'], ['last_changed', 'Last changed'], ['last_checked', 'Last checked'],
                ['link', 'Link'], ['snippet', 'Call-related text on the page']];
  const order = r => (r[h.indexOf('status')].indexOf('CHANGED') === 0 ? 0 :
                      /^(No change|First)/.test(r[h.indexOf('status')]) ? 2 : 1);
  const body = rows.slice(1).sort((a, b) => order(a) - order(b))
    .map(r => keep.map(([k]) => r[h.indexOf(k)] || ''));
  writeTable(ss, TABS.watch, [keep.map(([, label]) => label)].concat(body));
  const sheet = ss.getSheetByName(TABS.watch);
  sheet.setColumnWidth(1, 300);
  sheet.setColumnWidth(2, 280);
  sheet.setColumnWidth(8, 520);
}

function writeSetAside(ss, rows) {
  // Listings on topic but removed by a rule, with the reason: check now and then that nothing useful was cut.
  if (!rows.length) return writeTable(ss, TABS.setAside, rows);
  const h = rows[0];
  const keep = ['filtered_reason', 'title', 'funder', 'deadline', 'amount', 'link', 'source', 'first_seen'];
  const idx = keep.map(k => h.indexOf(k));
  writeTable(ss, TABS.setAside, rows.map(r => idx.map(i => (i >= 0 ? r[i] : ''))));
}

function writeAbout(ss, summary, counts) {
  // summary.csv columns: section, name, level, open, matches, set_aside, detail
  const rowsIn = section => summary.slice(1).filter(r => r[0] === section);
  const one = section => rowsIn(section)[0] || [];
  const total = one('total');
  const out = [];
  const bold = [];
  const add = (...cells) => out.push(cells);
  const heading = text => { bold.push(out.length + 1); add(text); };

  add('Forests by Heartfulness – funding tracker');
  add('Last refreshed ' + (one('run')[6] || '') + '. The Tracker tabs are rewritten every day; your decisions are kept.');
  add('');
  heading('YOUR REVIEW');
  add('To review', counts.review, counts.newReview + ' new this week. Tracker – To review (fit ' + REVIEW_MIN_SCORE +
      '+, not yet decided)');
  add('Shortlist', counts['Pursue'] + counts['Contact funder'] + counts['Clarify'],
      'Pursue ' + counts['Pursue'] + ', Contact funder ' + counts['Contact funder'] + ', Clarify ' + counts['Clarify'] +
      '. Tracker – Shortlist');
  add('Later', counts['Later']);
  add('Discarded', counts['Discard']);
  add('Weaker calls not shown in To review', counts.below, 'Fit 1-2, undecided. Still listed in Tracker – All open');
  add('');
  heading('THIS WEEK');
  add('Open calls that fit FBH', total[4] || '0');
  add('Closed or expired today', one('archived')[4] || '0', 'Kept in data/archive/ on GitHub, never deleted');
  add('Set aside by a rule', total[5] || '0', 'Tracker – Set aside, with the reason for each');
  const w = one('watch');
  add('Watched funder pages that changed', w[4] || '0', (w[3] || '0') + ' pages watched' +
      (Number(w[5] || 0) ? '; ' + w[5] + ' could not be read today' : '') + '. See Tracker – Watched pages');
  rowsIn('score').forEach(r => add(r[1], r[4]));
  add('');
  heading('SOURCES (check this when numbers look odd)');
  bold.push(out.length + 1);
  add('Source', 'Type', 'Open today', 'Fit FBH', 'Set aside', 'Status / what it covers');
  rowsIn('source').forEach(r => add(r[1], r[2], r[3], r[4], r[5], r[6]));
  add('');
  const checks = rowsIn('calendar_check');
  if (checks.length) {
    heading('CALENDAR ROWS THAT NEED AN UPDATE');
    checks.forEach(r => add(r[1], '', '', '', '', r[6]));
    add('');
  }
  heading('HOW TO READ THE SCORE');
  add('Why this score', 'Starts with the sum: topic (0-2) + place (0-2) + applicants (0-1) + size (-1 to 1) + pipeline (0-1), then any cap.');
  add('Caps', 'At most 3 when the call does not say where the work can happen; at most 2 when its main focus is outside FBH (marine, coastal, redwoods, animal welfare...) or it is an EU consortium call.');
  add('Confirmed vs. Verify', 'Confirmed = the listing says so. Verify = our assumption; check before applying.');
  add('Best-fit FBH projects', 'FBH projects or topics whose words appear in the call');
  add('Flag', 'NEW (first seen in the last 7 days), Closing soon (deadline within 21 days), Source down (not re-checked today)');
  add('');
  add('Settings and full data', 'https://github.com/' + REPO);

  const width = 6;
  const grid = out.map(r => r.map(String).concat(Array(width).fill('')).slice(0, width));
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
  SpreadsheetApp.getUi().createMenu('Funding tracker')
    .addItem('Refresh now', 'refreshNow')
    .addItem('Add selected call to Pipeline', 'addToPipeline')
    .addToUi();
}

function setUp() {
  // One daily refresh, an hour after the GitHub job (12:00 UTC). Removes only this script's own timers.
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'refreshNow')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('refreshNow').timeBased().everyDays(1).atHour(13).inTimezone('Etc/UTC').create();
  refreshNow();
}
