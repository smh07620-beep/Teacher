/* Teacher question bank: "點選圖片題" (atlas_hotspot) authoring fields.
 *
 * Owner of: the Atlas/mark picker shown in the manual "新增單題" form when the
 * question type is atlas_hotspot.  The mark itself is drawn once in the Atlas
 * editor (atlas-annotations-1010.js); here the teacher only picks which
 * published Atlas image and which mark the learner must click.  The server
 * (teacher_app/assessments/hotspot.py) validates the choice and keeps the
 * correct box private.
 *
 * Called from the canonical owners:
 *   admin-question-panel.js   updateManualQuestionType -> syncForm
 *   admin-question-actions.js adminAddQuizQuestion      -> collect
 */
(function (root) {
  'use strict';

  var cache = null; // published atlas items that have at least one mark

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function loadItems() {
    if (cache) return Promise.resolve(cache);
    return fetch('/api/atlas?status=published', { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error((res.d && res.d.error) || '讀取圖譜失敗');
        cache = (res.d.items || []).filter(function (it) {
          return it.published && it.annotationJson && Array.isArray(it.annotationJson.marks) && it.annotationJson.marks.length;
        });
        return cache;
      });
  }

  function ids(catId) {
    return { box: 'qform-' + catId + '-hotspot-config', atlas: 'qform-' + catId + '-hotspot-atlas', mark: 'qform-' + catId + '-hotspot-mark' };
  }

  function fillMarks(catId) {
    var i = ids(catId), atlasSel = document.getElementById(i.atlas), markSel = document.getElementById(i.mark);
    if (!atlasSel || !markSel) return;
    var item = (cache || []).filter(function (it) { return it.id === atlasSel.value; })[0];
    markSel.textContent = '';
    var marks = item ? item.annotationJson.marks : [];
    marks.forEach(function (m, n) {
      var o = el('option', null, (n + 1) + '. ' + m.label); o.value = m.id; markSel.appendChild(o);
    });
  }

  function build(catId) {
    var i = ids(catId);
    var box = el('div', 'hidden rounded-lg border border-teal-200 bg-teal-50/60 p-2 space-y-2 text-xs');
    box.id = i.box;
    box.appendChild(el('p', 'font-bold text-teal-900', '🔬 學員要在圖上點出哪一個？'));
    var row = el('div', 'flex gap-2 flex-wrap');
    var atlasSel = el('select', 'px-2 py-1.5 border rounded-lg bg-white flex-1 min-w-[10rem]'); atlasSel.id = i.atlas;
    var markSel = el('select', 'px-2 py-1.5 border rounded-lg bg-white flex-1 min-w-[8rem]'); markSel.id = i.mark;
    atlasSel.addEventListener('change', function () { fillMarks(catId); });
    row.appendChild(atlasSel); row.appendChild(markSel);
    box.appendChild(row);
    var note = el('p', 'text-slate-600', '');
    note.id = 'qform-' + catId + '-hotspot-note';
    box.appendChild(note);
    box.appendChild(el('p', 'text-amber-800',
      '提醒：學員在圖譜區看得到這張圖的標記名稱與詳解。正式考核若要避免提前看到，請另外用一張專為考試準備的圖。'));
    var anchor = document.getElementById('qform-' + catId + '-explain');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor);
    return box;
  }

  function syncForm(catId, type) {
    var i = ids(catId), box = document.getElementById(i.box);
    if (type !== 'atlas_hotspot') { if (box) box.classList.add('hidden'); return; }
    if (!box) box = build(catId);
    if (!box) return;
    box.classList.remove('hidden');
    var atlasSel = document.getElementById(i.atlas), note = document.getElementById('qform-' + catId + '-hotspot-note');
    note.textContent = '讀取圖譜中…';
    loadItems().then(function (items) {
      atlasSel.textContent = '';
      items.forEach(function (it) {
        var o = el('option', null, it.title + '（' + it.annotationJson.marks.length + ' 個標記）'); o.value = it.id; atlasSel.appendChild(o);
      });
      fillMarks(catId);
      note.textContent = items.length
        ? '只列出「已發布」且「已框選標記」的圖譜。'
        : '目前沒有可用的圖譜。請先到「教材 → 圖譜」編輯一張圖，在圖上框選細胞並發布，再回來出題。';
    }).catch(function (e) { note.textContent = e.message; });
  }

  // Returns {atlasItemId, correctMarkId} or null (alert shown) when incomplete.
  function collect(catId) {
    var i = ids(catId), atlasSel = document.getElementById(i.atlas), markSel = document.getElementById(i.mark);
    if (!atlasSel || !markSel || !atlasSel.value || !markSel.value) {
      alert('請先選擇圖譜與要讓學員點出的標記。若沒有選項，請先到圖譜區框選細胞並發布。');
      return null;
    }
    return { atlasItemId: atlasSel.value, correctMarkId: markSel.value };
  }

  function refresh() { cache = null; }

  var api = { syncForm: syncForm, collect: collect, refresh: refresh };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AdminHotspotQuestion = api;
})(typeof window !== 'undefined' ? window : globalThis);
