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
 *   - Every decision is saved straight away in "Tracker – Decisions" (this works even before setUp
 *     has been run), which the daily refresh never clears. A refresh also first saves any decision
 *     still showing in the review tabs, so nothing you typed is lost. The Shortlist, Deadlines and Dashboard update a few seconds later. Decided
 *     calls stay (shaded) in To review until the next full refresh, so rows don't jump while
 *     you work; choose Funding tracker > Refresh now to clear them out at once.
 *
 * When it runs: the GitHub job collects new calls every day at 12:00 UTC; this sheet pulls them
 * in every day at 13:00 UTC, and whenever you choose Funding tracker > Refresh now.
 *   - "Tracker – Shortlist" shows everything marked Pursue, Contact funder or Clarify, by deadline.
 *   - "Tracker – All open" shows every open call with its decision, including fit 1-2.
 * You can change a decision in any of these tabs, or in the Decisions tab itself.
 *
 * "Tracker – Dashboard" is the place to start each week: headline numbers, deadlines in the next
 * 30 days, the best calls waiting for a decision, your shortlist, funder pages that changed,
 * where the open calls are by FBH area and project, and whether every source was read.
 */

const REPO = 'martinbuess/heartfulness-funding-tracker';
const DATA_URL = 'https://raw.githubusercontent.com/' + REPO + '/main/data/';
const PIPELINE_TAB = 'Pipeline';
const TABS = {
  dashboard: 'Tracker – Dashboard',
  review: 'Tracker – To review',
  shortlist: 'Tracker – Shortlist',
  all: 'Tracker – All open',
  deadlines: 'Tracker – Deadlines',
  watch: 'Tracker – Watched pages',
  setAside: 'Tracker – Set aside',
  decisions: 'Tracker – Decisions',
};
// Tabs from earlier versions of this script, removed on refresh.
const OLD_TABS = ['Tracker – New this week', 'Tracker – Open opportunities', 'Tracker – Leads', 'Tracker – About'];
const DECISIONS = ['Pursue', 'Contact funder', 'Clarify', 'Later', 'Discard'];
const ACTIVE = ['Pursue', 'Contact funder', 'Clarify'];
const SHADE = { 'Pursue': '#d9efc9', 'Contact funder': '#d9efc9', 'Clarify': '#fff2cc', 'Later': '#eeeeee',
                'Discard': '#eeeeee' };
const STORE_HEADER = ['ID', 'Decision', 'My notes', 'Decided on', 'Funder', 'Grant / program', 'Deadline', 'Link',
                      'Still open?'];
// Calls scoring below this stay out of To review (they are still in All open).
const REVIEW_MIN_SCORE = 3;
const VIEWS = [TABS.review, TABS.shortlist, TABS.all];

/** Full refresh: new results from GitHub, then every Tracker tab. Runs daily and from the menu. */
function refreshNow() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    render(ss, true);
  } catch (err) {
    reportFailure(ss, err);
    throw err;  // also shows in Apps Script > Executions, and Google emails the owner
  }
}

/** Writes a failed refresh on the Dashboard's status line, so it can't go unnoticed. */
function reportFailure(ss, err) {
  const sheet = ss.getSheetByName(TABS.dashboard);
  if (!sheet) return;
  const when = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  sheet.getRange(2, 1, 1, DASH_WIDTH).breakApart().merge()
    .setValue('⚠ The sheet refresh on ' + when + ' failed: ' + String(err && err.message || err).slice(0, 300) +
              '  Try Funding tracker > Refresh now; if it fails again, send this message to Claude.')
    .setFontColor('#990000').setFontWeight('bold').setFontStyle('normal');
}

/**
 * Quick update after you make a decision: redraws the Shortlist, Deadlines and Dashboard from the
 * latest results and your saved decisions. To review and All open are left as they are (the row
 * you decided on is shaded) so rows don't jump while you work; decided calls leave To review at
 * the next full refresh, or when you choose Funding tracker > Refresh now.
 */
function updateShortlistAndDashboard() {
  render(SpreadsheetApp.getActiveSpreadsheet(), false);
}

function render(ss, full) {
  const all = fetchCsv('opportunities.csv');
  const header = all[0];
  const rows = all.slice(1);
  const col = name => header.indexOf(name);
  if (full) rescueUnsaved(ss);
  const decisions = readDecisions(ss);
  if (full) markStillOpen(ss, decisions, new Set(rows.map(r => r[col('ID')])));

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
  if (full) {
    writeView(ss, TABS.review, viewHeader, review);
    writeView(ss, TABS.all, viewHeader, withDecision);
  }
  writeView(ss, TABS.shortlist, viewHeader, shortlist);

  const keep = ['Decision', 'Deadline', 'Flag', 'Fit (1-5)', 'Funder', 'Grant / program', 'Amount',
                'Best-fit FBH projects', 'Link'];
  const dated = withDecision.filter(r => r[0] !== 'Discard' && /^\d{4}-\d{2}-\d{2}$/.test(deadline(r)))
    .sort(byDeadline).map(r => keep.map(k => r[viewHeader.indexOf(k)]));
  writeTable(ss, TABS.deadlines, [keep].concat(dated));
  const watchRows = fetchCsv('watch.csv');
  if (full) {
    writeWatch(ss, watchRows);
    writeSetAside(ss, fetchCsv('filtered_out.csv'));
  }

  writeDashboard(ss, { header: viewHeader, rows: withDecision, review: review, shortlist: shortlist,
                       summary: fetchCsv('summary.csv'), watch: watchRows });
  if (full) {
    OLD_TABS.forEach(name => { const s = ss.getSheetByName(name); if (s) ss.deleteSheet(s); });
    ss.toast(review.length + ' calls to review, ' + shortlist.length + ' on the shortlist', 'Funding tracker', 6);
  } else {
    ss.toast('Shortlist and dashboard updated (' + shortlist.length + ' on the shortlist)', 'Funding tracker', 4);
  }
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

/**
 * Safety net: before the review tabs are redrawn, any decision or note visible in them that is
 * missing from the Decisions tab is saved there, so a refresh can never wipe it. A decision you
 * changed in the Decisions tab itself is not overwritten.
 */
function rescueUnsaved(ss) {
  const saved = readDecisions(ss);
  VIEWS.forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (!sheet || sheet.getLastRow() < 2) return;
    const width = sheet.getLastColumn();
    const values = sheet.getRange(1, 1, sheet.getLastRow(), width).getValues();
    const header = values[0];
    const at = h => header.indexOf(h);
    if (at('ID') < 0 || header[0] !== 'Decision') return;
    values.slice(1).forEach(r => {
      const id = String(r[at('ID')] || '');
      const decision = String(r[0] || ''), notes = String(r[1] || '');
      if (!id || (!decision && !notes)) return;
      const old = saved[id];
      if (old && (old.decision || !decision) && (old.notes || !notes)) return;
      const rec = { id: id, decision: (old && old.decision) || decision, notes: (old && old.notes) || notes,
                    funder: r[at('Funder')], title: r[at('Grant / program')], deadline: r[at('Deadline')],
                    link: r[at('Link')] };
      saveDecision(ss, rec);
      saved[id] = { decision: rec.decision, notes: rec.notes };
    });
  });
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

/**
 * Saves a decision as soon as you pick it. This is a "simple trigger": Google runs it on every
 * edit with no setup at all, so decisions are saved even if setUp was never run.
 */
function onEdit(e) {
  saveEdit(e);
}

/**
 * Runs on every edit once setUp has been run. Saves the decision too (harmless if onEdit already
 * did), then updates the Shortlist, Deadlines and Dashboard, which needs permission to download
 * from GitHub and so can't be done by onEdit alone.
 */
function handleEdit(e) {
  if (saveEdit(e)) {
    // One update at a time; a decision made while one is running is included in the next one.
    const lock = LockService.getDocumentLock();
    if (!lock.tryLock(60000)) return;
    try {
      render(e.source, false);
    } finally {
      lock.releaseLock();
    }
  }
}

/** Saves the decisions in an edited range. Returns true when something was saved. */
function saveEdit(e) {
  const sheet = e.range.getSheet();
  const name = sheet.getName();
  if (name === TABS.decisions) {
    if (e.range.getColumn() <= 3 && e.range.getLastColumn() >= 2 && e.range.getLastRow() > 1) {
      const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
      const first = Math.max(2, e.range.getRow());
      sheet.getRange(first, 4, e.range.getLastRow() - first + 1, 1).setValue(today);
      return true;
    }
    return false;
  }
  if (VIEWS.indexOf(name) < 0 || e.range.getColumn() > 2 || e.range.getLastRow() < 2) return false;
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
  return true;
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
  updateShortlistAndDashboard();
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

// --- the dashboard ------------------------------------------------------------------------

const GREEN = '#274e13', LIGHT = '#e6f0e3', PALE = '#f6faf4', RED = '#f4cccc', AMBER = '#fff2cc', OK = '#d9ead3';
const DASH_WIDTH = 8;

function daysUntil(iso) {
  const today = new Date(Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd') + 'T00:00:00Z');
  return Math.round((new Date(iso + 'T00:00:00Z') - today) / 86400000);
}

function bar(n, max) {
  // A small text bar chart that works in any sheet language.
  return max ? '▇'.repeat(Math.max(n ? 1 : 0, Math.round(16 * n / max))) : '';
}

function link(text, url) {
  const b = SpreadsheetApp.newRichTextValue().setText(String(text || url || ''));
  return (url ? b.setLinkUrl(url) : b).build();
}

function writeDashboard(ss, d) {
  let sheet = ss.getSheetByName(TABS.dashboard);
  if (!sheet) {
    const old = ss.getSheetByName('Tracker – About');
    const at = old ? old.getIndex() - 1 : ss.getSheets().length;
    sheet = ss.insertSheet(TABS.dashboard, at);
  }
  sheet.clear();
  sheet.getRange(1, 1, sheet.getMaxRows(), sheet.getMaxColumns()).clearDataValidations().breakApart();
  sheet.setHiddenGridlines(true);
  [110, 95, 60, 190, 330, 250, 120, 230].forEach((w, i) => sheet.setColumnWidth(i + 1, w));

  const h = d.header;
  const at = name => h.indexOf(name);
  const get = (r, name) => String(r[at(name)] || '');
  const summary = d.summary.slice(1);
  const rowsIn = section => summary.filter(r => r[0] === section);
  const one = section => rowsIn(section)[0] || [];
  const isDate = v => /^\d{4}-\d{2}-\d{2}$/.test(v);
  const project = r => get(r, 'Best-fit FBH projects').split('; ')[0].replace(/ \(.*$/, '');
  const call = r => link(get(r, 'Grant / program'), get(r, 'Link'));
  let row = 1;

  // Title and status line.
  sheet.getRange(row, 1, 1, DASH_WIDTH).merge().setValue('Forests by Heartfulness · Funding dashboard')
    .setFontSize(18).setFontWeight('bold').setFontColor(GREEN);
  row++;
  const failed = rowsIn('source').filter(r => /FAILED/.test(r[6]));
  const status = failed.length ? '⚠ ' + failed.map(r => r[1]).join(', ') + ' could not be read; their listings may be out of date.'
                               : '✓ All ' + rowsIn('source').length + ' sources checked successfully.';
  sheet.getRange(row, 1, 1, DASH_WIDTH).merge()
    .setValue('Results from ' + (one('run')[6] || '') + ' · sheet refreshed ' +
              Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm') + '   ' + status)
    .setFontColor(failed.length ? '#990000' : '#38761d').setFontStyle('italic');
  row += 2;

  // Headline numbers.
  // Deadlines worth acting on: shortlisted calls, and undecided calls scoring 3+.
  const worth = r => ACTIVE.indexOf(r[0]) >= 0 || (!r[0] && Number(get(r, 'Fit (1-5)')) >= REVIEW_MIN_SCORE);
  const due30 = d.rows.filter(r => worth(r) && isDate(get(r, 'Deadline')) &&
                                   daysUntil(get(r, 'Deadline')) >= 0 && daysUntil(get(r, 'Deadline')) <= 30);
  const changed = d.watch.slice(1).filter(r => /^CHANGED/.test(r[d.watch[0].indexOf('status')]));
  const fresh = d.review.filter(r => /NEW/.test(get(r, 'Flag'))).length;
  const tiles = [
    [1, 2, d.review.length, 'To review', fresh + ' new this week', d.review.length ? AMBER : OK],
    [3, 2, d.shortlist.length, 'On the shortlist', 'Pursue · Contact · Clarify', LIGHT],
    [5, 1, due30.length, 'Deadlines in 30 days', 'shortlist + fit 3+', due30.length ? AMBER : OK],
    [6, 1, changed.length, 'Funder pages changed', 'see Watched pages', changed.length ? AMBER : OK],
    [7, 2, d.rows.filter(r => r[0] === 'Discard').length, 'Discarded', 'kept in Decisions', '#eeeeee'],
  ];
  tiles.forEach(([c, span, n, label, note, colour]) => {
    sheet.getRange(row, c, 1, span).merge().setValue(n).setFontSize(26).setFontWeight('bold')
      .setHorizontalAlignment('center').setBackground(colour).setFontColor(GREEN);
    sheet.getRange(row + 1, c, 1, span).merge().setValue(label).setFontWeight('bold')
      .setHorizontalAlignment('center').setBackground(colour);
    sheet.getRange(row + 2, c, 1, span).merge().setValue(note).setFontSize(9).setFontColor('#666666')
      .setHorizontalAlignment('center').setBackground(colour);
  });
  sheet.setRowHeight(row, 46);
  row += 4;

  // A titled table; cells may be plain values or rich-text links.
  const block = (title, note, header, body, empty, shade) => {
    sheet.getRange(row, 1, 1, DASH_WIDTH).merge().setValue(title).setFontWeight('bold').setFontColor('#ffffff')
      .setBackground(GREEN).setFontSize(11);
    row++;
    if (note) {
      sheet.getRange(row, 1, 1, DASH_WIDTH).merge().setValue(note).setFontColor('#666666').setFontSize(9);
      row++;
    }
    if (!body.length) {
      sheet.getRange(row, 1, 1, DASH_WIDTH).merge().setValue(empty).setFontStyle('italic').setFontColor('#666666');
      row += 2;
      return;
    }
    const pad = r => r.concat(Array(DASH_WIDTH).fill('')).slice(0, DASH_WIDTH);
    sheet.getRange(row, 1, 1, DASH_WIDTH).setValues([pad(header)]).setFontWeight('bold').setBackground(LIGHT);
    row++;
    body.forEach((cells, i) => {
      const range = sheet.getRange(row + i, 1, 1, DASH_WIDTH);
      range.setNumberFormat('@').setValues([pad(cells.map(c => (c && c.getText ? c.getText() : c)))])
        .setVerticalAlignment('top').setBackground(i % 2 ? PALE : null);
      cells.forEach((c, j) => { if (c && c.getText) sheet.getRange(row + i, j + 1).setRichTextValue(c); });
      if (shade) {
        const colour = shade(i);
        if (colour) sheet.getRange(row + i, 1).setBackground(colour);
      }
    });
    row += body.length + 1;
  };

  // 1. Deadlines coming up.
  const soon = due30.slice().sort((a, b) => get(a, 'Deadline').localeCompare(get(b, 'Deadline'))).slice(0, 12);
  block('⏰  DEADLINES IN THE NEXT 30 DAYS', 'Your shortlist and undecided calls scoring ' + REVIEW_MIN_SCORE + '+, soonest first. Red: within a week. Amber: within 3 weeks.',
        ['Days left', 'Deadline', 'Fit', 'Funder', 'Call', 'Best-fit FBH project', 'Decision', 'Amount'],
        soon.map(r => [String(daysUntil(get(r, 'Deadline'))), get(r, 'Deadline'), get(r, 'Fit (1-5)'),
                       get(r, 'Funder'), call(r), project(r), r[0] || 'not decided', get(r, 'Amount')]),
        'No deadlines in the next 30 days.',
        i => (daysUntil(get(soon[i], 'Deadline')) <= 7 ? RED : daysUntil(get(soon[i], 'Deadline')) <= 21 ? AMBER : null));

  // 2. Best calls still waiting for a decision.
  const top = d.review.slice(0, 10);
  block('📥  BEST CALLS WAITING FOR YOUR DECISION',
        'Top of Tracker – To review. Pick a Decision there (column A); they leave this list at the next refresh.',
        ['Fit', 'Flag', 'Deadline', 'Funder', 'Call', 'Best-fit FBH project', 'Geography', 'Amount'],
        top.map(r => [get(r, 'Fit (1-5)'), get(r, 'Flag'), get(r, 'Deadline'), get(r, 'Funder'), call(r), project(r),
                      get(r, 'Geography'), get(r, 'Amount')]),
        'Nothing waiting: To review is empty. 🎉');

  // 3. The shortlist.
  block('⭐  YOUR SHORTLIST', 'Calls marked Pursue, Contact funder or Clarify, soonest deadline first.',
        ['Decision', 'Deadline', 'Fit', 'Funder', 'Call', 'My notes', 'In pipeline', 'Best-fit FBH project'],
        d.shortlist.slice(0, 12).map(r => [r[0], get(r, 'Deadline'), get(r, 'Fit (1-5)'), get(r, 'Funder'), call(r),
                                           String(r[1] || ''), get(r, 'In pipeline'), project(r)]),
        'Nothing shortlisted yet. Mark calls Pursue, Contact funder or Clarify in Tracker – To review.');

  // 4. Funder pages that changed.
  const wh = d.watch[0] || [];
  const w = name => wh.indexOf(name);
  block('🔔  FUNDER PAGES THAT CHANGED', 'Open the page to see what is new. The full list is in Tracker – Watched pages.',
        ['Changed on', '', '', 'What the page says', 'Page', 'Next date mentioned', '', ''],
        changed.map(r => [r[w('last_changed')], '', '', r[w('signal')], link(r[w('name')], r[w('link')]),
                          r[w('next_date')], '', '']),
        'No watched page changed in the last 7 days.');

  // 5. Where the open calls are, by area and by project (fit 3 and up, not discarded).
  const strong = d.rows.filter(r => r[0] !== 'Discard' && Number(get(r, 'Fit (1-5)')) >= REVIEW_MIN_SCORE);
  const tally = (key, split) => {
    const out = {};
    strong.forEach(r => split(r).forEach(k => {
      if (!k) return;
      out[k] = out[k] || [0, 0];
      out[k][0]++;
      if (ACTIVE.indexOf(r[0]) >= 0) out[k][1]++;
    }));
    return Object.keys(out).map(k => [k, out[k][0], out[k][1]]).sort((a, b) => b[1] - a[1]);
  };
  const areas = tally('area', r => get(r, 'FBH area').split('; '));
  const projects = tally('project', r => get(r, 'Best-fit FBH projects').split('; ').map(p => p.replace(/ \(.*$/, '')));
  const most = Math.max(1, ...areas.map(a => a[1]), ...projects.map(p => p[1]));
  block('📊  WHERE THE OPEN CALLS ARE', 'Calls scoring ' + REVIEW_MIN_SCORE + '+ that are not discarded. A call can count for more than one area or project.',
        ['Open calls', 'Shortlisted', '', 'FBH area', '', '', '', ''],
        areas.map(a => [String(a[1]), String(a[2]), '', a[0], bar(a[1], most), '', '', '']), 'No open calls yet.');
  block('🌱  BY FBH PROJECT', 'Which projects the open calls fit best (from the summary deck).',
        ['Open calls', 'Shortlisted', '', 'FBH project', '', '', '', ''],
        projects.map(p => [String(p[1]), String(p[2]), '', p[0], bar(p[1], most), '', '', '']),
        'No calls matched a project yet.');

  // 6. Source health.
  const sources = rowsIn('source');
  block('🛰  SOURCES', 'Checked every morning. A source that fails 3 days running also sends GitHub an alert email.',
        ['Status', 'Open today', 'Fit FBH', 'Source', 'What it covers', '', '', ''],
        sources.map(r => [/FAILED/.test(r[6]) ? 'FAILED' : 'OK', String(r[3]), String(r[4]), r[1],
                          r[6].replace(/^FAILED[^.]*\.\s*/, ''), '', '', '']),
        '', i => (/FAILED/.test(sources[i][6]) ? RED : OK));

  // 7. Calendar rows to update.
  const checks = rowsIn('calendar_check');
  block('🗓  CALENDAR ROWS TO UPDATE', 'Yearly programs in data/calendar.csv whose dates need a look.',
        ['', '', '', 'Program', 'What to do', '', '', ''],
        checks.slice(0, 10).map(r => ['', '', '', r[1], r[6], '', '', '']), 'All calendar rows are up to date.');

  // 8. How to read the score (kept short).
  block('ℹ  HOW TO READ THE SCORE', '',
        ['', '', '', 'Column', 'Meaning', '', '', ''],
        [['', '', '', 'Fit (1-5)', 'topic (0-2) + place (0-2) + NGOs eligible (0-1) + size (-1 to 1) + pipeline funder (0-1)'],
         ['', '', '', 'Caps', 'At most 3 when the call does not say where the work happens; at most 2 when its focus is outside FBH or it is an EU consortium call'],
         ['', '', '', 'Confirmed / Verify', 'Confirmed = the listing says so. Verify = our assumption; check before applying'],
         ['', '', '', 'Flag', 'NEW = first seen in the last 7 days · Closing soon = deadline within 21 days'],
         ['', '', '', 'Settings and data', link('github.com/' + REPO, 'https://github.com/' + REPO)]], '');
  sheet.setFrozenRows(0);
}

function onOpen() {
  // Warn when the dashboard hasn't been refreshed for more than a day (the daily refresh isn't running).
  const dash = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(TABS.dashboard);
  const line = dash ? String(dash.getRange(2, 1).getValue()) : '';
  const found = line.match(/sheet refreshed (\d{4}-\d{2}-\d{2})/);
  const yesterday = Utilities.formatDate(new Date(Date.now() - 36 * 3600000), 'Etc/UTC', 'yyyy-MM-dd');
  if (dash && (!found || found[1] < yesterday)) {
    SpreadsheetApp.getActiveSpreadsheet().toast('The daily refresh has not run recently. Choose Funding tracker > ' +
      'Refresh now, then run setUp in Extensions > Apps Script to restart the daily refresh.', 'Funding tracker', 20);
  }
  SpreadsheetApp.getUi().createMenu('Funding tracker')
    .addItem('Refresh now (new results + all tabs)', 'refreshNow')
    .addItem('Update shortlist & dashboard', 'updateShortlistAndDashboard')
    .addItem('Add selected call to Pipeline', 'addToPipeline')
    .addToUi();
}

function setUp() {
  // A daily refresh an hour after the GitHub job (12:00 UTC), and the edit handler that saves
  // decisions and updates the shortlist and dashboard. Removes only this script's own triggers.
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ScriptApp.getProjectTriggers()
    .filter(t => ['refreshNow', 'handleEdit'].indexOf(t.getHandlerFunction()) >= 0)
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('refreshNow').timeBased().everyDays(1).atHour(13).inTimezone('Etc/UTC').create();
  ScriptApp.newTrigger('handleEdit').forSpreadsheet(ss).onEdit().create();
  refreshNow();
}
