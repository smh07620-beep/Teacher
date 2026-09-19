/* Teacher 7.1 M2 · audience-aware training progress.
 * PGY learners see the formal PGY matrix; everyone else sees online progress.
 */
(function () {
  'use strict';

  const ID = 'pgy-competency-matrix-71';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  async function getJSON(url) {
    const response = await fetch(url, {credentials:'same-origin', cache:'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data?.error || `讀取失敗（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function profile(force = false) {
    if (window.Teacher71Profile?.load) return window.Teacher71Profile.load(force);
    return getJSON('/api/training-command-center/profile');
  }

  function dashboardUrl(p) {
    const query = new URLSearchParams({empId:p?.empId || ''});
    if (p?.name) query.set('name', p.name);
    return `/api/dashboard/me?${query.toString()}`;
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const course = document.getElementById('course-overview');
    if (!course) return null;
    section = document.createElement('section');
    section.id = ID;
    section.className = 'rounded-xl border border-teal-100 bg-teal-50/20 px-3 py-3';
    section.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <span class="flex items-center gap-2 min-w-0"><b id="training-progress-title-71" class="text-sm text-slate-900">📈 訓練進度</b><span id="training-progress-summary-71" class="text-[11px] text-slate-500 truncate">讀取中…</span></span>
      </div>
      <div id="pgy-matrix-status-71" class="text-xs text-slate-500 mt-3">讀取訓練進度中…</div>
      <div id="pgy-matrix-stats-71" class="grid grid-cols-2 lg:grid-cols-4 gap-2 mt-3"></div>
      <div id="pgy-matrix-table-71" class="mt-3 overflow-x-auto"></div>`;
    const statusHost = document.getElementById('learning-status-detail-71');
    const command = document.getElementById('training-command-center-71');
    if (statusHost) statusHost.appendChild(section);
    else if (command) command.after(section);
    else {
      const header = course.querySelector(':scope > .edu-card');
      if (header) header.after(section); else course.prepend(section);
    }
    return section;
  }

  function card(label, value, suffix = '') {
    return `<div class="rounded-xl border border-slate-200 bg-white px-3 py-2"><div class="text-[9px] text-slate-400">${escapeHtml(label)}</div><div class="text-sm font-black text-slate-800 mt-0.5">${escapeHtml(value)}${suffix ? `<span class="text-[9px] text-slate-400 ml-1">${escapeHtml(suffix)}</span>` : ''}</div></div>`;
  }

  function numberOrDash(value, digits = 1) {
    const n = Number(value);
    return value === null || value === undefined || value === '' || !Number.isFinite(n) ? '—' : n.toFixed(digits);
  }

  function renderOnline(p, dashboard, analytics) {
    const section = document.getElementById(ID);
    if (section) section.classList.add('hidden');
    const title = document.getElementById('training-progress-title-71');
    const summaryLine = document.getElementById('training-progress-summary-71');
    const status = document.getElementById('pgy-matrix-status-71');
    const stats = document.getElementById('pgy-matrix-stats-71');
    const table = document.getElementById('pgy-matrix-table-71');
    if (!title || !summaryLine || !status || !stats || !table) return;
    title.textContent = '📈 線上訓練進度';
    summaryLine.textContent = `學習進度 ${Number(dashboard?.progressPercent || 0)}%`;
    status.textContent = '一般／線上人員只呈現課程、教材與考試進度，不顯示 PGY 能力矩陣。';
    const s = analytics?.summary || {};
    stats.innerHTML = [
      card('學習進度', Number(dashboard?.progressPercent || 0), '%'),
      card('教材完成', `${Number(dashboard?.materialsCompleted || 0)}/${Number(dashboard?.materialsTotal || 0)}`),
      card('進行中課程', Number(dashboard?.activeCourses || 0)),
      card('考試平均', numberOrDash(s.averageExamScore), '/100')
    ].join('');
    table.innerHTML = Number(dashboard?.examsPending || 0)
      ? `<div class="rounded-xl border border-amber-100 bg-amber-50/60 px-3 py-2 text-xs text-amber-800">目前有 <b>${Number(dashboard.examsPending)}</b> 份待完成考核，可由上方「考核任務」快速進入。</div>`
      : '<div class="rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-xs text-emerald-700">✓ 目前沒有待完成考核。</div>';
  }

  function renderPgy(matrix) {
    const section = document.getElementById(ID);
    if (section) section.classList.remove('hidden');
    const title = document.getElementById('training-progress-title-71');
    const summaryLine = document.getElementById('training-progress-summary-71');
    const status = document.getElementById('pgy-matrix-status-71');
    const stats = document.getElementById('pgy-matrix-stats-71');
    const table = document.getElementById('pgy-matrix-table-71');
    if (!title || !summaryLine || !status || !stats || !table) return;
    const summary = matrix?.summary || {};
    const learners = Array.isArray(matrix?.learners) ? matrix.learners : [];
    const types = Array.isArray(matrix?.assessmentTypes) ? matrix.assessmentTypes : [];
    title.textContent = '🧭 PGY 能力矩陣／訓練進度';
    summaryLine.textContent = `指派完成 ${Number(summary.assignmentCompletionPercent || 0).toFixed(0)}%`;
    status.textContent = '依正式 PGY 指派與評量工具彙整；不另產生能力分數或臨床勝任結論。';
    stats.innerHTML = [
      card('PGY 學員', Number(summary.learners || 0)),
      card('指派完成率', Number(summary.assignmentCompletionPercent || 0).toFixed(1), '%'),
      card('逾期指派', Number(summary.assignmentsOverdue || 0)),
      card('評量平均', numberOrDash(summary.averageAssessmentScore), '/5')
    ].join('');
    if (!learners.length) {
      table.innerHTML = '<div class="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs text-slate-400 text-center">尚無 PGY 能力矩陣資料。</div>';
      return;
    }
    table.innerHTML = `<table class="min-w-max w-full text-left text-xs border-separate border-spacing-0"><thead><tr><th class="bg-slate-50 border-y border-l border-slate-200 p-2 min-w-[160px]">學員</th><th class="bg-slate-50 border-y border-slate-200 p-2">訓練進度</th>${types.map(type=>`<th class="bg-slate-50 border-y border-slate-200 p-2 text-center">${escapeHtml(type.label)}</th>`).join('')}</tr></thead><tbody>${learners.map(learner=>`<tr><td class="border-b border-l border-slate-100 bg-white p-2"><b>${escapeHtml(learner.name || learner.empId)}</b><div class="text-[9px] text-slate-400">${escapeHtml(learner.empId)}</div></td><td class="border-b border-slate-100 bg-white p-2"><b>${Number(learner.progress?.percent || 0).toFixed(0)}%</b><div class="text-[9px] text-slate-400">${Number(learner.progress?.assignmentsCompleted || 0)}/${Number(learner.progress?.assignmentsTotal || 0)} 完成</div></td>${types.map(type=>{const cell=learner.competencies?.[type.key]||{};return `<td class="border-b border-slate-100 bg-white p-2 text-center"><b>${cell.count?numberOrDash(cell.averageScore):'—'}</b><div class="text-[9px] text-slate-400">${Number(cell.count||0)} 次</div></td>`;}).join('')}</tr>`).join('')}</tbody></table>`;
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    try {
      const p = await profile(force);
      if (p?.pgyLearner) {
        const matrix = await getJSON('/api/training-command-center/pgy-matrix');
        renderPgy(matrix);
      } else {
        const [dashboard, analytics] = await Promise.all([
          p?.empId ? getJSON(dashboardUrl(p)).catch(()=>({})) : Promise.resolve({}),
          getJSON('/api/training-command-center/learning-analytics').catch(()=>({summary:{}}))
        ]);
        renderOnline(p, dashboard, analytics);
      }
    } catch (error) {
      if (error?.status === 401 || error?.status === 403) { section.classList.add('hidden'); return; }
      const status = document.getElementById('pgy-matrix-status-71');
      if (status) status.textContent = `❌ ${error.message || '無法讀取訓練進度'}`;
    }
  }

  function init() { if (mount()) load(false); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
