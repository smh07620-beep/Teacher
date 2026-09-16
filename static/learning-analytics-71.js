/* Teacher 7.1 M3 · Learning Analytics
 * Descriptive read-only analytics over existing learning/exam/PGY records.
 */
(function () {
  'use strict';

  const ID = 'learning-analytics-71';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function groupLabel(key) {
    const group = (window.GROUPS || {})[key];
    return group?.name || group?.label || key || '—';
  }

  function numberOrDash(value, digits = 1) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const matrix = document.getElementById('pgy-competency-matrix-71');
    const command = document.getElementById('training-command-center-71');
    const anchor = matrix || command;
    const host = anchor?.parentElement || document.querySelector('main.flex-grow') || document.querySelector('main');
    if (!host) return null;
    section = document.createElement('section');
    section.id = ID;
    section.className = 'edu-card p-5 sm:p-6 border border-sky-100 bg-gradient-to-br from-white to-sky-50/30';
    section.innerHTML = `
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] font-black tracking-[0.18em] text-sky-600">TEACHER 7.1 · M3</p>
          <h2 class="text-xl font-black text-slate-950 mt-1">📊 Learning Analytics</h2>
          <p class="text-xs text-slate-500 mt-1">整合既有教材進度、考試與 PGY 紀錄；僅做描述性統計，不產生新的「總能力分數」。</p>
        </div>
        <button id="learning-analytics-refresh-71" type="button" class="text-xs font-bold px-3 py-2 rounded-xl border border-sky-200 bg-white text-sky-700 hover:bg-sky-50">↻ 更新</button>
      </div>
      <div id="learning-analytics-status-71" class="text-xs text-slate-500 mt-4">讀取學習分析中…</div>
      <div id="learning-analytics-stats-71" class="hidden grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-2 sm:gap-3 mt-4"></div>
      <div class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-4 mt-4">
        <div id="learning-analytics-table-71" class="overflow-x-auto"></div>
        <aside id="learning-analytics-timeline-71" class="rounded-2xl border border-slate-200 bg-white p-4"></aside>
      </div>
      <p class="text-[10px] text-slate-400 mt-4">教材完成率的分母是「已有學習紀錄的教材」，不是所有可用教材；考試平均與通過率只計已完成人工閱卷的紀錄。</p>`;
    if (anchor) anchor.after(section);
    else host.prepend(section);
    section.querySelector('#learning-analytics-refresh-71').addEventListener('click', () => load(true));
    return section;
  }

  function statCard(label, value, suffix = '', note = '') {
    return `<div class="rounded-xl border border-slate-200 bg-white px-3 py-3">
      <div class="text-[10px] text-slate-500">${escapeHtml(label)}</div>
      <div class="text-lg font-black text-slate-900 mt-0.5">${escapeHtml(value)}${suffix ? `<span class="text-[10px] font-bold text-slate-400 ml-1">${escapeHtml(suffix)}</span>` : ''}</div>
      ${note ? `<div class="text-[9px] text-slate-400 mt-0.5">${escapeHtml(note)}</div>` : ''}
    </div>`;
  }

  function domainCell(primary, secondary = '') {
    return `<div class="min-w-[110px]"><div class="font-black text-slate-900">${escapeHtml(primary)}</div>${secondary ? `<div class="text-[9px] text-slate-400 mt-0.5">${escapeHtml(secondary)}</div>` : ''}</div>`;
  }

  function renderTimeline(rows) {
    const host = document.getElementById('learning-analytics-timeline-71');
    if (!host) return;
    const timeline = Array.isArray(rows) ? rows : [];
    host.innerHTML = `<div class="font-black text-sm text-slate-900">近 6 個月活動</div>
      <p class="text-[10px] text-slate-400 mt-1">每月以既有紀錄時間戳記計數。</p>
      <div class="space-y-3 mt-4">${timeline.length ? timeline.map(month => {
        const total = Number(month.materials || 0) + Number(month.exams || 0) + Number(month.pgy || 0) + Number(month.assessments || 0);
        return `<div class="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2.5">
          <div class="flex items-center justify-between gap-2"><span class="text-xs font-black text-slate-700">${escapeHtml(month.month)}</span><span class="text-xs font-black text-sky-700">${total}</span></div>
          <div class="grid grid-cols-2 gap-x-2 gap-y-1 mt-2 text-[9px] text-slate-500">
            <span>教材 ${Number(month.materials || 0)}</span><span>考試 ${Number(month.exams || 0)}</span>
            <span>PGY完成 ${Number(month.pgy || 0)}</span><span>評量 ${Number(month.assessments || 0)}</span>
          </div>
        </div>`;
      }).join('') : '<div class="text-xs text-slate-400">尚無近期活動。</div>'}</div>`;
  }

  function render(data) {
    const status = document.getElementById('learning-analytics-status-71');
    const stats = document.getElementById('learning-analytics-stats-71');
    const table = document.getElementById('learning-analytics-table-71');
    if (!status || !stats || !table) return;
    const summary = data?.summary || {};
    const learners = Array.isArray(data?.learners) ? data.learners : [];

    status.textContent = learners.length
      ? `目前分析 ${learners.length} 位學員的既有學習紀錄。`
      : '目前範圍尚無可分析的學習紀錄。';
    stats.classList.remove('hidden');
    stats.innerHTML = [
      statCard('教材完成', `${Number(summary.materialsCompleted || 0)}/${Number(summary.materialsTracked || 0)}`, '', '已有追蹤紀錄'),
      statCard('教材平均進度', numberOrDash(summary.averageMaterialProgress), '%'),
      statCard('考試平均', numberOrDash(summary.averageExamScore), '/ 100'),
      statCard('考試通過率', numberOrDash(summary.examPassRate), '%', summary.examPendingReview ? `${summary.examPendingReview} 筆待人工閱卷` : ''),
      statCard('PGY 指派完成率', numberOrDash(summary.pgyCompletionRate), '%'),
      statCard('PGY 評量平均', numberOrDash(summary.averagePgyAssessmentScore), '/ 5')
    ].join('');

    if (!learners.length) {
      table.innerHTML = '<div class="rounded-xl border border-slate-200 bg-white px-4 py-5 text-xs text-slate-400 text-center">尚無 Learning Analytics 資料。</div>';
      renderTimeline(data?.timeline || []);
      return;
    }

    table.innerHTML = `<table class="min-w-[860px] w-full text-left text-xs border-separate border-spacing-0">
      <thead><tr>
        <th class="bg-slate-50 border-y border-l border-slate-200 rounded-tl-xl p-3 min-w-[180px]">學員</th>
        <th class="bg-slate-50 border-y border-slate-200 p-3">教材</th>
        <th class="bg-slate-50 border-y border-slate-200 p-3">考試</th>
        <th class="bg-slate-50 border-y border-slate-200 p-3">PGY 指派</th>
        <th class="bg-slate-50 border-y border-r border-slate-200 rounded-tr-xl p-3">PGY 評量</th>
      </tr></thead>
      <tbody>${learners.map(learner => {
        const materialAvg = learner.materials?.averageProgress;
        const examAvg = learner.exams?.averageScore;
        const assessmentAvg = learner.pgy?.assessmentAverage;
        return `<tr>
          <td class="border-b border-l border-slate-100 bg-white p-3"><div class="font-black text-slate-900">${escapeHtml(learner.name || learner.empId)}</div><div class="text-[10px] text-slate-400 mt-0.5">${escapeHtml(learner.empId)} · ${escapeHtml(groupLabel(learner.group))}</div></td>
          <td class="border-b border-slate-100 bg-white p-3">${domainCell(`${numberOrDash(materialAvg)}%`, `${Number(learner.materials?.completed || 0)}/${Number(learner.materials?.tracked || 0)} 完成`)}</td>
          <td class="border-b border-slate-100 bg-white p-3">${domainCell(numberOrDash(examAvg), `${Number(learner.exams?.passed || 0)}/${Number(learner.exams?.reviewedAttempts || 0)} 通過${Number(learner.exams?.pendingReview || 0) ? ` · ${learner.exams.pendingReview} 待閱` : ''}`)}</td>
          <td class="border-b border-slate-100 bg-white p-3">${domainCell(`${numberOrDash(learner.pgy?.completionRate)}%`, `${Number(learner.pgy?.completedAssignments || 0)}/${Number(learner.pgy?.assignments || 0)} 完成`)}</td>
          <td class="border-b border-r border-slate-100 bg-white p-3">${domainCell(numberOrDash(assessmentAvg), `${Number(learner.pgy?.assessments || 0)} 筆正式評量`)}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
    renderTimeline(data?.timeline || []);
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('learning-analytics-status-71');
    if (status) status.textContent = force ? '更新學習分析中…' : '讀取學習分析中…';
    try {
      const response = await fetch('/api/training-command-center/learning-analytics', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401 || response.status === 403) {
        section.classList.add('hidden');
        return;
      }
      if (!response.ok) throw new Error(data?.error || `讀取失敗（${response.status}）`);
      section.classList.remove('hidden');
      render(data);
    } catch (error) {
      if (status) status.textContent = `❌ ${error.message || '無法讀取 Learning Analytics'}`;
    }
  }

  function init() {
    if (!mount()) return;
    load(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
