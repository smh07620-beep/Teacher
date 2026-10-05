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

  const formatBytes = value => {
    const bytes = Math.max(0, Number(value || 0));
    if (!bytes) return '—';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
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
  let refreshDelayMs = 30000;
  let loading = false;
  let incidentResponders = [];
  let respondersLoaded = false;
  let sloWindow = '24h';
  const sloCache = new Map();
  let whatIfScenario = {
    documentCount: 10,
    documentPages: 20,
    mediaCount: 3,
    mediaMinutes: 30,
    imageCount: 0,
    archiveCount: 0
  };
  let whatIfResult = null;
  let whatIfLoading = false;

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
    if (document.hidden) return;
    if (!panel.classList.contains('hidden') && !modal.classList.contains('hidden')) {
      refreshTimer = setTimeout(() => renderWorkerStatus(false), refreshDelayMs);
    }
  }

  function queueCard(icon, title, value, note) {
    return `<div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="text-xs font-bold text-slate-500">${icon} ${escapeHtml(title)}</div>
      <div class="text-2xl font-black text-slate-950 mt-1">${Number(value || 0)}</div>
      <div class="text-[11px] text-slate-400 mt-1">${escapeHtml(note)}</div>
    </div>`;
  }

  const formatPercent = value => {
    if (value === null || value === undefined || value === '') return '資料累積中';
    const number = Number(value);
    return Number.isFinite(number) ? (number * 100).toFixed(1) + '%' : '資料累積中';
  };

  const formatSignedPercent = value => {
    if (value === null || value === undefined || value === '') return '尚無比較基準';
    const number = Number(value);
    if (!Number.isFinite(number)) return '尚無比較基準';
    if (Math.abs(number) < 0.05) return '與前期持平';
    return (number > 0 ? '↑ 慢 ' : '↓ 快 ') + Math.abs(number).toFixed(1) + '%';
  };

  function sloMetricCard(icon,title,value,note,target='') {
    return `<div class="rounded-xl border border-slate-200 bg-white p-3">
      <div class="text-[11px] font-bold text-slate-500">${icon} ${escapeHtml(title)}</div>
      <div class="mt-1 text-xl font-black text-slate-950">${escapeHtml(value)}</div>
      <div class="mt-1 text-[10px] text-slate-500">${escapeHtml(note||'')}${target?` · 目標 ${escapeHtml(target)}`:''}</div>
    </div>`;
  }

  function sloBarRows(series,key,maxValue,formatter) {
    if(!series.length)return '<div class="text-xs text-slate-400">採樣資料累積中。</div>';
    const ceiling=Math.max(1,Number(maxValue||0));
    return '<div class="space-y-1.5">'+series.map(row=>{
      const raw=Math.max(0,Number(row[key]||0));
      const width=Math.max(raw>0?3:0,Math.min(100,raw/ceiling*100));
      const when=new Date(row.sampledAt);
      const label=Number.isNaN(when.getTime())?String(row.sampledAt||''):(
        sloWindow==='7d'
          ? when.toLocaleDateString(undefined,{month:'numeric',day:'numeric'})
          : when.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})
      );
      return '<div class="grid grid-cols-[58px_minmax(0,1fr)_64px] items-center gap-2 text-[10px]"><span class="text-slate-400">'+escapeHtml(label)+'</span><div class="h-2 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-slate-500" style="width:'+width.toFixed(1)+'%"></div></div><span class="text-right font-semibold text-slate-600">'+escapeHtml(formatter(raw))+'</span></div>';
    }).join('')+'</div>';
  }

  async function loadCapacitySimulation(scenario) {
    const params=new URLSearchParams();
    Object.entries(scenario||{}).forEach(([key,value])=>params.set(key,String(value??'')));
    const response=await fetch('/api/operational-capacity-simulation?'+params.toString(),{
      credentials:'same-origin',
      cache:'no-store'
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||'高峰容量試算失敗');
    return data;
  }

  async function loadEmailDeliveryHealth() {
    try {
      const response=await fetch('/api/email-delivery-health',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.error||'Email 通知健康狀態讀取失敗');
      return data;
    } catch (_error) {
      return null;
    }
  }

  function renderEmailDeliveryHealth(data) {
    if(!data)return '<section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><h5 class="font-black text-slate-900">✉️ Email 通知健康狀態</h5><p class="mt-2 text-xs text-slate-500">目前無法讀取寄送紀錄；不影響其他維運狀態。</p></section>';
    const today=data.today||{}, schedule=data.schedule||{}, failed=Number(today.failed||0);
    const unhealthy=failed>0||['missing_run','delivery_issue','delivery_gap'].includes(String(schedule.health||''));
    return '<section id="email-delivery-health-70" class="rounded-2xl border '+(unhealthy?'border-rose-200':'border-slate-200')+' bg-white p-4 shadow-sm"><div class="flex flex-wrap items-start justify-between gap-3"><div><h5 class="font-black text-slate-900">✉️ Email 通知健康狀態</h5><p class="mt-1 text-[11px] text-slate-500">7／3／1 天學習與考核提醒的預計事件與實際寄送結果；失敗寄送會保留重試資格。</p></div><span class="rounded-full px-2 py-1 text-[10px] font-black '+(unhealthy?'bg-rose-50 text-rose-700':'bg-emerald-50 text-emerald-700')+'">'+(unhealthy?'需要檢查':(schedule.ranToday?'今日已執行':'正常'))+'</span></div>'+(schedule.issue?'<div class="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">'+escapeHtml(schedule.issue)+'</div>':'')+'<div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2"><div class="rounded-xl bg-sky-50 p-3"><div class="text-[10px] text-sky-700">今日預計事件</div><div class="text-xl font-black text-sky-900">'+Number(schedule.expectedEvents||0)+'</div><div class="text-[10px] text-sky-600">取得寄送資格 '+Number(schedule.claimedEvents||0)+'</div></div><div class="rounded-xl bg-emerald-50 p-3"><div class="text-[10px] text-emerald-700">成功事件</div><div class="text-xl font-black text-emerald-800">'+Number(today.sent||0)+'</div></div><div class="rounded-xl bg-rose-50 p-3"><div class="text-[10px] text-rose-700">失敗事件</div><div class="text-xl font-black text-rose-800">'+failed+'</div></div><div class="rounded-xl bg-slate-50 p-3"><div class="text-[10px] text-slate-500">最近寄送</div><div class="mt-1 text-xs font-bold">'+formatWhen(data.lastDeliveryAt)+'</div></div></div>'+(data.lastErrorType?'<div class="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">最近失敗：'+escapeHtml(data.lastErrorType)+'</div>':'')+'</section>';
  }

  async function loadOperationalMetrics(windowValue=sloWindow,force=false) {
    const cached=sloCache.get(windowValue);
    if(!force&&cached&&Date.now()-cached.loadedAt<60000)return cached.data;
    try{
      const response=await fetch('/api/operational-metrics?window='+encodeURIComponent(windowValue),{
        credentials:'same-origin',
        cache:'no-store'
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.error||'SLO 指標讀取失敗');
      sloCache.set(windowValue,{loadedAt:Date.now(),data});
      return data;
    }catch(_error){
      return cached?.data||null;
    }
  }

  function renderSloDashboard(metrics) {
    if(!metrics)return `<section id="worker-slo-70" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div class="font-black text-slate-900">📈 維運趨勢 / SLO</div><div class="mt-2 text-xs text-slate-500">目前無法讀取趨勢資料；即時 Worker / Job 狀態不受影響。</div></section>`;
    const material=metrics.material||{};
    const queue=metrics.queue||{};
    const worker=metrics.worker||{};
    const incident=metrics.incidents||{};
    const coverage=metrics.dataCoverage||{};
    const targets=metrics.targets||{};
    const trend=metrics.trendAnalysis||{};
    const trendSignals=Array.isArray(trend.signals)?trend.signals:[];
    const capacity=trend.capacity||{};
    const forecast=metrics.capacityForecast||{};
    const predictionAccuracy=forecast.predictionCalibration||{};
    const predictionWorkloads=Array.isArray(predictionAccuracy.workloads)?predictionAccuracy.workloads:[];
    const forecastRates=forecast.rates||{};
    const forecastQueue=forecast.queue||{};
    const forecastDecision=forecast.decision||{};
    const forecastCurrent=forecast.current||{};
    const forecastPlusOne=forecast.plusOneWorker||{};
    const workload=forecast.workloadCalibration||{};
    const workloadProfiles=Array.isArray(workload.profiles)?workload.profiles:[];
    const workloadCurrent=workload.current||{};
    const workloadPlusOne=workload.plusOneWorker||{};
    const series=Array.isArray(metrics.series)?metrics.series:[];
    const success=material.successRate===null||material.successRate===undefined?'資料不足':formatPercent(material.successRate);
    const workerAvailability=worker.observedAvailability===null||worker.observedAvailability===undefined?'採樣累積中':formatPercent(worker.observedAvailability);
    const p95=Number(material.p95DurationSeconds||0)>0?formatDuration(material.p95DurationSeconds):'資料不足';
    const mttr=Number(incident.averageMttrSeconds||0)>0?formatDuration(incident.averageMttrSeconds):(Number(incident.resolved||0)?'0 秒':'資料累積中');
    const targetAvailability=targets.workerAvailabilityPercent!=null?'≥ '+Number(targets.workerAvailabilityPercent).toFixed(1)+'%':'';
    const targetSuccess=targets.materialSuccessPercent!=null?'≥ '+Number(targets.materialSuccessPercent).toFixed(1)+'%':'';
    const targetDuration=targets.materialP95DurationSeconds!=null?'≤ '+formatDuration(targets.materialP95DurationSeconds):'';
    const top=Array.isArray(incident.topComponents)?incident.topComponents:[];
    const maxPending=Math.max(1,...series.map(row=>Number(row.pendingJobsMax||0)));
    const maxDuration=Math.max(1,...series.map(row=>Number(row.completedDurationAverageSeconds||0)));
    const coveragePct=(Number(coverage.coveragePercent||0)*100).toFixed(1);
    const baseline=metrics.targetsConfigured
      ? '正式 SLO 門檻已由環境設定；下方同時顯示實測值與目標。'
      : '目前先建立 baseline，尚未設定正式 SLO 門檻；不會用任意預設值判定通過／失敗。';
    const capacityState=String(capacity.state||'normal');
    const capacityClasses=capacityState==='pressure'
      ? 'border-rose-200 bg-rose-50 text-rose-800'
      : capacityState==='watch'
        ? 'border-amber-200 bg-amber-50 text-amber-800'
        : 'border-emerald-200 bg-emerald-50 text-emerald-800';
    const capacityIcon=capacityState==='pressure'?'🔴':capacityState==='watch'?'🟠':'🟢';
    const trendHtml=trendSignals.length
      ? trendSignals.map(signal=>'<article class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><div class="flex flex-wrap items-center justify-between gap-2"><b>'+escapeHtml(signal.title||signal.code||'趨勢異常')+'</b><span class="font-mono text-[10px]">'+escapeHtml(signal.code||'')+'</span></div><div class="mt-1">'+escapeHtml(signal.detail||'')+'</div>'+(signal.action?'<div class="mt-1 font-semibold">建議：'+escapeHtml(signal.action)+'</div>':'')+'</article>').join('')
      : '<div class="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">目前沒有符合「持續惡化」條件的趨勢異常；單次尖峰不會被升級。</div>';
    const forecastConfidence=String(forecast.confidence||'unavailable');
    const rawForecastConfidence=String(forecast.rawConfidence||forecastConfidence||'unavailable');
    const confidenceText=value=>value==='high'?'高':value==='medium'?'中':value==='low'?'低':'尚不可估';
    const forecastConfidenceLabel=confidenceText(forecastConfidence);
    const rawForecastConfidenceLabel=confidenceText(rawForecastConfidence);
    const arrivalRate=forecastRates.arrivalPerHour==null?'—':Number(forecastRates.arrivalPerHour).toFixed(2)+' / 小時';
    const workerRate=forecastRates.nominalPerWorkerPerHour==null?'—':Number(forecastRates.nominalPerWorkerPerHour).toFixed(2)+' / 小時';
    const workerConservative=forecastRates.conservativePerWorkerPerHour==null?'—':Number(forecastRates.conservativePerWorkerPerHour).toFixed(2)+' / 小時';
    const currentNominal=forecastCurrent.nominal||{};
    const currentConservative=forecastCurrent.conservative||{};
    const plusOneNominal=forecastPlusOne.nominal||{};
    const plusOneConservative=forecastPlusOne.conservative||{};
    const etaText=scenario=>{
      if(!scenario||scenario.state==='unavailable')return '資料不足';
      if(Number(scenario.clearEtaSeconds)===0)return '目前無 backlog';
      if(scenario.clearEtaSeconds==null)return '無法淨消化';
      return formatDuration(scenario.clearEtaSeconds);
    };
    const forecastLimitations=Array.isArray(forecast.limitations)?forecast.limitations:[];
    const blockers=Array.isArray(forecast.blockers)?forecast.blockers:[];
    const forecastClasses=forecastDecision.state==='dependency_blocked'
      ? 'border-rose-200 bg-rose-50'
      : ['one_more_worker_would_restore_drain','one_more_worker_may_help','one_more_worker_insufficient','borderline'].includes(forecastDecision.state)
        ? 'border-amber-200 bg-amber-50'
        : 'border-slate-200 bg-slate-50/60';
    const workloadEta=scenario=>{
      if(!scenario||scenario.state==='unavailable')return '資料不足';
      if(Number(scenario.clearEtaSeconds)===0)return '目前無 backlog';
      if(scenario.clearEtaSeconds==null)return '無法淨消化';
      return formatDuration(scenario.clearEtaSeconds);
    };
    const whatIfEta=scenario=>{
      if(!scenario||scenario.state==='unavailable')return '資料不足';
      if(Number(scenario.clearEtaSeconds)===0)return '目前無 backlog';
      if(scenario.clearEtaSeconds==null)return '持續堆積';
      return formatDuration(scenario.clearEtaSeconds);
    };
    const whatIfDecision=whatIfResult?.decision||{};
    const whatIfBottleneck=whatIfResult?.bottleneck||null;
    const whatIfOne=whatIfResult?.oneWorker||{};
    const whatIfTwo=whatIfResult?.twoWorkers||{};
    const whatIfLimitations=Array.isArray(whatIfResult?.limitations)?whatIfResult.limitations:[];
    const whatIfComponents=Array.isArray(whatIfResult?.components)?whatIfResult.components:[];
    const whatIfResultHtml=whatIfLoading
      ? '<div class="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800 animate-pulse">正在用目前實測 workload 模型計算高峰情境…</div>'
      : whatIfResult
        ? '<div class="space-y-3">'
          +'<div class="rounded-xl border '+(whatIfResult.available?'border-slate-200 bg-white':'border-amber-200 bg-amber-50')+' p-3">'
          +'<div class="flex flex-wrap items-start justify-between gap-2"><div><b class="text-sm text-slate-900">'+escapeHtml(whatIfDecision.label||'高峰試算結果')+'</b><div class="mt-1 text-[11px] text-slate-500">'+escapeHtml(whatIfDecision.detail||'')+'</div></div><span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-bold">峰值 backlog '+Number(whatIfResult.peakBacklogJobs||0)+' 筆</span></div>'
          +(whatIfBottleneck?'<div class="mt-2 text-[11px] text-slate-600"><b>主要瓶頸：</b>'+escapeHtml(whatIfBottleneck.label||whatIfBottleneck.kind||'')+' · 約占這批 P95 workload '+(Number(whatIfBottleneck.share||0)*100).toFixed(1)+'%</div>':'')
          +'</div>'
          +'<div class="grid lg:grid-cols-2 gap-3">'
          +'<div class="rounded-xl border border-slate-200 bg-white p-3 text-xs"><b>1 台 Worker</b><div class="mt-2 grid grid-cols-2 gap-2"><div><span class="text-slate-400">Nominal ETA</span><div class="font-black text-slate-900">'+escapeHtml(whatIfEta(whatIfOne.nominal))+'</div><div class="text-[10px] text-slate-400">背景利用率 '+(whatIfOne.nominal?.baselineUtilization==null?'—':(Number(whatIfOne.nominal.baselineUtilization)*100).toFixed(1)+'%')+'</div></div><div><span class="text-slate-400">P95 ETA</span><div class="font-black text-slate-900">'+escapeHtml(whatIfEta(whatIfOne.conservative))+'</div><div class="text-[10px] text-slate-400">背景利用率 '+(whatIfOne.conservative?.baselineUtilization==null?'—':(Number(whatIfOne.conservative.baselineUtilization)*100).toFixed(1)+'%')+'</div></div></div></div>'
          +'<div class="rounded-xl border border-slate-200 bg-white p-3 text-xs"><b>2 台 Worker</b><div class="mt-2 grid grid-cols-2 gap-2"><div><span class="text-slate-400">Nominal ETA</span><div class="font-black text-slate-900">'+escapeHtml(whatIfEta(whatIfTwo.nominal))+'</div><div class="text-[10px] text-slate-400">背景利用率 '+(whatIfTwo.nominal?.baselineUtilization==null?'—':(Number(whatIfTwo.nominal.baselineUtilization)*100).toFixed(1)+'%')+'</div></div><div><span class="text-slate-400">P95 ETA</span><div class="font-black text-slate-900">'+escapeHtml(whatIfEta(whatIfTwo.conservative))+'</div><div class="text-[10px] text-slate-400">背景利用率 '+(whatIfTwo.conservative?.baselineUtilization==null?'—':(Number(whatIfTwo.conservative.baselineUtilization)*100).toFixed(1)+'%')+'</div></div></div></div>'
          +'</div>'
          +(whatIfComponents.length?'<div class="flex flex-wrap gap-2">'+whatIfComponents.map(item=>'<span class="rounded-full border px-2 py-1 text-[10px] font-semibold '+(item.calibrated?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-amber-200 bg-amber-50 text-amber-700')+'">'+escapeHtml(item.label||item.kind||'')+' × '+Number(item.count||0)+' · '+(item.method==='pages'?'頁數校準':item.method==='media_duration'?'影音時長校準':item.method==='class_duration'?'類型中位/P95':'不可估')+'</span>').join('')+'</div>':'')
          +(whatIfLimitations.length?'<div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-800"><b>限制：</b> '+whatIfLimitations.map(item=>escapeHtml(item)).join(' · ')+'</div>':'')
          +'<div class="text-[10px] text-slate-400">試算時間：'+escapeHtml(formatWhen(whatIfResult.generatedAt))+'。這是唯讀容量情境，不會建立 Job、啟動 Worker 或修改排程。</div>'
          +'</div>'
        : '<div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">輸入高峰批次後按「試算高峰」，系統會用目前實測 workload 模型比較 1 台與 2 台 Worker。</div>';

    const predictionState=String(predictionAccuracy.state||'not_started');
    const predictionClasses=predictionState==='low_trust'
      ? 'border-rose-200 bg-rose-50'
      : predictionState==='caution'
        ? 'border-amber-200 bg-amber-50'
        : predictionState==='stable'
          ? 'border-emerald-200 bg-emerald-50'
          : 'border-slate-200 bg-slate-50';
    const predictionMedianError=predictionAccuracy.medianAbsolutePercentageError==null
      ? '資料累積中'
      : formatPercent(predictionAccuracy.medianAbsolutePercentageError);
    const predictionP95Coverage=predictionAccuracy.p95Coverage==null
      ? '資料累積中'
      : formatPercent(predictionAccuracy.p95Coverage);
    const signedBias=predictionAccuracy.medianSignedBias;
    const predictionBiasLabel=predictionAccuracy.bias==='optimistic'
      ? '偏樂觀（實際常比預估慢）'
      : predictionAccuracy.bias==='conservative'
        ? '偏保守（實際常比預估快）'
        : predictionAccuracy.bias==='balanced'
          ? '大致平衡'
          : '資料累積中';
    const predictionBiasValue=signedBias==null
      ? '—'
      : ((Number(signedBias)>=0?'+':'')+(Number(signedBias)*100).toFixed(1)+'%');
    const predictionWorkloadHtml=predictionWorkloads.length
      ? predictionWorkloads.map(item=>'<div class="rounded-lg border border-slate-200 bg-white p-2.5 text-[11px]"><div class="flex items-center justify-between gap-2"><b>'+escapeHtml(item.label||item.kind||'workload')+'</b><span class="text-[10px] text-slate-400">'+Number(item.evaluated||0)+' 筆</span></div><div class="mt-1 text-slate-600">中位誤差 '+escapeHtml(item.medianAbsolutePercentageError==null?'—':formatPercent(item.medianAbsolutePercentageError))+' · P95涵蓋 '+escapeHtml(item.p95Coverage==null?'—':formatPercent(item.p95Coverage))+'</div><div class="mt-1 text-[10px] text-slate-400">'+escapeHtml(item.bias==='optimistic'?'偏樂觀':item.bias==='conservative'?'偏保守':item.bias==='balanced'?'平衡':'資料不足')+'</div></div>').join('')
      : '<div class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-400">尚無已完成且可回測的事前預測。</div>';

    const workloadProfileHtml=workloadProfiles.length
      ? workloadProfiles.map(profile=>{
          const calibrated=Boolean(profile.calibrated);
          const media=profile.kind==='media';
          const document=profile.kind==='document';
          const specific=media&&Number(profile.medianMediaDurationSeconds||0)>0
            ? '影音中位 '+formatDuration(profile.medianMediaDurationSeconds)+' · 處理/影音 '+Number(profile.medianProcessingToMediaRatio||0).toFixed(2)+'×'
            : document&&Number(profile.medianPageCount||0)>0
              ? '中位 '+Number(profile.medianPageCount||0).toFixed(1)+' 頁 · '+Number(profile.medianSecondsPerPage||0).toFixed(1)+' 秒/頁'
              : '檔案中位 '+formatBytes(profile.medianSourceBytes||0);
          return '<article class="rounded-xl border border-slate-200 bg-white p-3 text-xs">'
            +'<div class="flex flex-wrap items-center justify-between gap-2"><b>'+escapeHtml(profile.label||profile.kind||'workload')+'</b><span class="rounded-full border px-2 py-0.5 text-[10px] font-bold '+(calibrated?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-amber-200 bg-amber-50 text-amber-700')+'">'+(calibrated?'已校準':'樣本不足')+'</span></div>'
            +'<div class="mt-2 grid grid-cols-2 gap-2 text-[11px]"><div><span class="text-slate-400">完成樣本</span><div class="font-bold">'+Number(profile.completedSamples||0)+'</div></div><div><span class="text-slate-400">近期到達率</span><div class="font-bold">'+Number(profile.arrivalPerHour||0).toFixed(2)+'/h</div></div><div><span class="text-slate-400">中位處理</span><div class="font-bold">'+escapeHtml(formatDuration(profile.medianDurationSeconds||0))+'</div></div><div><span class="text-slate-400">P95</span><div class="font-bold">'+escapeHtml(formatDuration(profile.p95DurationSeconds||0))+'</div></div></div>'
            +'<div class="mt-2 text-[10px] text-slate-500">'+escapeHtml(specific)+' · backlog '+Number(profile.backlogJobs||0)+' 筆 / '+escapeHtml(formatBytes(profile.backlogBytes||0))+'</div>'
            +'</article>';
        }).join('')
      : '<div class="rounded-xl border border-slate-200 bg-white px-3 py-3 text-xs text-slate-400">尚無可用 workload 完成樣本。</div>';
    return `<section id="worker-slo-70" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm space-y-4 scroll-mt-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><h5 class="font-black text-slate-900">📈 維運趨勢 / SLO</h5><p class="mt-1 text-[11px] text-slate-500">${escapeHtml(baseline)}</p></div>
        <div class="flex rounded-xl border border-slate-200 bg-slate-50 p-1 text-[11px]">
          <button type="button" data-slo-window="24h" class="rounded-lg px-3 py-1.5 font-bold ${sloWindow==='24h'?'bg-white text-slate-900 shadow-sm':'text-slate-500'}">24 小時</button>
          <button type="button" data-slo-window="7d" class="rounded-lg px-3 py-1.5 font-bold ${sloWindow==='7d'?'bg-white text-slate-900 shadow-sm':'text-slate-500'}">7 天</button>
        </div>
      </div>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-2">
        ${sloMetricCard('🟢','Worker 採樣可用率',workerAvailability,'有效樣本 '+Number(worker.availableSamples||0)+'；未知 '+Number(worker.unknownSamples||0),targetAvailability)}
        ${sloMetricCard('✅','教材成功率',success,'完成 '+Number(material.completedJobs||0)+' / terminal '+Number(material.terminalJobs||0),targetSuccess)}
        ${sloMetricCard('⏱️','教材 P95 處理時間',p95,formatSignedPercent(material.durationChangePercent),targetDuration)}
        ${sloMetricCard('🧯','Incident 平均 MTTR',mttr,'新開 '+Number(incident.opened||0)+' · 恢復 '+Number(incident.resolved||0)+' · 目前 '+Number(incident.currentlyOpen||0))}
      </div>
      <div class="rounded-xl border p-3 ${capacityClasses}">
        <div class="flex flex-wrap items-center justify-between gap-2"><b class="text-sm">${capacityIcon} 容量判讀：${escapeHtml(capacity.label||'目前沒有持續容量壓力訊號')}</b><span class="text-[10px]">判讀窗 ${Number(trend.sampleWindowMinutes||0)} 分鐘</span></div>
        <div class="mt-1 text-[11px]">此判讀會先排除單一尖峰；只有 queue、Worker 數與處理時間等證據持續惡化才升級。</div>
      </div>
      <div class="space-y-2">
        <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-700">趨勢異常判讀</b><span class="text-[10px] text-slate-400">${trendSignals.length} 個持續性訊號</span></div>
        ${trendHtml}
      </div>
      <div class="rounded-xl border p-3 ${forecastClasses}">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div><b class="text-sm text-slate-900">🧮 容量規劃 / Forecast</b><div class="mt-1 text-[11px] text-slate-500">最近 ${Number(forecast.windowHours||0)} 小時 · 模型信心 ${escapeHtml(forecastConfidenceLabel)} · 完成樣本 ${Number(forecast.sample?.completedJobs||0)} 筆</div></div>
          <span class="rounded-full border border-slate-300 bg-white px-2 py-1 text-[10px] font-bold text-slate-700">${escapeHtml(forecastDecision.label||'資料累積中')}</span>
        </div>
        <div class="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-2">
          ${sloMetricCard('📥','近期到達率',arrivalRate,'新工作進入 queue 的速度')}
          ${sloMetricCard('⚙️','單 Worker nominal',workerRate,'依完成 Job 中位處理時間')}
          ${sloMetricCard('🛡️','單 Worker 保守值',workerConservative,'依完成 Job P95 處理時間')}
          ${sloMetricCard('📚','目前 backlog',String(Number(forecastQueue.backlogJobs||0))+' 筆','pending '+Number(forecastQueue.pending||0)+' · retry '+Number(forecastQueue.retry||0)+' · processing '+Number(forecastQueue.processing||0))}
        </div>
        <div class="mt-3 grid lg:grid-cols-2 gap-3">
          <div class="rounded-xl border border-slate-200 bg-white p-3 text-xs">
            <b class="text-slate-800">目前 ${Number(forecastQueue.currentActiveWorkers||0)} 台 Worker</b>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <div><span class="text-slate-400">Nominal ETA</span><div class="font-bold text-slate-800">${escapeHtml(etaText(currentNominal))}</div><div class="text-[10px] text-slate-400">淨消化 ${currentNominal.netDrainPerHour==null?'—':Number(currentNominal.netDrainPerHour).toFixed(2)+'/h'}</div></div>
              <div><span class="text-slate-400">P95 保守 ETA</span><div class="font-bold text-slate-800">${escapeHtml(etaText(currentConservative))}</div><div class="text-[10px] text-slate-400">淨消化 ${currentConservative.netDrainPerHour==null?'—':Number(currentConservative.netDrainPerHour).toFixed(2)+'/h'}</div></div>
            </div>
          </div>
          <div class="rounded-xl border border-slate-200 bg-white p-3 text-xs">
            <b class="text-slate-800">模擬多 1 台 Worker</b>
            <div class="mt-2 grid grid-cols-2 gap-2">
              <div><span class="text-slate-400">Nominal ETA</span><div class="font-bold text-slate-800">${escapeHtml(etaText(plusOneNominal))}</div><div class="text-[10px] text-slate-400">淨消化 ${plusOneNominal.netDrainPerHour==null?'—':Number(plusOneNominal.netDrainPerHour).toFixed(2)+'/h'}</div></div>
              <div><span class="text-slate-400">P95 保守 ETA</span><div class="font-bold text-slate-800">${escapeHtml(etaText(plusOneConservative))}</div><div class="text-[10px] text-slate-400">淨消化 ${plusOneConservative.netDrainPerHour==null?'—':Number(plusOneConservative.netDrainPerHour).toFixed(2)+'/h'}</div></div>
            </div>
          </div>
        </div>
        <div class="mt-3 rounded-xl border p-3 ${predictionClasses}">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div><b class="text-sm text-slate-900">🎯 Prediction Calibration / Forecast 回測</b><div class="mt-1 text-[10px] text-slate-500">只比較 Job 完成前已固定的 service-time prediction 與真實 finished_at − started_at；未實際提交的 What-if 不列入評分。</div></div>
            <span class="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-700">${escapeHtml(predictionAccuracy.label||'尚未開始回測')}</span>
          </div>
          <div class="mt-3 grid grid-cols-2 lg:grid-cols-4 gap-2">
            ${sloMetricCard('🧪','已回測預測',String(Number(predictionAccuracy.evaluated||0))+' 筆','待完成 '+Number(predictionAccuracy.pending||0)+' 筆')}
            ${sloMetricCard('🎯','中位絕對誤差',predictionMedianError,'中位時間誤差 '+formatDuration(predictionAccuracy.medianAbsoluteErrorSeconds||0))}
            ${sloMetricCard('🛡️','P95 涵蓋率',predictionP95Coverage,'實際處理時間落在 P95 預估內的比例')}
            ${sloMetricCard('↔️','預測偏差',predictionBiasValue,predictionBiasLabel)}
          </div>
          <div class="mt-3 rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-[11px] text-slate-600"><b>Forecast 信心：</b>原始 ${escapeHtml(rawForecastConfidenceLabel)} → 回測後 ${escapeHtml(forecastConfidenceLabel)}${rawForecastConfidence!==forecastConfidence?'（已依真實誤差下調）':''}</div>
          <div class="mt-3 grid md:grid-cols-2 xl:grid-cols-4 gap-2">${predictionWorkloadHtml}</div>
          <div class="mt-2 text-[10px] text-slate-400">${escapeHtml(predictionAccuracy.note||'0111 上線後開始累積回測；舊 Job 不會事後補造預測。')}</div>
        </div>
        <div class="mt-3 rounded-xl border border-slate-200 bg-white/80 p-3">
          <div class="flex flex-wrap items-center justify-between gap-2"><b class="text-xs text-slate-800">🧩 Workload 校準</b><span class="text-[10px] font-bold ${workload.fullyCalibrated?'text-emerald-700':'text-amber-700'}">${workload.fullyCalibrated?'混合 workload 已完整校準':'部分校準 / 保留全體 Forecast'}</span></div>
          <div class="mt-1 text-[10px] text-slate-500">文件、影音、圖片等分開學習處理成本；每類至少 ${Number(workload.minimumCompletedPerKind||0)} 筆完成樣本才納入混合容量估算。</div>
          <div class="mt-3 grid md:grid-cols-2 xl:grid-cols-3 gap-2">${workloadProfileHtml}</div>
          <div class="mt-3 grid lg:grid-cols-2 gap-3 text-xs">
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5"><b>目前 Worker · workload-adjusted</b><div class="mt-1">Nominal ETA：<b>${escapeHtml(workloadEta(workloadCurrent.nominal))}</b> · 利用率 ${workloadCurrent.nominal?.utilization==null?'—':(Number(workloadCurrent.nominal.utilization)*100).toFixed(1)+'%'}</div><div>P95 ETA：<b>${escapeHtml(workloadEta(workloadCurrent.conservative))}</b> · 利用率 ${workloadCurrent.conservative?.utilization==null?'—':(Number(workloadCurrent.conservative.utilization)*100).toFixed(1)+'%'}</div></div>
            <div class="rounded-lg border border-slate-200 bg-slate-50 p-2.5"><b>多 1 台 Worker · workload-adjusted</b><div class="mt-1">Nominal ETA：<b>${escapeHtml(workloadEta(workloadPlusOne.nominal))}</b> · 利用率 ${workloadPlusOne.nominal?.utilization==null?'—':(Number(workloadPlusOne.nominal.utilization)*100).toFixed(1)+'%'}</div><div>P95 ETA：<b>${escapeHtml(workloadEta(workloadPlusOne.conservative))}</b> · 利用率 ${workloadPlusOne.conservative?.utilization==null?'—':(Number(workloadPlusOne.conservative.utilization)*100).toFixed(1)+'%'}</div></div>
          </div>
          ${Array.isArray(workload.limitations)&&workload.limitations.length?'<div class="mt-2 text-[10px] text-amber-700">'+workload.limitations.map(item=>escapeHtml(item)).join(' · ')+'</div>':''}
        </div>
        <div class="mt-3 rounded-xl border border-slate-300 bg-slate-50/80 p-3">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div><b class="text-sm text-slate-900">🧪 高峰情境 / Capacity What-if</b><div class="mt-1 text-[10px] text-slate-500">把一批教材瞬間加入目前 Queue，再假設近期背景到達率持續存在，比較 1 台與 2 台 Worker。</div></div>
            <div class="flex flex-wrap gap-1.5"><button type="button" data-capacity-preset="docs" class="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600">10 份文件</button><button type="button" data-capacity-preset="mixed" class="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600">10 文件 + 3×30分影音</button></div>
          </div>
          <div class="mt-3 grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2 text-xs">
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">文件數</span><input data-capacity-field="documentCount" type="number" min="0" max="100" value="${Number(whatIfScenario.documentCount||0)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">平均頁數</span><input data-capacity-field="documentPages" type="number" min="1" max="500" value="${Number(whatIfScenario.documentPages||20)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">影音數</span><input data-capacity-field="mediaCount" type="number" min="0" max="50" value="${Number(whatIfScenario.mediaCount||0)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">平均影音分鐘</span><input data-capacity-field="mediaMinutes" type="number" min="1" max="240" value="${Number(whatIfScenario.mediaMinutes||30)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">圖片數</span><input data-capacity-field="imageCount" type="number" min="0" max="100" value="${Number(whatIfScenario.imageCount||0)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
            <label class="space-y-1"><span class="text-[10px] font-bold text-slate-500">ZIP 數</span><input data-capacity-field="archiveCount" type="number" min="0" max="50" value="${Number(whatIfScenario.archiveCount||0)}" class="w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5"></label>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2"><button type="button" data-capacity-whatif-run class="rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white disabled:opacity-50" ${whatIfLoading?'disabled':''}>${whatIfLoading?'試算中…':'試算高峰'}</button><span class="text-[10px] text-slate-400">文件優先用秒/頁；影音優先用處理/影音倍率；樣本不足時不硬算。</span></div>
          <div class="mt-3">${whatIfResultHtml}</div>
        </div>
        <div class="mt-3 rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-xs text-slate-700"><b>判讀：</b>${escapeHtml(forecastDecision.detail||'樣本仍在累積。')}</div>
        ${blockers.length?'<div class="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800"><b>先排除 Incident：</b> '+blockers.map(item=>escapeHtml(item.code||item.title||'')).join('、')+'</div>':''}
        ${forecastLimitations.length?'<details class="mt-2 text-[10px] text-slate-500"><summary class="cursor-pointer font-bold">模型限制 / 為什麼目前信心不足</summary><ul class="mt-1 list-disc space-y-1 pl-5">'+forecastLimitations.map(item=>'<li>'+escapeHtml(item)+'</li>').join('')+'</ul></details>':''}
        <div class="mt-2 text-[10px] text-slate-400">Forecast 是容量情境模型，不是正式 SLO，也不會自動啟動第二台 Worker。nominal 使用中位處理時間；保守情境使用 P95。</div>
      </div>
      <div class="grid lg:grid-cols-2 gap-3">
        <div class="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-700">Queue depth 趨勢</b><span class="text-[10px] text-slate-400">最高 ${Number(queue.maxPendingJobs||0)} · 最久等待 ${escapeHtml(formatDuration(queue.maxOldestPendingAgeSeconds||0))}</span></div>
          <div class="mt-3">${sloBarRows(series,'pendingJobsAverage',maxPending,value=>Number(value).toFixed(1))}</div>
        </div>
        <div class="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
          <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-700">完成處理時間趨勢</b><span class="text-[10px] text-slate-400">目前平均 ${escapeHtml(formatDuration(material.averageDurationSeconds||0))}</span></div>
          <div class="mt-3">${sloBarRows(series,'completedDurationAverageSeconds',maxDuration,value=>formatDuration(value))}</div>
        </div>
      </div>
      <div class="grid lg:grid-cols-2 gap-3">
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-xs text-slate-700">最常觸發 Incident 的元件</b><div class="mt-2 flex flex-wrap gap-2">${top.length?top.map(item=>'<span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-semibold text-slate-600">'+escapeHtml(item.code||'UNKNOWN')+' · '+Number(item.count||0)+'</span>').join(''):'<span class="text-[11px] text-slate-400">0110 Incident 歷史資料累積中。</span>'}</div></div>
        <div class="rounded-xl border border-slate-200 bg-white p-3"><b class="text-xs text-slate-700">資料覆蓋</b><div class="mt-2 text-[11px] text-slate-600">10 分鐘採樣 ${Number(coverage.windowSampleCount||0)} / ${Number(coverage.expectedSampleCount||0)}，覆蓋約 ${coveragePct}%${coverage.firstSampleAt?'；首次 '+escapeHtml(formatWhen(coverage.firstSampleAt)):''}。</div><div class="mt-1 text-[10px] text-slate-400">${escapeHtml(coverage.note||'')}</div></div>
      </div>
    </section>`;
  }

  function bindCapacitySimulationControls() {
    panel.querySelectorAll('[data-capacity-field]').forEach(input=>{
      const key=String(input.dataset.capacityField||'');
      input.oninput=()=>{
        const value=Number(input.value);
        if(Number.isFinite(value))whatIfScenario={...whatIfScenario,[key]:value};
      };
    });
    panel.querySelectorAll('[data-capacity-preset]').forEach(button=>{
      button.onclick=()=>{
        if(button.dataset.capacityPreset==='docs'){
          whatIfScenario={documentCount:10,documentPages:20,mediaCount:0,mediaMinutes:30,imageCount:0,archiveCount:0};
        }else{
          whatIfScenario={documentCount:10,documentPages:20,mediaCount:3,mediaMinutes:30,imageCount:0,archiveCount:0};
        }
        whatIfResult=null;
        renderWorkerStatus(true);
      };
    });
    const run=panel.querySelector('[data-capacity-whatif-run]');
    if(run)run.onclick=async()=>{
      if(whatIfLoading)return;
      whatIfLoading=true;
      await renderWorkerStatus(false);
      try{
        whatIfResult=await loadCapacitySimulation(whatIfScenario);
      }catch(error){
        whatIfResult={
          available:false,
          generatedAt:new Date().toISOString(),
          decision:{label:'高峰試算失敗',detail:String(error?.message||error||'無法完成試算')},
          limitations:[String(error?.message||error||'無法完成試算')]
        };
      }finally{
        whatIfLoading=false;
        await renderWorkerStatus(false);
      }
    };
  }

  function bindSloControls() {
    panel.querySelectorAll('[data-slo-window]').forEach(button=>{
      button.onclick=async()=>{
        const next=button.dataset.sloWindow==='7d'?'7d':'24h';
        if(next===sloWindow)return;
        sloWindow=next;
        const host=document.getElementById('worker-slo-70');
        if(host)host.innerHTML='<div class="animate-pulse text-sm text-slate-400">讀取維運趨勢中…</div>';
        await renderWorkerStatus(true);
      };
    });
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
    if(category==='trend'||category==='capacity'||incident.incidentType==='trend_anomaly')return ['📈','趨勢'];
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
    if(type==='trend_anomaly'||category==='trend'||category==='capacity')return {href:'#worker-slo-70',label:'查看 SLO 趨勢'};
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
    if (force || panel.dataset.workerLoaded !== 'true') {
      panel.innerHTML = `<section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div class="animate-pulse text-sm text-slate-400">讀取 Worker 與佇列狀態中…</div></section>${firstRunGuide()}`;
    }
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
      const [sloMetrics,emailHealth] = await Promise.all([loadOperationalMetrics(sloWindow, force),loadEmailDeliveryHealth()]);
      const workerStatusAvailable = data.workerStatusAvailable !== false;
      const workerStatusError = data.workerStatusError || '無法讀取本機 Worker 狀態，請稍後再試。';
      const workers = Array.isArray(data.workers) ? data.workers : [];
      const activeWorkers = workerStatusAvailable ? workers.filter(worker => worker.status === 'online' || worker.status === 'busy') : [];
      const recentOfflineWorkers = workerStatusAvailable ? workers.filter(worker => worker.status === 'offline') : [];
      const aiWorkers = Array.isArray(data.aiWorkers) ? data.aiWorkers : [];
      const activeAiWorkers = workerStatusAvailable ? aiWorkers.filter(worker => worker.status === 'online') : [];
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      const activeJobCount = Number(data.pendingJobs || 0) + Number(data.processingJobs || 0) + Number(data.retryJobs || 0);
      refreshDelayMs = activeJobCount > 0 ? 10000 : 30000;
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
      const aiWorkerBody = !workerStatusAvailable
        ? `<div class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-700">AI Worker heartbeat 同樣無法讀取；先檢查 Web / DB 狀態。</div>`
        : aiWorkers.length
          ? aiWorkers.map(worker => {
              const online = worker.status === 'online';
              const queues = Array.isArray(worker.queues) ? worker.queues : [];
              const kokoro = worker.kokoroInstalled === true ? '🟢 Kokoro' : worker.kokoroInstalled === false ? '🔴 Kokoro' : '🟠 Kokoro 待回報';
              const whisper = worker.whisperInstalled === true ? '🟢 Whisper' : '⚪ Whisper';
              return `<div class="rounded-2xl border ${online ? 'border-emerald-200 bg-emerald-50/60' : 'border-amber-200 bg-amber-50/60'} p-4 shadow-sm"><div class="flex flex-wrap items-start justify-between gap-2"><div><div class="font-black text-slate-900">${online ? '🟢 AI Worker 在線' : '🟠 AI Worker 離線'}</div><div class="mt-1 text-xs text-slate-600">${escapeHtml(worker.workerMachine || worker.workerId || 'AI Worker')} · 最後回報 ${formatWhen(worker.lastSeen)}</div></div><div class="text-xs font-bold text-slate-700">${kokoro} · ${whisper}</div></div><div class="mt-2 text-[11px] text-slate-600">Queues：${escapeHtml(queues.join('、') || '尚未回報 queue capabilities')}</div></div>`;
            }).join('')
          : `<div class="rounded-2xl border border-dashed border-amber-300 bg-amber-50 p-4 text-sm text-amber-900"><b>🟠 AI Worker 尚未回報</b><div class="mt-1 text-xs leading-5">教材 Worker 正常不代表 AI Worker 已啟動。請確認院內電腦的 <code>run_ai_worker_autostart.ps1</code>／Teacher AI Worker 排程仍在執行；一旦 heartbeat 寫入同一資料庫，這裡會直接顯示 Kokoro 與 queue 能力。</div></div>`;
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
            ${queueCard('❌', `近${Number(data.failedAttentionHours||24)}小時失敗`, data.failedJobs, Number(data.failedJobsTotal||0) > Number(data.failedJobs||0) ? `歷史共 ${Number(data.failedJobsTotal||0)} 筆；舊失敗保留在紀錄但不持續亮紅燈` : '近期失敗會在下方顯示原因')}
          </div>
          <div class="grid sm:grid-cols-3 gap-2 text-xs">
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">最舊待處理等待：</span><b>${formatDuration(data.oldestPendingAgeSeconds)}</b>${data.oldestPendingAt ? ` · ${formatWhen(data.oldestPendingAt)}` : ''}</div>
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">近${Number(data.metricsWindowHours||24)}小時失敗率：</span><b>${Number(data.recentTerminalJobs||0) ? Math.round(Number(data.recentFailureRate || 0) * 100) + '%' : '—'}</b> · ${Number(data.recentTerminalJobs || 0)} 筆完成/失敗</div>
            <div class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><span class="text-slate-500">近${Number(data.metricsWindowHours||24)}小時平均完成：</span><b>${Number(data.recentTerminalJobs||0) ? formatDuration(data.averageCompletedDurationSeconds) : '—'}</b></div>
          </div>
          <div class="grid sm:grid-cols-3 gap-2 text-xs">
            <div class="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2"><span class="text-emerald-700">🟢 處理中 heartbeat 正常：</span><b>${Number(data.healthyProcessingJobs||0)}</b><div class="mt-1 text-[10px]">在線 Worker ${activeWorkers.length} 台</div></div>
            <div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2"><span class="text-amber-700">🟠 回報延遲：</span><b>${Number(data.heartbeatDelayedJobs||0)}</b><div class="mt-1 text-[10px]">警戒 ${formatDuration(data.heartbeatWarningSeconds||120)}</div></div>
            <div class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2"><span class="text-rose-700">🔴 可能卡住：</span><b>${Number(data.stalledJobs||0)}</b><div class="mt-1 text-[10px]">stale ${formatDuration(data.staleThresholdSeconds||1800)}</div></div>
          </div>
          <div class="text-xs rounded-xl bg-slate-50 border border-slate-200 px-3 py-2">Shared staging：<b>${escapeHtml(staging.backend || '未設定')}</b> · ${staging.available ? '可用' : '不可用'}${staging.shared ? ' · Web/Worker 共用' : ''}</div>
          ${operationalIssueHtml}
        </section>
        ${renderSloDashboard(sloMetrics)}
        ${renderEmailDeliveryHealth(emailHealth)}
        <section id="worker-runtime-70" class="space-y-3 scroll-mt-4">
          <div class="flex items-center justify-between"><h5 class="font-black text-slate-900">教材 Worker</h5><span class="text-xs text-slate-400">${workerSummary}</span></div>
          ${workerBody}
        </section>
        <section id="ai-worker-runtime-70" class="space-y-3 scroll-mt-4">
          <div class="flex items-center justify-between gap-3"><div><h5 class="font-black text-slate-900">AI Worker</h5><p class="mt-1 text-[11px] text-slate-500">AI 出題、講稿、PowerPoint、Kokoro 配音、字幕與影片共用；與教材轉檔 Worker 分開顯示。</p></div><span class="text-xs text-slate-400">${activeAiWorkers.length ? activeAiWorkers.length + ' 台在線' : '尚無在線回報'}</span></div>
          ${aiWorkerBody}
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
      panel.dataset.workerLoaded = 'true';
      document.getElementById('worker-refresh-70').onclick = () => renderWorkerStatus(true);
      bindIncidentControls();
      bindSloControls();
      bindCapacitySimulationControls();
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

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = null;
      return;
    }
    if (!panel.classList.contains('hidden') && !modal.classList.contains('hidden')) {
      void renderWorkerStatus(false);
    }
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
