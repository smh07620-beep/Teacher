/* Teacher 7.1 M2 · PGY 能力矩陣／訓練進度
 * Read-only projection over existing assignments and formal PGY assessments.
 */
(function () {
  'use strict';

  const ID = 'pgy-competency-matrix-71';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function groupLabel(key) {
    const group = (window.GROUPS || {})[key];
    return group?.name || group?.label || key || '—';
  }

  function formatScore(value) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(1) : '—';
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const command = document.getElementById('training-command-center-71');
    const host = command?.parentElement || document.querySelector('main.flex-grow') || document.querySelector('main');
    if (!host) return null;
    section = document.createElement('section');
    section.id = ID;
    section.className = 'edu-card p-5 sm:p-6 border border-teal-100 bg-white';
    section.innerHTML = `
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] font-black tracking-[0.18em] text-teal-600">TEACHER 7.1 · M2</p>
          <h2 class="text-xl font-black text-slate-950 mt-1">🧭 PGY 能力矩陣／訓練進度</h2>
          <p class="text-xs text-slate-500 mt-1">依正式評量工具彙整既有紀錄；不另產生能力分數，也不自動判定臨床勝任。</p>
        </div>
        <button id="pgy-matrix-refresh-71" type="button" class="text-xs font-bold px-3 py-2 rounded-xl border border-teal-200 bg-white text-teal-700 hover:bg-teal-50">↻ 更新</button>
      </div>
      <div id="pgy-matrix-status-71" class="text-xs text-slate-500 mt-4">讀取能力矩陣中…</div>
      <div id="pgy-matrix-stats-71" class="hidden grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3 mt-4"></div>
      <div id="pgy-matrix-table-71" class="mt-4 overflow-x-auto"></div>
      <p class="text-[10px] text-slate-400 mt-4">單格顯示該正式評量工具的平均分數與完成次數；「訓練進度」只以 PGY 指派是否 finalized 計算。</p>`;
    if (command) command.after(section);
    else host.prepend(section);
    section.querySelector('#pgy-matrix-refresh-71').addEventListener('click', () => load(true));
    return section;
  }

  function statCard(label, value, suffix = '') {
    return `<div class="rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3">
      <div class="text-[10px] text-slate-500">${escapeHtml(label)}</div>
      <div class="text-lg font-black text-slate-900 mt-0.5">${escapeHtml(value)}${suffix ? `<span class="text-[10px] font-bold text-slate-400 ml-1">${escapeHtml(suffix)}</span>` : ''}</div>
    </div>`;
  }

  function progressCell(progress) {
    const percent = Math.max(0, Math.min(100, Number(progress?.percent || 0)));
    const overdue = Number(progress?.assignmentsOverdue || 0);
    return `<div class="min-w-[150px]">
      <div class="flex items-center justify-between gap-2 text-[10px]"><span class="font-black text-slate-700">${percent.toFixed(0)}%</span><span class="text-slate-400">${Number(progress?.assignmentsCompleted || 0)}/${Number(progress?.assignmentsTotal || 0)}</span></div>
      <div class="h-1.5 rounded-full bg-slate-100 overflow-hidden mt-1"><div class="h-full bg-teal-500" style="width:${percent}%"></div></div>
      ${overdue ? `<div class="text-[10px] font-bold text-rose-600 mt-1">逾期 ${overdue}</div>` : ''}
    </div>`;
  }

  function competencyCell(cell) {
    const count = Number(cell?.count || 0);
    if (!count) return '<span class="text-slate-300">—</span>';
    return `<div class="min-w-[72px] text-center">
      <div class="font-black text-slate-900">${formatScore(cell.averageScore)}</div>
      <div class="text-[9px] text-slate-400">${count} 次 · 最新 ${formatScore(cell.latestScore)}</div>
    </div>`;
  }

  function render(data) {
    const status = document.getElementById('pgy-matrix-status-71');
    const stats = document.getElementById('pgy-matrix-stats-71');
    const table = document.getElementById('pgy-matrix-table-71');
    if (!status || !stats || !table) return;
    const summary = data?.summary || {};
    const learners = Array.isArray(data?.learners) ? data.learners : [];
    const types = Array.isArray(data?.assessmentTypes) ? data.assessmentTypes : [];

    status.textContent = learners.length
      ? `目前範圍共 ${learners.length} 位學員；矩陣僅呈現已存在的正式評量紀錄。`
      : '目前範圍尚無可彙整的 PGY 學員紀錄。';
    stats.classList.remove('hidden');
    stats.innerHTML = [
      statCard('學員', Number(summary.learners || 0)),
      statCard('指派完成率', Number(summary.assignmentCompletionPercent || 0).toFixed(1), '%'),
      statCard('逾期指派', Number(summary.assignmentsOverdue || 0)),
      statCard('評量平均', formatScore(summary.averageAssessmentScore), '/ 5')
    ].join('');

    if (!learners.length) {
      table.innerHTML = '<div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-5 text-xs text-slate-400 text-center">尚無能力矩陣資料。</div>';
      return;
    }

    table.innerHTML = `<table class="min-w-max w-full text-left text-xs border-separate border-spacing-0">
      <thead><tr>
        <th class="sticky left-0 z-10 bg-slate-50 border-y border-l border-slate-200 rounded-tl-xl p-3 min-w-[180px]">學員</th>
        <th class="bg-slate-50 border-y border-slate-200 p-3 min-w-[170px]">訓練進度</th>
        <th class="bg-slate-50 border-y border-slate-200 p-3 min-w-[100px]">評量覆蓋</th>
        ${types.map(type => `<th class="bg-slate-50 border-y border-slate-200 p-3 text-center min-w-[86px]">${escapeHtml(type.label)}</th>`).join('')}
      </tr></thead>
      <tbody>${learners.map((learner, index) => `<tr>
        <td class="sticky left-0 z-[1] bg-white border-b border-l border-slate-100 p-3 ${index === learners.length - 1 ? 'rounded-bl-xl' : ''}">
          <div class="font-black text-slate-900">${escapeHtml(learner.name || learner.empId)}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${escapeHtml(learner.empId)} · ${escapeHtml(groupLabel(learner.group))}</div>
        </td>
        <td class="border-b border-slate-100 p-3">${progressCell(learner.progress)}</td>
        <td class="border-b border-slate-100 p-3"><span class="font-black text-slate-800">${Number(learner.assessmentSummary?.coverageTypes || 0)}</span><span class="text-slate-400"> / ${Number(learner.assessmentSummary?.coverageTotal || types.length)}</span><div class="text-[9px] text-slate-400">共 ${Number(learner.assessmentSummary?.count || 0)} 筆</div></td>
        ${types.map(type => `<td class="border-b border-slate-100 p-3">${competencyCell(learner.competencies?.[type.key])}</td>`).join('')}
      </tr>`).join('')}</tbody>
    </table>`;
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('pgy-matrix-status-71');
    if (status) status.textContent = force ? '更新能力矩陣中…' : '讀取能力矩陣中…';
    try {
      const response = await fetch('/api/training-command-center/pgy-matrix', {
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
      if (status) status.textContent = `❌ ${error.message || '無法讀取 PGY 能力矩陣'}`;
    }
  }

  function init() {
    if (!mount()) return;
    load(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
