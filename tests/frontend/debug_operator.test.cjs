// BL-32 / BL-04: the hosted simulator (frontend/debug.html) crashed in init() with
// "Cannot read properties of undefined (reading 'length')" when /status answered with an error body, and it never sent
// the operator token the backend requires. The helpers under test are the pure block between the BEGIN/END markers.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "../../frontend/debug.html"), "utf8");
const begin = html.indexOf("// BEGIN OPERATOR HELPERS");
const end = html.indexOf("// END OPERATOR HELPERS");
assert.ok(begin > 0 && end > begin, "operator helper block markers are missing from debug.html");
const helpers = new Function(html.slice(begin, end) +
  "\nreturn {getOperatorToken, setOperatorToken, operatorHeaders, withOperatorToken, parseStatus, OPERATOR_TOKEN_KEY};")();

function memoryStorage(initial = {}) {
  const data = {...initial};
  return {getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); },
          removeItem: (k) => { delete data[k]; }, data};
}

test("the operator token round-trips through storage and is trimmed", () => {
  const storage = memoryStorage();
  assert.equal(helpers.getOperatorToken(storage), "");
  helpers.setOperatorToken("  secret-token \n", storage);
  assert.equal(helpers.getOperatorToken(storage), "secret-token");
  helpers.setOperatorToken("", storage);
  assert.equal(helpers.getOperatorToken(storage), "", "an empty value clears it");
  assert.deepEqual(Object.keys(storage.data), []);
});

test("unavailable storage never throws", () => {
  const broken = {getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); },
                  removeItem() { throw new Error("blocked"); }};
  assert.equal(helpers.getOperatorToken(broken), "");
  assert.doesNotThrow(() => helpers.setOperatorToken("x", broken));
});

test("requests carry X-Operator-Token only when a token is set, keeping other headers", () => {
  assert.deepEqual(helpers.operatorHeaders("", {"Content-Type": "application/json"}), {"Content-Type": "application/json"});
  assert.deepEqual(helpers.operatorHeaders("tok", {"Content-Type": "application/json"}),
                   {"Content-Type": "application/json", "X-Operator-Token": "tok"});
  assert.deepEqual(helpers.operatorHeaders("tok"), {"X-Operator-Token": "tok"});
});

test("the WebSocket URL gets the token as a query parameter (browsers cannot set WS headers)", () => {
  assert.equal(helpers.withOperatorToken("wss://h/beta/debug/ws", ""), "wss://h/beta/debug/ws");
  assert.equal(helpers.withOperatorToken("wss://h/beta/debug/ws", "a b&c"), "wss://h/beta/debug/ws?operator_token=a%20b%26c");
  assert.equal(helpers.withOperatorToken("wss://h/ws?x=1", "t"), "wss://h/ws?x=1&operator_token=t");
});

test("a good status response is read into stories, api base and Ollama models", () => {
  const status = helpers.parseStatus(200, {stories: [{id: "a", title: "A"}], api_base: "https://api",
                                           ollama: {available: true, models: ["m1", "m2"]}});
  assert.deepEqual(status, {ok: true, stories: [{id: "a", title: "A"}], apiBase: "https://api",
                            ollama: {available: true, models: ["m1", "m2"]}});
});

test("a 200 without stories (the crashing case) is reported, not thrown", () => {
  for (const body of [{detail: "Not authenticated"}, {}, null, "oops", {stories: "nope"}, {stories: null}]) {
    const status = helpers.parseStatus(200, body);
    assert.equal(status.ok, false);
    assert.equal(status.kind, "malformed");
  }
});

test("401 and 403 ask for the operator token; other failures offer a retry", () => {
  for (const code of [401, 403]) {
    const status = helpers.parseStatus(code, {detail: "operator token required"});
    assert.equal(status.ok, false);
    assert.equal(status.kind, "unauthorized");
    assert.match(status.message, /operator token/i);
  }
  for (const code of [404, 500, 502, 503]) {
    const status = helpers.parseStatus(code, null);
    assert.equal(status.kind, "unavailable");
    assert.match(status.message, new RegExp(String(code)));
  }
});

test("missing Ollama information defaults to offline with no models", () => {
  for (const ollama of [undefined, null, "x", {}, {available: true}, {models: ["m"]}]) {
    const status = helpers.parseStatus(200, {stories: [], ollama});
    assert.equal(status.ok, true);
    assert.ok(Array.isArray(status.ollama.models));
    assert.equal(typeof status.ollama.available, "boolean");
  }
  assert.equal(helpers.parseStatus(200, {stories: [], ollama: {available: true}}).ollama.models.length, 0);
});

test("init() no longer reads data.stories.length before validating the response", () => {
  const init = html.slice(html.indexOf("async function init()"), html.indexOf("// ---- Run ----"));
  assert.ok(init.includes("parseStatus("), "init must validate through parseStatus");
  assert.ok(init.indexOf("parseStatus(") < init.indexOf("data.stories.length"), "validation comes first");
  assert.ok(/catch\s*\(/.test(init), "a network failure must be caught");
});

test("every request to the debug API and the WebSocket carries the operator token", () => {
  const calls = [...html.matchAll(/fetch\(`\$\{_debugBase\}[^`]*`[\s\S]{0,220}?\)/g)].map((m) => m[0]);
  assert.ok(calls.length >= 4, "expected the status, scores and test-case requests");
  for (const call of calls) {
    assert.ok(call.includes("operatorHeaders("), `missing operator header: ${call.slice(0, 80)}`);
  }
  assert.ok(/new WebSocket\(withOperatorToken\(/.test(html), "the WebSocket URL must carry operator_token");
});
