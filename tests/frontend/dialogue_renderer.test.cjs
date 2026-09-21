const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
  class Element {
    constructor() { this.children = []; this.events = {}; this.attributes = {}; this.classList = { add() {}, remove() {} }; }
    appendChild(child) { this.children.push(child); child.parent = this; return child; }
    remove() { this.parent.children = this.parent.children.filter(c => c !== this); }
    setAttribute(k, v) { this.attributes[k] = v; }
    removeAttribute(k) { delete this.attributes[k]; }
    addEventListener(k, v) { this.events[k] = v; }
    removeEventListener(k) { delete this.events[k]; }
  }
  const frames = new Map();
  let id = 0;
  const ctx = {
    window: {}, AbortController, performance: { now: () => 0 },
    document: { createElement: () => new Element(), getElementById: () => ({ scrollHeight: 100, scrollTop: 0, clientHeight: 100 }) },
    requestAnimationFrame(fn) { frames.set(++id, fn); return id; },
    cancelAnimationFrame(id) { frames.delete(id); }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../frontend/dialogue.js'), 'utf8'), ctx);
  const api = ctx.window.createDialoguePresentation({
    renderAvatarImage: () => { throw Error('No remote image should be loaded for missing portraits'); },
    formatMsgText: text => text.replaceAll('<', '&lt;'),
    getTypewriterDelay: () => 10, scrollChatToBottom() {}
  });
  return { api, row: () => new Element(), advance(now) { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now)); } };
}

test('elapsed-time reveal is three times the old 30ms rate and respects speaker order', () => {
  const { api, row, advance } = setup();
  const scene = row();
  api.render(scene, '', [
    { kind: 'dialogue', speaker_name: 'IU', text: 'abcdefghij' },
    { kind: 'dialogue', speaker_name: 'Mizuki', text: 'klmnop' }
  ], true);
  advance(90);
  assert.equal(scene.children[0].children[1].children[1].textContent, 'abcdefghi');
  assert.equal(scene.children[1].hidden, true);
  advance(120);
  assert.equal(scene.children[0].children[1].children[1].innerHTML, 'abcdefghij');
  assert.equal(scene.children[1].children[1].children[1].textContent, 'kl');
  advance(160);
  assert.equal(scene.children[1].children[1].children[1].innerHTML, 'klmnop');
  assert.equal(scene.attributes['aria-busy'], undefined);
});

test('new turn completes the prior turn instead of leaving truncated dialogue', () => {
  const { api, row } = setup();
  const first = row();
  api.render(first, 'First complete reply', null, true);
  api.render(row(), 'Next reply', null, true);
  assert.equal(first.children[0].children[0].children[1].innerHTML, 'First complete reply');
  assert.equal(first.attributes['aria-busy'], undefined);
});

test('history uses the same identities; unsafe or missing portrait URLs use initials', () => {
  const { api, row } = setup();
  const scene = row();
  api.render(scene, '', [{ kind: 'dialogue', speaker_name: 'IU', portrait_url: 'javascript:bad()', text: '<script>hello' }], false);
  assert.equal(scene.children[0].children[0].title, 'IU');
  assert.equal(scene.children[0].children[1].children[0].textContent, 'IU');
  assert.equal(scene.children[0].children[1].children[1].innerHTML, '&lt;script>hello');
});
