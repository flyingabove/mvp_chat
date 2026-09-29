// Live iPhone Safari bug (2026-09-29): the update check reloaded a stale page 161 times in 52s.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../../frontend/index.html"), "utf8");
const start = html.indexOf("var UPDATE_RETRY_MS");
const end = html.indexOf("function showUpdateBanner");
const appUpdateAction = new Function(html.slice(start, end) + "\nreturn appUpdateAction;")();
const PAGE = "https://storieschat.ai/beta/";
const NOW = 1790712000000;

test("same revision does nothing", () => {
  assert.equal(appUpdateAction("abc", "abc", PAGE, NOW, ""), "none");
  assert.equal(appUpdateAction(undefined, "abc", PAGE, NOW, ""), "none");
});

test("a newer server revision reloads once", () => {
  assert.equal(appUpdateAction("new", "old", PAGE, NOW, ""), "reload");
});

test("still stale right after the update reload: prompt instead of looping", () => {
  const reloaded = PAGE + "?_hr=" + (NOW - 300);
  assert.equal(appUpdateAction("new", "old", reloaded, NOW, ""), "prompt");
});

test("an attempt already made for this revision prompts even without the URL marker", () => {
  assert.equal(appUpdateAction("new", "old", PAGE, NOW, "new"), "prompt");
});

test("a later deployment gets its own automatic reload", () => {
  assert.equal(appUpdateAction("newer", "old", PAGE, NOW, "new"), "reload");
  assert.equal(appUpdateAction("newer", "old", PAGE + "?_hr=" + (NOW - 120000), NOW, ""), "reload");
});

test("simulated stale cache cannot loop: at most one automatic reload", () => {
  let href = PAGE, attempted = "", reloads = 0, now = NOW;
  for (let i = 0; i < 50; i++) {
    const action = appUpdateAction("new", "old", href, now, attempted);   // cache always returns the old page
    if (action !== "reload") break;
    reloads++; attempted = "new"; href = PAGE + "?_hr=" + now; now += 300;
  }
  assert.equal(reloads, 1);
});
