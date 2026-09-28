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
  const canLearn = has('course.view') && has('material.read') && has('exam.take') && has('progress.self.read');
  const canSystem = roles.has('system_admin') && has('system.manage');
  const params = new URLSearchParams(window.location.search);
  const adminPage = params.get('admin') === '1';
  const requestedPersona = params.get('persona') || '';
  const teacherPersonaActive = adminPage && canTeach && requestedPersona !== 'system';
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

  function ensurePersonaSwitcher() {
    const choices = [];
    if (canLearn) choices.push('learning');
    if (canTeach) choices.push('teacher');
    if (canSystem) choices.push('system');
    if (choices.length < 2) return;
    if (document.getElementById('teacher-persona-switch-1014')) return;

    const actions = document.querySelector('.v56-system-actions');
    const userBox = document.querySelector('.v573-system-user');
    if (!actions) return;

    const host = document.createElement('div');
    host.id = 'teacher-persona-switch-1014';
    host.className = 'hidden sm:flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 p-1';

    if (canLearn) {
      host.appendChild(personaButton('📚 我的學習', !adminPage, () => window.location.assign(learningUrl())));
    }
    if (canTeach) {
      host.appendChild(personaButton('👨‍🏫 教師工作區', teacherPersonaActive, () => {
        window.location.assign(adminUrl('course-materials', 'teacher'));
      }));
    }
    if (canSystem) {
      const systemActive = adminPage && requestedPersona === 'system';
      host.appendChild(personaButton('⚙ 系統管理', systemActive, () => {
        window.location.assign(adminUrl('people', 'system'));
      }));
    }

    actions.insertBefore(host, userBox || actions.firstChild);
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
    const content = document.getElementById('admin-section-content');
    if (!content) return null;
    let section = document.getElementById('teacher-media-production-1014');
    if (section) return section;

    section = document.createElement('section');
    section.id = 'teacher-media-production-1014';
    section.className = 'hidden space-y-5';
    section.innerHTML = `
      <section class="bg-white border border-cyan-200 rounded-2xl p-5 shadow-sm space-y-5">
        <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
          <div><p class="admin-page-eyebrow text-cyan-700">MEDIA STUDIO</p><h4 class="text-xl font-black text-slate-950">🎙️ 教材媒體製作</h4><p class="mt-1 max-w-3xl text-xs text-slate-500">以既有教材為來源，逐步產生講稿、語音與影片。所有正式發布仍沿用原教材權限、組別範圍與發布流程。</p></div>
          <span class="admin-workspace-chip">教材 → 講稿 → 語音／影片 → 發布</span>
        </div>
        <div class="grid lg:grid-cols-3 gap-4">
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div class="text-2xl">📝</div><h5 class="mt-2 font-black text-slate-900">教材轉講稿</h5><p class="mt-1 text-xs text-slate-600 leading-5">從 PDF、Word、PPT 或既有教材建立口語化講稿；正式生成前由老師確認內容。</p><span class="mt-3 inline-flex rounded-full bg-cyan-100 px-2.5 py-1 text-[11px] font-bold text-cyan-800">流程骨架已建立</span></article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div class="text-2xl">🎧</div><h5 class="mt-2 font-black text-slate-900">老師錄音／AI 語音</h5><p class="mt-1 text-xs text-slate-600 leading-5">支援老師自行錄音；AI 語音則由背景 Worker 產生，避免 Render Web 長工作逾時。</p><span class="mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800">下一實作切點</span></article>
          <article class="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div class="text-2xl">🎬</div><h5 class="mt-2 font-black text-slate-900">老師錄影／教學影片</h5><p class="mt-1 text-xs text-slate-600 leading-5">預留攝影機、麥克風、螢幕分享與教材畫面合成；成品由 Worker 處理後回寫教材。</p><span class="mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800">下一實作切點</span></article>
        </div>
        <div class="rounded-2xl border border-teal-100 bg-teal-50/60 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"><div><b class="text-sm text-teal-950">先從既有教材開始</b><p class="mt-1 text-xs text-teal-800">媒體製作不另建教材資料；先選教材，再建立媒體版本，避免內容與版本分裂。</p></div><button id="teacher-media-pick-material-1014" type="button" class="shrink-0 rounded-xl bg-teal-700 px-4 py-2 text-xs font-black text-white">📚 回教材與課程選擇</button></div>
      </section>`;
    content.appendChild(section);
    section.querySelector('#teacher-media-pick-material-1014')?.addEventListener('click', () => openCourse());
    return section;
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
    if (summary) summary.textContent = '從既有教材建立講稿、錄音、AI 語音與教學影片；正式發布仍使用原教材權限與範圍。';
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

  function ensureAssessmentReviewShortcut() {
    const panel = document.getElementById('admin-section-quiz');
    if (!panel || document.getElementById('teacher-review-shortcut-1014')) return;
    const section = document.createElement('section');
    section.id = 'teacher-review-shortcut-1014';
    section.className = 'rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3';
    section.innerHTML = `<div><b class="text-sm text-indigo-950">✍️ 待批改／教師評核</b><p class="mt-1 text-xs text-indigo-700">閱卷仍屬於評量流程，不另外佔一個主導覽；需要時從這裡進入。</p></div><button id="teacher-open-review-1014" type="button" class="rounded-xl border border-indigo-200 bg-white px-4 py-2 text-xs font-black text-indigo-700">進入閱卷與評核</button>`;
    panel.insertBefore(section, panel.firstChild);
    section.querySelector('#teacher-open-review-1014')?.addEventListener('click', async () => {
      state.mode = 'assessment';
      await window.switchAdminWorkspace?.('teacher', true);
      await window.switchTeacherMode?.('scoring');
      markTeacherNav('assessment');
    });
  }

  function buildTeacherNavigation() {
    if (!teacherPersonaActive) return;
    const navHost = document.querySelector('.v580-admin-groups');
    if (!navHost) return;
    const buttons = [
      makeNavButton('teacher-nav-course-1014', '📚 教材與課程', openCourse),
      makeNavButton('teacher-nav-media-1014', '🎙️ 媒體製作', openMedia),
      makeNavButton('teacher-nav-assessment-1014', '📝 評量與出題', openAssessment),
      makeNavButton('teacher-nav-documents-1014', '📄 紙本文件與匯出', openDocuments)
    ];
    navHost.replaceChildren(navGroup('教師工作台', buttons));
    markTeacherNav(state.mode === 'documents' ? 'documents' : (state.mode === 'media' ? 'media' : (params.get('workspace') === 'assessment' ? 'assessment' : 'course')));
    ensureAssessmentReviewShortcut();
  }

  function syncTeacherHeader() {
    if (!teacherPersonaActive) return;
    const modal = document.getElementById('admin-modal');
    if (modal) modal.dataset.workspaceSurface = 'teacher';
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    if (title && !state.mode.startsWith('media')) title.textContent = '教師工作區';
    if (summary && state.mode === 'course') summary.textContent = '教材與課程、媒體製作、評量與出題、紙本文件集中在同一教師工作台。';
  }

  ensurePersonaSwitcher();
  if (!teacherPersonaActive) return;

  buildTeacherNavigation();
  ensureMediaWorkspace();
  ensureAssessmentReviewShortcut();
  syncTeacherHeader();

  window.AdminWorkspaceShell?.addAfterWorkspace?.(({workspace}) => {
    buildTeacherNavigation();
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
    openCourse, openMedia, openAssessment, openDocuments,
    learningUrl
  });
})();
