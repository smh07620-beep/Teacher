/* Teacher 7.0 M2: split system administration into focused subworkspaces.
 *
 * This is presentation/navigation only. Canonical server-side RBAC remains
 * authoritative. professional_title / responsibility_tags never participate
 * in authorization decisions.
 */
(function () {
  'use strict';

  const R = window.TeacherRBAC681 || {};
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  // Multi-role accounts must have exactly one presentation surface. Prefer the
  // canonical surface already resolved by rbac-ui-681; the fallback mirrors its
  // precedence so an auxiliary auditor role can never redraw a teacher/admin UI.
  const surfaceKey = String(R.surface?.key || (
    roles.has('system_admin') ? 'system' :
    roles.has('education_admin') || has('education.cross_group.manage') ? 'education' :
    roles.has('group_leader') || roles.has('clinical_teacher') ? 'teacher' :
    roles.has('auditor') ? 'audit' : 'learner'
  ));
  const isSystemAdmin = surfaceKey === 'system';
  const isEducationAdmin = surfaceKey === 'education';
  const isAuditor = surfaceKey === 'audit';
  const canMaintenance = has('backup.manage') || has('education.cross_group.manage');
  const canAudit = has('audit.read') || has('audit.view');
  const workspaceHost = document.getElementById('admin-workspace-content');
  const navHost = document.querySelector('.v580-admin-groups');
  const modal = document.getElementById('admin-modal');

  if (!workspaceHost || !navHost || !modal) return;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function ensurePanel(id, className = '') {
    let panel = document.getElementById(id);
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = id;
    panel.className = `admin-section-panel hidden space-y-5 overflow-y-auto max-h-[68vh] pr-1 ${className}`.trim();
    workspaceHost.appendChild(panel);
    return panel;
  }

  const maintenancePanel = ensurePanel('admin-section-maintenance');
  const auditPanel = ensurePanel('admin-section-audit');

  function moveMaintenanceCard() {
    const card = document.getElementById('teacher64-maintenance');
    if (card && card.parentElement !== maintenancePanel) maintenancePanel.appendChild(card);
  }

  moveMaintenanceCard();
  const maintenanceObserver = new MutationObserver(moveMaintenanceCard);
  maintenanceObserver.observe(workspaceHost, {childList: true, subtree: true});

  function button(id, label, workspace) {
    let item = document.getElementById(id);
    if (!item) {
      item = document.createElement('button');
      item.id = id;
      item.type = 'button';
      item.className = 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
    }
    item.textContent = label;
    item.onclick = () => window.switchAdminWorkspace?.(workspace, true);
    item.classList.remove('hidden');
    item.disabled = false;
    item.setAttribute('aria-hidden', 'false');
    return item;
  }

  function navGroup(label, buttons, compact = false) {
    const section = document.createElement('section');
    section.className = `v580-admin-group${compact ? ' compact' : ''}`;
    const title = document.createElement('span');
    title.className = 'v580-admin-group-label';
    title.textContent = label;
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    buttons.filter(Boolean).forEach(item => actions.appendChild(item));
    section.append(title, actions);
    return section;
  }

  function existing(id) {
    const item = document.getElementById(id);
    if (!item || item.classList.contains('hidden') || item.disabled) return null;
    return item;
  }

  function buildSystemNavigation() {
    if (!isSystemAdmin) return;
    const teaching = [
      existing('admin-nav-course-materials'),
      existing('admin-nav-assessment'),
      existing('admin-nav-teacher'),
      existing('admin-nav-results'),
      existing('admin-nav-word')
    ];
    const people = [existing('admin-nav-people')];
    const system = [existing('admin-nav-system')];
    const maintenance = canMaintenance ? [button('admin-nav-maintenance', '🛡️ 備份維護', 'maintenance')] : [];
    const audit = canAudit ? [button('admin-nav-audit', '🔎 稽核紀錄', 'audit')] : [];
    navHost.replaceChildren(
      navGroup('教學管理', teaching),
      navGroup('人員與權限', people, true),
      navGroup('系統與儲存', system, true),
      navGroup('備份維護', maintenance, true),
      navGroup('安全與稽核', audit, true)
    );
  }

  function addEducationMaintenanceNavigation() {
    if (!isEducationAdmin || !canMaintenance) return;
    if (document.getElementById('admin-nav-maintenance')) return;
    navHost.appendChild(navGroup('資料保護', [button('admin-nav-maintenance', '🛡️ 備份維護', 'maintenance')], true));
  }

  function exposeAuditorEntry() {
    if (!isAuditor || !canAudit) return;
    const entries = [document.getElementById('workspace-entry'), ...document.querySelectorAll('.v575-manage-direct')].filter(Boolean);
    entries.forEach(entry => {
      entry.classList.remove('hidden');
      entry.removeAttribute('aria-hidden');
      entry.disabled = false;
      entry.dataset.workspaceSurface = 'audit';
      if (entry.id === 'workspace-entry') entry.innerHTML = '<span>🔎</span>稽核檢視';
      else entry.textContent = '🔎 稽核檢視';
      entry.title = '唯讀檢視授權的稽核紀錄。';
      entry.onclick = event => {
        event?.preventDefault?.();
        window.toggleAdminModal?.(true);
      };
    });
    navHost.replaceChildren(navGroup('稽核／唯讀', [button('admin-nav-audit', '🔎 稽核紀錄', 'audit')]));
  }

  function markActive(id) {
    document.querySelectorAll('.admin-nav-btn').forEach(item => {
      const active = item.id === id;
      item.classList.toggle('bg-teal-700', active);
      item.classList.toggle('text-white', active);
      item.classList.toggle('shadow-sm', active);
      item.classList.toggle('bg-slate-100', !active);
      item.classList.toggle('text-slate-600', !active);
    });
  }

  function showOnlyPanel(panel, sectionName, navId) {
    document.querySelectorAll('.admin-section-panel').forEach(item => item.classList.add('hidden'));
    panel.classList.remove('hidden');
    modal.dataset.section = sectionName;
    markActive(navId);
    const status = document.getElementById('admin-workspace-status');
    if (status) {
      status.textContent = sectionName === 'audit'
        ? '唯讀稽核資料；此工作區不提供新增、修改、發布或刪除操作。'
        : '敏感備份／還原操作會要求短效再次驗證。';
    }
  }

  function groupLabel(group) {
    const catalog = window.GROUPS || {};
    return catalog[group]?.name || catalog[group]?.label || group || '—';
  }

  async function renderAudit(force = false) {
    if (!canAudit) return false;
    if (auditPanel.dataset.loaded === '1' && !force) return true;
    auditPanel.innerHTML = `
      <section class="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
        <div class="flex items-start justify-between gap-3 flex-wrap">
          <div><h4 class="font-black text-slate-950 text-lg">🔎 稽核／唯讀紀錄</h4>
          <p class="text-xs text-slate-500 mt-1">目前顯示 PGY 指派、送審與簽核流程紀錄。所有資料皆為唯讀。</p></div>
          <button id="audit-refresh-70" type="button" class="text-xs border border-slate-300 bg-white px-3 py-2 rounded-xl">🔄 更新</button>
        </div>
        <div id="audit-status-70" class="text-xs text-slate-500">讀取中…</div>
        <div class="overflow-x-auto border border-slate-200 rounded-xl">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50"><tr><th class="p-3">時間</th><th class="p-3">動作</th><th class="p-3">操作者</th><th class="p-3">組別</th><th class="p-3">項目</th><th class="p-3">狀態</th></tr></thead>
            <tbody id="audit-body-70" class="divide-y divide-slate-100"></tbody>
          </table>
        </div>
      </section>`;
    document.getElementById('audit-refresh-70').onclick = () => renderAudit(true);
    const status = document.getElementById('audit-status-70');
    const body = document.getElementById('audit-body-70');
    try {
      const response = await fetch('/api/pgy/audit', {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error((data && data.error) || `讀取失敗（${response.status}）`);
      const rows = Array.isArray(data) ? data : [];
      body.innerHTML = rows.length ? rows.map(row => `
        <tr>
          <td class="p-3 whitespace-nowrap text-slate-500">${escapeHtml(row.createdAt || '')}</td>
          <td class="p-3 font-bold text-slate-800">${escapeHtml(row.action || '—')}</td>
          <td class="p-3"><div class="font-semibold">${escapeHtml(row.actorUsername || '—')}</div><div class="text-[10px] text-slate-400">${escapeHtml(row.actorRole || '')}</div></td>
          <td class="p-3 whitespace-nowrap">${escapeHtml(groupLabel(row.group))}</td>
          <td class="p-3"><div class="font-semibold">${escapeHtml(row.title || row.assignmentId || '—')}</div><div class="text-[10px] text-slate-400">${escapeHtml(row.assignmentId || '')}</div></td>
          <td class="p-3 whitespace-nowrap">${escapeHtml([row.fromStatus, row.toStatus].filter(Boolean).join(' → ') || '—')}</td>
        </tr>`).join('') : '<tr><td colspan="6" class="p-6 text-center text-slate-400">目前沒有稽核紀錄。</td></tr>';
      status.textContent = `共 ${rows.length} 筆紀錄 · 唯讀`;
      auditPanel.dataset.loaded = '1';
      return true;
    } catch (error) {
      status.textContent = `❌ ${error.message || '無法讀取稽核紀錄'}`;
      body.innerHTML = '<tr><td colspan="6" class="p-6 text-center text-rose-500">稽核資料讀取失敗。</td></tr>';
      return false;
    }
  }

  const previousSwitch = window.switchAdminWorkspace;
  window.switchAdminWorkspace = async function (name, force) {
    if (name === 'maintenance') {
      if (!canMaintenance) return false;
      moveMaintenanceCard();
      showOnlyPanel(maintenancePanel, 'maintenance', 'admin-nav-maintenance');
      return true;
    }
    if (name === 'audit') {
      if (!canAudit) return false;
      showOnlyPanel(auditPanel, 'audit', 'admin-nav-audit');
      await renderAudit(Boolean(force));
      return true;
    }
    return typeof previousSwitch === 'function' ? previousSwitch(name, force) : false;
  };

  const previousToggle = window.toggleAdminModal;
  window.toggleAdminModal = async function (show) {
    if (show && isAuditor && canAudit && !R.workspaceAccess) {
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
      document.body?.classList.add('overflow-hidden');
      await window.switchAdminWorkspace('audit', true);
      return true;
    }
    const result = typeof previousToggle === 'function' ? await previousToggle(show) : false;
    if (show) {
      moveMaintenanceCard();
      if (isSystemAdmin) buildSystemNavigation();
      else addEducationMaintenanceNavigation();
    }
    return result;
  };

  buildSystemNavigation();
  addEducationMaintenanceNavigation();
  exposeAuditorEntry();

  if (isAuditor && canAudit) {
    const banner = document.getElementById('rbac-workspace-banner');
    if (banner) banner.classList.add('hidden');
  }
})();