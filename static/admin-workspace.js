/* Phase 3K/3L: admin workspace shell / section router.
 *
 * This module intentionally loads immediately after the legacy system-admin.js
 * bundle and before RBAC/workspace wrappers. Teacher/results mode state is
 * supplied by admin-results-workspace.js instead of the legacy router.
 */
(() => {
  'use strict';

  const state = {
    workspace: 'course-materials',
    section: 'content',
    loaded: {content:false, quiz:false, word:false, pgy:false, results:false}
  };

  function normalizeWorkspace(name) {
    if (name === 'courses' || name === 'materials') return 'course-materials';
    if (name === 'assessment' || name === 'questions') return 'assessment';
    if (name === 'scoring' || name === 'pgy') return 'teacher';
    return name;
  }

  function paintWorkspaceNav(name) {
    name = normalizeWorkspace(name);
    const names = ['course-materials','assessment','results','people','teacher','word','system'];
    names.forEach(item => {
      const button = document.getElementById(`admin-nav-${item}`);
      if (!button) return;
      button.className = item === name
        ? 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-teal-700 text-white shadow-sm'
        : 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
    });
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
    const names = ['content','quiz','word','pgy','results','exam-settings','people','system'];
    names.forEach(item => document.getElementById(`admin-section-${item}`)?.classList.toggle('hidden', item !== name));
    syncSectionChrome(name);

    if (name === 'exam-settings' || name === 'people' || name === 'system') return;
    if (!force && state.loaded[name]) return;
    state.loaded[name] = true;

    if (name === 'content') {
      await Promise.allSettled([
        Promise.resolve(window.refreshAdminMaterialCategoryOptions?.()),
        Promise.resolve(window.renderAdminCourses?.()),
        Promise.resolve(window.renderAdminMaterials?.(force))
      ]);
      await window.renderAdminCourseMaterialHub?.(force);
    }
    if (name === 'quiz') await window.renderAdminQuizCategories?.(force);
    if (name === 'word') await window.renderAdminDocTemplates?.();
    if (name === 'pgy') {
      await Promise.allSettled([
        Promise.resolve(window.renderAdminPgyTemplates?.()),
        Promise.resolve(window.renderAdminPgyAssessments?.())
      ]);
    }
    if (name === 'results') await window.renderAdminTable?.();
  }

  async function switchWorkspace(name, force=false) {
    const requested = name;
    name = normalizeWorkspace(name);
    state.workspace = name;
    paintWorkspaceNav(name);

    if (name === 'course-materials') {
      await switchSection('content', force);
      document.getElementById('admin-course-workspace')?.classList.remove('hidden');
      document.getElementById('admin-material-workspace')?.classList.remove('hidden');
      document.getElementById('admin-material-advanced')?.classList.remove('hidden');
      // Storage/worker probes remain intentionally deferred until their panels open.
      return;
    }
    if (name === 'assessment') {
      await switchSection('quiz', force);
      window.updateQuizWorkspacePresentation?.();
      return;
    }

    if (name === 'teacher' || name === 'results') {
      const modeRouter = window.__teacherAdminResultsWorkspace;
      if (modeRouter && typeof modeRouter.switchWorkspace === 'function') {
        return modeRouter.switchWorkspace({requested, workspace:name, force, switchSection});
      }
      if (name === 'teacher' && requested === 'pgy') return switchSection('pgy', true);
      return switchSection('results', true);
    }

    if (name === 'word') return switchSection('word', force);
    if (name === 'people') {
      await switchSection('people', true);
      await window.renderAdminPeople?.(force);
      return;
    }
    if (name === 'system') {
      await switchSection('system', true);
      await Promise.all([
        Promise.resolve(window.renderAdminSystemStatus?.(force)),
        Promise.resolve(window.renderAdminAnnouncements?.())
      ]);
    }
  }

  async function toggleModal(show) {
    const modal = document.getElementById('admin-modal');
    if (!modal) return false;
    if (show) {
      const key = await window.getAdminKey?.();
      if (!key) return false;
      window.populateAdminGroupSelects?.();
      const materialSelect = document.getElementById('admin-material-group');
      const quizSelect = document.getElementById('admin-quiz-group');
      if (materialSelect) materialSelect.value = window.currentGroupKey || materialSelect.value;
      if (quizSelect) quizSelect.value = window.currentGroupKey || quizSelect.value;
      modal.classList.remove('hidden');
      await window.switchAdminWorkspace?.('course-materials', false);
      return true;
    }
    modal.classList.add('hidden');
    return true;
  }

  async function openWorkspace(name) {
    const opened = await window.toggleAdminModal?.(true);
    if (opened === false) return false;
    return window.switchAdminWorkspace?.(name, true);
  }

  window.normalizeAdminWorkspace = normalizeWorkspace;
  window.paintAdminWorkspaceNav = paintWorkspaceNav;
  window.syncAdminSectionChrome = syncSectionChrome;
  window.switchAdminSection = switchSection;
  window.switchAdminWorkspace = switchWorkspace;
  window.toggleAdminModal = toggleModal;
  window.openAdminWorkspace = openWorkspace;
  window.openTeacherAssessment = () => openWorkspace('teacher');
  window.__teacherAdminWorkspaceRouter = {
    getState: () => ({workspace:state.workspace, section:state.section, loaded:{...state.loaded}})
  };
})();
