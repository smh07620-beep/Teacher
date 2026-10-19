/* Behaviour test for static/learner-slide-checkpoints-1011.js with a tiny fake DOM.
 * Run: node tests/test_learner_checkpoint_flow_1017.js */
'use strict';
const assert = require('assert');
const path = require('path');

function makeDom() {
  const byId = {};
  function node(tag) {
    const n = {
      tag, className: '', children: [], parent: null, attrs: {}, listeners: {}, disabled: false, _text: '',
      get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
      set textContent(v) { this._text = String(v); this.children = []; },
      set id(v) { this._id = v; byId[v] = this; }, get id() { return this._id; },
      appendChild(c) { c.parent = this; this.children.push(c); if (c._id) byId[c._id] = c; return c; },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this); if (this._id && byId[this._id] === this) delete byId[this._id]; },
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(t, f) { this.listeners[t] = f; },
      click() { this.listeners.click && this.listeners.click(); },
      querySelectorAll(sel) { const out = []; (function walk(x) { x.children.forEach(c => { if (sel === 'button' && c.tag === 'button') out.push(c); walk(c); }); })(this); return out; },
      classList: { contains: () => false },
    };
    return n;
  }
  const modal = node('div'); modal.id = 'slide-viewer-modal';
  return { byId, modal, document: { createElement: node, getElementById: id => byId[id] || null } };
}

function buttons(n) { return n.querySelectorAll('button'); }
function byLabel(n, text) { return buttons(n).find(b => b.textContent.includes(text)); }

const dom = makeDom();
const posted = [];
let answerReply = null;
globalThis.document = dom.document;
globalThis.slideViewerState = { mode: 'images', images: new Array(6).fill('x'), index: 0, materialId: 'm1' };
globalThis.goToSlidePage = i => { globalThis.slideViewerState.index = i; api._onReaderChanged({ detail: { open: true, materialId: 'm1', page: i + 1 } }); };
globalThis.fetch = (url, opts) => { posted.push({ url, body: opts && opts.body }); return Promise.resolve({ ok: true, json: () => Promise.resolve(answerReply) }); };
globalThis.LearnerBundleCheckpoints = { m1: [{ id: 'c1', page: 2, question: 'Q?', options: ['A', 'B', 'C'], answered: false }] };
globalThis.addEventListener = () => {};
const api = require(path.join(__dirname, '..', 'static', 'learner-slide-checkpoints-1011.js'));
const open = page => { globalThis.slideViewerState.index = page - 1; api._onReaderChanged({ detail: { open: true, materialId: 'm1', page } }); };
const card = () => dom.byId['aa-checkpoint-card'];
const tick = () => new Promise(r => setImmediate(r));

const slidesFlow = (async () => {
  // Not on the checkpoint's own page: it appears after the section, on page 3.
  open(2);
  assert.strictEqual(card(), undefined, 'no card on the question page itself');
  open(3);
  assert.ok(card(), 'card appears when moving on to the next page');

  // First wrong answer: explanation, retry, review and continue; no right answer yet.
  answerReply = { id: 'c1', page: 2, question: 'Q?', options: ['A', 'B', 'C'], answered: true, firstCorrect: false, attempts: 1, canRetry: true, isCorrect: false, chosenIndex: 0, explanation: 'E' };
  byLabel(card(), 'A. A').click();
  await tick(); await tick();
  assert.ok(card().textContent.includes('答錯了，先看說明再試一次'));
  assert.ok(!card().textContent.includes('（正確）'), 'right option still hidden');
  assert.ok(byLabel(card(), '再答一次'));
  assert.ok(byLabel(card(), '繼續往下'), 'never locked');
  const review = byLabel(card(), '回看第 2 頁');
  assert.ok(review && review.className.includes('btn-secondary'), 'review is secondary after the first miss');

  // 回看 jumps to page 2 and shows a bar that returns to page 3.
  review.click();
  assert.strictEqual(globalThis.slideViewerState.index, 1);
  const bar = dom.byId['aa-checkpoint-return'];
  assert.ok(bar && bar.textContent.includes('回到第 3 頁'));
  byLabel(bar, '回到第 3 頁').click();
  assert.strictEqual(globalThis.slideViewerState.index, 2, 'back where the learner was');
  assert.strictEqual(dom.byId['aa-checkpoint-return'], undefined);

  // Card is back on page 3 (not finished yet); second wrong answer makes 回看 the main button.
  assert.ok(card());
  answerReply = Object.assign({}, answerReply, { attempts: 2, canRetry: false, chosenIndex: 2, firstChosenIndex: 0, correctIndex: 1 });
  byLabel(card(), '再答一次').click();
  byLabel(card(), 'C. C').click();
  await tick(); await tick();
  assert.ok(card().textContent.includes('還是答錯了'));
  assert.ok(card().textContent.includes('B. B（正確）'));
  assert.ok(byLabel(card(), '回看第 2 頁').className.includes('btn-primary'));
  assert.ok(byLabel(card(), '繼續往下'), 'still never locked');
  byLabel(card(), '繼續往下').click();
  assert.strictEqual(card(), undefined);

  // Last page lists the weak pages.
  globalThis.LearnerBundleCheckpoints.m1[0] = answerReply;
  Object.assign(api._state.items[0], answerReply);
  open(6);
  const summary = dom.byId['aa-checkpoint-summary'];
  assert.ok(summary && summary.textContent.includes('這幾頁建議再看一次'));
  assert.ok(byLabel(summary, '第 2 頁'));
  assert.ok(posted.every(p => !p.url.includes('/checkpoints') || p.body), 'bundle used: no list request');
  console.log('learner checkpoint flow: ok');
})();

/* ---- video: pause at the second, review the segment, come back for the retry ---- */
slidesFlow.then(async () => {
  const dom2 = makeDom();
  const mediaModal = dom2.document.createElement('div'); mediaModal.id = 'media-viewer-modal';
  const video = dom2.document.createElement('video'); video.id = 'media-video';
  let playing = true;
  video.currentTime = 0;
  video.pause = () => { playing = false; };
  video.play = () => { playing = true; return Promise.resolve(); };
  video.removeEventListener = () => {};
  globalThis.document = dom2.document;
  globalThis.LearnerBundleCheckpoints.v1 = [
    { id: 'v-a', page: 60, question: 'Q1', options: ['A', 'B'], answered: false },
    { id: 'v-b', page: 120, question: 'Q2', options: ['A', 'B'], answered: false },
  ];
  api._onMediaChanged({ detail: { open: true, materialId: 'v1', kind: 'video' } });
  const m = api._media();
  assert.strictEqual(m.el, video, 'attached to the uploaded video');
  video.currentTime = 30; api._onTimeUpdate();
  assert.strictEqual(dom2.byId['aa-checkpoint-card'], undefined);
  video.currentTime = 121; api._onTimeUpdate();
  const c = dom2.byId['aa-checkpoint-card'];
  assert.ok(c && c.textContent.includes('Q2') && !playing, 'paused with the question at 120s');
  answerReply = { id: 'v-b', page: 120, question: 'Q2', options: ['A', 'B'], answered: true, firstCorrect: false, attempts: 1, canRetry: true, isCorrect: false, chosenIndex: 0, explanation: 'E' };
  byLabel(c, 'A. A').click();
  await tick(); await tick();
  const review = byLabel(dom2.byId['aa-checkpoint-card'], '回看 1 分 0 秒 起的片段');
  assert.ok(review, 'reviews the segment since the previous checkpoint');
  review.click();
  assert.strictEqual(video.currentTime, 60);
  assert.ok(playing);
  const bar = dom2.byId['aa-checkpoint-return'];
  assert.ok(bar && bar.textContent.includes('回到 2 分 1 秒'));
  byLabel(bar, '回到 2 分 1 秒').click();
  assert.strictEqual(video.currentTime, 121);
  assert.ok(byLabel(dom2.byId['aa-checkpoint-card'], '再答一次'), 'second try offered after review');
  assert.ok(!playing);
  byLabel(dom2.byId['aa-checkpoint-card'], '繼續往下').click();
  assert.ok(playing, 'continue resumes playback');
  console.log('learner media checkpoint flow: ok');
}).catch(err => { console.error(err); process.exit(1); });
