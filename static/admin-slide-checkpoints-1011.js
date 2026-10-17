/* Teacher: reading rules and optional checkpoint questions for one material.
 *
 * Owner of: the "閱讀規則與小測驗" editor opened from the course hub material menu
 * (openSlideCheckpointEditor).
 *   - 閱讀規則 (every material): 必讀／選讀; for slides/PDF also the minimum seconds per
 *     page and a switch for all checkpoints of this material.
 *   - 小測驗 (slides/PDF only): nothing is shown to learners until a teacher adds a
 *     question; every question can be switched off or deleted at any time.
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

  function header(panel, title) {
    var head = el('div', 'flex items-center justify-between gap-2');
    head.appendChild(el('h3', 'text-base font-bold', title));
    var x = el('button', 'btn btn-ghost', '關閉'); x.type = 'button'; x.addEventListener('click', close);
    head.appendChild(x);
    panel.appendChild(head);
  }

  function rulesSection(materialId, rules) {
    var box = el('section', 'space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3');
    box.appendChild(el('b', 'text-sm', '閱讀規則'));
    var need = el('select', 'field');
    [['required', '必讀：讀完才能考試'], ['optional', '選讀：不影響考試開放']].forEach(function (pair) {
      var o = el('option', null, pair[1]); o.value = pair[0]; need.appendChild(o);
    });
    need.value = rules.optional ? 'optional' : 'required';
    box.appendChild(labelled('這份教材', need));
    var seconds = null, cpToggle = null;
    if (rules.pagedMaterial) {
      seconds = el('input', 'field'); seconds.type = 'number'; seconds.min = '0'; seconds.max = '120';
      seconds.placeholder = '留白＝自動（依每頁字數 5～30 秒）';
      if (rules.minSecondsPerPage != null) seconds.value = String(rules.minSecondsPerPage);
      box.appendChild(labelled('每頁最短閱讀秒數', seconds));
    }
    if (rules.pagedMaterial || rules.mediaMaterial) {
      cpToggle = el('select', 'field');
      [['on', '開啟：學員會看到下方設定的小測驗'], ['off', '關閉：這份教材不出小測驗']].forEach(function (pair) {
        var o = el('option', null, pair[1]); o.value = pair[0]; cpToggle.appendChild(o);
      });
      cpToggle.value = rules.checkpointsEnabled ? 'on' : 'off';
      box.appendChild(labelled('小測驗', cpToggle));
    }
    var status = el('p', 'text-sm text-slate-600', '');
    var save = el('button', 'btn btn-primary', '儲存閱讀規則'); save.type = 'button';
    save.addEventListener('click', function () {
      var body = { optional: need.value === 'optional' };
      if (seconds) body.minSecondsPerPage = seconds.value.trim() === '' ? null : Number(seconds.value);
      if (cpToggle) body.checkpointsEnabled = cpToggle.value === 'on';
      save.disabled = true;
      request('/api/materials/' + encodeURIComponent(materialId) + '/reading-rules', { method: 'PUT', body: JSON.stringify(body) }).then(function (r) {
        save.disabled = false;
        status.textContent = r.ok ? '已儲存。' : ((r.d && r.d.error) || '儲存失敗');
      });
    });
    box.appendChild(save);
    box.appendChild(status);
    return box;
  }

  function labelled(text, control) {
    var l = el('label', 'block space-y-1 text-sm');
    l.appendChild(el('span', 'block font-bold', text));
    l.appendChild(control);
    return l;
  }

  function refresh(panel, materialId) {
    panel.textContent = '';
    panel.appendChild(el('p', 'text-sm text-slate-500', '讀取中…'));
    request('/api/materials/' + encodeURIComponent(materialId) + '/reading-rules').then(function (rulesRes) {
      if (!rulesRes.ok) {
        panel.textContent = '';
        header(panel, '閱讀規則');
        panel.appendChild(el('p', 'text-sm text-rose-700', (rulesRes.d && rulesRes.d.error) || '讀取失敗'));
        return;
      }
      var isMedia = !!rulesRes.d.mediaMaterial;
      if (!rulesRes.d.pagedMaterial && !isMedia) {
        panel.textContent = '';
        header(panel, '閱讀規則');
        panel.appendChild(rulesSection(materialId, rulesRes.d));
        return;
      }
      request('/api/materials/' + encodeURIComponent(materialId) + '/checkpoints/manage').then(function (res) {
        panel.textContent = '';
        header(panel, '閱讀規則與小測驗');
        panel.appendChild(rulesSection(materialId, rulesRes.d));
        panel.appendChild(el('b', 'block text-sm', isMedia ? '影音小測驗' : '投影片小測驗'));
        panel.appendChild(el('p', 'text-sm text-slate-600', isMedia
          ? '選填功能。影片播放到你指定的秒數時會暫停並跳出一題小測驗。答錯可以回看這一段（從上一題的位置開始）再答一次；第二次才顯示正確答案。答不答都能繼續播放，不影響完成與考試。小技巧：先播放到想出題的地方，看播放器上的時間再填秒數。'
          : '選填功能。學員讀完你指定的那一頁、翻到下一頁時，會跳出一題小測驗（若是最後一頁，就在最後一頁出現）。答錯第一次會先看說明、可以再答一次；第二次才顯示正確答案。答不答都能繼續閱讀，不影響完成與考試。'));
        if (!res.ok) { panel.appendChild(el('p', 'text-sm text-rose-700', (res.d && res.d.error) || '讀取失敗')); return; }
        var pages = res.d.pageCount || 0;
        var items = res.d.items || [];
        if (!items.length) panel.appendChild(el('p', 'rounded-lg bg-slate-50 p-3 text-sm text-slate-500', '目前沒有小測驗。'));
        items.forEach(function (item) {
          var row = el('div', 'space-y-1 rounded-lg border p-2 text-sm' + (item.active && !item.stale ? '' : ' opacity-70'));
          row.appendChild(el('div', 'font-bold', (isMedia ? '第 ' + item.page + ' 秒暫停' : '考第 ' + item.page + ' 頁') + '｜' + item.question));
          var answerLetter = String.fromCharCode(65 + item.correctIndex);
          row.appendChild(el('div', 'text-sm text-slate-600', '正確答案：' + answerLetter + '｜已作答 ' + item.stats.answered + ' 人、第一次就答對 ' + item.stats.correct + ' 人'));
          if (item.stale) row.appendChild(el('div', 'text-sm font-bold text-amber-700', '教材已更新版本，這題暫時不會顯示給學員。請確認頁碼後按「重新套用」。'));
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
        panel.appendChild(form(panel, materialId, pages, isMedia));
      });
    });
  }

  function button(label, onClick) {
    var b = el('button', 'btn btn-secondary', label);
    b.type = 'button'; b.addEventListener('click', onClick); return b;
  }

  function patch(panel, materialId, id, body) {
    request('/api/slide-checkpoints/' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify(body) }).then(function (r) {
      if (!r.ok) root.alert((r.d && r.d.error) || '更新失敗'); else refresh(panel, materialId);
    });
  }

  function form(panel, materialId, pages, isMedia) {
    var f = el('form', 'space-y-2 rounded-xl border border-teal-200 bg-teal-50/50 p-3');
    f.appendChild(el('b', 'text-sm', '新增一題'));
    var page = el('input', 'w-full rounded-lg border p-2 text-sm'); page.type = 'number'; page.min = '1';
    if (pages) page.max = String(pages);
    if (isMedia) { page.removeAttribute('max'); page.placeholder = '播放到第幾秒時暫停出題（例如 1 分 30 秒填 90）'; }
    else page.placeholder = '考第幾頁的內容' + (pages ? '（1～' + pages + '）' : '') + '：學員讀完這頁後出現';
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
    var why = el('textarea', 'w-full rounded-lg border p-2 text-sm'); why.rows = 2; why.placeholder = '答錯時先給的說明（選填，建議寫，學員會看著它再答一次）';
    f.appendChild(why);
    var submit = el('button', 'btn btn-primary', '新增小測驗'); submit.type = 'submit';
    f.appendChild(submit);
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var values = opts.map(function (i) { return i.value.trim(); });
      while (values.length && !values[values.length - 1]) values.pop();
      var body = { page: Number(page.value), second: isMedia ? Number(page.value) : undefined, question: q.value.trim(), options: values, correctIndex: Number(correct.value), explanation: why.value.trim() };
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
