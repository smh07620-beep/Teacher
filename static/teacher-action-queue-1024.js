/* Teacher P1 convergence: one scoped "需要我處理" queue.
 * Read-only projection. Mutations remain in their canonical workspaces and
 * server-side RBAC/scope remains authoritative.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const params = new URLSearchParams(window.location.search);
  const adminPage = params.get('admin') === '1';
  const teacherPersona = adminPage && params.get('persona') !== 'system' && Boolean(window.TeacherWorkspace1014?.canTeach);
  if (!teacherPersona) return;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  const kindMeta = kind => ({
    review: ['✍️', '待批改', 'border-indigo-200 bg-indigo-50 text-indigo-800'],
    material_failure: ['🛠️', '教材需要處理', 'border-rose-200 bg-rose-50 text-rose-800'],
    due: ['⏰', '截止提醒', 'border-amber-200 bg-amber-50 text-amber-800'],
    draft: ['📝', '未發布草稿', 'border-slate-200 bg-slate-50 text-slate-700'],
  }[kind] || ['•', '待處理', 'border-slate-200 bg-slate-50 text-slate-700']);

  const formatWhen = value => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  };

  let loading = false;

  function hostPanel() {
    return document.getElementById('admin-section-content');
  }

  function ensureSection() {
    const panel = hostPanel();
    if (!panel) return null;
    let section = document.getElementById('teacher-action-queue-1024');
    if (section) return section;
    section = document.createElement('section');
    section.id = 'teacher-action-queue-1024';
    section.className = 'rounded-2xl border border-slate-200 bg-white p-4 shadow-sm';
    const contextTools = document.getElementById('teacher-context-tools-101');
    if (contextTools?.parentElement === panel) panel.insertBefore(section, contextTools);
    else panel.insertBefore(section, panel.firstChild);
    return section;
  }

  function actionButton(item) {
    return `<button type="button" data-teacher-action-kind="${escapeHtml(item.kind || '')}" data-teacher-action-id="${escapeHtml(item.id || '')}" class="shrink-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50">${escapeHtml(item.actionLabel || '前往處理')}</button>`;
  }

  function itemCard(item) {
    const [icon, fallbackLabel, classes] = kindMeta(item.kind);
    const due = item.dueAt ? `<div class="mt-1 text-[11px] ${item.overdue ? 'font-bold text-rose-700' : 'text-slate-500'}">${item.overdue ? '已逾期：' : '截止：'}${escapeHtml(formatWhen(item.dueAt))}</div>` : '';
    const retained = item.sourceRetained ? '<div class="mt-1 text-[11px] font-bold text-violet-700">☁ 原始檔仍安全保留，不必重新上傳</div>' : '';
    return `<article class="rounded-xl border border-slate-200 bg-slate-50/40 p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <span class="inline-flex rounded-full border px-2 py-1 text-[10px] font-black ${classes}">${icon} ${escapeHtml(item.statusLabel || fallbackLabel)}</span>
          <b class="text-sm text-slate-900 break-words">${escapeHtml(item.title || '待處理項目')}</b>
        </div>
        ${item.detail ? `<p class="mt-1 text-xs text-slate-600 break-words">${escapeHtml(item.detail)}</p>` : ''}
        ${due}${retained}
      </div>
      ${actionButton(item)}
    </article>`;
  }

  function bindActions(section) {
    section.querySelectorAll('[data-teacher-action-kind]').forEach(button => {
      button.addEventListener('click', async () => {
        const kind = button.dataset.teacherActionKind || '';
        const api = window.TeacherWorkspace1014 || {};
        if (kind === 'review') {
          await api.openAssessment?.();
          const reviewShortcut = document.getElementById('teacher-open-review-1014');
          reviewShortcut?.focus();
          reviewShortcut?.scrollIntoView({behavior: 'smooth', block: 'center'});
          return;
        }
        await api.openCourse?.();
        const target = document.getElementById('admin-section-content');
        target?.scrollIntoView({behavior: 'smooth', block: 'start'});
      });
    });
  }

  function render(section, data) {
    const teacherItems = (Array.isArray(data.items) ? data.items : []).filter(item => item.domain !== 'pgy');
    const counts = data.counts || {};
    section.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <div class="flex items-center gap-2"><h4 class="text-base font-black text-slate-950">需要我處理</h4><span class="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-black text-white">${teacherItems.length}</span></div>
          <p class="mt-1 text-xs text-slate-500">待批改、教材異常、截止提醒與未發布草稿集中在這裡；完成後會自動從清單消失。</p>
        </div>
        <div class="flex flex-wrap gap-1.5 text-[10px] font-bold text-slate-600">
          <span class="rounded-full bg-indigo-50 px-2 py-1">待批改 ${Number(counts.review || 0)}</span>
          <span class="rounded-full bg-rose-50 px-2 py-1">教材 ${Number(counts.materialFailure || 0)}</span>
          <span class="rounded-full bg-amber-50 px-2 py-1">截止 ${Number(counts.due || 0)}</span>
          <span class="rounded-full bg-slate-100 px-2 py-1">草稿 ${Number(counts.draft || 0)}</span>
        </div>
      </div>
      <div class="mt-3 space-y-2" data-teacher-action-items>
        ${teacherItems.length ? teacherItems.slice(0, 12).map(itemCard).join('') : '<div class="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-4 text-sm font-bold text-emerald-800">✓ 目前沒有需要你處理的項目。</div>'}
      </div>
      ${teacherItems.length > 12 ? `<div class="mt-2 text-[11px] text-slate-500">另有 ${teacherItems.length - 12} 筆項目；完成目前工作後清單會自動收斂。</div>` : ''}`;
    bindActions(section);
  }

  async function refresh() {
    if (loading) return;
    const section = ensureSection();
    if (!section || section.classList.contains('hidden')) return;
    loading = true;
    section.innerHTML = '<div class="text-sm text-slate-500">正在整理需要你處理的項目…</div>';
    try {
      const response = await fetch('/api/training-command-center', {cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '待辦讀取失敗');
      render(section, data);
    } catch (error) {
      section.innerHTML = `<div class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"><b>待辦暫時讀取失敗</b><div class="mt-1 text-xs">${escapeHtml(error.message || '請重新整理後再試。')}</div><button type="button" data-teacher-action-retry class="mt-2 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-black">重新整理</button></div>`;
      section.querySelector('[data-teacher-action-retry]')?.addEventListener('click', () => refresh());
    } finally {
      loading = false;
    }
  }

  refresh();
  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => {
    if (new URLSearchParams(window.location.search).get('persona') !== 'system') refresh();
  });

  window.TeacherActionQueue1024 = Object.freeze({refresh});
})();
