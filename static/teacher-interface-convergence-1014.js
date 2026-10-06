/* Teacher 10/14 interface convergence.
 * Keep existing capabilities intact while reducing top-level choices:
 * - Media production lives under 教材與課程 instead of a separate main nav entry.
 * - Each course exposes one 管理課程 entry, with editing/assignment/delete nested inside.
 * - Kokoro voice IDs remain internal values for debugging but are not shown to teachers.
 */
(function () {
  'use strict';

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
    return window.TeacherVoiceCatalog1026?.label?.(id) || '中文語音';
  }

  function voiceOptions() {
    return window.TeacherVoiceCatalog1026?.options?.() || [];
  }

  function rewriteVoiceOptions(select) {
    if (!select) return;
    Array.from(select.options || []).forEach(option => {
      const id = String(option.value || '').trim();
      if (!id) return;
      const label = voiceLabel(id);
      if (option.textContent !== label) option.textContent = label;
    });
  }

  function rewriteVoiceResult(host) {
    if (!host) return;
    const rows = voiceOptions();
    if (!rows.length) return;
    host.querySelectorAll('p').forEach(node => {
      const original = String(node.textContent || '');
      if (!original.includes('Voice：')) return;
      let next = original;
      rows.forEach(({id, label}) => {
        if (id && next.includes(id)) next = next.split(id).join(label || '中文語音');
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
      summary.textContent = '日常工作只分「教材與課程」與「評量與追蹤」；媒體製作收在教材流程，公告與文件放在右上工具。';
    }
  }

  function ensureCourseMediaEntry(box) {
    // Media/Atlas are contextual course or material actions now. Remove the
    // historical full-width tool strip so it cannot compete with course work.
    box?.querySelector('#teacher-course-media-entry-1014')?.remove();
  }

  function invokeOriginal(button) {
    if (!button) return;
    button.click();
  }

  function convergeCourseCard(details) {
    const summary = details?.querySelector(':scope > summary');
    const body = details?.querySelector(':scope > div.grid.border-t');
    if (!summary || !body) return;

    const actionBar = details.querySelector(':scope > [data-course-card-actions]') || summary;
    const assignment = actionBar.querySelector('[data-learning-assign-course]');
    const edit = actionBar.querySelector('button[data-csp-click*="teachingEditCourse("]');
    const remove = actionBar.querySelector('button[data-csp-click*="adminDeleteCourse("]');
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
      const mediaButton = document.createElement('button');
      mediaButton.type = 'button';
      mediaButton.setAttribute('data-teacher-course-media-1014', '1');
      mediaButton.className = 'rounded-xl border border-violet-200 bg-white px-3 py-2 text-xs font-black text-violet-700';
      mediaButton.textContent = '✨ AI／影音製作';
      mediaButton.addEventListener('click', async event => {
        event.preventDefault();
        await window.TeacherWorkspace1014?.openMedia?.();
        convergeTeacherNavigation();
        installVoicePrivacy();
      });
      actions.appendChild(mediaButton);
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

    // A legacy re-render can move the action host while leaving our previous
    // button behind in the card.  The card, not a transient host, owns this
    // singleton.  Keep the first existing button (and its click listener),
    // remove stale copies, then move it to the current host.
    const manages = [...details.querySelectorAll('[data-teacher-manage-course-1014]')];
    let manage = manages.shift();
    manages.forEach(node => node.remove());
    if (manage && manage.parentElement !== actionHost) actionHost.appendChild(manage);
    if (!manage) {
      manage = document.createElement('button');
      manage.type = 'button';
      // Keep the public selector stable. dataset camel-casing cannot express
      // the separator before the numeric suffix in data-*-1014.
      manage.setAttribute('data-teacher-manage-course-1014', '1');
      manage.className = 'teaching-primary';
      manage.textContent = '管理課程';
      manage.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        details.open = true;
        // The course renderer can replace only the card body while keeping this
        // management button alive. Resolve the panel from the current DOM on
        // every click instead of closing over the panel created earlier.
        const currentPanel = details.querySelector(':scope > div.grid.border-t > [data-teacher-course-tools-1014]');
        if (!currentPanel) {
          convergeCourseCard(details);
          return;
        }
        currentPanel.classList.toggle('hidden');
        manage.setAttribute('aria-expanded', currentPanel.classList.contains('hidden') ? 'false' : 'true');
        if (!currentPanel.classList.contains('hidden')) currentPanel.scrollIntoView?.({block: 'nearest', behavior: 'smooth'});
      });
      manage.setAttribute('aria-expanded', 'false');
      actionHost.appendChild(manage);
    }
  }

  function convergeCourseSurface() {
    const box = document.getElementById('admin-course-material-hub');
    if (!box || state.applyingCourses) return;
    if (state.courseBox !== box) {
      state.courseObserver?.disconnect();
      state.courseBox = box;
      state.courseObserver = new MutationObserver(() => {
        // A course refresh replaces the card list in one DOM task.  Deferring
        // convergence to requestAnimationFrame leaves a visible/readable
        // frame where fresh cards have no singleton management button.  Run
        // in this mutation microtask instead; the observer is disconnected
        // while we apply our own changes, so this remains loop-safe.
        convergeCourseSurface();
      });
    }
    // MutationObserver callbacks run after this function returns; a boolean
    // applying flag alone cannot suppress notifications from our own inserts.
    state.courseObserver.disconnect();
    state.applyingCourses = true;
    try {
      ensureCourseMediaEntry(box);
      box.querySelectorAll('.admin-course-list > details').forEach(convergeCourseCard);
    } finally {
      state.applyingCourses = false;
      state.courseObserver.observe(box, {childList: true, subtree: true});
    }
  }

  function convergeAll() {
    convergeTeacherNavigation();
    convergeCourseSurface();
    installVoicePrivacy();
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => queueMicrotask(convergeAll));
  // The canonical course renderer announces a completed replacement so card
  // decoration happens in the same task.  MutationObserver remains as the
  // compatibility fallback for legacy renderers and third-party extensions.
  document.addEventListener('teacher-course-surface-rendered-1014', event => {
    if (event.target === document.getElementById('admin-course-material-hub')) convergeCourseSurface();
  });
  document.addEventListener('click', event => {
    if (event.target.closest?.('#teacher-nav-course-1014')) setTimeout(convergeAll, 0);
  });

  [0, 250, 900, 2200].forEach(delay => setTimeout(convergeAll, delay));
})();
