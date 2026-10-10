/* Teacher question bank: 情境題 (scenario) authoring fields.
 *
 * Owner of: the step builder shown in the manual "新增單題" form when the
 * question type is "scenario".  The case description is the normal question
 * text; here the teacher writes 2-6 follow-up steps, each with up to four
 * options and one right answer.  The server (assessments/scenario.py)
 * validates and keeps the right answers private.
 *
 * Called from the canonical owners:
 *   admin-question-panel.js   updateManualQuestionType -> syncForm
 *   admin-question-actions.js adminAddQuizQuestion      -> collect
 */
(function (root) {
  'use strict';

  var MIN_STEPS = 2, MAX_STEPS = 6, OPTIONS = 4;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function boxId(catId) { return 'qform-' + catId + '-scenario-config'; }
  function listId(catId) { return 'qform-' + catId + '-scenario-steps'; }

  function renumber(list) {
    Array.prototype.forEach.call(list.children, function (row, n) {
      row.querySelector('.aa-step-title').textContent = '小問題 ' + (n + 1);
    });
  }

  function addStep(catId) {
    var list = document.getElementById(listId(catId));
    if (!list || list.children.length >= MAX_STEPS) return;
    var row = el('div', 'rounded-lg border border-slate-200 bg-white p-2 space-y-1.5');
    row.setAttribute('data-step', '1');
    var head = el('div', 'flex items-center justify-between gap-2');
    head.appendChild(el('span', 'aa-step-title font-bold text-slate-700', ''));
    var del = el('button', 'text-rose-600 font-bold', '刪除此小問題');
    del.type = 'button';
    del.addEventListener('click', function () {
      if (list.children.length <= MIN_STEPS) { alert('情境題至少要有 ' + MIN_STEPS + ' 個小問題。'); return; }
      row.remove(); renumber(list);
    });
    head.appendChild(del);
    row.appendChild(head);
    var prompt = el('input', 'w-full px-2 py-1.5 border rounded-lg'); prompt.type = 'text';
    prompt.placeholder = '小問題，例如：下一步最適當的處置是？'; prompt.setAttribute('data-role', 'prompt');
    row.appendChild(prompt);
    for (var k = 0; k < OPTIONS; k++) {
      var o = el('input', 'w-full px-2 py-1.5 border rounded-lg'); o.type = 'text';
      o.placeholder = '選項 ' + String.fromCharCode(65 + k) + (k >= 2 ? '（可留白）' : '');
      o.setAttribute('data-role', 'option'); row.appendChild(o);
    }
    var wrap = el('label', 'flex items-center gap-2');
    wrap.appendChild(el('span', 'font-bold text-slate-600', '正確答案'));
    var sel = el('select', 'px-2 py-1.5 border rounded-lg bg-white'); sel.setAttribute('data-role', 'correct');
    for (var c = 0; c < OPTIONS; c++) { var op = el('option', null, String.fromCharCode(65 + c)); op.value = String(c); sel.appendChild(op); }
    wrap.appendChild(sel); row.appendChild(wrap);
    list.appendChild(row);
    renumber(list);
  }

  function build(catId) {
    var box = el('div', 'hidden rounded-lg border border-violet-200 bg-violet-50/60 p-2 space-y-2 text-xs');
    box.id = boxId(catId);
    box.appendChild(el('p', 'font-bold text-violet-900', '🩺 情境題：上方「題目內容」寫病例／情境，下面設定小問題'));
    box.appendChild(el('p', 'text-slate-600', '學員要答完每一個小問題；全部答對才算這題答對。正確答案學員看不到。'));
    var list = el('div', 'space-y-2'); list.id = listId(catId);
    box.appendChild(list);
    var add = el('button', 'px-3 py-1.5 rounded-lg border border-violet-300 bg-white font-bold text-violet-800', '＋ 增加小問題');
    add.type = 'button';
    add.addEventListener('click', function () { addStep(catId); });
    box.appendChild(add);
    var anchor = document.getElementById('qform-' + catId + '-explain');
    if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(box, anchor);
    for (var n = 0; n < MIN_STEPS; n++) addStep(catId);
    return box;
  }

  function syncForm(catId, type) {
    var box = document.getElementById(boxId(catId));
    if (type !== 'scenario') { if (box) box.classList.add('hidden'); return; }
    if (!box) box = build(catId);
    if (box) box.classList.remove('hidden');
  }

  // Returns {steps:[...]} or null (alert shown) when incomplete.
  function collect(catId) {
    var list = document.getElementById(listId(catId));
    if (!list) { alert('請先填寫情境題的小問題。'); return null; }
    var steps = [];
    for (var n = 0; n < list.children.length; n++) {
      var row = list.children[n];
      var prompt = row.querySelector('[data-role="prompt"]').value.trim();
      var opts = Array.prototype.map.call(row.querySelectorAll('[data-role="option"]'), function (i) { return i.value.trim(); });
      var correct = Number(row.querySelector('[data-role="correct"]').value);
      // Trailing blanks are dropped; a blank in the middle or an empty right answer is an error.
      while (opts.length && !opts[opts.length - 1]) opts.pop();
      if (!prompt) { alert('小問題 ' + (n + 1) + ' 還沒寫題目。'); return null; }
      if (opts.length < 2 || opts.some(function (o) { return !o; })) { alert('小問題 ' + (n + 1) + ' 至少要有 2 個選項，且選項之間不能留空白。'); return null; }
      if (correct >= opts.length) { alert('小問題 ' + (n + 1) + ' 的正確答案選到沒有填寫的選項。'); return null; }
      steps.push({ prompt: prompt, options: opts, correctIndex: correct });
    }
    if (steps.length < MIN_STEPS) { alert('情境題至少要有 ' + MIN_STEPS + ' 個小問題。'); return null; }
    return { steps: steps };
  }

  var api = { syncForm: syncForm, collect: collect };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AdminScenarioQuestion = api;
})(typeof window !== 'undefined' ? window : globalThis);
