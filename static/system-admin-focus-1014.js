/* Teacher 10/14 cut: keep system administration focused on platform governance.
 * Teaching work stays in the teacher persona; this file changes presentation only.
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

  const NAV_WORKSPACES = Object.freeze({
    'admin-nav-people': 'people',
    'admin-nav-system': 'system',
    'admin-nav-worker': 'worker',
    'admin-nav-maintenance': 'maintenance',
    'admin-nav-audit': 'audit',
  });

  function existing(id, label = '') {
    const item = document.getElementById(id);
    if (!item || item.disabled || item.classList.contains('hidden')) return null;
    if (label && item.textContent !== label) item.textContent = label;
    const workspace = NAV_WORKSPACES[id];
    if (workspace) {
      item.dataset.adminWorkspace = workspace;
      item.onclick = null;
      item.removeAttribute('onclick');
      item.setAttribute('data-csp-click', `switchAdminWorkspace('${workspace}',true)`);
    }
    item.classList.remove('hidden');
    item.removeAttribute('aria-hidden');
    return item;
  }

  function hideTeacherOwnedWordEntry() {
    const item = document.getElementById('admin-nav-word');
    if (!item) return;
    item.classList.add('hidden');
    item.setAttribute('aria-hidden', 'true');
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

  function leaveLegacyWordWorkspace() {
    if (params.get('workspace') !== 'word') return;
    params.set('workspace', 'people');
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', 'people');
    url.searchParams.set('persona', 'system');
    window.history?.replaceState?.(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    void window.switchAdminWorkspace?.('people', true);
  }

  function rebuild() {
    hideTeacherOwnedWordEntry();
    const spec = [
      ['人員與權限', [existing('admin-nav-people', '👥 人員與權限')]],
      ['系統與儲存', [
        existing('admin-nav-system', '⚙️ 系統與服務'),
        existing('admin-nav-worker', '🖥️ Worker / Job 狀態'),
      ]],
      ['資料保護', [existing('admin-nav-maintenance', '🛡️ 備份維護')]],
      ['安全與稽核', [existing('admin-nav-audit', '🔎 稽核紀錄')]],
    ].map(([label, buttons]) => [label, buttons.filter(Boolean)])
      .filter(([, buttons]) => buttons.length);

    const signature = groups => groups.map(group => {
      const label = group.querySelector('.v580-admin-group-label')?.textContent?.trim() || '';
      const ids = [...group.querySelectorAll('.admin-nav-btn')].map(button => button.id).join(',');
      return `${label}:${ids}`;
    }).join('|');
    const desiredSignature = spec.map(([label, buttons]) => `${label}:${buttons.map(button => button.id).join(',')}`).join('|');
    const currentSignature = signature([...navHost.querySelectorAll(':scope > .v580-admin-group')]);
    if (currentSignature !== desiredSignature) {
      navHost.replaceChildren(...spec.map(([label, buttons]) => navGroup(label, buttons)));
    }

    const banner = document.getElementById('rbac-workspace-banner');
    if (banner && !document.getElementById('system-focus-note-1014')) {
      const note = document.createElement('div');
      note.id = 'system-focus-note-1014';
      note.className = 'mt-2 text-[11px] text-slate-500';
      note.textContent = '日常教材、媒體、出題、紙本輸出與範本維護已移至「教師工作區」；系統管理只保留平台治理與高風險維運。';
      banner.appendChild(note);
    }
  }

  rebuild();
  leaveLegacyWordWorkspace();

  const observer = new MutationObserver(() => {
    const hasTeacherOwnedButton = navHost.querySelector('#admin-nav-course-materials,#admin-nav-assessment,#admin-nav-results,#admin-nav-word');
    const workerReady = document.getElementById('admin-nav-worker');
    if (hasTeacherOwnedButton || (workerReady && !navHost.contains(workerReady))) rebuild();
  });
  observer.observe(navHost, { childList: true, subtree: true });

  window.SystemAdminFocus1014 = Object.freeze({ rebuild });
})();
