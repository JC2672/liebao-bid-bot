// Paste this whole file into Extensions > Apps Script for the Google Sheet
// you want Applied jobs logged to, replace SECRET below with a long random
// string of your own, then Deploy > New deployment > type "Web app",
// Execute as "Me", Who has access "Anyone with the link" > Deploy.
//
// Copy the resulting Web app URL into the profile's "Sheet Web App URL"
// field (Profiles screen), and copy the same SECRET value into that
// profile's "Sheet Secret" field. See backend/app/sheets.py for the Python
// side that calls this.
//
// Why a shared secret at all: a Web App deployed this way isn't
// authenticated by Google - anyone who gets this URL could call it. This
// check is what stops that.
//
// If you ever edit this script after deploying, use Deploy > Manage
// deployments > edit (pencil icon) > New version, not a fresh deployment -
// a fresh deployment gets a new URL, which you'd then have to update in
// every profile pointed at this sheet.

const SECRET = "REPLACE_WITH_A_LONG_RANDOM_STRING";
const HEADER = ["Date", "Company", "Title", "Source", "Job URL", "Stage"];

function doPost(e) {
  const body = JSON.parse(e.postData.contents);

  if (body.secret !== SECRET) {
    return respond({ error: "bad secret" });
  }
  if (!body.tab) {
    return respond({ error: "missing tab" });
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(body.tab);
  if (!sheet) {
    sheet = ss.insertSheet(body.tab);
    sheet.appendRow(HEADER);
  }

  if (body.action === "append") {
    // Written by matching each existing column's own header text, not a
    // fixed position - so a tab whose "Stage" column was added by hand in
    // a different spot (or isn't there at all, for an older tab) still
    // gets the right value in the right place, instead of this assuming
    // every tab's columns line up with the HEADER constant above.
    const header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const fieldsByHeader = {
      Date: body.date, Company: body.company, Title: body.title,
      Source: body.source, "Job URL": body.url, Stage: body.stage || "Applied",
    };
    const values = header.map((h) => (h in fieldsByHeader ? fieldsByHeader[h] : ""));
    sheet.appendRow(values);
    return respond({ ok: true });
  }

  if (body.action === "get_urls") {
    const rows = sheet.getDataRange().getValues();
    if (rows.length < 2) return respond({ urls: [] });
    const header = rows[0];
    const urlCol = header.indexOf("Job URL");
    const urls = rows.slice(1).map((r) => r[urlCol]).filter(Boolean);
    return respond({ urls: urls });
  }

  if (body.action === "get_applied_rows_for_companies") {
    // Filtered to just the companies the caller actually asked about
    // (an import batch's own company names), not the whole sheet - the
    // Queue table's company-dupe flag shows *which* past application(s)
    // at that company it's flagging against (title/date/stage), but
    // there's no reason to ship back someone's entire applied history to
    // answer that for one import's worth of companies. Column lookups by
    // header name, same reasoning as "append" above - works whether or
    // not "Stage" exists on this tab.
    const wanted = new Set((body.companies || []).map((c) => String(c).trim().toLowerCase()));
    const rows = sheet.getDataRange().getValues();
    if (rows.length < 2 || wanted.size === 0) return respond({ rows: [] });
    const header = rows[0];
    const col = {
      date: header.indexOf("Date"), company: header.indexOf("Company"),
      title: header.indexOf("Title"), stage: header.indexOf("Stage"),
    };
    const out = rows.slice(1)
      .filter((r) => r[col.company] && wanted.has(String(r[col.company]).trim().toLowerCase()))
      .map((r) => ({
        company: r[col.company], title: col.title >= 0 ? r[col.title] : "",
        date: col.date >= 0 ? r[col.date] : "", stage: col.stage >= 0 ? r[col.stage] : "",
      }));
    return respond({ rows: out });
  }

  return respond({ error: "unknown action: " + body.action });
}

function respond(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON,
  );
}
