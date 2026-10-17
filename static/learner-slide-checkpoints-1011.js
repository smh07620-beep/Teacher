/* Learner reader: optional checkpoint questions (小測驗) between slides.
 *
 * Owner of: the checkpoint card, the "回看中" return bar and the end-of-material
 * "建議再看一次" summary.  Opt-in: a material with no checkpoints shows nothing,
 * and nothing here ever blocks reading, paging, completion or the exam.
 *
 * Placement: a checkpoint written for page N appears when the learner moves on to
 * page N+1 (after the section), or on page N itself when N is the last page.
 *
 * Wrong answers (plan 2026-10-15):
 *   1st wrong -> explanation, buttons 回看第 N 頁 / 再答一次 / 繼續往下
 *   2nd wrong -> right answer shown, 回看第 N 頁 becomes the main button, 繼續往下 stays
 *   回看 jumps to page N and shows a bar that returns to where the learner was.
 *
 * Driven by the reader's own 'teacher:reader-changed' event (no polling, no wrapping).
 */
(function (root) {
  'use strict';

  var state = { materialId: '', items: [], loading: '', dismissed: {}, returnIndex: -1, summaryShown: false, lastPage: 0 };

  function el(tag, cls, text) {
    var n = root.document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function button(label, kind, onClick) {
    var b = el('button', 'btn ' + (kind || 'btn-secondary'), label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function host() {
    var modal = root.document.getElementById('slide-viewer-modal');
    return modal && !modal.classList.contains('hidden') ? modal : null;
  }

  function viewer() { return root.slideViewerState || {}; }

  function totalPages() {
    var s = viewer();
    return Math.max(1, Number(s.mode === 'pdf' ? s.pageCount : (s.images || []).length) || Number(s.pageCount) || 1);
  }

  function goTo(page) {
    if (typeof root.goToSlidePage === 'function') root.goToSlidePage(Number(page) - 1);
  }

  function removeById(id) {
    var old = root.document.getElementById(id);
    if (old) old.remove();
  }

  function request(url, options) {
    return root.fetch(url, Object.assign({ credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }, options || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; }); });
  }

  function setItems(materialId, items) {
    state.materialId = materialId;
    state.items = Array.isArray(items) ? items : [];
    state.dismissed = {};
    state.summaryShown = false;
  }

  function load(materialId, then) {
    var bundled = root.LearnerBundleCheckpoints && root.LearnerBundleCheckpoints[materialId];
    if (Array.isArray(bundled)) {
      setItems(materialId, bundled); // delivered with the course learner-bundle: no extra request
      then();
      return;
    }
    state.loading = materialId;
    request('/api/materials/' + encodeURIComponent(materialId) + '/checkpoints').then(function (res) {
      if (state.loading !== materialId) return;
      state.loading = '';
      setItems(materialId, res.ok && Array.isArray(res.d.items) ? res.d.items : []);
      then();
    });
  }

  function finished(item) { return item.answered && !item.canRetry; }

  function dueOn(page) {
    var total = totalPages();
    return state.items.filter(function (it) {
      if (finished(it) || state.dismissed[it.id]) return false;
      return page === it.page + 1 || (it.page === total && page === total);
    });
  }

  /* ---------- 回看中 bar ---------- */
  function showReturnBar() {
    removeById('aa-checkpoint-return');
    var modal = host();
    if (!modal || state.returnIndex < 0) return;
    var bar = el('div', 'checkpoint-return-bar');
    bar.id = 'aa-checkpoint-return';
    bar.setAttribute('role', 'status');
    bar.appendChild(el('span', '', '回看中'));
    bar.appendChild(button('讀完按這裡回到第 ' + (state.returnIndex + 1) + ' 頁', 'btn-primary', function () {
      var back = state.returnIndex;
      state.returnIndex = -1;
      removeById('aa-checkpoint-return');
      goTo(back + 1);
    }));
    modal.appendChild(bar);
  }

  function reviewPage(page) {
    var current = Number(viewer().index || 0);
    if (state.returnIndex < 0) state.returnIndex = current;
    removeById('aa-checkpoint-card');
    removeById('aa-checkpoint-summary');
    goTo(page);
    showReturnBar();
  }

  /* ---------- card ---------- */
  function paintResult(box, item, done) {
    box.textContent = '';
    var verdict = item.isCorrect ? '答對了' : (item.attempts >= 2 ? '還是答錯了，正確答案如下' : '答錯了，先看說明再試一次');
    box.appendChild(el('p', 'checkpoint-verdict ' + (item.isCorrect ? 'is-correct' : 'is-wrong'), verdict));
    box.appendChild(el('p', 'checkpoint-question', item.question));
    item.options.forEach(function (opt, j) {
      var cls = 'checkpoint-option';
      var mark = '';
      if (item.correctIndex === j) { cls += ' is-correct'; mark = '（正確）'; }
      else if (item.chosenIndex === j) { cls += ' is-wrong'; mark = '（你的答案）'; }
      box.appendChild(el('p', cls, String.fromCharCode(65 + j) + '. ' + opt + mark));
    });
    if (item.explanation) box.appendChild(el('p', 'checkpoint-explain', '說明：' + item.explanation));
    var actions = el('div', 'checkpoint-actions');
    if (!item.isCorrect) {
      actions.appendChild(button('回看第 ' + item.page + ' 頁', item.attempts >= 2 ? 'btn-primary' : 'btn-secondary', function () { reviewPage(item.page); }));
      if (item.canRetry) actions.appendChild(button('再答一次', 'btn-primary', function () { paintQuestion(box, item, done); }));
    }
    actions.appendChild(button(item.isCorrect ? '繼續閱讀' : '繼續往下', item.isCorrect ? 'btn-primary' : 'btn-ghost', done));
    box.appendChild(actions);
  }

  function paintQuestion(box, item, done) {
    box.textContent = '';
    box.appendChild(el('p', 'checkpoint-question', item.question));
    item.options.forEach(function (opt, j) {
      var b = button(String.fromCharCode(65 + j) + '. ' + opt, 'btn-secondary checkpoint-choice', function () {
        Array.prototype.forEach.call(box.querySelectorAll('button'), function (x) { x.disabled = true; });
        request('/api/slide-checkpoints/' + encodeURIComponent(item.id) + '/answer', {
          method: 'POST', body: JSON.stringify({ chosenIndex: j })
        }).then(function (res) {
          if (!res.ok) {
            Array.prototype.forEach.call(box.querySelectorAll('button'), function (x) { x.disabled = false; });
            box.appendChild(el('p', 'checkpoint-error', (res.d && res.d.error) || '送出失敗，請再試一次。'));
            return;
          }
          Object.assign(item, res.d);
          paintResult(box, item, done);
        });
      });
      box.appendChild(b);
    });
  }

  function paintCard(items) {
    removeById('aa-checkpoint-card');
    var modal = host();
    if (!modal || !items.length) return;
    var card = el('div', 'card checkpoint-card');
    card.id = 'aa-checkpoint-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', '小測驗');
    var head = el('div', 'checkpoint-head');
    head.appendChild(el('span', 'checkpoint-title', '小測驗（不計入成績，答不答都可以繼續閱讀）'));
    head.appendChild(button('稍後再說', 'btn-ghost', function () {
      items.forEach(function (it) { state.dismissed[it.id] = true; });
      removeById('aa-checkpoint-card');
    }));
    card.appendChild(head);
    var remaining = items.length;
    items.forEach(function (item) {
      var box = el('div', 'checkpoint-box');
      var done = function () {
        state.dismissed[item.id] = true;
        box.remove();
        remaining -= 1;
        if (!remaining) removeById('aa-checkpoint-card');
      };
      if (item.answered) paintResult(box, item, done); else paintQuestion(box, item, done);
      card.appendChild(box);
    });
    modal.appendChild(card);
  }

  /* ---------- end-of-material summary ---------- */
  function weakPages() {
    var pages = {};
    state.items.forEach(function (it) { if (it.answered && it.firstCorrect === false) pages[it.page] = true; });
    return Object.keys(pages).map(Number).sort(function (a, b) { return a - b; });
  }

  function paintSummary() {
    removeById('aa-checkpoint-summary');
    var pages = weakPages();
    var modal = host();
    if (!modal || !pages.length || state.summaryShown) return;
    state.summaryShown = true;
    var card = el('div', 'card checkpoint-card');
    card.id = 'aa-checkpoint-summary';
    card.setAttribute('role', 'status');
    card.appendChild(el('p', 'checkpoint-title', '這幾頁建議再看一次'));
    var row = el('div', 'checkpoint-actions');
    pages.forEach(function (p) { row.appendChild(button('第 ' + p + ' 頁', 'btn-secondary', function () { reviewPage(p); })); });
    row.appendChild(button('關閉', 'btn-ghost', function () { removeById('aa-checkpoint-summary'); }));
    card.appendChild(row);
    modal.appendChild(card);
  }

  /* ---------- reader events ---------- */
  function onPage(page) {
    state.lastPage = page;
    if (state.returnIndex >= 0 && page - 1 === state.returnIndex) {
      state.returnIndex = -1; // came back by other means
      removeById('aa-checkpoint-return');
    }
    if (state.returnIndex >= 0) return; // reviewing: no new questions until back
    var due = dueOn(page);
    if (due.length) paintCard(due); else removeById('aa-checkpoint-card');
    if (page === totalPages() && !due.length) paintSummary();
  }

  function onReaderChanged(event) {
    var detail = (event && event.detail) || {};
    if (!detail.open || !host()) {
      removeById('aa-checkpoint-card');
      removeById('aa-checkpoint-return');
      removeById('aa-checkpoint-summary');
      state.returnIndex = -1;
      state.summaryShown = false;
      return;
    }
    var id = String(detail.materialId || '');
    if (!id) return;
    var page = Number(detail.page) || 1;
    if (id !== state.materialId) {
      state.returnIndex = -1;
      if (state.loading !== id) load(id, function () { onPage(page); });
      return;
    }
    onPage(page);
  }

  var api = { _state: state, _onReaderChanged: onReaderChanged, _dueOn: dueOn, _weakPages: weakPages };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.SlideCheckpoints = api;
    root.addEventListener('teacher:reader-changed', onReaderChanged);
  }
})(typeof window !== 'undefined' ? window : globalThis);
