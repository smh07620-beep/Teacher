/* Teacher 10/14: keep persona switching stable and bind the legacy platform entry. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const canSystem = roles.has('system_admin') && typeof R.hasPermission === 'function' && R.hasPermission('system.manage');

  function systemUrl() {
    const url = new URL(window.location.href);
    url.searchParams.set('admin', '1');
    url.searchParams.set('workspace', 'people');
    url.searchParams.set('persona', 'system');
    url.searchParams.delete('teacherMode');
    return `${url.pathname}${url.search}${url.hash}`;
  }

  function bindPlatformEntry() {
    if (!canSystem) return;
    document.querySelectorAll('.v575-manage-direct').forEach(entry => {
      entry.textContent = '⚙ 平台管理';
      entry.title = '帳號、權限、平台設定與高風險維運';
      entry.dataset.workspaceSurface = 'system';
      if (entry.dataset.teacher1014PlatformBound === '1') return;
      entry.dataset.teacher1014PlatformBound = '1';
      entry.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        window.location.assign(systemUrl());
      }, true);
    });
  }

  function sync() {
    // teacher-workspace-1014.js is the single owner of the persona switcher.
    // Do not remove its system button here; doing so caused the third persona
    // to disappear on first paint and reappear after later workspace updates.
    bindPlatformEntry();
  }

  sync();
  setTimeout(sync, 0);
  setTimeout(sync, 400);
  window.TeacherWorkspaceNavFix1014 = Object.freeze({ sync });
})();
