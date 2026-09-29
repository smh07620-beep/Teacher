/* Teacher 10/14: hard persona isolation for dual-role system-admin teachers.
 * Worker/Job and platform governance belong only to persona=system.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const T = window.TeacherWorkspace1014 || {};
  const params = new URLSearchParams(window.location.search);
  const workspace = params.get('workspace') || '';
  const persona = params.get('persona') || '';
  const teacherOwnedWorkspaces = new Set([
    'course-materials','content','assessment','questions','quiz','exams','exam-settings',
    'teacher','scoring','pgy','results','compliance','word'
  ]);
  const teacherPersona = params.get('admin') === '1' && !!T.canTeach && (
    persona === 'teacher' || (!persona && teacherOwnedWorkspaces.has(workspace))
  );
  if (!teacherPersona) return;

  // Canonicalize legacy teacher URLs so all later-loaded scripts see one
  // unambiguous persona instead of treating an empty persona as both teacher
  // and system administration.
  if (persona !== 'teacher' && window.history?.replaceState) {
    const url = new URL(window.location.href);
    url.searchParams.set('persona', 'teacher');
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }

  const navHost = document.querySelector('.v580-admin-groups');
  if (!navHost) return;
  let syncing = false;

  const buttonSpec = [
    ['teacher-nav-course-1014', '📚 教材與課程', () => T.openCourse?.()],
    ['teacher-nav-media-1014', '🎙️ 媒體製作', () => T.openMedia?.()],
    ['teacher-nav-assessment-1014', '📝 評量與出題', () => T.openAssessment?.()],
    ['teacher-nav-documents-1014', '📄 紙本文件與匯出', () => T.openDocuments?.()],
  ];

  function currentMode() {
    const now = new URLSearchParams(window.location.search);
    const mode = now.get('teacherMode') || '';
    if (mode === 'media' || mode === 'documents') return mode;
    return now.get('workspace') === 'assessment' ? 'assessment' : 'course';
  }

  function makeButton(id, label, handler, active) {
    const button = document.createElement('button');
    button.id = id;
    button.type = 'button';
    button.textContent = label;
    button.className = active
      ? 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-teal-700 text-white shadow-sm'
      : 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
    button.addEventListener('click', event => {
      event.preventDefault();
      void handler();
    });
    return button;
  }

  function updateHeader() {
    const icon = document.getElementById('admin-workspace-icon');
    const title = document.getElementById('admin-workspace-title');
    const summary = document.getElementById('admin-workspace-summary');
    if (icon) icon.textContent = '👨‍🏫';
    if (title && !title.textContent.includes('媒體製作')) title.textContent = '檢驗科教學平台｜教師工作區';
    if (summary && !title?.textContent?.includes('媒體製作')) {
      summary.textContent = '教材、媒體、評量與正式紙本輸出集中於教師工作區；平台維運與 Worker 狀態只在系統管理顯示。';
    }

    const banner = document.getElementById('rbac-workspace-banner');
    if (banner) {
      const group = String(R.user?.preferredGroup || '').trim();
      const scope = R.scopedTeacher && group
        ? `<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-600">目前管理範圍：${group.replace(/[<>&"']/g, '')}</span>`
        : '';
      banner.innerHTML = `<div class="flex flex-wrap items-center justify-between gap-2"><div class="flex flex-wrap items-center gap-2"><span class="text-xs font-black text-slate-800">👨‍🏫 教師工作區</span><span class="text-[11px] text-slate-400">從左側選擇教學工作項目</span></div>${scope}</div>`;
    }
  }

  function rebuildTeacherNav() {
    if (syncing) return;
    syncing = true;
    try {
      const mode = currentMode();
      const activeByMode = {
        course: 'teacher-nav-course-1014',
        media: 'teacher-nav-media-1014',
        assessment: 'teacher-nav-assessment-1014',
        documents: 'teacher-nav-documents-1014',
      };
      const group = document.createElement('section');
      group.className = 'v580-admin-group';
      const label = document.createElement('span');
      label.className = 'v580-admin-group-label';
      label.textContent = '教師工作台';
      const actions = document.createElement('div');
      actions.className = 'v580-admin-group-actions';
      buttonSpec.forEach(([id, text, handler]) => {
        actions.appendChild(makeButton(id, text, handler, id === activeByMode[mode]));
      });
      group.append(label, actions);
      navHost.replaceChildren(group);

      document.getElementById('admin-section-worker')?.classList.add('hidden');
      document.getElementById('system-focus-note-1014')?.remove();
      updateHeader();
    } finally {
      syncing = false;
    }
  }

  rebuildTeacherNav();

  // An older system-admin script and Worker status module can both mutate the
  // same navigation host. Keep teacher persona final and deterministic.
  const observer = new MutationObserver(() => {
    if (syncing) return;
    const leakedSystemControl = navHost.querySelector(
      '#admin-nav-worker,#admin-nav-people,#admin-nav-system,#admin-nav-maintenance,#admin-nav-audit'
    );
    const teacherButtons = navHost.querySelectorAll('[id^="teacher-nav-"]');
    if (leakedSystemControl || teacherButtons.length !== 4) rebuildTeacherNav();
  });
  observer.observe(navHost, {childList:true, subtree:true});

  // If an explicitly teacher URL inherited a platform-only workspace, move it
  // back to the teacher landing workspace once without exposing the Worker page.
  if (new Set(['people','system','worker','maintenance','audit']).has(workspace)) {
    await T.openCourse?.();
    rebuildTeacherNav();
  }

  window.TeacherPersonaIsolation1014 = Object.freeze({ rebuild: rebuildTeacherNav });
})();
