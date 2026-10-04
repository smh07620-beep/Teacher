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

  const selectorEscape = value => {
    const text = String(value ?? '');
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(text);
    return text.replace(/[^A-Za-z0-9_-]/g, char => `\\${char}`);
  };

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
  let latestItems = [];

  function currentContext() {
    const now = new URLSearchParams(window.location.search);
    const workspace = now.get('workspace') || '';
    const teacherMode = now.get('teacherMode') || '';
    if (teacherMode === 'media' || teacherMode === 'documents') return 'contextual-tool';
    if (['assessment', 'results', 'teacher'].includes(workspace) || teacherMode === 'scoring' || teacherMode === 'pgy') return 'assessment';
    return 'course';
  }

  function hostPanel() {
    const context = currentContext();
    if (context === 'contextual-tool') return null;
    if (context === 'assessment') {
      const workspace = new URLSearchParams(window.location.search).get('workspace') || '';
      return document.getElementById(workspace === 'assessment' ? 'admin-section-quiz' : 'admin-section-results');
    }
    return document.getElementById('admin-section-content');
  }

  function ensureTeacherHomeIntro(panel, section) {
    if (!panel || currentContext() !== 'course') return;
    let intro = document.getElementById('teacher-home-intro-1024');
    if (!intro) {
      intro = document.createElement('section');
      intro.id = 'teacher-home-intro-1024';
      intro.className = 'teacher-home-intro-1024 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm';
      intro.innerHTML = `
        <div class="teacher-home-intro-copy">
          <p class="text-[11px] font-black tracking-[.16em] text-teal-700">TEACHER DESK</p>
          <h3 class="mt-1 text-xl font-black text-slate-950">今天的教學工作</h3>
          <p class="mt-1 text-sm text-slate-600">先完成待處理事項，再進入主要工作。系統管理與學員功能維持獨立，不混在教師日常流程。</p>
        </div>
        <div class="teacher-home-jobs-1024 mt-4 grid gap-2 sm:grid-cols-3">
          <button type="button" data-teacher-home-job="course" class="teacher-home-job-1024"><b>📚 教材與課程</b><span>課程、教材、版本與媒體工具</span></button>
          <button type="button" data-teacher-home-job="assessment" class="teacher-home-job-1024"><b>📝 評量與出題</b><span>題庫、考卷、待批改與紀錄</span></button>
          <button type="button" data-teacher-home-job="documents" class="teacher-home-job-1024"><b>📄 紙本文件</b><span>正式紀錄、Word 匯出與留存</span></button>
        </div>`;
      intro.querySelector('[data-teacher-home-job="course"]')?.addEventListener('click', () => window.TeacherWorkspace1014?.openCourse?.());
      intro.querySelector('[data-teacher-home-job="assessment"]')?.addEventListener('click', () => window.TeacherWorkspace1014?.openAssessment?.());
      intro.querySelector('[data-teacher-home-job="documents"]')?.addEventListener('click', () => window.TeacherWorkspace1014?.openDocuments?.());
    }
    if (intro.parentElement !== panel) {
      const anchor = section?.parentElement === panel ? section : panel.firstChild;
      panel.insertBefore(intro, anchor || null);
    }
  }

  function ensureSection() {
    const panel = hostPanel();
    let section = document.getElementById('teacher-action-queue-1024');
    if (!panel) {
      section?.classList.add('hidden');
      return null;
    }
    if (!section) {
      section = document.createElement('section');
      section.id = 'teacher-action-queue-1024';
      section.className = 'rounded-2xl border border-slate-200 bg-white p-4 shadow-sm';
    }
    section.classList.remove('hidden');
    section.dataset.productSection = 'needs-action';
    ensureTeacherHomeIntro(panel, section);
    if (section.parentElement !== panel) {
      const context = currentContext();
      const anchor = context === 'assessment'
        ? (document.getElementById('teacher-review-shortcut-1014') || panel.firstChild)
        : (document.getElementById('teacher-context-tools-101') || panel.firstChild);
      const safeAnchor = anchor?.parentElement === panel ? anchor : panel.firstChild;
      panel.insertBefore(section, safeAnchor || null);
    }
    return section;
  }

  function actionButton(item, index) {
    return `<button type="button" data-teacher-action-index="${index}" data-teacher-action-kind="${escapeHtml(item.kind || '')}" data-teacher-action-id="${escapeHtml(item.id || '')}" class="shrink-0 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60">${escapeHtml(item.actionLabel || '前往處理')}</button>`;
  }

  function itemCard(item, index) {
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
      ${actionButton(item, index)}
    </article>`;
  }

  function pulseTarget(node) {
    if (!node) return false;
    node.scrollIntoView?.({behavior: 'smooth', block: 'center'});
    const before = node.style.boxShadow;
    node.style.boxShadow = '0 0 0 3px rgba(14, 165, 233, .28)';
    setTimeout(() => { node.style.boxShadow = before; }, 2600);
    return true;
  }

  function setCourseScope(item) {
    const area = document.getElementById('wizard-area');
    const group = document.getElementById('wizard-group');
    if (area && item.area && [...area.options].some(option => option.value === item.area)) area.value = item.area;
    if (group && item.group && [...group.options].some(option => option.value === item.group)) group.value = item.group;
  }

  async function refreshCourseHub(item) {
    const api = window.TeacherWorkspace1014 || {};
    await api.openCourse?.();
    setCourseScope(item);
    if (typeof window.renderAdminCourseMaterialHub === 'function') {
      await window.renderAdminCourseMaterialHub(true);
      const hub = document.getElementById('admin-course-material-hub');
      if (hub?._adminCourseMaterialRefresh) await hub._adminCourseMaterialRefresh;
    }
  }

  async function openReview(item) {
    await window.switchAdminWorkspace?.('teacher', true);
    await window.switchTeacherMode?.('scoring');
    if (typeof window.renderAdminTable === 'function') await window.renderAdminTable();
    const records = typeof adminRecords !== 'undefined' && Array.isArray(adminRecords) ? adminRecords : [];
    const index = records.findIndex(record => String(record?.id || '') === String(item.resourceId || item.id || ''));
    if (index >= 0 && typeof window.openEssayReview === 'function') {
      window.openEssayReview(index);
      pulseTarget(document.getElementById('essay-review-panel'));
      return;
    }
    const reviewShortcut = document.getElementById('teacher-open-review-1014');
    pulseTarget(reviewShortcut || document.getElementById('admin-table-body'));
  }

  async function openMaterialFailure(item) {
    const api = window.TeacherWorkspace1014 || {};
    await api.openCourse?.();
    const wanted = String(item.resourceId || item.id || '');

    // This queue is only a projection. The mutation stays in the canonical
    // material-job owner, but a retained R2 source should make the visible
    // "重新處理" action actually invoke that owner instead of only navigating.
    if (item.sourceRetained && wanted && typeof window.retryMaterialJob === 'function') {
      const retried = await window.retryMaterialJob(wanted);
      if (retried !== false) {
        await refresh();
        return;
      }
    }

    if (typeof window.renderMaterialJobs === 'function') await window.renderMaterialJobs(true);
    const host = document.getElementById('admin-material-jobs-list');
    const diagnostic = [...(host?.querySelectorAll('details') || [])].find(node => node.textContent?.includes(wanted));
    const card = diagnostic?.closest('.rounded-xl.border.bg-white') || diagnostic?.parentElement || host;
    pulseTarget(card);
    diagnostic?.setAttribute('open', '');
  }

  async function openDueAssignment(item) {
    await refreshCourseHub(item);
    const courseId = String(item.courseId || item.resourceId || '');
    const button = document.querySelector(`[data-learning-assign-course="${selectorEscape(courseId)}"]`);
    if (button) {
      pulseTarget(button.closest('details') || button);
      button.click();
      return;
    }
    pulseTarget(document.getElementById('admin-course-material-hub'));
  }

  async function openDraft(item) {
    await refreshCourseHub(item);
    const courseId = String(item.courseId || item.resourceId || item.id || '');
    if (courseId && typeof window.teachingEditCourse === 'function') {
      window.teachingEditCourse(courseId);
      return;
    }
    const card = document.querySelector(`[data-course-id="${selectorEscape(courseId)}"]`);
    pulseTarget(card || document.getElementById('admin-course-material-hub'));
  }

  async function openAction(item) {
    if (!item) return;
    if (item.kind === 'review') return openReview(item);
    if (item.kind === 'material_failure') return openMaterialFailure(item);
    if (item.kind === 'due') return openDueAssignment(item);
    if (item.kind === 'draft') return openDraft(item);
    await window.TeacherWorkspace1014?.openCourse?.();
  }

  function bindActions(section) {
    section.querySelectorAll('[data-teacher-action-index]').forEach(button => {
      button.addEventListener('click', async () => {
        const item = latestItems[Number(button.dataset.teacherActionIndex)];
        if (!item || button.disabled) return;
        const original = button.textContent;
        button.disabled = true;
        button.textContent = item.kind === 'material_failure' && item.sourceRetained ? '重新排隊中…' : '開啟中…';
        try {
          await openAction(item);
        } catch (error) {
          console.error('teacher action queue navigation failed', error);
          button.textContent = '開啟失敗，請重試';
          setTimeout(() => { button.textContent = original; }, 1800);
        } finally {
          button.disabled = false;
          if (button.textContent === '開啟中…' || button.textContent === '重新排隊中…') button.textContent = original;
        }
      });
    });
  }

  function render(section, data) {
    const allTeacherItems = (Array.isArray(data.items) ? data.items : []).filter(item => item.domain !== 'pgy');
    const context = currentContext();
    const teacherItems = context === 'assessment'
      ? allTeacherItems.filter(item => item.kind === 'review')
      : allTeacherItems.filter(item => item.kind !== 'review');
    latestItems = teacherItems.slice(0, 12);
    const counts = data.counts || {};
    section.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <div class="flex items-center gap-2"><h4 class="text-base font-black text-slate-950">需要我處理</h4><span class="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-black text-white">${teacherItems.length}</span></div>
          <p class="mt-1 text-xs text-slate-500">待批改、教材異常、截止提醒與未發布草稿集中在這裡；「前往處理」會直接定位到對應工作。</p>
        </div>
        <div class="flex flex-wrap gap-1.5 text-[10px] font-bold text-slate-600">
          <span class="rounded-full bg-indigo-50 px-2 py-1">待批改 ${Number(counts.review || 0)}</span>
          <span class="rounded-full bg-rose-50 px-2 py-1">教材 ${Number(counts.materialFailure || 0)}</span>
          <span class="rounded-full bg-amber-50 px-2 py-1">截止 ${Number(counts.due || 0)}</span>
          <span class="rounded-full bg-slate-100 px-2 py-1">草稿 ${Number(counts.draft || 0)}</span>
        </div>
      </div>
      <div class="mt-3 space-y-2" data-teacher-action-items>
        ${teacherItems.length ? latestItems.map(itemCard).join('') : '<div class="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-4 text-sm font-bold text-emerald-800">✓ 目前沒有需要你處理的項目。</div>'}
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

  window.TeacherActionQueue1024 = Object.freeze({refresh, openAction});
})();
