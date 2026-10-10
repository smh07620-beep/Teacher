/* Teacher: set up optional in-slide checkpoint questions for a slide material.
 *
 * Owner of: the "投影片小測驗" editor opened from the course hub material menu
 * (openSlideCheckpointEditor).  Nothing is shown to learners until a teacher adds
 * a question here; every question can be switched off or deleted at any time.
 */
(function (root) {
  'use strict';

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function request(url, options) {
    return fetch(url, Object.assign({ credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } }, options || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; }); });
  }

  var modal = null;

  function close() { if (modal) { modal.remove(); modal = null; } }

  function open(materialId) {
    close();
    modal = el('div', 'fixed inset-0 z-[130] flex items-start justify-center overflow-y-auto bg-black/50 p-4');
    modal.setAttribute('role', 'dialog');
    var panel = el('div', 'w-full max-w-2xl space-y-3 rounded-2xl bg-white p-4 shadow-2xl');
    modal.appendChild(panel);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    document.body.appendChild(modal);
    refresh(panel, materialId);
  }

  function refresh(panel, materialId) {
    panel.textContent = '';
    panel.appendChild(el('p', 'text-sm text-slate-500', '讀取中…'));
    request('/api/materials/' + encodeURIComponent(materialId) + '/checkpoints/manage').then(function (res) {
      panel.textContent = '';
      var head = el('div', 'flex items-center justify-between gap-2');
      head.appendChild(el('h3', 'text-base font-black', '📝 投影片小測驗'));
      var x = el('button', 'rounded-lg border px-3 py-1 text-xs font-bold', '關閉'); x.type = 'button'; x.addEventListener('click', close);
      head.appendChild(x);
      panel.appendChild(head);
      panel.appendChild(el('p', 'text-xs text-slate-600',
        '選填功能。學員翻到你設定的頁面時，會跳出一題小測驗；答不答都能繼續閱讀，不影響完成率。學員作答後才會看到答案與說明。沒有設定任何題目就不會有任何變化。'));
      if (!res.ok) { panel.appendChild(el('p', 'text-sm text-rose-700', (res.d && res.d.error) || '讀取失敗')); return; }
      var pages = res.d.pageCount || 0;
      var items = res.d.items || [];
      if (!items.length) panel.appendChild(el('p', 'rounded-lg bg-slate-50 p-3 text-sm text-slate-500', '目前沒有小測驗。'));
      items.forEach(function (item) {
        var row = el('div', 'space-y-1 rounded-lg border p-2 text-sm' + (item.active && !item.stale ? '' : ' opacity-70'));
        row.appendChild(el('div', 'font-bold', '第 ' + item.page + ' 頁｜' + item.question));
        var answerLetter = String.fromCharCode(65 + item.correctIndex);
        row.appendChild(el('div', 'text-xs text-slate-600', '正確答案：' + answerLetter + '｜已作答 ' + item.stats.answered + ' 人、答對 ' + item.stats.correct + ' 人'));
        if (item.stale) row.appendChild(el('div', 'text-xs font-bold text-amber-700', '⚠ 教材已更新版本，這題暫時不會顯示給學員。請確認頁碼後按「重新套用」。'));
        var actions = el('div', 'flex flex-wrap gap-2');
        if (item.stale) actions.appendChild(button('重新套用', function () { patch(panel, materialId, item.id, { page: item.page }); }));
        actions.appendChild(button(item.active ? '停用' : '啟用', function () { patch(panel, materialId, item.id, { active: !item.active }); }));
        actions.appendChild(button('刪除', function () {
          if (!root.confirm('刪除這題小測驗？學員已作答的紀錄仍會保留。')) return;
          request('/api/slide-checkpoints/' + encodeURIComponent(item.id), { method: 'DELETE' }).then(function (r) {
            if (!r.ok) root.alert((r.d && r.d.error) || '刪除失敗'); else refresh(panel, materialId);
          });
        }));
        row.appendChild(actions);
        panel.appendChild(row);
      });
      panel.appendChild(form(panel, materialId, pages));
    });
  }

  function button(label, onClick) {
    var b = el('button', 'rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-bold', label);
    b.type = 'button'; b.addEventListener('click', onClick); return b;
  }

  function patch(panel, materialId, id, body) {
    request('/api/slide-checkpoints/' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify(body) }).then(function (r) {
      if (!r.ok) root.alert((r.d && r.d.error) || '更新失敗'); else refresh(panel, materialId);
    });
  }

  function form(panel, materialId, pages) {
    var f = el('form', 'space-y-2 rounded-xl border border-teal-200 bg-teal-50/50 p-3');
    f.appendChild(el('b', 'text-sm', '＋ 新增一題'));
    var page = el('input', 'w-full rounded-lg border p-2 text-sm'); page.type = 'number'; page.min = '1';
    if (pages) page.max = String(pages);
    page.placeholder = '要在第幾頁出現' + (pages ? '（1～' + pages + '）' : '');
    var q = el('textarea', 'w-full rounded-lg border p-2 text-sm'); q.rows = 2; q.placeholder = '題目';
    f.appendChild(page); f.appendChild(q);
    var opts = [];
    for (var i = 0; i < 4; i++) {
      var o = el('input', 'w-full rounded-lg border p-2 text-sm'); o.type = 'text';
      o.placeholder = '選項 ' + String.fromCharCode(65 + i) + (i >= 2 ? '（可留白）' : '');
      opts.push(o); f.appendChild(o);
    }
    var correct = el('select', 'rounded-lg border p-2 text-sm');
    for (var c = 0; c < 4; c++) { var op = el('option', null, '正確答案：' + String.fromCharCode(65 + c)); op.value = String(c); correct.appendChild(op); }
    f.appendChild(correct);
    var why = el('textarea', 'w-full rounded-lg border p-2 text-sm'); why.rows = 2; why.placeholder = '答完後顯示的說明（選填）';
    f.appendChild(why);
    var submit = el('button', 'rounded-lg bg-teal-700 px-3 py-2 text-sm font-bold text-white', '新增小測驗'); submit.type = 'submit';
    f.appendChild(submit);
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var values = opts.map(function (i) { return i.value.trim(); });
      while (values.length && !values[values.length - 1]) values.pop();
      var body = { page: Number(page.value), question: q.value.trim(), options: values, correctIndex: Number(correct.value), explanation: why.value.trim() };
      submit.disabled = true;
      request('/api/materials/' + encodeURIComponent(materialId) + '/checkpoints', { method: 'POST', body: JSON.stringify(body) }).then(function (r) {
        submit.disabled = false;
        if (!r.ok) root.alert((r.d && r.d.error) || '新增失敗'); else refresh(panel, materialId);
      });
    });
    return f;
  }

  var api = { open: open, close: close };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.AdminSlideCheckpoints = api;
    root.openSlideCheckpointEditor = open;
  }
})(typeof window !== 'undefined' ? window : globalThis);
