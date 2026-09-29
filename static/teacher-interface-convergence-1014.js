/* Teacher 10/14 interface convergence.
 * Keep existing capabilities intact while reducing top-level choices:
 * - Media production lives under 教材與課程 instead of a separate main nav entry.
 * - Each course exposes one 管理課程 entry, with editing/assignment/delete nested inside.
 * - Kokoro voice IDs remain internal values for debugging but are not shown to teachers.
 */
(function () {
  'use strict';

  const VOICE_LABELS = Object.freeze({
    zf_xiaobei: '中文女聲 A',
    zf_xiaoni: '中文女聲 B',
    zf_xiaoxiao: '中文女聲 C',
    zf_xiaoyi: '中文女聲 D',
    zm_yunjian: '中文男聲 A',
    zm_yunxi: '中文男聲 B',
    zm_yunxia: '中文男聲 C',
    zm_yunyang: '中文男聲 D',
  });

  const state = {
    voiceSelectObserver: null,
    voiceSelect: null,
    voiceResultObserver: null,
    voiceResult: null,
    courseObserver: null,
    courseBox: null,
    applyingCourses: false,
  };

  function voiceLabel(id) {
    return VOICE_LABELS[String(id || '').trim()] || '中文語音';
  }

  function rewriteVoiceOptions(select) {
    if (!select) return;
    Array.from(select.options || []).forEach(option => {
      const id = String(option.value || '').trim();
      if (!VOICE_LABELS[id]) return;
      // The raw ID is deliberately retained as the submitted value. Only the
      // teacher-facing label is translated; API/job diagnostics keep the ID.
      const label = voiceLabel(id);
      if (option.textContent !== label) option.textContent = label;
    });
  }

  function rewriteVoiceResult(host) {
    if (!host) return;
    host.querySelectorAll('p').forEach(node => {
      const original = String(node.textContent || '');
      if (!original.includes('Voice：')) return;
      let next = original;
      Object.entries(VOICE_LABELS).forEach(([id, label]) => {
        if (next.includes(id)) next = next.split(id).join(label);
      });
      if (next !== original) node.textContent = next;
    });
  }

  function installVoicePrivacy() {
    const select = document.getElementById('teacher-audio-voice-1014');
    if (select) {
      rewriteVoiceOptions(select);
      if (state.voiceSelect !== select) {
        state.voiceSelectObserver?.disconnect();
        state.voiceSelect = select;
        state.voiceSelectObserver = new MutationObserver(() => rewriteVoiceOptions(select));
        state.voiceSelectObserver.observe(select, {childList: true, subtree: true});
      }
    }

    const result = document.getElementById('teacher-audio-result-1014');
    if (result) {
      rewriteVoiceResult(result);
      if (state.voiceResult !== result) {
        state.voiceResultObserver?.disconnect();
        state.voiceResult = result;
        state.voiceResultObserver = new MutationObserver(() => rewriteVoiceResult(result));
        state.voiceResultObserver.observe(result, {childList: true, subtree: true, characterData: true});
      }
    }
  }

  function setCourseNavActive() {
    const button = document.getElementById('teacher-nav-course-1014');
    if (!button) return;
    button.classList.add('bg-teal-700', 'text-white', 'shadow-sm');
    button.classList.remove('bg-slate-100', 'text-slate-600');
  }

  function convergeTeacherNavigation() {
    const courseButton = document.getElementById('teacher-nav-course-1014');
    if (!courseButton) return;

    // 媒體製作仍存在，改為教材與課程內的二級入口。
    document.getElementById('teacher-nav-media-1014')?.remove();

    const mediaWorkspace = document.getElementById('teacher-media-production-1014');
    if (mediaWorkspace && !mediaWorkspace.classList.contains('hidden')) setCourseNavActive();

    const summary = document.getElementById('admin-workspace-summary');
    if (summary && summary.textContent?.includes('教材與課程、媒體製作')) {
      summary.textContent = '教材與課程（含媒體製作）、評量與出題、紙本文件集中在同一教師工作台。';
    }
  }

  function ensureCourseMediaEntry(box) {
    if (!box || box.querySelector('#teacher-course-media-entry-1014')) return;
    const dashboard = box.querySelector('.admin-course-dashboard');
    if (!dashboard) return;

    const entry = document.createElement('section');
    entry.id = 'teacher-course-media-entry-1014';
    entry.className = 'mb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 rounded-2xl border border-cyan-100 bg-cyan-50/50 px-4 py-3';
    entry.innerHTML = '<div><b class="text-sm text-slate-900">教材與課程</b><p class="mt-0.5 text-[11px] text-slate-600">課程內容、教材與媒體製作集中在這裡。</p></div>';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'shrink-0 rounded-xl border border-cyan-200 bg-white px-4 py-2 text-xs font-black text-cyan-800 hover:bg-cyan-50';
    button.textContent = '🎙️ 製作語音／錄影';
    button.addEventListener('click', async event => {
      event.preventDefault();
      await window.TeacherWorkspace1014?.openMedia?.();
      convergeTeacherNavigation();
      installVoicePrivacy();
    });
    entry.appendChild(button);
    box.insertBefore(entry, dashboard);
  }

  function invokeOriginal(button) {
    if (!button) return;
    button.click();
  }

  function convergeCourseCard(details) {
    const summary = details?.querySelector(':scope > summary');
    const body = details?.querySelector(':scope > div.border-t');
    if (!summary || !body) return;

    const assignment = summary.querySelector('[data-learning-assign-course]');
    const edit = summary.querySelector('button[data-csp-click*="teachingEditCourse("]');
    const remove = summary.querySelector('button[data-csp-click*="adminDeleteCourse("]');
    if (!edit && !assignment && !remove) return;

    const actionHost = (edit || assignment || remove)?.parentElement;
    if (!actionHost) return;

    [assignment, edit, remove].filter(Boolean).forEach(button => {
      button.classList.add('hidden');
      button.tabIndex = -1;
      button.setAttribute('aria-hidden', 'true');
    });

    let panel = body.querySelector(':scope > [data-teacher-course-tools-1014]');
    if (!panel) {
      panel = document.createElement('section');
      panel.dataset.teacherCourseTools1014 = '1';
      panel.className = 'hidden lg:col-span-2 rounded-2xl border border-slate-200 bg-slate-50/80 p-4';
      const title = document.createElement('div');
      title.className = 'text-xs font-black text-slate-800';
      title.textContent = '課程管理';
      const actions = document.createElement('div');
      actions.className = 'mt-3 flex flex-wrap gap-2';

      if (edit) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'rounded-xl bg-violet-700 px-3 py-2 text-xs font-black text-white';
        button.textContent = '✏️ 內容編排';
        button.addEventListener('click', event => { event.preventDefault(); invokeOriginal(edit); });
        actions.appendChild(button);
      }
      if (assignment) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'rounded-xl bg-teal-700 px-3 py-2 text-xs font-black text-white';
        button.textContent = '👥 學習指派';
        button.addEventListener('click', event => { event.preventDefault(); invokeOriginal(assignment); });
        actions.appendChild(button);
      }
      if (remove) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-black text-rose-700';
        button.textContent = '刪除課程';
        button.addEventListener('click', event => { event.preventDefault(); invokeOriginal(remove); });
        actions.appendChild(button);
      }

      panel.append(title, actions);
      body.insertBefore(panel, body.firstChild);
    }

    let manage = actionHost.querySelector('[data-teacher-manage-course-1014]');
    if (!manage) {
      manage = document.createElement('button');
      manage.type = 'button';
      manage.dataset.teacherManageCourse1014 = '1';
      manage.className = 'teaching-primary';
      manage.textContent = '管理課程';
      manage.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        details.open = true;
        panel.classList.toggle('hidden');
        manage.setAttribute('aria-expanded', panel.classList.contains('hidden') ? 'false' : 'true');
        if (!panel.classList.contains('hidden')) panel.scrollIntoView?.({block: 'nearest', behavior: 'smooth'});
      });
      manage.setAttribute('aria-expanded', 'false');
      actionHost.appendChild(manage);
    }
  }

  function convergeCourseSurface() {
    const box = document.getElementById('admin-course-material-hub');
    if (!box || state.applyingCourses) return;
    state.applyingCourses = true;
    try {
      ensureCourseMediaEntry(box);
      box.querySelectorAll('.admin-course-list > details').forEach(convergeCourseCard);
    } finally {
      state.applyingCourses = false;
    }

    if (state.courseBox === box && state.courseObserver) return;
    state.courseObserver?.disconnect();
    state.courseBox = box;
    state.courseObserver = new MutationObserver(() => {
      if (state.applyingCourses) return;
      queueMicrotask(convergeCourseSurface);
    });
    state.courseObserver.observe(box, {childList: true, subtree: true});
  }

  function convergeAll() {
    convergeTeacherNavigation();
    convergeCourseSurface();
    installVoicePrivacy();
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => queueMicrotask(convergeAll));
  document.addEventListener('click', event => {
    if (event.target.closest?.('#teacher-nav-course-1014')) setTimeout(convergeAll, 0);
  });

  [0, 250, 900, 2200].forEach(delay => setTimeout(convergeAll, delay));
})();
