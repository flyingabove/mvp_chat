// Live iPhone Safari bug (2026-09-29): the update check reloaded a stale page 161 times in 52s.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../../frontend/index.html"), "utf8");
const start = html.indexOf("var SHELL_REVISION");
const end = html.indexOf("function showUpdateNotice");
const appUpdateAction = new Function(html.slice(start, end) + "\nreturn appUpdateAction;")();
test("same revision does nothing", () => {
  assert.equal(appUpdateAction("abc", "abc"), "none");
  assert.equal(appUpdateAction(undefined, "abc"), "none");
});

test("a newer server revision prompts without reloading", () => {
  assert.equal(appUpdateAction("new", "old"), "prompt");
  assert.equal(appUpdateAction("newer", "old"), "prompt");
});

test("service-worker controller changes never navigate automatically", () => {
  const block = html.slice(html.indexOf("/* ─── PWA SERVICE WORKER"), html.indexOf("var SHELL_REVISION"));
  assert.doesNotMatch(block, /(?:location\.(?:reload|replace|assign)|window\.location\s*=)/);
});

test("version polling never starts an automatic hard reload", () => {
  const block = html.slice(html.indexOf("function checkAppUpdate"), html.indexOf("/* ─── HARD RELOAD"));
  assert.doesNotMatch(block, /hardReloadApp|location\.(?:reload|replace|assign)/);
});

test("update notice uses the existing tab without covering gameplay controls", () => {
  const block = html.slice(html.indexOf("function showUpdateNotice"), html.indexOf("function checkAppUpdate"));
  assert.match(block, /tab-update-app/);
  assert.match(block, /tab\.children\[1\]\.textContent = "Update Ready"/);
  assert.doesNotMatch(block, /createElement|position:fixed/);
});
