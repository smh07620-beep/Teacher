/* Teacher 10/14 cut: keep system administration focused on platform governance.
 * Teaching work stays in the teacher persona; this file changes presentation only.
 * Structural system navigation is owned by workspace-shell-70.js.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const params = new URLSearchParams(window.location.search);
  const requestedPersona = params.get('persona') || '';
  const requestedWorkspace = params.get('workspace') || '';
  const legacySystemWorkspaces = new Set(['people','system','worker','maintenance','audit']);
  const systemPersona = params.get('admin') === '1' && (
    requestedPersona === 'system' || (!requestedPersona && legacySystemWorkspaces.has(requestedWorkspace))
  );
  if (!roles.has('system_admin') || !has('system.manage') || !systemPersona) return;

  const navHost = document.querySelector('.v580-admin-groups');
  if (!navHost) return;

  const TEACHER_OWNED_NAV_IDS = Object.freeze([
    'admin-nav-course-materials',
    'admin-nav-assessment',
    'admin-nav-teacher',
    'admin-nav-results',
    'admin-nav-word',
  ]);

  function hideTeacherOwnedNavigation() {
    TEACHER_OWNED_NAV_IDS.forEach(id => {
      const item = document.getElementById(id);
      if (!item) return;
      item.classList.add('hidden');
      item.setAttribute('aria-hidden', 'true');
    });
  }

  function ensureFocusNote() {
    const banner = document.getElementById('rbac-workspace-banner');
    if (!banner) return;
    let note = document.getElementById('system-focus-note-1014');
    if (!note) {
      note = document.createElement('div');
      note.id = 'system-focus-note-1014';
      note.className = 'mt-2 text-[11px] text-slate-500';
      banner.appendChild(note);
    }
    const text = '日常教材、媒體、出題、紙本輸出與範本維護已移至「教師工作區」；系統管理只保留平台治理與高風險維運。';
    if (note.textContent !== text) note.textContent = text;
  }

  function leaveLegacyWordWorkspace() {
    if (params.get('workspace') !== 'word') return;
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', 'people');
    url.searchParams.set('persona', 'system');
    window.history?.replaceState?.(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    void window.switchAdminWorkspace?.('people', true);
  }

  function applySystemFocus() {
    hideTeacherOwnedNavigation();
    ensureFocusNote();
    return true;
  }

  applySystemFocus();
  leaveLegacyWordWorkspace();

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => applySystemFocus());
  window.AdminWorkspaceShell?.addAfterModal?.(({show}) => {
    if (show) applySystemFocus();
  });

  // Compatibility scripts may still insert teacher-owned controls later. Hide
  // those controls, but never rebuild or replace the canonical navigation tree.
  const observer = new MutationObserver(records => {
    const addedTeacherControl = records.some(record =>
      [...(record.addedNodes || [])].some(node =>
        node instanceof Element && (
          TEACHER_OWNED_NAV_IDS.some(id => node.id === id) ||
          TEACHER_OWNED_NAV_IDS.some(id => node.querySelector?.(`#${id}`))
        )
      )
    );
    if (addedTeacherControl) applySystemFocus();
  });
  observer.observe(navHost, {childList:true, subtree:true});

  window.SystemAdminFocus1014 = Object.freeze({
    apply: applySystemFocus,
    rebuild: applySystemFocus,
  });
})();
