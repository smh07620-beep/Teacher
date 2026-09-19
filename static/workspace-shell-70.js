/* Teacher 7.0 M2: split system administration into focused subworkspaces.
 *
 * This is presentation/navigation only. Canonical server-side RBAC remains
 * authoritative. professional_title / responsibility_tags never participate
 * in authorization decisions.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const surfaceKey = String(R.surface?.key || 'learner');
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

  function ensureSystemAdvancedMaintenance(){
    if(!isSystemAdmin)return;
    const systemPanel=document.getElementById('admin-section-system');
    if(!systemPanel)return;
    let details=document.getElementById('system-advanced-maintenance-75');
    if(!details){
      details=document.createElement('details');
      details.id='system-advanced-maintenance-75';
      details.className='bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden';
      details.innerHTML=`<summary class="cursor-pointer list-none p-5 flex items-center justify-between gap-3"><div><h4 class="font-black text-slate-950">🧰 進階維護</h4><p class="mt-1 text-xs text-slate-500">只在儲存搬移或維運異常時使用；日常教學不需要展開。</p></div><span class="text-xs font-bold text-slate-500">需要時展開</span></summary><div class="border-t border-slate-100 p-5 space-y-4"><div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">僅 system_admin 顯示。教材建立請使用「＋ 建立教學內容」；這裡只保留高風險維運工具。</div><div class="flex flex-wrap gap-2"><button id="system75-refresh-status" type="button" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold">🔄 重新檢查系統狀態</button><button id="system75-migrate-mega" type="button" class="rounded-xl bg-fuchsia-700 px-3 py-2 text-xs font-bold text-white">☁️ 搬移既有教材到 MEGA</button><button id="system75-migrate-r2" type="button" class="rounded-xl border border-cyan-300 bg-white px-3 py-2 text-xs font-bold text-cyan-800">☁️ R2 舊備援搬移</button></div></div>`;
      systemPanel.appendChild(details);
      details.querySelector('#system75-refresh-status').onclick=()=>window.renderAdminSystemStatus?.(true);
      details.querySelector('#system75-migrate-mega').onclick=async()=>{await window.migrateMaterialsToMega?.();await window.renderAdminSystemStatus?.(true);};
      details.querySelector('#system75-migrate-r2').onclick=async()=>{await window.migrateLocalMaterialsToR2?.();await window.renderAdminSystemStatus?.(true);};
    }
  }

  async function renderSystemSecurityStatus(force = false) {
    if (!isSystemAdmin) return false;
    const systemPanel = document.getElementById('admin-section-system');
    if (!systemPanel) return false;
    let section = document.getElementById('system-security-status-70');
    if (!section) {
      section = document.createElement('section');
      section.id = 'system-security-status-70';
      section.className = 'bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3';
      section.innerHTML = `
        <div class="flex items-start justify-between gap-3 flex-wrap">
          <div><h4 class="font-black text-slate-900">🛡️ 安全狀態</h4><p class="mt-1 text-xs text-slate-500">只顯示安全策略是否啟用，不回傳或顯示任何密鑰。</p></div>
          <button id="security-refresh-70" type="button" class="text-xs border border-slate-300 bg-white px-3 py-2 rounded-xl">🔄 更新</button>
        </div>
        <div id="security-status-70" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-2"><div class="text-xs text-slate-400">讀取安全狀態中…</div></div>`;
      systemPanel.appendChild(section);
      section.querySelector('#security-refresh-70').onclick = () => renderSystemSecurityStatus(true);
    }
    if (section.dataset.loaded === '1' && !force) return true;
    const securityHost = section.querySelector('#security-status-70');
    try {
      const securityResponse = await fetch('/api/security/status', {credentials: 'same-origin', cache: 'no-store'});
      const security = await securityResponse.json().catch(() => ({}));
      if (!securityResponse.ok) throw new Error(security.error || `讀取失敗（${securityResponse.status}）`);
      const chip = (label, value, good=true) => `<div class="rounded-xl border ${good?'border-emerald-200 bg-emerald-50':'border-amber-200 bg-amber-50'} p-3"><div class="text-[11px] font-bold text-slate-500">${escapeHtml(label)}</div><div class="mt-1 text-sm font-black text-slate-900">${escapeHtml(value)}</div></div>`;
      securityHost.innerHTML = [
        chip('Session 期限', `${Number(security.sessionHours||0)} 小時`, Number(security.sessionHours||0)>0),
        chip('Secure Cookie', security.secureCookie?'已啟用':'未啟用', !!security.secureCookie),
        chip('CSRF Origin 檢查', security.csrfOriginCheck?'已啟用':'未啟用', !!security.csrfOriginCheck),
        chip('登入失敗限制', `${Number(security.loginRateLimitMaxAttempts||0)} 次`, Number(security.loginRateLimitMaxAttempts||0)>0),
        chip('CSP', security.cspEnforced?'強制模式':'Report-Only', !!security.cspEnforced),
        chip('Production Secret', security.productionSecretRequired?'正式環境必填':'非強制', !!security.productionSecretRequired),
      ].join('');
      section.dataset.loaded = '1';
      return true;
    } catch (error) {
      if (securityHost) securityHost.innerHTML = `<div class="sm:col-span-2 lg:col-span-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">⚠️ ${escapeHtml(error.message)}</div>`;
      return false;
    }
  }

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

  const adminShell = window.AdminWorkspaceShell;
  adminShell?.registerWorkspace('maintenance', async ({force}) => {
      if (!canMaintenance) return false;
      moveMaintenanceCard();
      showOnlyPanel(maintenancePanel, 'maintenance', 'admin-nav-maintenance');
      return true;
  });
  adminShell?.registerWorkspace('audit', async ({force}) => {
      if (!canAudit) return false;
      showOnlyPanel(auditPanel, 'audit', 'admin-nav-audit');
      await renderAudit(Boolean(force));
      return true;
  });
  adminShell?.addModalOpenOverride(async ({show}) => {
    if (show && isAuditor && canAudit) {
      modal.classList.remove('hidden');
      modal.setAttribute('aria-hidden', 'false');
      document.body?.classList.add('overflow-hidden');
      await window.switchAdminWorkspace('audit', true);
      return {handled:true, result:true};
    }
    return null;
  });
  adminShell?.addAfterWorkspace(({workspace}) => {
    if (workspace === 'system') void renderSystemSecurityStatus(false);
  });
  adminShell?.addAfterModal(({show}) => {
    if (show) {
      moveMaintenanceCard();
      ensureSystemAdvancedMaintenance();
      if (isSystemAdmin) buildSystemNavigation();
      else addEducationMaintenanceNavigation();
    }
  });

  ensureSystemAdvancedMaintenance();
  buildSystemNavigation();
  addEducationMaintenanceNavigation();
  exposeAuditorEntry();

  if (isAuditor && canAudit) {
    const banner = document.getElementById('rbac-workspace-banner');
    if (banner) banner.classList.add('hidden');
  }
})();
