/* Teacher 10/14 cut: dual-role persona switch + focused teacher workspace shell.
 * Presentation only. Server-side RBAC/scope remains authoritative.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const hasTeachingRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  const canTeach = hasTeachingRole && (has('course.manage') || has('material.manage') || has('question.manage') || has('exam.manage'));
  const canLearn = roles.has('student') || (has('course.view') && has('material.read') && has('exam.take') && has('progress.self.read'));
  const canSystem = roles.has('system_admin') && has('system.manage');
  const params = new URLSearchParams(window.location.search);
  const adminPage = params.get('admin') === '1';
  const requestedPersona = params.get('persona') || '';
  const requestedWorkspace = params.get('workspace') || 'course-materials';
  const teacherOwnedWorkspaces = new Set([
    'course-materials','courses','materials','assessment','questions','exams',
    'teacher','scoring','results','compliance','pgy','word'
  ]);
  const teacherPersonaActive = adminPage && canTeach && (
    requestedPersona === 'teacher' ||
    (!requestedPersona && teacherOwnedWorkspaces.has(requestedWorkspace))
  );
  const state = { mode: params.get('teacherMode') || 'course' };

  function learningUrl() {
    const url = new URL(window.location.href);
    ['admin','workspace','persona','teacherMode'].forEach(key => url.searchParams.delete(key));
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function adminUrl(workspace, persona, teacherMode = '') {
    const url = new URL(window.location.href);
    url.searchParams.set('admin', '1');
    url.searchParams.set('workspace', workspace);
    url.searchParams.set('persona', persona);
    if (teacherMode) url.searchParams.set('teacherMode', teacherMode);
    else url.searchParams.delete('teacherMode');
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function personaButton(label, active, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.className = active
      ? 'rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-black text-white shadow-sm'
      : 'rounded-full px-3 py-1.5 text-[11px] font-bold text-slate-600 hover:bg-white';
    button.addEventListener('click', onClick);
    return button;
  }

  function personaMountTarget() {
    if (adminPage) {
      const header = document.getElementById('admin-workspace-header');
      if (header) {
        let mount = document.getElementById('admin-workspace-persona-actions-1014');
        if (!mount) {
          mount = document.createElement('div');
          mount.id = 'admin-workspace-persona-actions-1014';
          mount.className = 'ml-auto flex items-center gap-2';
          const close = document.getElementById('admin-workspace-close');
          header.insertBefore(mount, close || null);
        }
        return {actions: mount, userBox: null, pageMode: true};
      }
    }
    return {
      actions: document.querySelector('.v56-system-actions'),
      userBox: document.querySelector('.v573-system-user'),
      pageMode: false,
    };
  }

  function ensurePersonaSwitcher() {
    const choices = [];
    if (canLearn) choices.push('learning');
    if (canTeach) choices.push('teacher');
    if (canSystem) choices.push('system');
    if (choices.length < 2) return;

    const mount = personaMountTarget();
    const actions = mount.actions;
    const userBox = mount.userBox;
    if (!actions) return;

    let host = document.getElementById('teacher-persona-switch-1014');
    if (!host) {
      host = document.createElement('div');
      host.id = 'teacher-persona-switch-1014';
    }
    host.className = mount.pageMode
      ? 'flex items-center gap-1 rounded-full border border-slate-700 bg-slate-800/80 p-1'
      : 'hidden sm:flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 p-1';

    if (host.parentElement !== actions) {
      actions.insertBefore(host, userBox || null);
    }

    const expected = [];
    if (canLearn) {
      expected.push(personaButton('📚 我的學習', !adminPage, () => window.location.assign(learningUrl())));
    }
    if (canTeach) {
      expected.push(personaButton('👨‍🏫 教師工作區', teacherPersonaActive, () => {
        window.location.assign(adminUrl('course-materials', 'teacher'));
      }));
    }
    if (canSystem) {
      const systemActive = adminPage && requestedPersona === 'system';
      expected.push(personaButton('⚙ 系統管理', systemActive, () => {
        window.location.assign(adminUrl('people', 'system'));
      }));
    }
    host.replaceChildren(...expected);
  }

  function makeNavButton(id, label, handler) {
    const button = document.createElement('button');
    button.id = id;
    button.type = 'button';
    button.className = 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
    button.textContent = label;
    button.addEventListener('click', handler);
    return button;
  }

  function navGroup(label, buttons) {
    const section = document.createElement('section');
    section.className = 'v580-admin-group';
    const heading = document.createElement('span');
    heading.className = 'v580-admin-group-label';
    heading.textContent = label;
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    buttons.forEach(button => actions.appendChild(button));
    section.append(heading, actions);
    return section;
  }

  function markTeacherNav(mode) {
    const map = {
      course: 'teacher-nav-course-1014',
      media: 'teacher-nav-media-1014',
      assessment: 'teacher-nav-assessment-1014',
      documents: 'teacher-nav-documents-1014'
    };
    document.querySelectorAll('#teacher-nav-course-1014,#teacher-nav-media-1014,#teacher-nav-assessment-1014,#teacher-nav-documents-1014').forEach(button => {
      const active = button.id === map[mode];
      button.classList.toggle('bg-teal-700', active);
      button.classList.toggle('text-white', active);
      button.classList.toggle('shadow-sm', active);
      button.classList.toggle('bg-slate-100', !active);
      button.classList.toggle('text-slate-600', !active);
    });
  }

  function restoreCourseWorkspace() {
    document.querySelectorAll('[data-teacher1014-hidden-by-media="1"]').forEach(node => {
      node.classList.remove('hidden');
      delete node.dataset.teacher1014HiddenByMedia;
    });
    document.getElementById('teacher-media-production-1014')?.classList.add('hidden');
  }

  function ensureMediaWorkspace() {
    // Workflow compatibility: 教材 → 講稿 → 語音／影片 → 發布；正式發布仍沿用原教材權限、組別範圍與發布流程。
    const content = document.getElementById('admin-section-content');
    if (!content) return null;
    let section = document.getElementById('teacher-media-production-1014');
    if (section) {
      normalizeMediaShell(section);
      return section;
    }

    section = document.createElement('section');
    section.id = 'teacher-media-production-1014';
    section.className = 'hidden space-y-5';
    section.innerHTML = `
      <section id="teacher-media-studio-shell-1018" class="teacher-media-shell-compact-1018 flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3 px-1">
        <div><p class="admin-page-eyebrow text-cyan-700">TEACHER CONTENT STUDIO</p><h4 class="text-xl font-black text-slate-950">🧰 教材媒體製作室</h4><p class="mt-1 max-w-3xl text-xs text-slate-500">同一頁完成 AI PowerPoint、講稿與配音、老師錄影、字幕與 AI 教學影片。</p></div>
        <div class="teacher-media-shell-actions-1014 flex flex-wrap items-center gap-2"><span class="admin-workspace-chip">本機 AI｜隱私模式</span><button id="teacher-media-pick-material-1014" type="button" class="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50">📚 回教材與課程</button></div>
      </section>`;
    content.appendChild(section);
    normalizeMediaShell(section);
    return section;
  }

  function normalizeMediaShell(section) {
    const shell = section?.querySelector('#teacher-media-studio-shell-1018');
    if (!shell) return;

    // Keep the studio identity, but not the old full-width card shell.  The
    // shared source picker immediately below is the only substantial card.
    shell.className = 'teacher-media-shell-compact-1018 flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3 px-1';
    shell.dataset.teacherMediaCompactShell = '1';

    // Flatten the previous card's nested header so hydrated legacy markup has
    // the same compact layout as a newly-created workspace.
    const legacyHeader = [...shell.children].find(node => node.classList?.contains('lg:justify-between'));
    if (legacyHeader) {
      while (legacyHeader.firstChild) shell.insertBefore(legacyHeader.firstChild, legacyHeader);
      legacyHeader.remove();
    }

    // Earlier media shells rendered a second, large "準備媒體來源" card here.
    // The shared selector in TeacherAIMediaStudio1018 is the sole source picker.
    // Never walk past this media shell: the surrounding full-page admin shell
    // also uses rounded-2xl and must never be removed during media cleanup.
    shell.querySelectorAll('[data-teacher-media-source-placeholder-1014], #teacher-media-pick-material-1014').forEach(node => {
      const legacyCard = node.closest('[data-teacher-media-source-placeholder-1014]')
        || (node.id === 'teacher-media-pick-material-1014' && node.closest('.rounded-2xl'));
      if (legacyCard && legacyCard !== shell && shell.contains(legacyCard)) legacyCard.remove();
    });
    shell.querySelectorAll('b').forEach(heading => {
      if (heading.textContent?.trim() !== '準備媒體來源') return;
      const legacyCard = heading.closest('.rounded-2xl');
      if (legacyCard && legacyCard !== shell && shell.contains(legacyCard)) legacyCard.remove();
    });

    let actions = shell.querySelector(':scope > .teacher-media-shell-actions-1014');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'teacher-media-shell-actions-1014 flex flex-wrap items-center gap-2';
      const privacy = shell.querySelector('.admin-workspace-chip');
      if (privacy) actions.appendChild(privacy);
      shell.appendChild(actions);
    }

    // PowerPoint is now the first stable tab in the unified studio; remove the
    // legacy shortcut that previously flashed while the course hub repainted.
    shell.querySelector('#teacher-media-open-presentation-1014')?.remove();

    let existingButton = shell.querySelector('#teacher-media-pick-material-1014');
    if (!existingButton) {
      existingButton = document.createElement('button');
      existingButton.id = 'teacher-media-pick-material-1014';
      existingButton.type = 'button';
      existingButton.className = 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50';
      existingButton.textContent = '📚 回教材與課程';
      actions.appendChild(existingButton);
    }
    if (existingButton.dataset.teacherMediaBackBound !== '1') {
      existingButton.dataset.teacherMediaBackBound = '1';
      existingButton.addEventListener('click', () => openCourse());
    }
  }

  function showMediaWorkspace() {
    const content = document.getElementById('admin-section-content');
    const media = ensureMediaWorkspace();
    if (!content || !media) return;
    [...content.children].forEach(child => {
      if (child === media || child.classList.contains('hidden')) return;
      child.dataset.teacher1014HiddenByMedia = '1';
      child.classList.add('hidden');
    });
    media.classList.remove('hidden');
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    const icon = document.getElementById('admin-workspace-icon');
    if (icon) icon.textContent = '🎙️';
    if (title) title.textContent = '教材媒體製作 Workspace';
    if (summary) summary.textContent = '同一製作室完成 AI PowerPoint、講稿與配音、老師錄影與 AI 教學影片；正式發布仍使用原教材權限與範圍。';
  }

  function setTeacherModeParam(mode) {
    if (!window.history?.replaceState) return;
    const url = new URL(window.location.href);
    url.searchParams.set('admin', '1');
    url.searchParams.set('persona', 'teacher');
    url.searchParams.set('workspace', mode === 'assessment' ? 'assessment' : (mode === 'documents' ? 'teacher' : 'course-materials'));
    if (mode === 'course' || mode === 'assessment') url.searchParams.delete('teacherMode');
    else url.searchParams.set('teacherMode', mode);
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  async function openCourse() {
    state.mode = 'course';
    restoreCourseWorkspace();
    setTeacherModeParam('course');
    await window.switchAdminWorkspace?.('course-materials', true);
    restoreCourseWorkspace();
    markTeacherNav('course');
  }

  async function openPresentation() {
    await openMedia();
    window.TeacherAIMediaStudio1018?.showMode?.('presentation');
    const host = document.getElementById('teacher-media-panel-presentation-1018');
    const target = document.getElementById('teacher-ai-material-1014')
      || document.getElementById('teacher-ai-presentation-1016')
      || host;
    if (target) {
      target.classList.remove('hidden');
      target.removeAttribute('aria-hidden');
      target.scrollIntoView?.({block: 'start', behavior: 'smooth'});
    }
  }

  async function openAssessment() {
    state.mode = 'assessment';
    restoreCourseWorkspace();
    setTeacherModeParam('assessment');
    await window.switchAdminWorkspace?.('assessment', true);
    markTeacherNav('assessment');
  }

  async function openMedia() {
    state.mode = 'media';
    setTeacherModeParam('media');
    await window.switchAdminWorkspace?.('course-materials', true);
    showMediaWorkspace();
    markTeacherNav('media');
  }

  async function openDocuments() {
    state.mode = 'documents';
    restoreCourseWorkspace();
    setTeacherModeParam('documents');
    await window.switchAdminWorkspace?.('teacher', true);
    await window.switchTeacherMode?.('documents');
    markTeacherNav('documents');
  }

  function ensureAssessmentWorkflow() {
    const panel = document.getElementById('admin-section-quiz');
    if (!panel) return;
    let flow = document.getElementById('teacher-assessment-flow-1014');
    if (!flow) {
      flow = document.createElement('section');
      flow.id = 'teacher-assessment-flow-1014';
      flow.className = 'rounded-2xl border border-slate-200 bg-white p-4 shadow-sm';
      flow.innerHTML = `
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div><p class="admin-page-eyebrow text-indigo-700">ASSESSMENT FLOW</p><h4 class="text-base font-black text-slate-950">評量工作流程</h4><p class="mt-1 text-xs text-slate-500">從建立到批改使用同一條流程；題庫、AI 出題與教師評核不再拆成彼此競爭的入口。</p></div>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-1.5 text-[10px] font-bold text-slate-700">
            <span class="teacher-assessment-step-1014">1 建立評量</span><span class="teacher-assessment-step-1014">2 準備題目</span><span class="teacher-assessment-step-1014">3 對象／期限</span><span class="teacher-assessment-step-1014">4 審核發布</span><span class="teacher-assessment-step-1014">5 待批改</span><span class="teacher-assessment-step-1014">6 歷史紀錄</span>
          </div>
        </div>`;
    }
    if (flow.parentElement !== panel) panel.insertBefore(flow, panel.firstChild);
  }

  function ensureAssessmentReviewShortcut() {
    const panel = document.getElementById('admin-section-quiz');
    if (!panel || document.getElementById('teacher-review-shortcut-1014')) return;
    const section = document.createElement('section');
    section.id = 'teacher-review-shortcut-1014';
    section.dataset.productSection = 'history';
    section.className = 'rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3';
    section.innerHTML = `<div><b class="text-sm text-indigo-950">⑤ 待批改 → ⑥ 歷史紀錄</b><p class="mt-1 text-xs text-indigo-700">待批改會優先出現在「需要我處理」；完成後自動進入歷史紀錄，不需要切換到另一套教師評核功能。</p></div><div class="flex flex-wrap gap-2"><button id="teacher-open-pending-review-1014" type="button" class="rounded-xl bg-indigo-700 px-4 py-2 text-xs font-black text-white">查看待批改</button><button id="teacher-open-review-1014" type="button" class="rounded-xl border border-indigo-200 bg-white px-4 py-2 text-xs font-black text-indigo-700">查看歷史紀錄</button></div>`;
    panel.appendChild(section);
    section.querySelector('#teacher-open-pending-review-1014')?.addEventListener('click', async () => {
      state.mode = 'assessment';
      await window.switchAdminWorkspace?.('teacher', true);
      await window.switchTeacherMode?.('scoring');
      markTeacherNav('assessment');
    });
    section.querySelector('#teacher-open-review-1014')?.addEventListener('click', async () => {
      state.mode = 'assessment';
      await window.switchAdminWorkspace?.('results', true);
      markTeacherNav('assessment');
    });
  }

  function buildTeacherNavigation() {
    if (!teacherPersonaActive) return;
    const navHost = document.querySelector('.v580-admin-groups');
    if (!navHost) return;
    const buttons = [
      makeNavButton('teacher-nav-course-1014', '📚 教材與課程', openCourse),
      makeNavButton('teacher-nav-assessment-1014', '📝 評量與出題', openAssessment),
      makeNavButton('teacher-nav-documents-1014', '📄 紙本文件與匯出', openDocuments)
    ];
    navHost.replaceChildren(navGroup('教師工作台', buttons));
    markTeacherNav(state.mode === 'documents' ? 'documents' : (state.mode === 'media' ? 'media' : (params.get('workspace') === 'assessment' ? 'assessment' : 'course')));
    ensureAssessmentWorkflow();
    ensureAssessmentReviewShortcut();
  }

  function syncTeacherHeader() {
    if (!teacherPersonaActive) return;
    const modal = document.getElementById('admin-modal');
    if (modal) modal.dataset.workspaceSurface = 'teacher';
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    if (title && !state.mode.startsWith('media')) title.textContent = '教師工作區';
    if (summary && state.mode === 'course') summary.textContent = '先處理今天需要完成的工作，再進入教材與課程、評量與出題或紙本文件；媒體製作收在教材工具內。';
  }

  ensurePersonaSwitcher();
  if (!teacherPersonaActive) return;

  buildTeacherNavigation();
  ensureMediaWorkspace();
  ensureAssessmentWorkflow();
  ensureAssessmentReviewShortcut();
  syncTeacherHeader();

  window.AdminWorkspaceShell?.addAfterWorkspace?.(({workspace}) => {
    ensurePersonaSwitcher();
    buildTeacherNavigation();
    ensureAssessmentWorkflow();
    ensureAssessmentReviewShortcut();
    if (state.mode === 'media' && workspace === 'course-materials') {
      showMediaWorkspace();
      markTeacherNav('media');
      return;
    }
    if (workspace !== 'course-materials') restoreCourseWorkspace();
    if (workspace === 'assessment') markTeacherNav('assessment');
    else if (workspace === 'teacher') markTeacherNav(state.mode === 'documents' ? 'documents' : 'assessment');
    else if (workspace === 'course-materials') markTeacherNav('course');
  });

  if (state.mode === 'media') {
    await openMedia();
  } else if (state.mode === 'documents') {
    await openDocuments();
  }

  window.TeacherWorkspace1014 = Object.freeze({
    canLearn, canTeach, canSystem,
    openCourse, openPresentation, openMedia, openAssessment, openDocuments,
    learningUrl, ensurePersonaSwitcher
  });

  // Reconcile once more after the teacher workspace has finished mounting.
  // This is idempotent and protects dual-role users from late presentation
  // mutations without changing authorization.
  ensurePersonaSwitcher();
  setTimeout(ensurePersonaSwitcher, 0);
})();