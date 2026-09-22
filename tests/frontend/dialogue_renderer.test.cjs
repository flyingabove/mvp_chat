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
    renderAvatarImage: (target, src) => { const img = new Element(); img.src = src; target.appendChild(img); return img; },
    formatMsgText: text => text.replaceAll('<', '&lt;'),
    getTypewriterDelay: () => 10, scrollChatToBottom() {}
  });
  return { api, row: () => new Element(), advance(now) { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now)); } };
}

test('renders one old-style bubble and uses the speaker with the most dialogue', () => {
  const { api, row, advance } = setup();
  const scene = row();
  api.render(scene, 'IU: hi\n\nMizuki: abcdefghij', [
    { kind: 'dialogue', speaker_id: 'iu', speaker_name: 'IU', portrait_url: '/img/characters/iu.png', text: 'hi' },
    { kind: 'dialogue', speaker_id: 'mizuki', speaker_name: 'Mizuki', portrait_url: '/img/characters/mizuki.png', text: 'abcdefghij' }
  ], true, { name: 'Terrace in the City', src: '/img/six_strangers.png' });
  assert.equal(scene.children.length, 2);
  assert.equal(scene.children[0].title, 'Mizuki');
  assert.equal(scene.children[1].className, 'msg-bubble npc');
  advance(90);
  assert.equal(scene.children[1].textContent, 'IU: hi\n\n');
  advance(400);
  assert.equal(scene.children[1].innerHTML, 'IU: hi\n\nMizuki: abcdefghij');
  assert.equal(scene.attributes['aria-busy'], undefined);
});

test('new turn completes the prior turn instead of leaving truncated dialogue', () => {
  const { api, row } = setup();
  const first = row();
  api.render(first, 'First complete reply', null, true, { name: 'Game', src: '/img/game.png' });
  api.render(row(), 'Next reply', null, true, { name: 'Game', src: '/img/game.png' });
  assert.equal(first.children[1].innerHTML, 'First complete reply');
  assert.equal(first.attributes['aria-busy'], undefined);
});

test('narration and an unknown side character use the game picture', () => {
  const { api, row } = setup();
  for (const segments of [
    [{ kind: 'narration', speaker_id: null, text: 'Rain falls.' }],
    [{ kind: 'dialogue', speaker_id: null, speaker_name: 'Waiter', portrait_url: '/img/avatars/persona_default.svg', text: 'Welcome.' }]
  ]) {
    const scene = row();
    api.render(scene, '<script>hello', segments, false, { name: 'Terrace in the City', src: '/img/six_strangers.png' });
    assert.equal(scene.children[0].title, 'Terrace in the City');
    assert.equal(scene.children[1].innerHTML, '&lt;script>hello');
  }
});

test('dialogue totals are combined by speaker and ties use first appearance', () => {
  const { api, row } = setup();
  const scene = row();
  api.render(scene, 'Mixed reply', [
    { kind: 'dialogue', speaker_id: 'mizuki', speaker_name: 'Mizuki', portrait_url: '/img/mizuki.png', text: '1234' },
    { kind: 'dialogue', speaker_id: 'iu', speaker_name: 'IU', portrait_url: '/img/iu.png', text: '1234567' },
    { kind: 'dialogue', speaker_id: 'mizuki', speaker_name: 'Mizuki', portrait_url: '/img/mizuki.png', text: '567' }
  ], false, { name: 'Game', src: '/img/game.png' });
  assert.equal(scene.children[0].title, 'Mizuki');
});
