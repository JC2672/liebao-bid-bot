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
const HEADER = ["Date", "Company", "Title", "Source", "Job URL"];

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
    sheet.appendRow([body.date, body.company, body.title, body.source, body.url]);
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

  return respond({ error: "unknown action: " + body.action });
}

function respond(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON,
  );
}
