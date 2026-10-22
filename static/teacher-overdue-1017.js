/* Teacher 未完成名單 (2026-10-17, 2026-10-22 adds 「尚未考核」). Owner of #teacher-overdue-1017.
 * One list across every course this teacher can see (server scope via
 * /api/training-command-center/course-tracking), loaded on demand, with a CSV
 * download for follow-up.  Two views:
 *   pending — 還沒逾期，但考卷尚未通過（未考／待批改／未通過）的學員
 *   overdue — 已過完成期限但還沒完成的學員
 * Plus a 考卷 (course) filter.  Shown on the 評量與追蹤 workspace. */
(function () {
  'use strict';

  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  let courses = [];
  let rows = [];
  let mode = 'pending';
  let courseFilter = '';

  const MODES = {
    pending: {label: '尚未考核（未逾期）', hint: '還沒到期限，但考卷還沒通過的學員：未考、待批改或未通過。', empty: '目前沒有未逾期但尚未考核的學員。', file: '尚未考核名單'},
    overdue: {label: '已逾期', hint: '已過完成期限但還沒完成課程的學員。', empty: '目前沒有逾期未完成的學員。', file: '逾期未完成名單'},
  };

  function teacherPage() {
    return !!document.getElementById('admin-section-quiz');
  }

  function ensure() {
    if (!teacherPage()) return null;
    const host = document.getElementById('admin-section-quiz');
    if (!host) return null;
    let section = document.getElementById('teacher-overdue-1017');
    if (section) return section;
    section = document.createElement('section');
    section.id = 'teacher-overdue-1017';
    section.className = 'card teacher-overdue-pane-1019';
    section.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div><h3 class="font-black text-slate-900">⏰ 未完成名單</h3>
          <p class="text-sm text-slate-500 mt-1" data-overdue-hint></p></div>
        <span class="flex gap-2"><button type="button" class="btn btn-secondary" data-overdue-load>重新整理</button>
          <button type="button" class="btn btn-secondary hidden" data-overdue-csv>下載 CSV</button></span>
      </div>
      <div class="flex flex-wrap items-center gap-2 mt-3">
        <span class="flex gap-1" role="group" aria-label="名單類型">
          <button type="button" class="btn btn-secondary" data-overdue-mode="pending" aria-pressed="true">${MODES.pending.label}</button>
          <button type="button" class="btn btn-secondary" data-overdue-mode="overdue" aria-pressed="false">${MODES.overdue.label}</button>
        </span>
        <label class="text-sm text-slate-500 flex items-center gap-1">考卷
          <select class="border rounded px-2 py-1 text-sm" data-overdue-course><option value="">全部考卷</option></select></label>
      </div>
      <p class="text-sm text-slate-500 mt-2" role="status" data-overdue-status></p>
      <div class="overflow-x-auto" data-overdue-table></div>`;
    const flow = document.getElementById('teacher-assessment-flow-1014');
    host.insertBefore(section, flow && flow.parentElement === host ? flow.nextSibling : host.firstChild);
    section.querySelector('[data-overdue-load]').addEventListener('click', load);
    section.querySelector('[data-overdue-csv]').addEventListener('click', downloadCsv);
    section.querySelectorAll('[data-overdue-mode]').forEach(button => button.addEventListener('click', () => {
      mode = button.getAttribute('data-overdue-mode');
      render();
    }));
    section.querySelector('[data-overdue-course]').addEventListener('change', event => {
      courseFilter = event.target.value;
      render();
    });
    paintMode(section);
    return section;
  }

  const day = value => (value ? String(value).slice(0, 10) : '');

  function examLabel(learner) {
    if (!learner.examRequired) return '不需考試';
    if (learner.examPassed) return '已通過';
    if (!learner.examAttempts) return '未考';
    return learner.examNotPassed ? '未通過' : '待批改';
  }

  function matches(learner) {
    if (mode === 'overdue') return !!learner.overdue;
    // 還沒逾期、課程需要考試、考試還沒通過。
    return !learner.overdue && !!learner.examRequired && !learner.examPassed;
  }

  function paintMode(section) {
    section.querySelectorAll('[data-overdue-mode]').forEach(button => {
      const active = button.getAttribute('data-overdue-mode') === mode;
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
      button.classList.toggle('btn-primary', active);
      button.classList.toggle('btn-secondary', !active);
    });
    section.querySelector('[data-overdue-hint]').textContent = MODES[mode].hint;
  }

  function render() {
    const section = ensure(); if (!section) return;
    paintMode(section);
    const status = section.querySelector('[data-overdue-status]');
    const table = section.querySelector('[data-overdue-table]');
    rows = [];
    courses.forEach(course => {
      if (courseFilter && String(course.courseId) !== courseFilter) return;
      (course.learners || []).forEach(learner => {
        if (!matches(learner)) return;
        rows.push({course: course.title || '', name: learner.name || learner.username || '', empId: learner.empId || '', dueAt: day(learner.dueAt), progress: `${learner.materialsCompleted || 0}/${learner.materialsTotal || 0}`, exam: examLabel(learner)});
      });
    });
    // 期限近的排前面；沒有期限的放最後。
    rows.sort((a, b) => (a.dueAt || '9999').localeCompare(b.dueAt || '9999') || a.course.localeCompare(b.course) || a.name.localeCompare(b.name));
    status.textContent = rows.length ? `共 ${rows.length} 位學員。` : MODES[mode].empty;
    section.querySelector('[data-overdue-csv]').classList.toggle('hidden', !rows.length);
    table.innerHTML = rows.length ? `<table class="w-full text-left mt-2"><thead><tr class="text-sm text-slate-500"><th class="py-1 pr-3">課程／考卷</th><th class="py-1 pr-3">姓名</th><th class="py-1 pr-3">工號</th><th class="py-1 pr-3">期限</th><th class="py-1 pr-3">教材完成</th><th class="py-1">考試</th></tr></thead><tbody>${rows.map(r => `<tr class="border-t border-slate-100"><td class="py-1.5 pr-3">${esc(r.course)}</td><td class="py-1.5 pr-3 font-bold">${esc(r.name)}</td><td class="py-1.5 pr-3">${esc(r.empId)}</td><td class="py-1.5 pr-3">${esc(r.dueAt || '未設定')}</td><td class="py-1.5 pr-3">${esc(r.progress)}</td><td class="py-1.5">${esc(r.exam)}</td></tr>`).join('')}</tbody></table>` : '';
  }

  function fillCourseSelect(section) {
    const select = section.querySelector('[data-overdue-course]');
    const options = courses.map(course => `<option value="${esc(course.courseId)}">${esc(course.title || course.courseId)}</option>`).join('');
    select.innerHTML = `<option value="">全部考卷</option>${options}`;
    if (courseFilter && courses.some(course => String(course.courseId) === courseFilter)) select.value = courseFilter;
    else { courseFilter = ''; select.value = ''; }
  }

  async function load() {
    const section = ensure(); if (!section) return;
    const status = section.querySelector('[data-overdue-status]');
    status.textContent = '讀取中…';
    try {
      const response = await fetch('/api/training-command-center/course-tracking', {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (response.status === 403) { status.textContent = '這份名單需要「指派課程」權限（組長、教學管理者、系統管理者）才看得到。'; return; }
      if (!response.ok) throw new Error(data.error || '名單讀取失敗');
      courses = Array.isArray(data.courses) ? data.courses : [];
      fillCourseSelect(section);
      render();
    } catch (error) {
      status.textContent = `${error.message}，請稍後再試。`;
    }
  }

  function downloadCsv() {
    const cell = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const lines = [['課程／考卷', '姓名', '工號', '期限', '教材完成', '考試'].map(cell).join(',')]
      .concat(rows.map(r => [r.course, r.name, r.empId, r.dueAt, r.progress, r.exam].map(cell).join(',')));
    const blob = new Blob(['﻿' + lines.join('\r\n')], {type: 'text/csv;charset=utf-8'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${MODES[mode].file}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  window.addEventListener('teacher:admin-rendered', ensure);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ensure, {once: true});
  else ensure();
  // Opening the tab loads the list once; 「重新整理」 reloads it.
  let loadedOnce = false;
  async function open(nextMode) {
    if (nextMode && MODES[nextMode]) mode = nextMode;
    ensure();
    if (!loadedOnce) { loadedOnce = true; await load(); } else render();
  }
  window.TeacherOverdue1017 = Object.freeze({load, open});
})();
