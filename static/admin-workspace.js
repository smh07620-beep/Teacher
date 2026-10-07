/* Phase 3K/3L: admin workspace shell / section router.
 *
 * This module intentionally loads immediately after the legacy system-admin.js
 * bundle and before RBAC/workspace wrappers. Teacher/results mode state is
 * supplied by admin-results-workspace.js instead of the legacy router.
 */
(() => {
  'use strict';

  // Names, aliases, areas and URLs come from workspace-routes-1007.js.
  const ROUTES = window.AppWorkspaceRoutes;
  const state = {
    workspace: ROUTES.DEFAULT_WORKSPACE,
    section: 'content',
    loaded: {content:false, quiz:false, word:false, pgy:false, results:false}
  };
  const workspaceHandlers = new Map();
  const workspaceGuards = [];
  const beforeWorkspaceHooks = [];
  const afterWorkspaceHooks = [];
  const modalOpenOverrides = [];
  const modalGuards = [];
  const afterModalHooks = [];
  const PAGE_MODE_PARAM = 'admin';
  const SYSTEM_WORKSPACES = new Set(ROUTES.systemNames());
  const DEFERRED_EXTENSION_WORKSPACES = new Set(['worker','maintenance','audit']);
  function isPageMode() {
    return new URLSearchParams(window.location.search).get(PAGE_MODE_PARAM) === '1';
  }

  function workspaceUrl(workspace = state.workspace || ROUTES.DEFAULT_WORKSPACE) {
    const canonical = normalizeWorkspace(String(workspace || ROUTES.DEFAULT_WORKSPACE));
    const url = new URL(window.location.href);
    url.searchParams.set(PAGE_MODE_PARAM, '1');
    url.searchParams.set('workspace', String(workspace || canonical));
    if (SYSTEM_WORKSPACES.has(canonical)) {
      url.searchParams.set('persona', 'system');
      url.searchParams.delete('teacherMode');
    }
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function learningUrl() {
    const url = new URL(window.location.href);
    url.searchParams.delete(PAGE_MODE_PARAM);
    url.searchParams.delete('workspace');
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function syncPageModeClass(active = isPageMode()) {
    document.body?.classList.toggle('admin-page-mode', Boolean(active));
    const modal = document.getElementById('admin-modal');
    if (modal) modal.dataset.pageMode = active ? '1' : '0';
  }

  function syncWorkspaceUrl(workspace) {
    if (!isPageMode() || !window.history?.replaceState) return;
    window.history.replaceState(window.history.state, '', workspaceUrl(workspace));
  }

  function addHook(list, handler) {
    if (typeof handler !== 'function') return () => {};
    list.push(handler);
    return () => {
      const index = list.indexOf(handler);
      if (index >= 0) list.splice(index, 1);
    };
  }

  function registerWorkspace(name, handler) {
    const key = String(name || '').trim();
    if (!key || typeof handler !== 'function') return () => {};
    workspaceHandlers.set(key, handler);
    return () => workspaceHandlers.delete(key);
  }

  async function resolveWorkspaceHandler(requested, workspace) {
    let handler = workspaceHandlers.get(requested) || workspaceHandlers.get(workspace);
    if (handler || !DEFERRED_EXTENSION_WORKSPACES.has(workspace)) return handler || null;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 25));
      handler = workspaceHandlers.get(requested) || workspaceHandlers.get(workspace);
      if (handler) return handler;
    }
    return null;
  }

  function normalizeWorkspace(name) {
    // Aliases (courses, questions, exams, scoring, pgy...) live in the route registry.
    return ROUTES.normalize(name);
  }

  function paintWorkspaceNav(name) {
    name = normalizeWorkspace(name);
    document.querySelectorAll('.admin-nav-btn').forEach(button => {
      const idWorkspace = button.id?.startsWith('admin-nav-') ? button.id.slice('admin-nav-'.length) : '';
      const buttonWorkspace = normalizeWorkspace(button.dataset.adminWorkspace || idWorkspace);
      const active = buttonWorkspace === name;
      button.classList.toggle('bg-teal-700', active);
      button.classList.toggle('text-white', active);
      button.classList.toggle('shadow-sm', active);
      button.classList.toggle('bg-slate-100', !active);
      button.classList.toggle('text-slate-600', !active);
      button.classList.toggle('hover:bg-slate-200', !active);
      button.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  function paintWorkspaceHeader(name) {
    const key = normalizeWorkspace(name);
    const meta = ROUTES.has(key)
      ? ROUTES.get(key)
      : {icon:'⚙️', title:'檢驗科教學平台｜教學管理', summary:'依工作目的分區：建立內容、執行評量、維護平台。'};
    const icon = document.getElementById('admin-workspace-icon');
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    if (icon) icon.textContent = meta.icon;
    if (title) title.textContent = meta.title;
    // Eleven internal workspaces, four product areas: always say which area
    // (教學 / 評量 / 系統管理) the current workspace belongs to.
    const area = ROUTES.has(key) ? ROUTES.areaLabel(key) : '';
    if (summary) summary.textContent = area ? `${area}｜${meta.summary}` : meta.summary;
    const modal = document.getElementById('admin-modal');
    if (modal) modal.dataset.area = area ? ROUTES.areaOf(key) : '';
  }

  function syncSectionChrome(name) {
    state.section = name || '';
    const actions = document.getElementById('exam-settings-actions');
    if (actions) actions.classList.toggle('hidden', name !== 'exam-settings');
    const teacherNav = document.getElementById('admin-teacher-subnav');
    if (teacherNav) teacherNav.classList.toggle('hidden', state.workspace !== 'teacher');
    const modal = document.getElementById('admin-modal');
    if (modal) {
      modal.dataset.workspace = state.workspace || '';
      modal.dataset.section = state.section;
    }
  }

  async function switchSection(name, force=false) {
    const sectionId = `admin-section-${name}`;
    document.querySelectorAll('.admin-section-panel').forEach(item => {
      item.classList.toggle('hidden', item.id !== sectionId);
    });
    syncSectionChrome(name);

    if (name === 'exam-settings' || name === 'people' || name === 'system') return;
    if (!force && state.loaded[name]) return;
    state.loaded[name] = true;

    if (name === 'content') {
      // RC 7.10: the daily course/material hub paints progressively. Do not
      // wait for the legacy hidden material list or per-material search-index
      // probes before allowing the workspace to open.
      const jobs = [
        Promise.resolve().then(() => window.renderAdminCourseMaterialHub?.(force)),
        Promise.resolve().then(() => window.renderAdminCourses?.(force)),
        Promise.resolve().then(() => window.refreshAdminMaterialCategoryOptions?.())
      ];
      void Promise.allSettled(jobs);
      return;
    }
    if (name === 'quiz') {
      // The assessment shell should become usable immediately; the category
      // renderer already knows how to paint cache/skeleton state while its API
      // request finishes. Callers that need fresh category DOM explicitly call
      // renderAdminQuizCategories again after setting their scope.
      void Promise.resolve().then(() => window.renderAdminQuizCategories?.(force));
      return;
    }
    if (name === 'word') await window.renderAdminDocTemplates?.();
    if (name === 'pgy') {
      await Promise.allSettled([
        Promise.resolve(window.renderAdminPgyTemplates?.()),
        Promise.resolve(window.renderAdminPgyAssessments?.())
      ]);
    }
    if (name === 'results') await window.renderAdminTable?.();
  }

  async function switchCoreWorkspace({requested, workspace:name, force}) {
    state.workspace = name;
    paintWorkspaceNav(name);

    if (name === 'course-materials') {
      await switchSection('content', force);
      document.getElementById('admin-course-workspace')?.classList.remove('hidden');
      const materialExecutor = document.getElementById('admin-material-workspace');
      materialExecutor?.classList.add('hidden');
      materialExecutor?.setAttribute('aria-hidden', 'true');
      document.getElementById('admin-material-advanced')?.classList.remove('hidden');
      // RC 7.5 mobile stability: the canonical upload executor stays mounted but is never promoted into the daily workspace.
      // Storage/worker probes remain intentionally deferred until their panels open.
      return;
    }
    if (name === 'assessment') {
      await switchSection('quiz', force);
      window.updateQuizWorkspacePresentation?.();
      return;
    }

    if (name === 'teacher') {
      if (requested === 'pgy') return switchSection('pgy', true);
      return switchSection('results', true);
    }
    if (name === 'results') return switchSection('results', force || true);
    if (name === 'compliance') {
      await switchSection('compliance', true);
      await window.renderTrainingCompliance?.(force);
      return;
    }

    if (name === 'word') return switchSection('word', force);
    if (name === 'people') {
      await switchSection('people', true);
      window.ensureAdminUserCreatePanel?.();
      await window.renderAdminPeople?.(force);
      window.ensureAdminUserCreatePanel?.();
      return;
    }
    if (name === 'system') {
      await switchSection('system', true);
      window.mountSystemAnnouncementCard?.();
      await Promise.all([
        Promise.resolve(window.renderAdminSystemStatus?.(force)),
        Promise.resolve(window.renderAdminAnnouncements?.('system'))
      ]);
    }
  }

  async function switchWorkspace(name, force=false) {
    const requested = String(name || '');
    const workspace = normalizeWorkspace(requested);
    if (isPageMode() && SYSTEM_WORKSPACES.has(workspace)) {
      const currentPersona = new URLSearchParams(window.location.search).get('persona') || '';
      if (currentPersona !== 'system') {
        window.location.assign(workspaceUrl(requested || workspace));
        return true;
      }
    }
    const context = {requested, workspace, force:Boolean(force), switchSection};
    for (const hook of beforeWorkspaceHooks) await hook(context);
    for (const guard of workspaceGuards) {
      if (await guard(context) === false) return false;
    }
    const extension = await resolveWorkspaceHandler(requested, workspace);
    if (!extension && DEFERRED_EXTENSION_WORKSPACES.has(workspace)) {
      const status = document.getElementById('admin-workspace-status');
      if (status) status.textContent = '工作區元件尚未完成載入，請重新整理後再試。';
      return false;
    }
    state.workspace = workspace;
    paintWorkspaceNav(workspace);
    paintWorkspaceHeader(workspace);
    const modal = document.getElementById('admin-modal');
    if (modal) modal.dataset.workspace = workspace;
    // Keep the requested deep-link stable before slower workspace renderers run.
    // This prevents a valid system workspace URL from briefly falling back to
    // course-materials while account/job data is still loading.
    syncWorkspaceUrl(requested || workspace);
    const result = extension
      ? await extension(context)
      : await switchCoreWorkspace(context);
    for (const hook of afterWorkspaceHooks) await hook({...context, result});
    return result;
  }

  async function toggleCoreModal(show) {
    const modal = document.getElementById('admin-modal');
    if (!modal) return false;
    if (show) {
      if (!isPageMode()) {
        window.location.assign(workspaceUrl(state.workspace || ROUTES.DEFAULT_WORKSPACE));
        return true;
      }
      syncPageModeClass(true);
      window.populateAdminGroupSelects?.();
      const materialSelect = document.getElementById('admin-material-group');
      const quizSelect = document.getElementById('admin-quiz-group');
      if (materialSelect) materialSelect.value = window.currentGroupKey || materialSelect.value;
      if (quizSelect) quizSelect.value = window.currentGroupKey || quizSelect.value;
      modal.classList.remove('hidden');
      const requestedWorkspace = new URLSearchParams(window.location.search).get('workspace');
      await window.switchAdminWorkspace?.(requestedWorkspace || state.workspace || ROUTES.DEFAULT_WORKSPACE, false);
      return true;
    }
    if (isPageMode()) {
      window.location.assign(learningUrl());
      return true;
    }
    modal.classList.add('hidden');
    return true;
  }

  async function toggleModal(show) {
    const context = {show:Boolean(show)};
    for (const guard of modalGuards) {
      if (await guard(context) === false) return false;
    }
    if (context.show) {
      for (const override of modalOpenOverrides) {
        const outcome = await override(context);
        if (outcome?.handled) {
          for (const hook of afterModalHooks) await hook({...context, result:outcome.result});
          return outcome.result;
        }
      }
    }
    const result = await toggleCoreModal(context.show);
    for (const hook of afterModalHooks) await hook({...context, result});
    return result;
  }

  async function openWorkspace(name) {
    if (!isPageMode()) {
      window.location.assign(workspaceUrl(name || ROUTES.DEFAULT_WORKSPACE));
      return true;
    }
    const opened = await window.toggleAdminModal?.(true);
    if (opened === false) return false;
    return window.switchAdminWorkspace?.(name, true);
  }

  window.normalizeAdminWorkspace = normalizeWorkspace;
  window.paintAdminWorkspaceNav = paintWorkspaceNav;
  window.paintAdminWorkspaceHeader = paintWorkspaceHeader;
  window.syncAdminSectionChrome = syncSectionChrome;
  window.switchAdminSection = switchSection;
  window.switchAdminWorkspace = switchWorkspace;
  window.toggleAdminModal = toggleModal;
  window.openAdminWorkspace = openWorkspace;
  window.openTeacherAssessment = () => openWorkspace('teacher');
  window.isAdminWorkspacePage = isPageMode;
  window.adminWorkspaceLearningUrl = learningUrl;
  window.AdminWorkspaceShell = Object.freeze({
    registerWorkspace,
    addWorkspaceGuard: handler => addHook(workspaceGuards, handler),
    addBeforeWorkspace: handler => addHook(beforeWorkspaceHooks, handler),
    addAfterWorkspace: handler => addHook(afterWorkspaceHooks, handler),
    addModalOpenOverride: handler => addHook(modalOpenOverrides, handler),
    addModalGuard: handler => addHook(modalGuards, handler),
    addAfterModal: handler => addHook(afterModalHooks, handler),
    hasWorkspace: name => workspaceHandlers.has(String(name || '')),
    isPageMode,
    workspaceUrl,
    learningUrl,
    getState: () => ({workspace:state.workspace, section:state.section, loaded:{...state.loaded}})
  });
  window.__teacherAdminWorkspaceRouter = {
    getState: () => ({workspace:state.workspace, section:state.section, loaded:{...state.loaded}})
  };
  // Do not hide the learning page merely because the URL contains admin=1.
  // The bootstrapper opens the workspace after all deferred integrations are
  // available.  Keeping the normal page visible until that succeeds prevents
  // a timing failure from becoming an unrecoverable blank screen.
  syncPageModeClass(false);
})();
