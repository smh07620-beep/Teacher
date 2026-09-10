/* Teacher 6.6 M1 · multi-role management UI */
(function () {
  'use strict';

  const ROLE_MAP = {
    learner: 'student',
    teacher: 'clinical_teacher',
    manager: 'education_admin',
    student: 'student',
    clinical_teacher: 'clinical_teacher',
    group_leader: 'group_leader',
    education_admin: 'education_admin',
    system_admin: 'system_admin',
    auditor: 'auditor'
  };

  const ROLE_LABELS = {
    student: '學員',
    clinical_teacher: '臨床教師',
    group_leader: '組長',
    education_admin: '教學管理者',
    system_admin: '系統管理者',
    auditor: '稽核／唯讀'
  };

  const ROLE_CODES = Object.keys(ROLE_LABELS);

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));

  function canonical(value) {
    return ROLE_MAP[String(value || '').trim()] || 'student';
  }

  function checkboxHTML(prefix) {
    return ROLE_CODES.map((role) => `
      <label class="flex items-center gap-2 text-xs bg-white border border-slate-200 rounded-lg px-2.5 py-2">
        <input type="checkbox" data-role66="${prefix}" value="${role}">
        <span>${esc(ROLE_LABELS[role])}</span>
      </label>
    `).join('');
  }

  function checkedRoles(prefix) {
    return Array.from(
      document.querySelectorAll(`[data-role66="${prefix}"]:checked`)
    ).map((el) => el.value);
  }

  function setChecked(prefix, roles) {
    const wanted = new Set((roles || []).map(canonical));
    document.querySelectorAll(`[data-role66="${prefix}"]`).forEach((el) => {
      el.checked = wanted.has(el.value);
    });
  }

  function installCreateRoles() {
    const primary = document.getElementById('admin-user-role');
    if (!primary || document.getElementById('role66-create-box')) return;

    const box = document.createElement('div');
    box.id = 'role66-create-box';
    box.className = 'sm:col-span-2 lg:col-span-4 rounded-xl border border-teal-100 bg-teal-50/40 p-3';
    box.innerHTML = `
      <div class="text-xs font-black text-teal-900">多重身分</div>
      <div class="text-[11px] text-slate-500 mt-1">
        上方「角色」保留為主要身分；這裡可再加第二或第三身分。
      </div>
      <div class="grid sm:grid-cols-3 lg:grid-cols-6 gap-2 mt-2">
        ${checkboxHTML('create')}
      </div>
    `;

    const label = primary.closest('label');
    if (label?.parentNode) {
      label.parentNode.insertBefore(box, label.nextSibling);
    }

    function syncPrimary() {
      const main = canonical(primary.value);
      const target = box.querySelector(`[value="${main}"]`);
      if (target) target.checked = true;
    }

    primary.addEventListener('change', syncPrimary);
    syncPrimary();

    if (window.__teacher66CreateWrapped) return;
    window.__teacher66CreateWrapped = true;

    window.createAdminUserAccount = async function () {
      const status = document.getElementById('admin-user-status');
      const key = typeof getAdminKey === 'function' ? await getAdminKey() : null;
      if (!key) return;

      const mainRole = canonical(
        document.getElementById('admin-user-role')?.value || 'student'
      );

      const roles = checkedRoles('create');
      if (!roles.includes(mainRole)) roles.unshift(mainRole);

      const payload = {
        username: document.getElementById('admin-user-username')?.value || '',
        password: document.getElementById('admin-user-password')?.value || '',
        name: document.getElementById('admin-user-name')?.value || '',
        empId: document.getElementById('admin-user-empid')?.value || '',
        role: mainRole,
        roles,
        preferredArea: document.getElementById('admin-user-area')?.value || 'internal',
        preferredGroup: document.getElementById('admin-user-group')?.value || 'grpBio'
      };

      if (status) status.textContent = '⏳ 建立帳號中…';

      const response = await fetch('/api/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Key': key
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (status) status.textContent = `❌ ${data.error || '建立帳號失敗'}`;
        return;
      }

      if (status) {
        status.textContent = `✅ 已建立 ${data.user?.name || payload.name}；身分：${(data.user?.roles || roles).map(r => ROLE_LABELS[r] || r).join('＋')}`;
      }

      const password = document.getElementById('admin-user-password');
      if (password) password.value = '';

      if (typeof renderAdminUserAccounts === 'function') {
        await renderAdminUserAccounts();
      }

      await loadRoleManager();
    };
  }

  let cachedUsers = [];

  function installRoleManager() {
    if (document.getElementById('role66-manager')) return;

    const panel = document.getElementById('admin-section-people');
    const section = panel?.querySelector('section');
    if (!section) return;

    const box = document.createElement('div');
    box.id = 'role66-manager';
    box.className = 'rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4 space-y-3';
    box.innerHTML = `
      <div>
        <div class="text-sm font-black text-indigo-950">👥 多重身分管理</div>
        <div class="text-[11px] text-indigo-700 mt-1">
          同一帳號可同時具備臨床教師、組長或管理身分。主要身分仍供舊版功能相容。
        </div>
      </div>

      <div class="grid md:grid-cols-2 gap-3">
        <label class="text-xs font-bold text-slate-600">
          帳號
          <select id="role66-user" class="learning-input mt-1">
            <option value="">選擇帳號</option>
          </select>
        </label>

        <label class="text-xs font-bold text-slate-600">
          主要身分
          <select id="role66-primary" class="learning-input mt-1">
            ${ROLE_CODES.map(role => `<option value="${role}">${esc(ROLE_LABELS[role])}</option>`).join('')}
          </select>
        </label>
      </div>

      <div class="grid sm:grid-cols-3 lg:grid-cols-6 gap-2">
        ${checkboxHTML('manage')}
      </div>

      <div class="flex items-center gap-3 flex-wrap">
        <button id="role66-save" type="button"
          class="bg-indigo-700 hover:bg-indigo-600 text-white text-xs font-bold px-4 py-2 rounded-xl">
          儲存身分
        </button>
        <button id="role66-refresh" type="button"
          class="bg-white border border-indigo-200 text-indigo-700 text-xs font-bold px-4 py-2 rounded-xl">
          ↻ 更新
        </button>
        <span id="role66-status" class="text-xs text-slate-500"></span>
      </div>
    `;

    section.appendChild(box);

    document.getElementById('role66-user')?.addEventListener('change', syncRoleManagerUser);

    document.getElementById('role66-primary')?.addEventListener('change', () => {
      const primary = document.getElementById('role66-primary')?.value;
      const el = document.querySelector(`[data-role66="manage"][value="${primary}"]`);
      if (el) el.checked = true;
    });

    document.getElementById('role66-save')?.addEventListener('click', saveRoleManager);
    document.getElementById('role66-refresh')?.addEventListener('click', loadRoleManager);
  }

  function syncRoleManagerUser() {
    const username = document.getElementById('role66-user')?.value || '';
    const user = cachedUsers.find((item) => item.username === username);
    if (!user) return;

    const primary = canonical(user.role);
    const roles = Array.isArray(user.roles) && user.roles.length ? user.roles : [primary];

    const select = document.getElementById('role66-primary');
    if (select) select.value = primary;

    setChecked('manage', roles);
  }

  async function loadRoleManager() {
    const select = document.getElementById('role66-user');
    if (!select) return;

    const status = document.getElementById('role66-status');
    if (status) status.textContent = '讀取帳號中…';

    const key = typeof getAdminKey === 'function' ? await getAdminKey() : null;
    if (!key) return;

    const response = await fetch('/api/users', {
      headers: { 'X-Admin-Key': key },
      cache: 'no-store'
    });

    const data = await response.json().catch(() => []);

    if (!response.ok) {
      if (status) status.textContent = `❌ ${data.error || '無法讀取帳號'}`;
      return;
    }

    cachedUsers = Array.isArray(data) ? data : [];

    const previous = select.value;

    select.innerHTML =
      '<option value="">選擇帳號</option>' +
      cachedUsers.map((user) => `
        <option value="${esc(user.username)}">
          ${esc(user.name || user.username)}（${esc(user.empId || user.username)}）
        </option>
      `).join('');

    if (cachedUsers.some((user) => user.username === previous)) {
      select.value = previous;
    }

    syncRoleManagerUser();

    if (status) status.textContent = `已載入 ${cachedUsers.length} 個帳號`;
  }

  async function saveRoleManager() {
    const username = document.getElementById('role66-user')?.value || '';
    const primary = canonical(document.getElementById('role66-primary')?.value);
    const status = document.getElementById('role66-status');

    if (!username) {
      if (status) status.textContent = '請先選擇帳號。';
      return;
    }

    const roles = checkedRoles('manage');
    if (!roles.includes(primary)) roles.unshift(primary);

    const key = typeof getAdminKey === 'function' ? await getAdminKey() : null;
    if (!key) return;

    if (status) status.textContent = '儲存身分中…';

    const response = await fetch(`/api/users/${encodeURIComponent(username)}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Key': key
      },
      body: JSON.stringify({
        role: primary,
        roles
      })
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (status) status.textContent = `❌ ${data.error || '更新失敗'}`;
      return;
    }

    if (status) {
      status.textContent =
        `✅ 已更新：${(data.user?.roles || roles).map(r => ROLE_LABELS[r] || r).join('＋')}。若修改的是目前登入帳號，請重新登入。`;
    }

    if (typeof renderAdminUserAccounts === 'function') {
      await renderAdminUserAccounts();
    }

    await loadRoleManager();
  }

  async function init() {
    installCreateRoles();
    installRoleManager();
    await loadRoleManager();
  }

  window.addEventListener('DOMContentLoaded', () => {
    setTimeout(init, 80);
  });
})();
