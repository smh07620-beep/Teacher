/* Teacher assessment page · inline 待批改 and 歷史紀錄 (stage 2).
 *
 * 待批改 and 歷史紀錄 used to jump to another workspace, open a panel at the
 * bottom of it and confirm through message windows.  Both now live inside the
 * assessment page as tabs: list -> click a person -> the answer opens in the
 * same place, with 返回名單 and 上一位／下一位.  Nothing here decides who may
 * review: GET /api/records is already scoped by the server and
 * PATCH /api/records/<id>/review re-checks the reviewer, so this module only
 * presents what the server returned.  No inline handlers (CSP-safe).
 */
(function () {
  'use strict';

  const PAGE = 30;
  const state = {
    tab: 'exams',
    records: [],
    loaded: false,
    loading: false,
    view: {pending: {openId: '', query: ''}, history: {openId: '', query: '', result: 'all', visible: PAGE}},
    drafts: {},
    notice: {pending: '', history: ''},
  };

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const isPending = r => r?.reviewStatus === 'pending';
  const time = r => {
    const t = Date.parse(r?.timestamp || r?.submittedAt || r?.recordedAt || '');
    return Number.isFinite(t) ? t : 0;
  };
  const byNewest = (a, b) => time(b) - time(a);

  function panel() { return document.getElementById('admin-section-quiz'); }

  function ensurePane(name, title) {
    const host = panel();
    if (!host) return null;
    const id = `teacher-assess-${name}-1031`;
    let pane = document.getElementById(id);
    if (!pane) {
      pane = document.createElement('section');
      pane.id = id;
      pane.className = 'teacher-assess-pane-1031 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3';
      pane.setAttribute('aria-label', title);
      pane.addEventListener('click', event => onClick(name, event));
      pane.addEventListener('input', event => onInput(name, event));
      pane.addEventListener('change', event => onInput(name, event));
      host.appendChild(pane);
    }
    return pane;
  }

  async function load(force) {
    if (state.loading) return;
    if (state.loaded && !force) return;
    state.loading = true;
    try {
      const res = await fetch('/api/records', {credentials: 'same-origin'});
      if (res.status === 401) throw new Error('登入狀態已失效，請重新登入後再試。');
      const data = await res.json().catch(() => []);
      if (!res.ok) throw new Error(data?.error || '無法取得成績');
      state.records = Array.isArray(data) ? data : [];
      state.loaded = true;
      state.error = '';
    } catch (error) {
      state.error = error.message || '讀取失敗';
    } finally {
      state.loading = false;
    }
    updateBadge();
  }

  function updateBadge() {
    const badge = document.getElementById('teacher-assessment-pending-badge-1030');
    if (!badge || !state.loaded) return;
    const count = state.records.filter(isPending).length;
    badge.textContent = String(count);
    badge.classList.toggle('hidden', count <= 0);
  }

  function pendingList() {
    const q = state.view.pending.query.trim().toLowerCase();
    return state.records.filter(isPending).filter(r => !q || `${r.name || ''} ${r.empId || ''} ${r.quizTitle || ''}`.toLowerCase().includes(q)).sort(byNewest);
  }

  function historyList() {
    const v = state.view.history;
    const q = v.query.trim().toLowerCase();
    return state.records.filter(r => !isPending(r)).filter(r => {
      if (q && !`${r.name || ''} ${r.empId || ''} ${r.quizTitle || ''} ${r.groupLabel || ''}`.toLowerCase().includes(q)) return false;
      if (v.result === 'pass') return r.status === '合格';
      if (v.result === 'fail') return r.status !== '合格';
      return true;
    }).sort(byNewest);
  }

  const searchBox = (name, placeholder, extra = '') => `<div class="flex flex-wrap items-center gap-2"><input type="search" data-assess-search="${name}" value="${esc(state.view[name].query)}" placeholder="${placeholder}" class="min-w-[12rem] flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm">${extra}</div>`;
  const noticeHtml = name => state.notice[name] ? `<p role="status" class="rounded-xl bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800">${esc(state.notice[name])}</p>` : '';
  const backBar = (name, list, index) => `<div class="flex flex-wrap items-center justify-between gap-2"><button type="button" data-assess-back class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700">← 返回名單</button><span class="flex items-center gap-2 text-xs text-slate-500">第 ${index + 1} / ${list.length} 位<button type="button" data-assess-step="-1" ${index <= 0 ? 'disabled' : ''} class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-slate-700 disabled:opacity-40">← 上一位</button><button type="button" data-assess-step="1" ${index >= list.length - 1 ? 'disabled' : ''} class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-bold text-slate-700 disabled:opacity-40">下一位 →</button></span></div>`;

  function renderPending() {
    const pane = ensurePane('pending', '待批改');
    if (!pane) return;
    if (!state.loaded) { pane.innerHTML = `<p class="text-sm text-slate-500">${state.error ? '❌ ' + esc(state.error) : '讀取待批改作答中…'}</p>`; return; }
    const v = state.view.pending;
    const list = pendingList();
    const index = list.findIndex(r => String(r.id) === v.openId);
    if (v.openId && index >= 0) { renderPendingDetail(pane, list, index); return; }
    v.openId = '';
    const rows = list.length ? list.map(r => `<li class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2"><div class="min-w-0"><b class="text-sm text-slate-900">${esc(r.name)}</b> <span class="text-xs text-slate-500">${esc(r.empId)}</span><div class="truncate text-xs text-slate-600">${esc(r.quizTitle)}<span class="ml-2 text-slate-400">${esc(r.timestamp || '')}</span></div></div><button type="button" data-assess-open="${esc(r.id)}" class="whitespace-nowrap rounded-lg bg-indigo-700 px-4 py-2 text-xs font-black text-white">批改</button></li>`).join('') : '<li class="rounded-xl bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">🎉 目前沒有待批改的作答</li>';
    pane.innerHTML = `${noticeHtml('pending')}<div class="flex items-center justify-between gap-2"><h4 class="text-sm font-black text-slate-900">待批改（${list.length}）</h4></div>${searchBox('pending', '🔎 搜尋姓名、工號或考卷')}<ul class="space-y-2">${rows}</ul>`;
    restoreSearchFocus(pane, 'pending');
  }

  function draftFor(record) {
    const id = String(record.id);
    if (!state.drafts[id]) {
      const scores = {}; const comments = {};
      (record.answersDetail || []).forEach((a, i) => {
        if (a?.questionType !== 'essay') return;
        scores[i] = a.reviewScore ?? '';
        comments[i] = a.reviewComment || '';
      });
      state.drafts[id] = {scores, comments, overall: record.reviewComment || '', error: '', saving: false};
    }
    return state.drafts[id];
  }

  function renderPendingDetail(pane, list, index) {
    const r = list[index];
    const draft = draftFor(r);
    const answers = r.answersDetail || [];
    const essays = answers.map((a, i) => ({a, i})).filter(x => x.a?.questionType === 'essay');
    const auto = answers.filter(a => a?.questionType !== 'essay');
    const autoRight = auto.filter(a => a.isCorrect === true).length;
    const questions = essays.length ? essays.map(({a, i}) => `<div class="space-y-2 rounded-xl border border-rose-100 bg-white p-3"><div class="text-sm font-semibold text-slate-800">第 ${i + 1} 題：${esc(a.questionText || '')}</div><div class="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm">${esc(a.userAnswer || '未答')}</div><div class="grid grid-cols-1 items-center gap-2 md:grid-cols-[auto_6rem_1fr]"><label class="text-xs font-bold text-slate-600" for="assess-score-${i}">本題分數 0–100</label><input id="assess-score-${i}" data-assess-score="${i}" type="number" min="0" max="100" step="1" value="${esc(draft.scores[i] ?? '')}" class="rounded-lg border px-2 py-1.5 text-sm"><input data-assess-comment="${i}" type="text" maxlength="1000" value="${esc(draft.comments[i] ?? '')}" placeholder="本題評語（選填）" class="rounded-lg border px-2 py-1.5 text-sm"></div></div>`).join('') : '<p class="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">此份作答沒有問答題。</p>';
    pane.innerHTML = `${noticeHtml('pending')}${backBar('pending', list, index)}<div><h4 class="text-base font-black text-slate-900">${esc(r.name)} <span class="text-xs font-normal text-slate-500">${esc(r.empId)}</span></h4><p class="text-xs text-slate-600">${esc(r.quizTitle)}・${esc(r.timestamp || '')}${auto.length ? `・其餘 ${auto.length} 題系統已自動評分（答對 ${autoRight} 題）` : ''}</p></div>${questions}<textarea data-assess-overall rows="2" maxlength="2000" placeholder="整體評語（選填）" class="w-full rounded-xl border px-3 py-2 text-sm">${esc(draft.overall)}</textarea><p data-assess-error role="alert" class="${draft.error ? '' : 'hidden '}rounded-xl bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700">${esc(draft.error)}</p><div class="flex flex-wrap items-center gap-3"><button type="button" data-assess-save ${draft.saving ? 'disabled' : ''} class="rounded-lg bg-rose-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">✅ 儲存批改${index < list.length - 1 ? '並看下一位' : ''}</button><span class="text-[11px] text-slate-500">切換上一位／下一位時，已輸入的分數會暫存在本頁，按「儲存批改」後才正式送出。</span></div>`;
  }

  function renderHistory() {
    const pane = ensurePane('history', '歷史紀錄');
    if (!pane) return;
    if (!state.loaded) { pane.innerHTML = `<p class="text-sm text-slate-500">${state.error ? '❌ ' + esc(state.error) : '讀取歷史紀錄中…'}</p>`; return; }
    const v = state.view.history;
    const list = historyList();
    const index = list.findIndex(r => String(r.id) === v.openId);
    if (v.openId && index >= 0) { renderHistoryDetail(pane, list, index); return; }
    v.openId = '';
    const shown = list.slice(0, v.visible);
    const filter = `<select data-assess-result class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"><option value="all" ${v.result === 'all' ? 'selected' : ''}>全部結果</option><option value="pass" ${v.result === 'pass' ? 'selected' : ''}>合格</option><option value="fail" ${v.result === 'fail' ? 'selected' : ''}>未通過</option></select>`;
    const rows = shown.length ? shown.map(r => `<li class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 px-3 py-2"><div class="min-w-0"><b class="text-sm text-slate-900">${esc(r.name)}</b> <span class="text-xs text-slate-500">${esc(r.empId)}</span><div class="truncate text-xs text-slate-600">${esc(r.quizTitle)}<span class="ml-2 text-slate-400">${esc(r.timestamp || '')}</span></div></div><div class="flex items-center gap-3"><span class="text-sm font-black ${r.status === '合格' ? 'text-emerald-700' : 'text-rose-700'}">${esc(r.score)} 分・${esc(r.status)}</span><button type="button" data-assess-open="${esc(r.id)}" class="whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-bold text-slate-700">查看</button></div></li>`).join('') : '<li class="rounded-xl bg-slate-50 px-3 py-6 text-center text-sm text-slate-500">沒有符合條件的紀錄</li>';
    const more = list.length > shown.length ? `<button type="button" data-assess-more class="w-full rounded-xl border border-slate-200 py-2 text-xs font-bold text-slate-600">顯示更多（還有 ${list.length - shown.length} 筆）</button>` : '';
    pane.innerHTML = `<h4 class="text-sm font-black text-slate-900">歷史紀錄（${list.length}）</h4>${searchBox('history', '🔎 搜尋姓名、工號、考卷或組別', filter)}<ul class="space-y-2">${rows}</ul>${more}`;
    restoreSearchFocus(pane, 'history');
  }

  function renderHistoryDetail(pane, list, index) {
    const r = list[index];
    const answers = r.answersDetail || [];
    const items = answers.map((a, i) => {
      const essay = a?.questionType === 'essay';
      const verdict = essay ? `問答題：${esc(a.reviewScore ?? '—')} 分` : (a?.isCorrect === true ? '✅ 答對' : (a?.isCorrect === false ? '❌ 答錯' : '—'));
      return `<li class="space-y-1 rounded-xl border border-slate-200 p-3"><div class="flex items-start justify-between gap-2 text-sm font-semibold text-slate-800"><span>第 ${i + 1} 題：${esc(a?.questionText || '')}</span><span class="whitespace-nowrap text-xs">${verdict}</span></div><div class="whitespace-pre-wrap rounded-lg bg-slate-50 p-2 text-sm">${esc(a?.userAnswer ?? '未答')}</div>${essay && a.reviewComment ? `<p class="text-xs text-slate-600">評語：${esc(a.reviewComment)}</p>` : ''}</li>`;
    }).join('') || '<li class="text-sm text-slate-500">此紀錄沒有題目明細。</li>';
    pane.innerHTML = `${backBar('history', list, index)}<div><h4 class="text-base font-black text-slate-900">${esc(r.name)} <span class="text-xs font-normal text-slate-500">${esc(r.empId)}</span></h4><p class="text-xs text-slate-600">${esc(r.quizTitle)}・${esc(r.timestamp || '')}・<b class="${r.status === '合格' ? 'text-emerald-700' : 'text-rose-700'}">${esc(r.score)} 分・${esc(r.status)}</b>${r.reviewerName ? `・批改：${esc(r.reviewerName)}` : ''}</p>${r.reviewComment ? `<p class="mt-1 text-xs text-slate-700">整體評語：${esc(r.reviewComment)}</p>` : ''}</div><ul class="space-y-2">${items}</ul>`;
  }

  function restoreSearchFocus(pane, name) {
    if (state.focusSearch !== name) return;
    state.focusSearch = '';
    const input = pane.querySelector(`[data-assess-search="${name}"]`);
    if (input) { input.focus(); try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) { /* ignore */ } }
  }

  function render(name) { (name === 'pending' ? renderPending : renderHistory)(); }

  function currentList(name) { return name === 'pending' ? pendingList() : historyList(); }

  function onInput(name, event) {
    const t = event.target;
    if (t.matches?.('[data-assess-search]')) {
      state.view[name].query = t.value;
      if (name === 'history') state.view.history.visible = PAGE;
      state.focusSearch = name;
      render(name);
      return;
    }
    if (t.matches?.('[data-assess-result]')) { state.view.history.result = t.value; state.view.history.visible = PAGE; render('history'); return; }
    if (name !== 'pending') return;
    const record = state.records.find(r => String(r.id) === state.view.pending.openId);
    if (!record) return;
    const draft = draftFor(record);
    if (t.matches('[data-assess-score]')) draft.scores[t.dataset.assessScore] = t.value;
    else if (t.matches('[data-assess-comment]')) draft.comments[t.dataset.assessComment] = t.value;
    else if (t.matches('[data-assess-overall]')) draft.overall = t.value;
  }

  async function onClick(name, event) {
    const target = event.target.closest?.('button');
    if (!target) return;
    const v = state.view[name];
    if (target.hasAttribute('data-assess-open')) { v.openId = target.dataset.assessOpen; state.notice[name] = ''; render(name); panel()?.scrollIntoView?.({block: 'start'}); return; }
    if (target.hasAttribute('data-assess-back')) { v.openId = ''; render(name); return; }
    if (target.hasAttribute('data-assess-more')) { v.visible += PAGE; render(name); return; }
    if (target.hasAttribute('data-assess-step')) {
      const list = currentList(name);
      const index = list.findIndex(r => String(r.id) === v.openId);
      const next = list[index + Number(target.dataset.assessStep)];
      if (next) { v.openId = String(next.id); render(name); }
      return;
    }
    if (target.hasAttribute('data-assess-save') && name === 'pending') await save();
  }

  async function save() {
    const v = state.view.pending;
    const list = pendingList();
    const index = list.findIndex(r => String(r.id) === v.openId);
    const record = list[index];
    if (!record) return;
    const draft = draftFor(record);
    const missing = [];
    const essayScores = {}; const essayComments = {};
    (record.answersDetail || []).forEach((a, i) => {
      if (a?.questionType !== 'essay') return;
      const value = draft.scores[i];
      if (value === '' || value === undefined || value === null) missing.push(i + 1);
      essayScores[i] = value;
      essayComments[i] = draft.comments[i] || '';
    });
    if (missing.length) { draft.error = `問答題必須逐題給分，尚未評分：第 ${missing.join('、')} 題`; render('pending'); return; }
    draft.error = ''; draft.saving = true; render('pending');
    try {
      const res = await fetch(`/api/records/${encodeURIComponent(record.id)}/review`, {
        method: 'PATCH', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({essayScores, essayComments, reviewComment: draft.overall}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || '批改儲存失敗');
      const nextRecord = list[index + 1] || list[index - 1] || null;
      delete state.drafts[String(record.id)];
      state.notice.pending = `✅ 已儲存 ${record.name} 的批改：${data.score} 分（${data.status}）`;
      v.openId = nextRecord && list.length > 1 ? String(nextRecord.id) : '';
      await load(true);
      window.TeacherActionQueue1024?.refresh?.();
      document.dispatchEvent(new CustomEvent('teacher-assessment-graded-1031', {detail: {id: record.id}}));
    } catch (error) {
      draft.saving = false;
      draft.error = error.message || '批改儲存失敗';
    }
    draft.saving = false;
    render('pending');
  }

  async function show(tab) {
    const host = panel();
    if (!host) return false;
    state.tab = ['pending', 'history'].includes(tab) ? tab : 'exams';
    host.dataset.assessTab = state.tab;
    document.getElementById('teacher-assessment-flow-1014')?.querySelectorAll('[data-assessment-tab-1030]').forEach(button => {
      const active = button.dataset.assessmentTab1030 === (tab === 'analytics' ? 'analytics' : state.tab);
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    if (state.tab === 'exams') return true;
    ensurePane('pending', '待批改'); ensurePane('history', '歷史紀錄');
    render(state.tab);
    await load(true);
    render(state.tab);
    return true;
  }

  // Open one specific answer from elsewhere (e.g. 需要我處理) without leaving the page.
  async function openRecord(recordId) {
    state.view.pending.openId = String(recordId || '');
    state.view.pending.query = '';
    await show('pending');
    return !!state.records.find(r => String(r.id) === state.view.pending.openId && isPending(r));
  }

  window.TeacherAssessmentInline1031 = Object.freeze({show, openRecord, refresh: () => load(true).then(() => { if (state.tab !== 'exams') render(state.tab); })});
})();
