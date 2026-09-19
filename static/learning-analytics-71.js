/* Teacher 7.1 M3 · compact audience-aware Learning Analytics.
 * Visible course/material counts use the same dashboard projection as home.
 */
(function () {
  'use strict';

  const ID = 'learning-analytics-71';
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

  function numberOrDash(value, digits = 1) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const statusHost = document.getElementById('learning-status-detail-71');
    const header = document.querySelector('#course-overview > .edu-card');
    const host = statusHost || header;
    if (!host) return null;
    section = document.createElement('div');
    section.id = ID;
    section.className = 'pt-3 border-t border-slate-100';
    section.innerHTML = `
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <div><b class="text-xs text-slate-800">📊 學習摘要</b><span id="learning-analytics-status-71" class="ml-2 text-[10px] text-slate-400">讀取中…</span></div>
        <button id="learning-analytics-refresh-71" type="button" class="text-[10px] font-bold text-sky-700 hover:text-sky-900">↻ 更新</button>
      </div>
      <div id="learning-analytics-stats-71" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-2 mt-2"></div>
      <details id="learning-analytics-detail-71" class="mt-2 rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2">
        <summary class="cursor-pointer text-[11px] font-bold text-slate-600">查看詳細 Learning Analytics ▾</summary>
        <div id="learning-analytics-table-71" class="mt-3 overflow-x-auto"></div>
        <div id="learning-analytics-timeline-71" class="mt-3"></div>
      </details>`;
    host.appendChild(section);
    section.querySelector('#learning-analytics-refresh-71').addEventListener('click', () => load(true));
    return section;
  }

  function chip(label, value, note = '') {
    return `<div class="rounded-xl border border-slate-200 bg-white px-3 py-2"><div class="text-[9px] text-slate-400">${escapeHtml(label)}</div><div class="text-sm font-black text-slate-800 mt-0.5">${escapeHtml(value)}</div>${note ? `<div class="text-[9px] text-slate-400 mt-0.5">${escapeHtml(note)}</div>` : ''}</div>`;
  }

  function renderTimeline(rows, includePgy) {
    const host = document.getElementById('learning-analytics-timeline-71');
    if (!host) return;
    const timeline = Array.isArray(rows) ? rows.slice(-6) : [];
    host.innerHTML = `<div class="text-[10px] font-black text-slate-500 mb-2">近 6 個月活動</div><div class="grid sm:grid-cols-3 lg:grid-cols-6 gap-2">${timeline.map(month => {
      const parts = [`教材 ${Number(month.materials || 0)}`, `考試 ${Number(month.exams || 0)}`];
      if (includePgy) parts.push(`PGY ${Number(month.pgy || 0)}`, `評量 ${Number(month.assessments || 0)}`);
      return `<div class="rounded-lg border border-slate-100 bg-white px-2 py-2"><b class="block text-[10px] text-slate-700">${escapeHtml(month.month)}</b><span class="text-[9px] text-slate-400">${parts.join(' · ')}</span></div>`;
    }).join('') || '<span class="text-xs text-slate-400">尚無近期活動。</span>'}</div>`;
  }

  function renderTable(rows, includePgy) {
    const host = document.getElementById('learning-analytics-table-71');
    if (!host) return;
    const learners = Array.isArray(rows) ? rows : [];
    if (!learners.length) {
      host.innerHTML = '<div class="text-xs text-slate-400 py-2">尚無詳細學習分析資料。</div>';
      return;
    }
    const pgyHead = includePgy ? '<th class="bg-white border-y border-slate-200 p-2">PGY 指派</th><th class="bg-white border-y border-r border-slate-200 p-2">PGY 評量</th>' : '<th class="bg-white border-y border-r border-slate-200 p-2">考試</th>';
    host.innerHTML = `<table class="min-w-[620px] w-full text-left text-[10px] border-separate border-spacing-0"><thead><tr><th class="bg-white border-y border-l border-slate-200 p-2">學員</th><th class="bg-white border-y border-slate-200 p-2">教材</th>${includePgy ? '<th class="bg-white border-y border-slate-200 p-2">考試</th>' : ''}${pgyHead}</tr></thead><tbody>${learners.map(row => {
      const pgy = row.pgy || {};
      return `<tr><td class="bg-white border-b border-l border-slate-100 p-2"><b>${escapeHtml(row.name || row.empId)}</b><div class="text-slate-400">${escapeHtml(row.empId || '')}</div></td><td class="bg-white border-b border-slate-100 p-2"><b>${numberOrDash(row.materials?.averageProgress)}%</b><div class="text-slate-400">${Number(row.materials?.completed || 0)}/${Number(row.materials?.tracked || 0)} 完成</div></td><td class="bg-white border-b border-slate-100 p-2"><b>${numberOrDash(row.exams?.averageScore)}</b><div class="text-slate-400">${Number(row.exams?.passed || 0)}/${Number(row.exams?.reviewedAttempts || 0)} 通過</div></td>${includePgy ? `<td class="bg-white border-b border-slate-100 p-2"><b>${numberOrDash(pgy.completionRate)}%</b><div class="text-slate-400">${Number(pgy.completedAssignments || 0)}/${Number(pgy.assignments || 0)} 完成</div></td><td class="bg-white border-b border-r border-slate-100 p-2"><b>${numberOrDash(pgy.assessmentAverage)}</b><div class="text-slate-400">${Number(pgy.assessments || 0)} 筆</div></td>` : ''}</tr>`;
    }).join('')}</tbody></table>`;
  }

  function render(p, dashboard, analytics) {
    const status = document.getElementById('learning-analytics-status-71');
    const stats = document.getElementById('learning-analytics-stats-71');
    if (!status || !stats) return;
    const s = analytics?.summary || {};
    const includePgy = Boolean(p?.pgyLearner);

    // These visible material/course values intentionally come from /dashboard/me
    // so M3 and the home-page personal summary cannot disagree.
    const chips = [
      chip('教材完成', `${Number(dashboard?.materialsCompleted || 0)}/${Number(dashboard?.materialsTotal || 0)}`),
      chip('整體學習進度', `${Number(dashboard?.progressPercent || 0)}%`),
      chip('進行中課程', String(Number(dashboard?.activeCourses || 0))),
      chip('待完成考核', String(Number(dashboard?.examsPending || 0))),
      chip('考試平均', numberOrDash(s.averageExamScore), '/ 100')
    ];
    if (includePgy) {
      chips.push(chip('PGY 指派完成', `${numberOrDash(s.pgyCompletionRate)}%`));
      chips.push(chip('PGY 評量平均', numberOrDash(s.averagePgyAssessmentScore), '/ 5'));
    }
    stats.className = `grid grid-cols-2 sm:grid-cols-4 ${includePgy ? 'lg:grid-cols-7' : 'lg:grid-cols-5'} gap-2 mt-2`;
    stats.innerHTML = chips.join('');
    status.textContent = includePgy ? 'PGY 學員：線上學習＋PGY 指標' : '線上學習：課程／教材／考試';
    renderTable(analytics?.learners || [], includePgy);
    renderTimeline(analytics?.timeline || [], includePgy);
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('learning-analytics-status-71');
    if (status) status.textContent = force ? '更新中…' : '讀取中…';
    try {
      const p = await profile(force);
      const [dashboard, analytics] = await Promise.all([
        p?.empId ? getJSON(dashboardUrl(p)).catch(()=>({})) : Promise.resolve({}),
        getJSON('/api/training-command-center/learning-analytics').catch(()=>({summary:{},learners:[],timeline:[]}))
      ]);
      section.classList.remove('hidden');
      render(p, dashboard, analytics);
    } catch (error) {
      if (error?.status === 401 || error?.status === 403) { section.classList.add('hidden'); return; }
      if (status) status.textContent = `❌ ${error.message || '無法讀取學習摘要'}`;
    }
  }

  function init() { if (mount()) load(false); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
