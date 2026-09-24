const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../../frontend/index.html"), "utf8");
const block = html.slice(html.indexOf('navigator.serviceWorker.register("sw.js", {updateViaCache: "none"})'));
const body = block.match(/\.then\(function\(reg\)\{([\s\S]*?)\n    \}\)/)[1];
const registered = new Function("reg", body);

test("initial service-worker installation does not start a competing update", () => {
  let updates = 0;
  registered({active: null, installing: {}, update() {updates++;}});
  assert.equal(updates, 0);
});

test("active service-worker update handles rejected update promises", () => {
  let handled = false;
  registered({active: {}, installing: null, update() {
    return {catch(callback) {handled = true; callback(new Error("Load request cancelled"));}};
  }});
  assert.equal(handled, true);
});

test("a waiting worker still receives activation message", () => {
  let message;
  registered({active: null, installing: null, waiting: {postMessage(value) {message = value;}}, update() {}});
  assert.deepEqual(message, {type: "SKIP_WAITING"});
});
