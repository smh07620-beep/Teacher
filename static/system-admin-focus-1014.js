/* Teacher 10/14 cut: keep system administration focused on platform governance.
 * Teaching work stays in the teacher persona; this file changes presentation only.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const params = new URLSearchParams(window.location.search);
  const systemPersona = params.get('admin') === '1' && params.get('persona') !== 'teacher';
  if (!roles.has('system_admin') || !has('system.manage') || !systemPersona) return;

  const navHost = document.querySelector('.v580-admin-groups');
  if (!navHost) return;

  function existing(id, label = '') {
    const item = document.getElementById(id);
    if (!item || item.disabled || item.classList.contains('hidden')) return null;
    if (label) item.textContent = label;
    item.classList.remove('hidden');
    item.removeAttribute('aria-hidden');
    return item;
  }

  function navGroup(label, buttons) {
    const usable = buttons.filter(Boolean);
    if (!usable.length) return null;
    const section = document.createElement('section');
    section.className = 'v580-admin-group compact';
    const heading = document.createElement('span');
    heading.className = 'v580-admin-group-label';
    heading.textContent = label;
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    usable.forEach(button => actions.appendChild(button));
    section.append(heading, actions);
    return section;
  }

  function rebuild() {
    const groups = [
      navGroup('人員與權限', [existing('admin-nav-people', '👥 人員與權限')]),
      navGroup('正式文件治理', [existing('admin-nav-word', '📄 紙本文件範本')]),
      navGroup('系統與儲存', [
        existing('admin-nav-system', '⚙️ 系統與服務'),
        existing('admin-nav-worker', '🖥️ Worker / Job 狀態'),
      ]),
      navGroup('資料保護', [existing('admin-nav-maintenance', '🛡️ 備份維護')]),
      navGroup('安全與稽核', [existing('admin-nav-audit', '🔎 稽核紀錄')]),
    ].filter(Boolean);
    navHost.replaceChildren(...groups);

    const banner = document.getElementById('rbac-workspace-banner');
    if (banner && !document.getElementById('system-focus-note-1014')) {
      const note = document.createElement('div');
      note.id = 'system-focus-note-1014';
      note.className = 'mt-2 text-[11px] text-slate-500';
      note.textContent = '日常教材、媒體、出題與紙本輸出已移至「教師工作區」；系統管理只保留平台治理與高風險維運。';
      banner.appendChild(note);
    }
  }

  rebuild();

  const observer = new MutationObserver(() => {
    const hasTeachingButton = navHost.querySelector('#admin-nav-course-materials,#admin-nav-assessment,#admin-nav-results');
    const workerReady = document.getElementById('admin-nav-worker');
    if (hasTeachingButton || (workerReady && !navHost.contains(workerReady))) rebuild();
  });
  observer.observe(navHost, { childList: true, subtree: true });

  window.SystemAdminFocus1014 = Object.freeze({ rebuild });
})();
