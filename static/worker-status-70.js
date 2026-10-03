/* Teacher 7.0 M3: system-admin Worker / job status and incident response surface.
 *
 * Server-side RBAC remains authoritative. Incident response mutations use the
 * authenticated session only and cannot mark a live operational failure resolved.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
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

  const formatDuration = value => {
    const seconds = Math.max(0, Number(value || 0));
    if (!seconds) return '—';
    if (seconds < 60) return `${Math.round(seconds)} 秒`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} 分`;
    return `${(seconds / 3600).toFixed(1)} 小時`;
  };

  const elapsedFrom = value => {
    if (!value) return '—';
    const started = new Date(value).getTime();
    if (!Number.isFinite(started)) return '—';
    return formatDuration(Math.max(0, (Date.now() - started) / 1000));
  };

  const statusMeta = status => ({
    online: ['🟢', '在線', 'text-emerald-700 bg-emerald-50 border-emerald-200'],
    busy: ['🔵', '處理中', 'text-sky-700 bg-sky-50 border-sky-200'],
    offline: ['⚪', '離線', 'text-slate-600 bg-slate-50 border-slate-200']
  }[status] || ['⚪', status || '未知', 'text-slate-600 bg-slate-50 border-slate-200']);

  const jobMeta = status => ({
    queued: ['⏳', '等待處理', 'text-slate-700 bg-slate-50 border-slate-200'],
    processing: ['⚙️', '處理中', 'text-sky-700 bg-sky-50 border-sky-200'],
    retry_wait: ['🔁', '等待重試', 'text-amber-700 bg-amber-50 border-amber-200'],
    completed: ['✅', '已完成', 'text-emerald-700 bg-emerald-50 border-emerald-200'],
    failed: ['❌', '失敗', 'text-rose-700 bg-rose-50 border-rose-200'],
    cancelled: ['⏹', '已取消', 'text-slate-600 bg-slate-50 border-slate-200']
  }[status] || ['•', status || '未知', 'text-slate-600 bg-slate-50 border-slate-200']);

  const jobHealthMeta = job => ({
    active: ['🟢', '持續處理', 'text-emerald-700 bg-emerald-50 border-emerald-200'],
    heartbeat_delayed: ['🟠', '回報延遲', 'text-amber-700 bg-amber-50 border-amber-200'],
    stalled: ['🔴', '可能卡住', 'text-rose-700 bg-rose-50 border-rose-200'],
    queued: ['⚪', '等待 Worker', 'text-slate-600 bg-slate-50 border-slate-200'],
    retry_wait: ['🟠', '等待重試', 'text-amber-700 bg-amber-50 border-amber-200'],
    completed: ['🟢', '已完成', 'text-emerald-700 bg-emerald-50 border-emerald-200'],
    failed: ['🔴', '需要處理', 'text-rose-700 bg-rose-50 border-rose-200'],
    cancelled: ['⚪', '已取消', 'text-slate-600 bg-slate-50 border-slate-200']
  }[String(job.observabilityState || '')] || ['⚪', job.observabilityLabel || '狀態待確認', 'text-slate-600 bg-slate-50 border-slate-200']);

  let panel = document.getElementById('admin-section-worker');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'admin-section-worker';
    panel.className = 'admin-section-panel hidden space-y-5 overflow-y-auto max-h-[68vh] pr-1';
    workspaceHost.appendChild(panel);
  }
  panel.dataset.productSection = 'needs-action';

  let refreshTimer = null;
  let loading = false;
  let incidentResponders = [];
  let respondersLoaded = false;

  function workerButton() {
    let button = document.getElementById('admin-nav-worker');
    if (!button) {
      button = document.createElement('button');
      button.id = 'admin-nav-worker';
      button.type = 'button';
      button.className = 'admin-nav-btn px-3 py-2 rounded-xl text-sm font-bold bg-slate-100 text-slate-600 hover:bg-slate-200';
      button.textContent = '🖥️ Worker / Job 狀態';
    }
    button.onclick = null;
    button.removeAttribute('onclick');
    button.setAttribute('data-csp-click', "switchAdminWorkspace('worker',true)");
    button.dataset.adminWorkspace = 'worker';
    button.disabled = false;
    button.classList.remove('hidden');
    button.setAttribute('aria-hidden', 'false');
    return button;
  }

  function ensureNavigation() {
    const existingButton = document.getElementById('admin-nav-worker');
    const operations = navHost.querySelector('[data-admin-nav-group="operations"] .v580-admin-group-actions');
    if (operations) {
      const button = existingButton || workerButton();
      if (button.parentElement !== operations) operations.appendChild(button);
      return;
    }
    if (existingButton && navHost.contains(existingButton)) return;
    const group = document.createElement('section');
    group.className = 'v580-admin-group compact';
    group.dataset.adminNavGroup = 'operations';
    const label = document.createElement('span');
    label.className = 'v580-admin-group-label';
    label.textContent = '系統健康與維運';
    const actions = document.createElement('div');
    actions.className = 'v580-admin-group-actions';
    actions.appendChild(existingButton || workerButton());
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
      refreshTimer = setTimeout(() => renderWorkerStatus(false), 8000);
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
    const storageBlocked = worker.storagePreflightReady === false;
    const [icon, label, classes] = storageBlocked
      ? ['🔴', '儲存未就緒', 'text-rose-700 bg-rose-50 border-rose-200']
      : statusMeta(worker.status);
    const preflightText = storageBlocked
      ? '<div class="rounded-xl border border-rose-200 bg-rose-50 p-2 text-[11px] font-bold text-rose-800">儲存尚未就緒，Worker 已暫停領取新教材。'+(worker.storagePreflightBackend?'<div class="mt-1">Provider：'+escapeHtml(worker.storagePreflightBackend)+'</div>':'')+(worker.storagePreflightError?'<div class="mt-1 font-normal">'+escapeHtml(worker.storagePreflightError)+'</div>':'')+'</div>'
      : '';
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
        <span class="px-2 py-1 rounded-full ${worker.videoAccelerationAvailable?'bg-emerald-100 text-emerald-800':'bg-slate-100 text-slate-700'}">Video ${worker.videoAccelerationAvailable?escapeHtml(worker.videoAccelerationEncoder||'HW')+' ✓':worker.videoAccelerationEnabled===true?'CPU fallback':worker.videoAccelerationEnabled===false?'HW off':'—'}</span>
        <span class="px-2 py-1 rounded-full ${worker.libreOfficeWarmRunning?'bg-emerald-100 text-emerald-800':'bg-slate-100 text-slate-700'}">LO warm ${worker.libreOfficeWarmRunning===true?'✓':worker.libreOfficeWarmEnabled===true?'✕':'—'}</span>
        <span class="px-2 py-1 rounded-full ${storageBlocked?'bg-rose-100 text-rose-800':'bg-slate-100 text-slate-700'}">儲存 preflight ${worker.storagePreflightReady===false?'✕':worker.storagePreflightReady===true?'✓':'—'}</span>
        ${updateText}
      </div>
      ${preflightText}
      <div class="text-[11px] text-slate-500">最近自動更新檢查：${formatWhen(worker.lastUpdateCheckAt)}。更新只會在 Worker 閒置時於本機執行，Web 端不能遠端下令 pull。</div>
    </article>`;
  }

  function jobRows(jobs) {
    if (!jobs.length) return '<tr><td colspan="6" class="p-5 text-center text-slate-400">目前沒有背景教材工作。</td></tr>';
    return jobs.map(job => {
      const [icon,label,classes]=jobMeta(job.status);
      const [healthIcon,healthLabel,healthClasses]=jobHealthMeta(job);
      const progress=Math.max(0,Math.min(100,Number(job.progressPercent||0)));
      const heartbeatAge=Number(job.heartbeatAgeSeconds);
      const heartbeat=job.status==='processing'?(Number.isFinite(heartbeatAge)?'heartbeat '+formatDuration(heartbeatAge)+'前':'尚未取得本輪 heartbeat'):'';
      const detail=String(job.detail||'').trim();
      const error=String(job.error||'').trim();
      const timerBase=job.startedAt||job.createdAt;
      const duration=Number.isFinite(Number(job.elapsedSeconds))
        ? formatDuration(job.elapsedSeconds)
        : (job.finishedAt&&timerBase
          ? formatDuration(Math.max(0,(new Date(job.finishedAt)-new Date(timerBase))/1000))
          : elapsedFrom(timerBase));
      return `<tr class="align-top">
        <td class="p-3 font-mono text-[11px] break-all">${escapeHtml(job.id || '')}</td>
        <td class="p-3"><div class="font-semibold text-slate-800">${escapeHtml(job.title || job.originalName || '未命名教材')}</div><div class="text-[10px] text-slate-400">${escapeHtml(job.originalName || '')}</div>${job.workerId?`<div class="text-[10px] text-slate-400 mt-1">Worker：${escapeHtml(job.workerId)}</div>`:''}</td>
        <td class="p-3 whitespace-nowrap"><span class="inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${classes}">${icon} ${label}</span><div class="mt-1"><span class="inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${healthClasses}">${healthIcon} ${escapeHtml(healthLabel)}</span></div><div class="mt-1 text-[10px] text-slate-400">第 ${Number(job.attempts||0)}/${Number(job.maxAttempts||3)} 次</div></td>
        <td class="p-3 text-slate-600"><div class="font-semibold">${escapeHtml(job.stage || '—')} · ${progress}%</div><div class="mt-1 h-1.5 rounded-full bg-slate-100 overflow-hidden"><div class="h-full bg-sky-500" style="width:${progress}%"></div></div>${detail?`<div class="mt-1 text-[11px]">${escapeHtml(detail)}</div>`:''}<div class="mt-1 text-[10px] ${job.stalled?'text-rose-700 font-bold':job.heartbeatDelayed?'text-amber-700':'text-slate-400'}">${escapeHtml(job.observabilityDetail||'')}${heartbeat?` · ${escapeHtml(heartbeat)}`:''}</div>${error?`<div class="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2 py-1.5 text-[11px] font-semibold text-rose-700">失敗原因：${escapeHtml(error)}</div>`:''}</td>
        <td class="p-3 whitespace-nowrap text-slate-500"><div>${escapeHtml(duration)}</div><div class="mt-1 text-[10px] text-slate-400">開始：${formatWhen(job.startedAt||job.createdAt)}</div>${job.retryInSeconds?`<div class="mt-1 text-[10px] text-amber-700">約 ${formatDuration(job.retryInSeconds)} 後重試</div>`:''}</td>
        <td class="p-3 whitespace-nowrap text-slate-500">${formatWhen(job.updatedAt || job.createdAt)}</td>
      </tr>`;
    }).join('');
  }

  function failureCards(jobs) {
    const failed=jobs.filter(job=>['failed','retry_wait'].includes(job.status)||['heartbeat_delayed','stalled'].includes(job.observabilityState));
    if(!failed.length)return '<div class="rounded-xl bg-emerald-50 px-3 py-3 text-sm text-emerald-800">目前沒有失敗、等待重試或 heartbeat 異常工作。</div>';
    return failed.map(job=>{
      const [icon,label,classes]=job.observabilityState==='stalled'
        ? ['🔴','可能卡住','text-rose-700 bg-rose-50 border-rose-200']
        : job.observabilityState==='heartbeat_delayed'
          ? ['🟠','回報延遲','text-amber-700 bg-amber-50 border-amber-200']
          : jobMeta(job.status);
      const critical=job.status==='failed'||job.observabilityState==='stalled';
      return `<article class="rounded-xl border ${critical?'border-rose-200 bg-rose-50':'border-amber-200 bg-amber-50'} p-3 text-sm">
        <div class="flex flex-wrap items-start justify-between gap-2"><div><b>${escapeHtml(job.title||job.originalName||job.id)}</b><div class="mt-1 font-mono text-[10px] text-slate-500">${escapeHtml(job.id||'')}</div></div><span class="rounded-full border px-2 py-1 text-[10px] font-bold ${classes}">${icon} ${label}</span></div>
        <div class="mt-2 text-xs text-slate-700"><b>階段：</b>${escapeHtml(job.stage||'—')}　<b>嘗試：</b>${Number(job.attempts||0)}/${Number(job.maxAttempts||3)}</div>
        <div class="mt-2 rounded-lg bg-white/80 px-2 py-2 text-xs ${critical?'text-rose-700':'text-slate-600'}"><b>${job.errorMessage?'判定':'詳細資訊'}：</b>${escapeHtml(job.errorMessage||job.observabilityDetail||job.detail||'Worker 未提供詳細原因')}${job.errorCode?` <span class="font-mono text-[10px]">[${escapeHtml(job.errorCode)}]</span>`:''}${job.errorAction?`<div class="mt-1 font-semibold">建議：${escapeHtml(job.errorAction)}</div>`:''}</div>
        ${job.technicalDetail?`<details class="mt-2 rounded-lg border border-slate-200 bg-white/70 p-2 text-[10px] text-slate-600"><summary class="cursor-pointer font-bold">技術細節</summary><div class="mt-1">${escapeHtml(job.technicalDetail)}</div></details>`:''}
        <div class="mt-2 text-[10px] text-slate-500">建立 ${formatWhen(job.createdAt)} · 更新 ${formatWhen(job.updatedAt)} · Worker ${escapeHtml(job.workerId||'—')}${Number.isFinite(Number(job.heartbeatAgeSeconds))?` · heartbeat ${formatDuration(job.heartbeatAgeSeconds)}前`:''}</div>
      </article>`;
    }).join('');
  }

  function incidentCategoryMeta(incident) {
    const category=String(incident.category||'').toLowerCase();
    const code=String(incident.errorCode||'').toUpperCase();
    if(category==='ai'||incident.incidentType==='ai_queue_failure')return ['🤖','AI'];
    if(category==='storage'||/(R2|GDRIVE|MEGA|OCI|STORAGE)/.test(code))return ['☁️','Storage'];
    if(category==='worker'||/WORKER|FFMPEG|LIBREOFFICE/.test(code))return ['🖥️','Worker'];
    return ['🛠️','系統'];
  }

  function incidentResponseMeta(incident) {
    if(incident.status==='resolved')return ['🟢','已恢復','text-emerald-700 bg-emerald-50 border-emerald-200'];
    if(incident.maintenanceActive)return ['🛠️','維護中','text-indigo-700 bg-indigo-50 border-indigo-200'];
    if(incident.responseState==='assigned')return ['👤','處理中','text-sky-700 bg-sky-50 border-sky-200'];
    if(incident.responseState==='acknowledged')return ['✓','已確認','text-teal-700 bg-teal-50 border-teal-200'];
    return ['!','待確認','text-amber-700 bg-amber-50 border-amber-200'];
  }

  function incidentActionMeta(incident) {
    const type=String(incident.incidentType||'');
    const category=String(incident.category||'').toLowerCase();
    const code=String(incident.errorCode||'').toUpperCase();
    const resource=String(incident.resourceId||'').toLowerCase();
    if(type==='worker_offline')return {href:'#worker-runtime-70',label:'查看 Worker'};
    if(type==='job_stalled'||type==='failure_rate'||(type==='error_burst'&&category==='worker'))return {href:'#worker-problems-70',label:'查看異常工作'};
    if(category==='storage'||/(R2|GDRIVE|MEGA|OCI|STORAGE)/.test(code))return {href:'/system?admin=1&workspace=system&persona=system&from=incident&focus=storage',label:'前往系統與儲存'};
    if(category==='ai'||type==='ai_queue_failure'){
      const canTeach=Boolean(window.TeacherWorkspace1014?.canTeach);
      if(canTeach){
        const assessment=resource==='question';
        return {
          href:assessment
            ? '/system?admin=1&workspace=assessment&persona=teacher&from=incident&focus=ai-question'
            : '/system?admin=1&workspace=course-materials&persona=teacher&from=incident&focus=ai-media',
          label:assessment?'前往評量與出題':'前往教材與媒體'
        };
      }
      return {href:'#worker-problems-70',label:'查看 AI Worker 技術狀態'};
    }
    return {href:'#worker-problems-70',label:'查看維運狀態'};
  }

  async function loadIncidentResponders() {
    if (respondersLoaded) return incidentResponders;
    respondersLoaded = true;
    try {
      const response = await fetch('/api/operational-incidents/responders', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && Array.isArray(data.responders)) {
        incidentResponders = data.responders;
      }
    } catch (_error) {
      incidentResponders = [];
    }
    return incidentResponders;
  }

  async function updateIncidentResponse(card, key, payload) {
    const status = card?.querySelector('[data-incident-response-status]');
    const controls = card?.querySelectorAll('button,select,input') || [];
    controls.forEach(control => { control.disabled = true; });
    if (status) status.textContent = '⏳ 儲存處置狀態中…';
    try {
      const response = await fetch('/api/operational-incidents/' + encodeURIComponent(key), {
        method: 'PATCH',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `更新失敗（${response.status}）`);
      if (status) status.textContent = '✅ 處置狀態已更新';
      await renderWorkerStatus(true);
    } catch (error) {
      if (status) status.textContent = '❌ ' + (error.message || '更新失敗');
      controls.forEach(control => { control.disabled = false; });
    }
  }

  function bindIncidentControls() {
    panel.querySelectorAll('[data-incident-card]').forEach(card => {
      const key = card.dataset.incidentKey || '';
      card.querySelectorAll('[data-incident-response-action]').forEach(button => {
        button.onclick = () => {
          const action = button.dataset.incidentResponseAction || '';
          const payload = {action};
          if (action === 'assign') {
            payload.assignedTo = card.querySelector('[data-incident-assignee]')?.value || '';
          } else if (action === 'maintenance') {
            payload.maintenanceMinutes = Number(card.querySelector('[data-incident-maintenance]')?.value || 60);
          } else if (action === 'note') {
            payload.note = card.querySelector('[data-incident-note]')?.value || '';
          }
          void updateIncidentResponse(card, key, payload);
        };
      });
    });
  }

  function incidentCards(rows, emptyText='目前沒有事件。', responders=[]) {
    if(!rows.length)return '<div class="rounded-xl bg-emerald-50 px-3 py-3 text-sm text-emerald-800">'+escapeHtml(emptyText)+'</div>';
    return rows.map(incident=>{
      const open=incident.status==='open';
      const classes=open
        ? (incident.severity==='critical'?'border-rose-200 bg-rose-50':'border-amber-200 bg-amber-50')
        : 'border-emerald-200 bg-emerald-50';
      const [categoryIcon,categoryLabel]=incidentCategoryMeta(incident);
      const [responseIcon,responseLabel,responseClasses]=incidentResponseMeta(incident);
      const action=incidentActionMeta(incident);
      const occurrences=Math.max(1,Number(incident.occurrenceCount||1));
      const runbook=incident.runbook&&typeof incident.runbook==='object'?incident.runbook:{};
      const steps=Array.isArray(runbook.steps)?runbook.steps.filter(Boolean):[];
      const assignee=String(incident.assignedTo||'').trim();
      const maintenance=incident.maintenanceActive&&incident.maintenanceUntil?` · 維護至 ${formatWhen(incident.maintenanceUntil)}`:'';
      const responderOptions=['<option value="">未指派</option>',...(responders||[]).map(person=>{
        const username=String(person.username||'');
        const selected=username===assignee?' selected':'';
        return '<option value="'+escapeHtml(username)+'"'+selected+'>'+escapeHtml(person.name||username)+' · '+escapeHtml(username)+'</option>';
      })].join('');
      const maintenanceControl=incident.maintenanceActive
        ? '<button type="button" data-incident-response-action="clear_maintenance" class="rounded-lg border border-amber-300 bg-white px-2 py-1 text-[11px] font-bold text-amber-800">結束維護</button>'
        : '<select data-incident-maintenance class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px]"><option value="30">維護 30 分</option><option value="60" selected>維護 1 小時</option><option value="240">維護 4 小時</option><option value="1440">維護 24 小時</option></select><button type="button" data-incident-response-action="maintenance" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-bold">開始維護</button>';
      return `<article class="rounded-xl border ${classes} p-3 text-sm" data-incident-card data-incident-key="${escapeHtml(incident.incidentKey||'')}" data-incident-type="${escapeHtml(incident.incidentType||'')}" data-incident-status="${open?'open':'resolved'}">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div class="min-w-0"><div class="flex flex-wrap items-center gap-1.5"><span class="rounded-full border border-slate-200 bg-white/70 px-2 py-0.5 text-[10px] font-bold text-slate-600">${categoryIcon} ${escapeHtml(categoryLabel)}</span><span class="rounded-full border border-slate-200 bg-white/70 px-2 py-0.5 text-[10px] font-bold text-slate-600">發生 ${occurrences} 次</span></div><b class="mt-1.5 block text-slate-900">${escapeHtml(incident.title||'系統維運事件')}</b><div class="mt-1 font-mono text-[10px] text-slate-500">${escapeHtml(incident.errorCode||incident.incidentType||'')} · generation ${Number(incident.generation||1)}</div></div>
          <span class="rounded-full border px-2 py-1 text-[10px] font-bold ${responseClasses}">${responseIcon} ${escapeHtml(responseLabel)}</span>
        </div>
        <div class="mt-2 text-xs text-slate-700">${escapeHtml(open?(incident.detail||'需要處理'):'系統已確認此事件恢復正常。')}</div>
        ${open&&incident.action?`<div class="mt-2 rounded-lg bg-white/70 px-2.5 py-2 text-xs font-semibold text-slate-700"><span class="text-slate-500">建議動作：</span>${escapeHtml(incident.action)}</div>`:''}
        ${(assignee||incident.acknowledgedBy||incident.responseNote||maintenance)?`<div class="mt-2 text-[11px] text-slate-600">${assignee?`負責人：<b>${escapeHtml(assignee)}</b> · `:''}${incident.acknowledgedBy?`確認：${escapeHtml(incident.acknowledgedBy)} · `:''}${incident.responseNote?`備註：${escapeHtml(incident.responseNote)}`:''}${maintenance}</div>`:''}
        ${open?`<div class="mt-3 rounded-lg border border-slate-200 bg-white/80 p-2 space-y-2">
          <div class="flex flex-wrap gap-2">
            ${incident.responseState==='unacknowledged'?'<button type="button" data-incident-response-action="acknowledge" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-bold">✓ 已知悉</button>':''}
            <select data-incident-assignee class="min-w-40 rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px]">${responderOptions}</select>
            <button type="button" data-incident-response-action="assign" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-bold">指派處理</button>
            ${assignee?'<button type="button" data-incident-response-action="unassign" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px]">解除指派</button>':''}
            ${maintenanceControl}
          </div>
          <div class="flex gap-2">
            <input data-incident-note type="text" maxlength="1000" value="${escapeHtml(incident.responseNote||'')}" placeholder="處置備註（例如：已聯絡資訊室）" class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px]">
            <button type="button" data-incident-response-action="note" class="rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-bold">儲存備註</button>
          </div>
          <div data-incident-response-status class="text-[10px] text-slate-500"></div>
        </div>`:''}
        ${steps.length?`<details class="mt-2 rounded-lg border border-slate-200 bg-white/70 p-2 text-xs text-slate-700"><summary class="cursor-pointer font-bold">📋 ${escapeHtml(runbook.title||'處置步驟')}</summary><ol class="mt-2 list-decimal space-y-1 pl-5">${steps.map(step=>`<li>${escapeHtml(step)}</li>`).join('')}</ol></details>`:''}
        <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
          <div class="text-[10px] text-slate-500">首次 ${formatWhen(incident.openedAt)} · 最後觀察 ${formatWhen(incident.lastSeenAt)}${incident.resolvedAt?` · 恢復 ${formatWhen(incident.resolvedAt)}`:''}${incident.responseUpdatedBy?` · 最後處置 ${escapeHtml(incident.responseUpdatedBy)} ${formatWhen(incident.responseUpdatedAt)}`:''}</div>
          <a data-incident-action href="${escapeHtml(action.href)}" class="inline-flex items-center rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-50">${escapeHtml(action.label)} →</a>
        </div>
      </article>`;
    }).join('');
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
          <li>建立只存在本機的 <code>.local-worker.env</code>，至少填入 <code>TEACHER_BASE_URL</code>、<code>MATERIAL_WORKER_TOKEN</code> 與正式儲存 provider 的設定；若未指定 <code>MATERIAL_WORKER_ID</code>，啟動器會建立 gitignored 的固定 <code>.worker-id</code>。</li>
          <li>第一次手動啟動：<code>powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\TeacherWorker\\run_material_worker_autostart.ps1"</code>，確認本頁顯示 🟢 在線。</li>
          <li>若 MEGAcmd 安裝在目前 Windows 使用者帳號下，執行 <code>install_material_worker_task.ps1 -TaskUser "$env:USERDOMAIN\$env:USERNAME" -InteractiveLogon -StartNow</code>；由 Windows Task Scheduler 在該帳號登入後啟動 Worker，不需要 Windows 密碼。只有使用機器層級 provider 的環境才適合 ServiceAccount/SYSTEM。</li>
        </ol>
        <p class="font-bold">自動更新預設關閉；只有明確啟用且設定核准 release tag 時，安全 updater 才會在 Worker 閒置時自動 fast-forward。一般情況可由管理者更新 <code>main</code> 後重新啟動排程。</p>
      </div>
    </details>`;
  }

  async function renderWorkerStatus(force = false) {
    if (loading && !force) return;
    loading = true;
    panel.innerHTML = `<section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div class="animate-pulse text-sm text-slate-400">讀取 Worker 與佇列狀態中…</div></section>${firstRunGuide()}`;
    try {
      const response = await fetch(`/api/material-jobs?limit=30${force ? '&refresh=1' : ''}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = `/login?next=${next}`;
        return;
      }
      if (!response.ok) throw new Error(data.error || `讀取失敗（${response.status}）`);
      await loadIncidentResponders();
      const workerStatusAvailable = data.workerStatusAvailable !== false;
      const workerStatusError = data.workerStatusError || '無法讀取本機 Worker 狀態，請稍後再試。';
      const workers = Array.isArray(data.workers) ? data.workers : [];
      const activeWorkers = workerStatusAvailable ? workers.filter(worker => worker.status === 'online' || worker.status === 'busy') : [];
      const recentOfflineWorkers = workerStatusAvailable ? workers.filter(worker => worker.status === 'offline') : [];
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      const rawProblemJobs = Array.isArray(data.problemJobs) ? data.problemJobs : jobs.filter(job => ['failed','retry_wait'].includes(job.status));
      const problemMap = new Map(rawProblemJobs.map(job => [String(job.id||''), job]));
      jobs.filter(job => ['heartbeat_delayed','stalled'].includes(job.observabilityState)).forEach(job => problemMap.set(String(job.id||''), job));
      const problemJobs = [...problemMap.values()];
      const incidents = Array.isArray(data.incidents) ? data.incidents : [];
      const currentIncidents = incidents.filter(incident=>incident.status==='open');
      const resolvedIncidents = incidents.filter(incident=>incident.status==='resolved');
      const openIncidents = currentIncidents.length;
      const operationalIssues = Array.isArray(data.operationalIssues) ? data.operationalIssues : [];
      const operationalIssueHtml = operationalIssues.length
        ? '<div class="space-y-2">'+operationalIssues.map(issue=>'<div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"><b>'+escapeHtml(issue.message||issue.code||'維運提醒')+'</b>'+(issue.code?'<span class="ml-1 font-mono text-[10px]">['+escapeHtml(issue.code)+']</span>':'')+(issue.action?'<div class="mt-1">'+escapeHtml(issue.action)+'</div>':'')+'</div>').join('')+'</div>'
        : '';
      const staging = data.staging || {};
      const emptyWorkerMessage = recentOfflineWorkers.length
        ? '⚠ 目前沒有在線 Worker；下方仍保留最近 24 小時內的離線紀錄供檢查。'
        : '⚠ 尚未收到本機 Worker heartbeat。若這是第一次使用，請展開下方「第一次安裝」完成院內電腦設定。';
      const workerSummary = workerStatusAvailable
        ? `${activeWorkers.length} 台在線${recentOfflineWorkers.length ? ` · ${recentOfflineWorkers.length} 台近期離線` : ''}`
        : '狀態讀取異常';
      const workerBody = !workerStatusAvailable
        ? `<div data-worker-status-error class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${escapeHtml(workerStatusError)}<div class="mt-1 text-xs text-rose-600">佇列統計仍可使用；此訊息不代表 Worker 已離線。</div></div>`
        : `${activeWorkers.length ? activeWorkers.map(workerCard).join('') : `<div class="rounded-2xl border border-dashed border-amber-300 bg-amber-50 p-5 text-sm text-amber-800">${emptyWorkerMessage}</div>`}${recentOfflineWorkers.length ? `<details class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><summary class="cursor-pointer text-sm font-bold text-slate-700">近期離線 Worker（${recentOfflineWorkers.length}）</summary><div class="mt-3 space-y-3">${recentOfflineWorkers.map(workerCard).join('')}</div></details>` : ''}`;
      panel.innerHTML = `
        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
          <div class="flex items-start justify-between gap-3 flex-wrap">
            <div><h4 class="font-black text-slate-950 text-lg">🖥️ Worker / Job 狀態</h4>
            <p class="text-xs text-slate-500 mt-1">失敗原因、Worker、真實進度、heartbeat、處理時間與重試次數會保留在工作紀錄中；長時間處理不等於卡住。</p></div>
            <button id="worker-refresh-70" type="button" class="text-xs border border-slate-300 bg-white px-3 py-2 rounded-xl">↻ 立即更新</button>
          </div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            ${queueCard('⏳', '待處理', data.pendingJobs, 'queued + retry_wait')}
            ${queueCard('⚙️', '處理中', data.processingJobs, '正在由本機 Worker 執行')}
            ${queueCard('🔁', '等待重試', data.retryJobs, '保留原始檔後再次處理')}
            ${queueCard('❌', '失敗', data.failedJobs, '下方直接顯示失敗原因')}
          </div>
          <div class="grid sm:grid-cols-3 gap-2 text-xs">
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">最舊待處理等待：</span><b>${formatDuration(data.oldestPendingAgeSeconds)}</b>${data.oldestPendingAt ? ` · ${formatWhen(data.oldestPendingAt)}` : ''}</div>
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">最近失敗率：</span><b>${Math.round(Number(data.recentFailureRate || 0) * 100)}%</b> · ${Number(data.recentTerminalJobs || 0)} 筆 terminal job</div>
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">平均完成時間：</span><b>${formatDuration(data.averageCompletedDurationSeconds)}</b></div>
          </div>
          <div class="grid sm:grid-cols-3 gap-2 text-xs">
            <div class="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2"><span class="text-emerald-700">🟢 Heartbeat 正常：</span><b>${Number(data.healthyProcessingJobs||0)}</b></div>
            <div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2"><span class="text-amber-700">🟠 回報延遲：</span><b>${Number(data.heartbeatDelayedJobs||0)}</b><div class="mt-1 text-[10px]">警戒 ${formatDuration(data.heartbeatWarningSeconds||120)}</div></div>
            <div class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2"><span class="text-rose-700">🔴 可能卡住：</span><b>${Number(data.stalledJobs||0)}</b><div class="mt-1 text-[10px]">stale ${formatDuration(data.staleThresholdSeconds||1800)}</div></div>
          </div>
          <div class="text-xs rounded-xl bg-slate-50 border border-slate-200 px-3 py-2">Shared staging：<b>${escapeHtml(staging.backend || '未設定')}</b> · ${staging.available ? '可用' : '不可用'}${staging.shared ? ' · Web/Worker 共用' : ''}</div>
          ${operationalIssueHtml}
        </section>
        <section id="worker-runtime-70" class="space-y-3 scroll-mt-4">
          <div class="flex items-center justify-between"><h5 class="font-black text-slate-900">本機 Worker</h5><span class="text-xs text-slate-400">${workerSummary}</span></div>
          ${workerBody}
        </section>
        <section id="worker-incidents-70" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-4 scroll-mt-4">
          <div class="flex items-start justify-between gap-3 flex-wrap"><div><h5 class="font-black text-slate-900">🚨 維運事件</h5><p class="mt-1 text-[11px] text-slate-500">Worker、AI 與 Storage 的持續性問題集中在這裡；單次可恢復 fallback 不會升級成事件。</p></div><div class="flex gap-2 text-[11px]"><span class="rounded-full border border-rose-200 bg-rose-50 px-2 py-1 font-bold text-rose-700">目前問題 ${currentIncidents.length}</span><span class="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 font-bold text-emerald-700">已恢復 ${resolvedIncidents.length}</span></div></div>
          <div><div class="mb-2 text-xs font-black text-slate-700">目前問題</div><div class="space-y-2">${incidentCards(currentIncidents,'目前沒有需要處理的維運事件。',incidentResponders)}</div></div>
          <details class="rounded-xl border border-slate-200 bg-slate-50/60 p-3"><summary class="cursor-pointer text-xs font-black text-slate-700">最近已恢復（24 小時） · ${resolvedIncidents.length} 筆</summary><div class="mt-3 space-y-2">${incidentCards(resolvedIncidents,'最近 24 小時沒有已恢復事件。',incidentResponders)}</div></details>
        </section>
        <section id="worker-problems-70" class="rounded-2xl border border-rose-200 bg-white p-4 shadow-sm space-y-3 scroll-mt-4">
          <div class="flex items-center justify-between gap-3"><h5 class="font-black text-slate-900">⚠ 需要注意的工作</h5><span class="text-[11px] text-slate-400">${problemJobs.length} 筆</span></div>
          <div class="space-y-2">${failureCards(problemJobs)}</div>
        </section>
        <section id="worker-jobs-history-70" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-3 scroll-mt-4">
          <div class="flex items-center justify-between gap-3"><h5 class="font-black text-slate-900">最近背景工作</h5><span class="text-[11px] text-slate-400">最近 ${jobs.length} 筆</span></div>
          <div class="overflow-x-auto border border-slate-200 rounded-xl"><table class="w-full text-left text-xs"><thead class="bg-slate-50"><tr><th class="p-3">Job ID</th><th class="p-3">教材</th><th class="p-3">狀態</th><th class="p-3">階段／原因</th><th class="p-3">耗時</th><th class="p-3">更新時間</th></tr></thead><tbody class="divide-y divide-slate-100">${jobRows(jobs)}</tbody></table></div>
        </section>
        ${firstRunGuide()}`;
      document.getElementById('worker-refresh-70').onclick = () => renderWorkerStatus(true);
      bindIncidentControls();
    } catch (error) {
      panel.innerHTML = `<section class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${escapeHtml(error.message || '無法讀取 Worker 狀態')}</section>${firstRunGuide()}`;
    } finally {
      loading = false;
      scheduleRefresh();
    }
  }

  const adminShell = window.AdminWorkspaceShell;
  adminShell?.registerWorkspace('worker', async ({force}) => {
      document.querySelectorAll('.admin-section-panel').forEach(item => item.classList.add('hidden'));
      panel.classList.remove('hidden');
      modal.dataset.section = 'worker';
      markActive();
      const status = document.getElementById('admin-workspace-status');
      if (status) status.textContent = '系統管理者檢視 Worker / Job 狀態並處置 OPEN Incident；恢復仍由系統自動判定。';
      await renderWorkerStatus(Boolean(force));
      return true;
  });
  adminShell?.addBeforeWorkspace(({requested, workspace}) => {
    if (requested !== 'worker' && workspace !== 'worker' && refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  });
  adminShell?.addAfterModal(({show}) => {
    if (show) ensureNavigation();
    else if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
  });

  ensureNavigation();

  // Deep links can be restored by system-bootstrap before this deferred
  // extension has registered its workspace handler. Once registration is
  // complete, reclaim an explicit system/worker URL so the visible section
  // cannot remain on a previously rendered teacher/assessment workspace.
  const initialParams = new URLSearchParams(window.location.search);
  if (
    initialParams.get('admin') === '1' &&
    initialParams.get('workspace') === 'worker' &&
    initialParams.get('persona') === 'system'
  ) {
    setTimeout(() => {
      void window.switchAdminWorkspace?.('worker', true);
    }, 0);
  }
})();
