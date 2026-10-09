/* Teacher 10/14 interface convergence.
 * Keep existing capabilities intact while reducing top-level choices:
 * - Media production lives under 教材與課程 instead of a separate main nav entry.
 * - Each course card shows 編輯課程 / 學習成果 and one 更多 menu (lifecycle, delete); media is reached from the course wizard.
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
      summary.textContent = '日常工作只分「教材與課程」與「評量與追蹤」；媒體製作收在課程的教材流程內。';
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

  function makeCardButton(label, className, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); handler(); });
    return button;
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

    // Legacy buttons stay in the DOM (they own the real handlers) but are
    // hidden; the card shows one compact set instead of a second panel.
    [assignment, edit, remove].filter(Boolean).forEach(button => {
      button.classList.add('hidden');
      button.tabIndex = -1;
      button.setAttribute('aria-hidden', 'true');
    });
    // The old 管理課程 toggle panel duplicated these same buttons.
    body.querySelector(':scope > [data-teacher-course-tools-1014]')?.remove();
    details.querySelectorAll('[data-teacher-manage-course-1014]').forEach(node => node.remove());

    // The card owns one compact action group. A legacy re-render can move the
    // action host, so keep the first group, drop stale copies and re-home it.
    const groups = [...details.querySelectorAll('[data-teacher-course-actions-1014]')];
    let group = groups.shift();
    groups.forEach(node => node.remove());
    if (group && group.parentElement !== actionHost) actionHost.appendChild(group);
    if (!group) {
      group = document.createElement('div');
      group.setAttribute('data-teacher-course-actions-1014', '1');
      group.className = 'flex flex-wrap items-center gap-2';
      if (edit) {
        const button = makeCardButton('編輯課程', 'teaching-primary', () => {
          const courseId = String(details.dataset.courseId || '');
          // 編輯課程 reopens the course wizard (single authoring path); the legacy
          // plan dialog stays reachable from inside the wizard as a fallback.
          if (courseId && typeof window.openTeacherCourseEditWorkspace === 'function') {
            void window.openTeacherCourseEditWorkspace(courseId, 2);
          } else {
            invokeOriginal(edit);
          }
        });
        button.setAttribute('data-teacher-edit-course-1014', '1');
        group.appendChild(button);
      }

      const more = document.createElement('details');
      more.setAttribute('data-teacher-course-more-1014', '1');
      more.className = 'relative';
      const moreSummary = document.createElement('summary');
      moreSummary.className = 'cursor-pointer list-none select-none rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-700';
      moreSummary.textContent = '⋯ 更多';
      moreSummary.setAttribute('aria-label', '更多課程操作');
      const menu = document.createElement('div');
      menu.setAttribute('data-teacher-course-more-menu-1014', '1');
      menu.className = 'absolute right-0 z-20 mt-1 flex w-44 flex-col gap-1 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg';
      const lifecycleSlot = document.createElement('div');
      lifecycleSlot.setAttribute('data-teacher-course-lifecycle-slot-1014', '1');
      lifecycleSlot.className = 'flex flex-col gap-1 [&_button]:w-full [&_button]:text-left';
      if (assignment) {
        // 學習指派的主要入口是「編輯課程」第 1 步；舊課程補指派才用這裡。
        const assignButton = makeCardButton('👥 補指派學員', 'w-full text-left text-[11px] px-2.5 py-1.5 rounded-lg border border-teal-200 bg-teal-50 font-bold text-teal-800', () => { more.open = false; invokeOriginal(assignment); });
        assignButton.setAttribute('data-teacher-assign-course-1014', '1');
        menu.appendChild(assignButton);
      }
      menu.appendChild(lifecycleSlot);
      if (remove) {
        const divider = document.createElement('div');
        divider.className = 'my-0.5 border-t border-slate-100';
        menu.appendChild(divider);
        menu.appendChild(makeCardButton('🗑️ 刪除課程', 'w-full text-left text-[11px] px-2.5 py-1.5 rounded-lg border border-rose-200 bg-rose-50 font-bold text-rose-700', () => { more.open = false; invokeOriginal(remove); }));
      }
      more.append(moreSummary, menu);
      group.appendChild(more);
      actionHost.appendChild(group);
    }

    // Lifecycle: the next step of a draft/ready course (發布檢查／正式發布) stays
    // visible; end/archive/reopen move into 更多.
    const lifecycle = actionHost.querySelector('[data-course-lifecycle-actions]') || details.querySelector('[data-course-lifecycle-actions]');
    const status = String(details.dataset.courseLifecycle || 'draft');
    const slot = group.querySelector('[data-teacher-course-lifecycle-slot-1014]');
    if (lifecycle && slot) {
      const primaryStep = status === 'draft' || status === 'ready';
      if (primaryStep) {
        if (lifecycle.parentElement !== group) group.insertBefore(lifecycle, group.firstChild);
      } else if (lifecycle.parentElement !== slot) {
        slot.appendChild(lifecycle);
      }
    }
    // 學習追蹤 is added by teacher-course-tracking-f2.js into the bar; keep it
    // next to the other primary actions, ahead of 更多.
    const tracking = actionHost.querySelector('[data-course-tracking-f2]');
    const moreNode = group.querySelector('[data-teacher-course-more-1014]');
    if (tracking && moreNode && tracking.parentElement !== group) group.insertBefore(tracking, moreNode);
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
