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

test('game cover surrounds ordered narration and named individual speech bubbles', () => {
  const { api, row, advance } = setup();
  const scene = row();
  api.render(scene, 'Scene', [
    {kind: 'narration', text: 'Rain falls.'},
    {kind: 'dialogue', speaker_name: 'Mizuki', portrait_url: '/img/characters/Mizuki_Shida.png', text: 'Hello'},
    {kind: 'dialogue', speaker_name: 'Yuki', portrait_url: '/img/characters/Yuki_Adachi.png', text: 'Welcome'}
  ], true, {name: 'Terrace', src: '/img/six_strangers_house.jpg'});
  assert.equal(scene.children[0].title, 'Terrace');
  const outer = scene.children[1];
  assert.equal(outer.children.length, 3);
  assert.equal(outer.children[1].className, 'scene-speech');
  assert.equal(outer.children[1].children[0].title, 'Mizuki');
  assert.equal(outer.children[2].children[0].title, 'Yuki');
  advance(40);
  assert.equal(outer.children[0].children[0].textContent, 'Rain');
  assert.equal(outer.children[1].hidden, true);
  advance(1000);
  assert.equal(outer.children[1].children[1].children[1].innerHTML, 'Hello');
  assert.equal(scene.attributes['aria-busy'], undefined);
});

test('new turn completes prior turn and legacy prose stays intact and escaped', () => {
  const {api, row} = setup();
  const first = row();
  api.render(first, '<script>First complete reply', null, true, {name: 'Game'});
  api.render(row(), 'Next', null, true, {name: 'Game'});
  assert.equal(first.children[1].children[0].children[0].innerHTML, '&lt;script>First complete reply');
  assert.equal(first.attributes['aria-busy'], undefined);
});

test('unknown speech has its own initials, never a borrowed character portrait', () => {
  const {api, row} = setup();
  const scene = row();
  api.render(scene, 'Hello', [{kind:'dialogue', text:'Hello'}], false, {name:'Game'});
  const portrait = scene.children[1].children[0].children[0];
  assert.equal(portrait.title, 'Unknown speaker');
  assert.equal(portrait.textContent, 'US');
});

test('long narration and speech split into readable named beats', () => {
  const {api, row} = setup();
  const scene = row();
  const long = 'A small detail changes the room. '.repeat(12);
  api.render(scene, long, [
    {kind:'narration', text:long},
    {kind:'dialogue', speaker_name:'Mizuki', portrait_url:'/img/characters/Mizuki_Shida.png', text:long}
  ], false, {name:'Terrace'});
  const blocks = scene.children[1].children;
  assert.ok(blocks.filter(b => b.className === 'scene-narration').length >= 2);
  const speeches = blocks.filter(b => b.className === 'scene-speech');
  assert.ok(speeches.length >= 2);
  assert.ok(speeches.every(b => b.children[1].children[0].textContent === 'Mizuki'));
});
