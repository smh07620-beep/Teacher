/* Teacher 7.0 M3: system-admin Worker / job status surface.
 *
 * Read-only operational UI. Server-side RBAC remains authoritative and this
 * file never sends worker tokens, storage credentials, ADMIN_KEY headers, or
 * mutation requests.
 */
(function () {
  'use strict';

  const R = window.TeacherRBAC681 || {};
  const roles = R.roles instanceof Set ? R.roles : new Set();
  if (!roles.has('system_admin')) return;

  const workspaceHost = document.getElementById('admin-workspace-content');
  const navHost = document.querySelector('.v580-admin-groups');
  const modal = document.getElementById('admin-modal');
  if (!workspaceHost || !navHost || !modal) return;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  const formatWhen = value => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString();
  };

  const statusMeta = status => ({
    online: ['🟢', '在線', 'text-emerald-700 bg-emerald-50 border-emerald-200'],
    busy: ['🔵', '處理中', 'text-sky-700 bg-sky-50 border-sky-200'],
    offline: ['⚪', '離線', 'text-slate-600 bg-slate-50 border-slate-200']
  }[status] || ['⚪', status || '未知', 'text-slate-600 bg-slate-50 border-slate-200']);

  let panel = document.getElementById('admin-section-worker');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'admin-section-worker';
    panel.className = 'admin-section-panel hidden space-y-5 overflow-y-auto max-h-[68vh] pr-1';
    workspaceHost.appendChild(panel);
  }

  let refreshTimer = null;
  let loading = false;

  function workerButton() {
    let button = document.getElementById('admin-nav-worker');
    if (!button) {
      button = document.createElement('button');
      button.id = 'admin-nav-worker';
      button.type = 'button';
      button.className = 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
      button.textContent = '🖥️ Worker / Job 狀態';
      button.onclick = () => window.switchAdminWorkspace?.('worker', true);
    }
    button.disabled = false;
    button.classList.remove('hidden');
    button.setAttribute('aria-hidden', 'false');
    return button;
  }

  function ensureNavigation() {
    if (document.getElementById('admin-nav-worker')) return;
    const groups = [...navHost.querySelectorAll('.v580-admin-group')];
    const systemGroup = groups.find(group => group.querySelector('.v580-admin-group-label')?.textContent?.includes('系統與儲存'));
    if (systemGroup) {
      const actions = systemGroup.querySelector('.v580-admin-group-actions');
      actions?.appendChild(workerButton());
      return;
    }
    const group = document.createElement('section');
    group.className = 'v580-admin-group compact';
    const label = document.createElement('span');
    label.className = 'v580-admin-group-label';
    label.textContent = 'Worker 與佇列';
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    actions.appendChild(workerButton());
    group.append(label, actions);
    navHost.appendChild(group);
  }

  function markActive() {
    document.querySelectorAll('.admin-nav-btn').forEach(item => {
      const active = item.id === 'admin-nav-worker';
      item.classList.toggle('bg-teal-700', active);
      item.classList.toggle('text-white', active);
      item.classList.toggle('shadow-sm', active);
      item.classList.toggle('bg-slate-100', !active);
      item.classList.toggle('text-slate-600', !active);
    });
  }

  function scheduleRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = null;
    if (!panel.classList.contains('hidden') && !modal.classList.contains('hidden')) {
      refreshTimer = setTimeout(() => renderWorkerStatus(false), 15000);
    }
  }

  function queueCard(icon, title, value, note) {
    return `<div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="text-xs font-bold text-slate-500">${icon} ${escapeHtml(title)}</div>
      <div class="text-2xl font-black text-slate-950 mt-1">${Number(value || 0)}</div>
      <div class="text-[11px] text-slate-400 mt-1">${escapeHtml(note)}</div>
    </div>`;
  }

  function workerCard(worker) {
    const [icon, label, classes] = statusMeta(worker.status);
    const updateText = worker.updateAvailable
      ? '<span class="inline-flex px-2 py-1 rounded-full border border-amber-200 bg-amber-50 text-amber-700 font-bold">⚠ 最近安全更新檢查有版本變更</span>'
      : '<span class="inline-flex px-2 py-1 rounded-full border border-emerald-200 bg-emerald-50 text-emerald-700 font-bold">✓ 無待更新訊號</span>';
    return `<article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div class="font-black text-slate-950">${escapeHtml(worker.workerId || '未命名 Worker')}</div>
          <div class="text-[11px] text-slate-500 mt-1">最後 heartbeat：${formatWhen(worker.lastSeen)}</div>
        </div>
        <span class="text-xs px-2.5 py-1 rounded-full border font-bold ${classes}">${icon} ${label}</span>
      </div>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-2 text-xs">
        <div class="rounded-xl bg-slate-50 p-2.5"><div class="text-slate-400">Worker version</div><div class="font-bold mt-1">${escapeHtml(worker.workerVersion || '—')}</div></div>
        <div class="rounded-xl bg-slate-50 p-2.5"><div class="text-slate-400">Git SHA</div><div class="font-mono font-bold mt-1">${escapeHtml((worker.workerSha || '—').slice(0, 12))}</div></div>
        <div class="rounded-xl bg-slate-50 p-2.5"><div class="text-slate-400">Branch</div><div class="font-bold mt-1">${escapeHtml(worker.workerBranch || '—')}</div></div>
        <div class="rounded-xl bg-slate-50 p-2.5"><div class="text-slate-400">目前工作</div><div class="font-mono font-bold mt-1 break-all">${escapeHtml(worker.currentJobId || '閒置')}</div></div>
      </div>
      <div class="flex flex-wrap gap-2 text-[11px]">
        <span class="px-2 py-1 rounded-full bg-slate-100 text-slate-700">FFmpeg ${worker.ffmpeg ? '✓' : '✕'}</span>
        <span class="px-2 py-1 rounded-full bg-slate-100 text-slate-700">LibreOffice ${worker.libreOffice ? '✓' : '✕'}</span>
        ${updateText}
      </div>
      <div class="text-[11px] text-slate-500">最近自動更新檢查：${formatWhen(worker.lastUpdateCheckAt)}。更新只會在 Worker 閒置時於本機執行，Web 端不能遠端下令 pull。</div>
    </article>`;
  }

  function jobRows(jobs) {
    if (!jobs.length) return '<tr><td colspan="5" class="p-5 text-center text-slate-400">目前沒有背景教材工作。</td></tr>';
    return jobs.map(job => `<tr>
      <td class="p-3 font-mono text-[11px] break-all">${escapeHtml(job.id || '')}</td>
      <td class="p-3"><div class="font-semibold text-slate-800">${escapeHtml(job.title || job.originalName || '未命名教材')}</div><div class="text-[10px] text-slate-400">${escapeHtml(job.originalName || '')}</div></td>
      <td class="p-3 whitespace-nowrap font-bold">${escapeHtml(job.status || '')}</td>
      <td class="p-3 text-slate-500">${escapeHtml(job.stage || '')}</td>
      <td class="p-3 whitespace-nowrap text-slate-500">${formatWhen(job.updatedAt || job.createdAt)}</td>
    </tr>`).join('');
  }

  function firstRunGuide() {
    return `<details class="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4">
      <summary class="cursor-pointer font-black text-indigo-950">🧰 本機 Worker 第一次安裝（只需要做一次）</summary>
      <div class="mt-3 text-xs text-indigo-950 space-y-2 leading-6">
        <p>第一次一定要在院內 Windows 電腦實際設定，因為 Python、FFmpeg、LibreOffice、MEGAcmd、Worker Token 與本機儲存登入不能由 Render 遠端安裝。</p>
        <ol class="list-decimal pl-5 space-y-1">
          <li>安裝 Git、Python 3.12、FFmpeg/FFprobe、LibreOffice、官方 MEGAcmd。</li>
          <li>把 Teacher repository 放在固定目錄，例如 <code>C:\\TeacherWorker</code>，並保持在 <code>main</code> branch。</li>
          <li>建立虛擬環境：<code>py -3.12 -m venv .venv</code>。</li>
          <li>安裝依賴：<code>.venv\\Scripts\\python.exe -m pip install -r requirements.txt</code>。</li>
          <li>建立只存在本機的 <code>.local-worker.env</code>，至少填入 <code>TEACHER_BASE_URL</code>、<code>MATERIAL_WORKER_TOKEN</code> 與 MEGA 登入資料。</li>
          <li>第一次手動啟動：<code>powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\TeacherWorker\\run_material_worker_autostart.ps1"</code>，確認本頁顯示 🟢 在線。</li>
          <li>確認正常後，再把同一個 command 放進 Windows Task Scheduler 的「登入時」觸發器。</li>
        </ol>
        <p class="font-bold">完成這一次後，正常版本更新會由安全 updater 在閒置時自動 fast-forward <code>origin/main</code>，需要新版程式時 launcher 會自動重啟；不需要每次都人工更新。</p>
      </div>
    </details>`;
  }

  async function renderWorkerStatus(force = false) {
    if (loading && !force) return;
    loading = true;
    panel.innerHTML = `<section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div class="animate-pulse text-sm text-slate-400">讀取 Worker 與佇列狀態中…</div></section>${firstRunGuide()}`;
    try {
      const response = await fetch(`/api/material-jobs?limit=12${force ? '&refresh=1' : ''}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = `/login?next=${next}`;
        return;
      }
      if (!response.ok) throw new Error(data.error || `讀取失敗（${response.status}）`);
      const workers = Array.isArray(data.workers) ? data.workers : [];
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      const staging = data.staging || {};
      panel.innerHTML = `
        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          <div class="flex items-start justify-between gap-3 flex-wrap">
            <div><h4 class="font-black text-slate-950 text-lg">🖥️ Worker / Job 狀態</h4>
            <p class="text-xs text-slate-500 mt-1">只顯示非敏感營運資訊；Worker 與 Web 之間只有 outbound HTTPS，不開放院內電腦 inbound port。</p></div>
            <button id="worker-refresh-70" type="button" class="text-xs border border-slate-300 bg-white px-3 py-2 rounded-xl">↻ 立即更新</button>
          </div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            ${queueCard('⏳', '待處理', data.pendingJobs, 'queued + retry_wait')}
            ${queueCard('⚙️', '處理中', data.processingJobs, '正在由本機 Worker 執行')}
            ${queueCard('🔁', '等待重試', data.retryJobs, '保留原始檔後再次處理')}
            ${queueCard('❌', '失敗', data.failedJobs, '需要檢查錯誤或人工重試')}
          </div>
          <div class="text-xs rounded-xl bg-slate-50 border border-slate-200 px-3 py-2">Shared staging：<b>${escapeHtml(staging.backend || '未設定')}</b> · ${staging.available ? '可用' : '不可用'}${staging.shared ? ' · Web/Worker 共用' : ''}</div>
        </section>
        <section class="space-y-3">
          <div class="flex items-center justify-between"><h5 class="font-black text-slate-900">本機 Worker</h5><span class="text-xs text-slate-400">${workers.length} 台有 heartbeat 紀錄</span></div>
          ${workers.length ? workers.map(workerCard).join('') : '<div class="rounded-2xl border border-dashed border-amber-300 bg-amber-50 p-5 text-sm text-amber-800">⚠ 尚未收到本機 Worker heartbeat。若這是第一次使用，請展開下方「第一次安裝」完成院內電腦設定。</div>'}
        </section>
        <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
          <div class="flex items-center justify-between gap-3"><h5 class="font-black text-slate-900">最近背景工作</h5><span class="text-[11px] text-slate-400">最近 ${jobs.length} 筆</span></div>
          <div class="overflow-x-auto border border-slate-200 rounded-xl"><table class="w-full text-left text-xs"><thead class="bg-slate-50"><tr><th class="p-3">Job ID</th><th class="p-3">教材</th><th class="p-3">狀態</th><th class="p-3">階段</th><th class="p-3">更新時間</th></tr></thead><tbody class="divide-y divide-slate-100">${jobRows(jobs)}</tbody></table></div>
        </section>
        ${firstRunGuide()}`;
      document.getElementById('worker-refresh-70').onclick = () => renderWorkerStatus(true);
    } catch (error) {
      panel.innerHTML = `<section class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${escapeHtml(error.message || '無法讀取 Worker 狀態')}</section>${firstRunGuide()}`;
    } finally {
      loading = false;
      scheduleRefresh();
    }
  }

  const previousSwitch = window.switchAdminWorkspace;
  window.switchAdminWorkspace = async function (name, force) {
    if (name === 'worker') {
      document.querySelectorAll('.admin-section-panel').forEach(item => item.classList.add('hidden'));
      panel.classList.remove('hidden');
      modal.dataset.section = 'worker';
      markActive();
      const status = document.getElementById('admin-workspace-status');
      if (status) status.textContent = '系統管理者唯讀檢視 Worker heartbeat、背景佇列與自動更新訊號。';
      await renderWorkerStatus(Boolean(force));
      return true;
    }
    if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
    return typeof previousSwitch === 'function' ? previousSwitch(name, force) : false;
  };

  const previousToggle = window.toggleAdminModal;
  window.toggleAdminModal = async function (show) {
    const result = typeof previousToggle === 'function' ? await previousToggle(show) : false;
    if (show) ensureNavigation();
    else if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
    return result;
  };

  ensureNavigation();
})();
