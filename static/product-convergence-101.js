/* Product Convergence 10.1
 * Presentation-only convergence. Canonical server-side RBAC and existing
 * workspace implementations remain authoritative.
 *
 * The final teacher persona navigation is owned by teacher-persona-isolation-
 * 1014.js. Structural system navigation is owned by workspace-shell-70.js.
 * This layer only adds contextual tools and stable presentation labels; it does
 * not rebuild either navigation tree.
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
  const isTeacherPersona = () => Boolean(window.TeacherWorkspace1014) && persona() !== 'system';

  function ensureTeacherContextTools() {
    if (!isTeacherPersona()) return false;
    const panel = document.getElementById('admin-section-content');
    if (!panel) return false;

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

    const summary = document.getElementById('admin-workspace-summary');
    const now = new URLSearchParams(window.location.search);
    if (summary && now.get('workspace') === 'course-materials' && !now.get('teacherMode')) {
      summary.textContent = '主要工作只保留「教材與課程」與「評量與出題」；媒體、紙本等延伸能力從流程內開啟。';
    }
    return true;
  }

  function ensureTeacherMaterialHistory() {
    if (!isTeacherPersona()) return false;
    const course = document.getElementById('admin-course-workspace');
    const panel = document.getElementById('admin-material-jobs-panel');
    if (!course || !panel) return false;

    panel.dataset.productSection = 'history';
    panel.classList.remove('hidden');
    panel.removeAttribute('aria-hidden');
    if (panel.parentElement !== course) course.appendChild(panel);

    const heading = panel.querySelector('h5');
    const description = panel.querySelector('p');
    const refreshButton = panel.querySelector('button[data-csp-click*="renderMaterialJobs"]');
    if (heading && heading.textContent !== '教材處理紀錄') heading.textContent = '教材處理紀錄';
    if (description) description.textContent = '最近教材的接收、處理、完成與失敗紀錄集中在這裡；需要技術細節時再展開。';
    if (refreshButton && refreshButton.textContent !== '↻ 更新紀錄') refreshButton.textContent = '↻ 更新紀錄';
    return true;
  }

  function existing(id, label = '') {
    const button = document.getElementById(id);
    if (!button || button.disabled || button.classList.contains('hidden')) return null;
    if (label && button.textContent !== label) button.textContent = label;
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
    const allowed = new Set([people, system, worker, maintenance, audit].filter(Boolean).map(button => button.id));

    [...navHost.querySelectorAll('.admin-nav-btn')].forEach(button => {
      if (!allowed.has(button.id)) {
        button.classList.add('hidden');
        button.setAttribute('aria-hidden', 'true');
      }
    });

    const labels = {
      people: '人員與權限',
      operations: '系統健康與維運',
      audit: '安全與稽核',
    };
    Object.entries(labels).forEach(([key, text]) => {
      const label = navHost.querySelector(`[data-admin-nav-group="${key}"] .v580-admin-group-label`);
      if (label && label.textContent !== text) label.textContent = text;
    });

    const note = document.getElementById('system-focus-note-1014');
    if (note) {
      const text = '教材、出題、媒體與紙本輸出屬於教師工作；系統管理只保留人員權限、系統健康維運與稽核。';
      if (note.textContent !== text) note.textContent = text;
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
      else {
        ensureTeacherContextTools();
        ensureTeacherMaterialHistory();
      }
    });
  }

  refresh();
  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => refresh());

  // System modules may insert Worker/maintenance entries asynchronously. The
  // observer is safe for teacher persona because teacher refresh only ensures
  // contextual tools and never rewrites the navigation host.
  const observer = new MutationObserver(() => refresh());
  observer.observe(navHost, {childList: true, subtree: true});

  window.ProductConvergence101 = Object.freeze({
    refresh,
    ensureTeacherContextTools,
    ensureTeacherMaterialHistory,
    convergeSystemNavigation,
  });
})();
