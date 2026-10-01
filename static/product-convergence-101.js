/* Product Convergence 10.1
 * Presentation-only navigation convergence. Canonical server-side RBAC and
 * existing workspace implementations remain authoritative.
 *
 * Goal:
 * - Teacher persona exposes two primary jobs: 教材與課程 / 評量與出題.
 * - Media production and paper export remain available as contextual tools,
 *   not separate top-level workspaces.
 * - System persona groups platform operations under one health/maintenance
 *   surface instead of exposing infrastructure concepts as separate groups.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const params = new URLSearchParams(window.location.search);
  const adminPage = params.get('admin') === '1';
  const surfaceKey = String(R.surface?.key || 'learner');
  const workspace = () => new URLSearchParams(window.location.search).get('workspace') || '';
  const persona = () => new URLSearchParams(window.location.search).get('persona') || '';
  const navHost = document.querySelector('.v580-admin-groups');

  if (!adminPage || !navHost) return;

  const systemWorkspaceNames = new Set(['people', 'system', 'worker', 'maintenance', 'audit']);
  const isSystemPersona = () => surfaceKey === 'system' && (
    persona() === 'system' || (!persona() && systemWorkspaceNames.has(workspace()))
  );
  // TeacherWorkspace1014 is exported only when the existing persona layer has
  // actually activated a teaching surface. This also covers multi-role
  // system_admin + teacher accounts whose global surface key remains `system`.
  const isTeacherPersona = () => Boolean(window.TeacherWorkspace1014) && persona() !== 'system';

  function makeButton(id, label, handler) {
    let button = document.getElementById(id);
    if (!button) {
      button = document.createElement('button');
      button.id = id;
      button.type = 'button';
    }
    button.textContent = label;
    button.className = 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
    button.onclick = handler;
    return button;
  }

  function navGroup(label, buttons, compact = false) {
    const usable = buttons.filter(Boolean);
    if (!usable.length) return null;
    const section = document.createElement('section');
    section.className = `v580-admin-group${compact ? ' compact' : ''}`;
    const heading = document.createElement('span');
    heading.className = 'v580-admin-group-label';
    heading.textContent = label;
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    usable.forEach(button => actions.appendChild(button));
    section.append(heading, actions);
    return section;
  }

  function markPrimary(activeId) {
    navHost.querySelectorAll('.admin-nav-btn').forEach(button => {
      const active = button.id === activeId;
      button.classList.toggle('bg-teal-700', active);
      button.classList.toggle('text-white', active);
      button.classList.toggle('shadow-sm', active);
      button.classList.toggle('bg-slate-100', !active);
      button.classList.toggle('text-slate-600', !active);
    });
  }

  function ensureTeacherContextTools() {
    if (!isTeacherPersona()) return;
    const panel = document.getElementById('admin-section-content');
    if (!panel) return;

    let tools = document.getElementById('teacher-context-tools-101');
    if (!tools) {
      tools = document.createElement('section');
      tools.id = 'teacher-context-tools-101';
      tools.className = 'rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3';
      tools.innerHTML = `
        <div>
          <b class="text-sm text-slate-900">延伸教學工具</b>
          <p class="mt-0.5 text-[11px] text-slate-500">媒體製作與紙本匯出屬於教材流程，不再各自佔一個主導覽。</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button id="teacher-context-media-101" type="button" class="rounded-xl border border-cyan-200 bg-white px-3 py-2 text-xs font-black text-cyan-800">🎙️ AI 媒體製作</button>
          <button id="teacher-context-documents-101" type="button" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-black text-slate-700">📄 紙本文件與匯出</button>
        </div>`;
      panel.insertBefore(tools, panel.firstChild);
    }

    const api = window.TeacherWorkspace1014 || {};
    const media = tools.querySelector('#teacher-context-media-101');
    const documents = tools.querySelector('#teacher-context-documents-101');
    if (media) media.onclick = () => api.openMedia?.();
    if (documents) documents.onclick = () => api.openDocuments?.();
  }

  function convergeTeacherNavigation() {
    if (!isTeacherPersona()) return false;
    const api = window.TeacherWorkspace1014;
    if (!api) return false;

    const desiredIds = ['product-nav-course-101', 'product-nav-assessment-101'];
    const currentIds = [...navHost.querySelectorAll('.admin-nav-btn')].map(button => button.id);
    const alreadyConverged = desiredIds.length === currentIds.length && desiredIds.every((id, index) => currentIds[index] === id);

    if (!alreadyConverged) {
      const group = navGroup('教師工作區', [
        makeButton('product-nav-course-101', '📚 教材與課程', () => api.openCourse?.()),
        makeButton('product-nav-assessment-101', '📝 評量與出題', () => api.openAssessment?.()),
      ]);
      navHost.replaceChildren(group);
    }

    const current = workspace();
    const teacherMode = new URLSearchParams(window.location.search).get('teacherMode') || '';
    markPrimary(current === 'assessment' && !teacherMode ? 'product-nav-assessment-101' : 'product-nav-course-101');
    ensureTeacherContextTools();

    const summary = document.getElementById('admin-workspace-summary');
    if (summary && current === 'course-materials' && !teacherMode) {
      summary.textContent = '主要工作只保留「教材與課程」與「評量與出題」；媒體、紙本等延伸能力從流程內開啟。';
    }
    return true;
  }

  function existing(id, label = '') {
    const button = document.getElementById(id);
    if (!button || button.disabled || button.classList.contains('hidden')) return null;
    if (label) button.textContent = label;
    button.classList.remove('hidden');
    button.removeAttribute('aria-hidden');
    return button;
  }

  function convergeSystemNavigation() {
    if (!isSystemPersona()) return false;

    const people = existing('admin-nav-people', '👥 人員與權限');
    const system = existing('admin-nav-system', '⚙️ 系統與服務');
    const worker = existing('admin-nav-worker', '🖥️ Worker / Job 狀態');
    const maintenance = existing('admin-nav-maintenance', '🛡️ 備份維護');
    const audit = existing('admin-nav-audit', '🔎 稽核紀錄');

    const expected = [people, system, worker, maintenance, audit].filter(Boolean).map(button => button.id);
    const current = [...navHost.querySelectorAll('.admin-nav-btn')].map(button => button.id);
    const labels = [...navHost.querySelectorAll('.v580-admin-group-label')].map(label => label.textContent?.trim());
    const desiredLabels = ['人員與權限', '系統健康與維運', '安全與稽核'].filter((label, index) => index !== 2 || audit);
    const alreadyConverged = expected.length === current.length
      && expected.every((id, index) => current[index] === id)
      && desiredLabels.every(label => labels.includes(label));

    if (alreadyConverged) return true;

    const groups = [
      navGroup('人員與權限', [people], true),
      navGroup('系統健康與維運', [system, worker, maintenance], true),
      navGroup('安全與稽核', [audit], true),
    ].filter(Boolean);
    navHost.replaceChildren(...groups);

    const note = document.getElementById('system-focus-note-1014');
    if (note) {
      note.textContent = '教材、出題、媒體與紙本輸出屬於教師工作；系統管理只保留人員權限、系統健康維運與稽核。';
    }
    return true;
  }

  let refreshQueued = false;
  function refresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    queueMicrotask(() => {
      refreshQueued = false;
      if (isSystemPersona()) convergeSystemNavigation();
      else convergeTeacherNavigation();
    });
  }

  refresh();
  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => refresh());

  const observer = new MutationObserver(() => refresh());
  observer.observe(navHost, {childList: true, subtree: true});

  window.ProductConvergence101 = Object.freeze({
    refresh,
    convergeTeacherNavigation,
    convergeSystemNavigation,
  });
})();
