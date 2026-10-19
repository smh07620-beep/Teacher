/* Teacher 逾期未完成名單 (2026-10-17). Owner of #teacher-overdue-1017.
 * One list across every course this teacher can see (server scope via
 * /api/training-command-center/course-tracking), loaded on demand, with a CSV
 * download for follow-up.  Shown on the 評量與追蹤 workspace. */
(function () {
  'use strict';

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let rows = [];

  // Any back-office page that has the 評量與追蹤 results panel (/teach, /admin, ?admin=1).
  // The server scopes the list to the teacher's own courses; learners never get this panel.
  function teacherPage() {
    return !!document.getElementById('admin-section-results');
  }

  function ensure() {
    if (!teacherPage()) return null;
    const host = document.getElementById('admin-section-results');
    if (!host) return null;
    let section = document.getElementById('teacher-overdue-1017');
    if (section) return section;
    section = document.createElement('section');
    section.id = 'teacher-overdue-1017';
    section.className = 'card';
    section.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div><h3 class="font-black text-slate-900">⏰ 逾期未完成名單</h3>
          <p class="text-sm text-slate-500 mt-1">你負責的課程中，已過完成期限但還沒完成的學員。</p></div>
        <span class="flex gap-2"><button type="button" class="btn btn-secondary" data-overdue-load>載入名單</button>
          <button type="button" class="btn btn-secondary hidden" data-overdue-csv>下載 CSV</button></span>
      </div>
      <p class="text-sm text-slate-500 mt-2" role="status" data-overdue-status></p>
      <div class="overflow-x-auto" data-overdue-table></div>`;
    host.insertBefore(section, host.firstChild);
    section.querySelector('[data-overdue-load]').addEventListener('click', load);
    section.querySelector('[data-overdue-csv]').addEventListener('click', downloadCsv);
    return section;
  }

  const day = value => (value ? String(value).slice(0, 10) : '');

  async function load() {
    const section = ensure(); if (!section) return;
    const status = section.querySelector('[data-overdue-status]');
    const table = section.querySelector('[data-overdue-table]');
    status.textContent = '讀取中…';
    try {
      const response = await fetch('/api/training-command-center/course-tracking', {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '名單讀取失敗');
      rows = [];
      (data.courses || []).forEach(course => (course.learners || []).forEach(learner => {
        if (learner.overdue) rows.push({course: course.title || '', name: learner.name || learner.username || '', empId: learner.empId || '', dueAt: day(learner.dueAt), progress: `${learner.materialsCompleted || 0}/${learner.materialsTotal || 0}`, exam: learner.examRequired ? (learner.examPassed ? '已通過' : (learner.examAttempts ? '未通過' : '未考')) : '不需考試'});
      }));
      rows.sort((a, b) => a.dueAt.localeCompare(b.dueAt) || a.course.localeCompare(b.course));
      status.textContent = rows.length ? `共 ${rows.length} 位學員逾期未完成。` : '目前沒有逾期未完成的學員。';
      section.querySelector('[data-overdue-csv]').classList.toggle('hidden', !rows.length);
      table.innerHTML = rows.length ? `<table class="w-full text-left mt-2"><thead><tr class="text-sm text-slate-500"><th class="py-1 pr-3">課程</th><th class="py-1 pr-3">姓名</th><th class="py-1 pr-3">工號</th><th class="py-1 pr-3">期限</th><th class="py-1 pr-3">教材完成</th><th class="py-1">考試</th></tr></thead><tbody>${rows.map(r => `<tr class="border-t border-slate-100"><td class="py-1.5 pr-3">${esc(r.course)}</td><td class="py-1.5 pr-3 font-bold">${esc(r.name)}</td><td class="py-1.5 pr-3">${esc(r.empId)}</td><td class="py-1.5 pr-3">${esc(r.dueAt)}</td><td class="py-1.5 pr-3">${esc(r.progress)}</td><td class="py-1.5">${esc(r.exam)}</td></tr>`).join('')}</tbody></table>` : '';
    } catch (error) {
      status.textContent = `${error.message}，請稍後再試。`;
    }
  }

  function downloadCsv() {
    const cell = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [['課程', '姓名', '工號', '期限', '教材完成', '考試'].map(cell).join(',')]
      .concat(rows.map(r => [r.course, r.name, r.empId, r.dueAt, r.progress, r.exam].map(cell).join(',')));
    const blob = new Blob(['﻿' + lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `逾期未完成名單-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  window.addEventListener('teacher:admin-rendered', ensure);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure, {once: true});
  else ensure();
  window.TeacherOverdue1017 = Object.freeze({load});
})();
