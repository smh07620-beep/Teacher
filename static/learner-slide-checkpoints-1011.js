/* Learner reader: optional in-slide checkpoint questions (小測驗).
 *
 * Owner of: showing a teacher's checkpoint card when the learner reaches a page
 * that has one, and sending the answer.  Entirely opt-in: a material with no
 * checkpoints never shows anything, and the card never blocks reading, paging
 * or completion (the learner can always press 稍後再說).
 *
 * Read-only observer of window.slideViewerState (no wrapping of the viewer's
 * functions).  The server returns the right answer and explanation only after
 * this learner answered; the first answer is the learning record.
 */
(function (root) {
  'use strict';

  var POLL_MS = 600;
  var state = { materialId: '', items: [], page: -1, dismissed: {}, loading: '' };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function cardHost() {
    var modal = document.getElementById('slide-viewer-modal');
    if (!modal || modal.classList.contains('hidden')) return null;
    return modal;
  }

  function removeCard() {
    var old = document.getElementById('aa-checkpoint-card');
    if (old) old.remove();
  }

  function request(url, options) {
    return fetch(url, Object.assign({ credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }, options || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; }); });
  }

  function load(materialId) {
    state.loading = materialId;
    request('/api/materials/' + encodeURIComponent(materialId) + '/checkpoints').then(function (res) {
      if (state.loading !== materialId) return;
      state.items = res.ok && Array.isArray(res.d.items) ? res.d.items : [];
      state.materialId = materialId;
      state.page = -1; // force a repaint for the current page
    });
  }

  function itemsOnPage(page) {
    return state.items.filter(function (it) { return it.page === page; });
  }

  function paintResult(box, item) {
    box.textContent = '';
    box.appendChild(el('div', 'font-black text-sm ' + (item.isCorrect ? 'text-emerald-700' : 'text-rose-700'),
      item.isCorrect ? '✅ 答對了' : '❌ 這題答錯了'));
    box.appendChild(el('p', 'text-sm font-bold text-slate-800', item.question));
    item.options.forEach(function (opt, j) {
      var mark = j === item.correctIndex ? '✔ ' : (j === item.chosenIndex ? '✘ ' : '　');
      var cls = j === item.correctIndex ? 'text-emerald-800 font-bold' : (j === item.chosenIndex ? 'text-rose-700' : 'text-slate-500');
      box.appendChild(el('p', 'text-sm ' + cls, mark + String.fromCharCode(65 + j) + '. ' + opt));
    });
    if (item.explanation) box.appendChild(el('p', 'rounded-lg bg-slate-50 p-2 text-xs text-slate-700', '說明：' + item.explanation));
  }

  function paintQuestion(box, item, host) {
    box.textContent = '';
    box.appendChild(el('p', 'text-sm font-bold text-slate-800', item.question));
    item.options.forEach(function (opt, j) {
      var btn = el('button', 'block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-left text-sm hover:bg-slate-50',
        String.fromCharCode(65 + j) + '. ' + opt);
      btn.type = 'button';
      btn.addEventListener('click', function () {
        Array.prototype.forEach.call(box.querySelectorAll('button'), function (b) { b.disabled = true; });
        request('/api/slide-checkpoints/' + encodeURIComponent(item.id) + '/answer', {
          method: 'POST', body: JSON.stringify({ chosenIndex: j })
        }).then(function (res) {
          if (!res.ok) {
            Array.prototype.forEach.call(box.querySelectorAll('button'), function (b) { b.disabled = false; });
            box.appendChild(el('p', 'text-xs text-rose-700', (res.d && res.d.error) || '送出失敗，請再試一次。'));
            return;
          }
          Object.assign(item, res.d);
          paintResult(box, item);
        });
      });
      box.appendChild(btn);
    });
  }

  function paintPage(page) {
    removeCard();
    var host = cardHost();
    var items = itemsOnPage(page).filter(function (it) { return !state.dismissed[it.id + ':' + page]; });
    if (!host || !items.length) return;
    var card = el('div', 'fixed bottom-4 left-1/2 z-[120] w-[min(92vw,34rem)] -translate-x-1/2 space-y-2 rounded-2xl border border-teal-300 bg-white p-4 shadow-2xl');
    card.id = 'aa-checkpoint-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', '小測驗');
    var head = el('div', 'flex items-center justify-between gap-2');
    head.appendChild(el('span', 'text-xs font-black text-teal-800', '📝 小測驗（不計入成績，答不答都可以繼續閱讀）'));
    var close = el('button', 'rounded-lg border border-slate-300 px-2 py-1 text-xs font-bold text-slate-600', '稍後再說');
    close.type = 'button';
    close.addEventListener('click', function () {
      items.forEach(function (it) { state.dismissed[it.id + ':' + page] = true; });
      removeCard();
    });
    head.appendChild(close);
    card.appendChild(head);
    items.forEach(function (item) {
      var box = el('div', 'space-y-1.5');
      if (item.answered) paintResult(box, item); else paintQuestion(box, item, host);
      card.appendChild(box);
    });
    host.appendChild(card);
  }

  function tick() {
    var s = root.slideViewerState;
    var host = cardHost();
    if (!host || !s || !s.materialId) {
      if (!host) { removeCard(); state.page = -1; }
      return;
    }
    var id = String(s.materialId);
    if (id !== state.materialId) {
      if (state.loading !== id) { state.items = []; state.dismissed = {}; load(id); }
      return;
    }
    var page = Number(s.index) + 1;
    if (page !== state.page) {
      state.page = page;
      paintPage(page);
    }
  }

  var api = { _state: state, _tick: tick, start: function () { return setInterval(tick, POLL_MS); } };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.SlideCheckpoints = api;
    api.start();
  }
})(typeof window !== 'undefined' ? window : globalThis);
