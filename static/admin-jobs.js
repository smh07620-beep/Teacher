/* Phase 3H · Canonical admin material jobs/Worker queue runtime. */
(function(){
  'use strict';

  let materialJobsRefreshTimer = null;

  window.materialJobStatusLabel = function(status){
    return ({queued:'等待處理',retry_wait:'等待重試',processing:'背景處理中',completed:'已完成',failed:'失敗',cancelled:'已取消'})[status]||status||'未知';
  };

  window.materialJobStatusClass = function(status){
    return status==='completed'?'text-emerald-700 bg-emerald-50 border-emerald-200':
      status==='failed'?'text-rose-700 bg-rose-50 border-rose-200':
      status==='processing'?'text-sky-700 bg-sky-50 border-sky-200':
      status==='retry_wait'?'text-amber-700 bg-amber-50 border-amber-200':
      'text-slate-600 bg-slate-50 border-slate-200';
  };

  window.scheduleMaterialJobsRefresh = function(active){
    if(materialJobsRefreshTimer){
      clearTimeout(materialJobsRefreshTimer);
      materialJobsRefreshTimer=null;
    }
    if(active){
      materialJobsRefreshTimer=setTimeout(()=>window.renderMaterialJobs(false),4000);
    }
  };

  window.renderMaterialJobs = async function(force=false){
    const host=document.getElementById('admin-material-jobs-list');
    if(!host) return;
    const key=await getAdminKey();
    if(!key) return;
    try{
      const r=await fetch(`/api/material-jobs?limit=20${force?'&refresh=1':''}`,{headers:{'X-Admin-Key':key},cache:'no-store'});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'背景工作讀取失敗');
      const jobs=d.jobs||[];
      const workers=d.workers||[];
      const worker=workers[0];
      const workerLabel=worker?(worker.status==='busy'?'🟡 Busy':worker.status==='online'?'🟢 Online':'⚪ Offline'):'⚪ Offline';
      const workerDetail=worker?`${worker.workerId}｜FFmpeg ${worker.ffmpeg?'✓':'✕'}｜LibreOffice ${worker.libreOffice?'✓':'✕'}`:'尚未收到本機 Worker heartbeat';
      const workerBuild=worker&&worker.workerVersion?`<div class="mt-1">Version ${escapeHtml(worker.workerVersion)} · SHA ${escapeHtml(worker.workerSha||'unknown')} · ${escapeHtml(worker.workerBranch||'unknown')}</div>`:'';
      const workerUpdate=worker?.updateAvailable?'<div class="mt-1 text-amber-800 font-bold">⚠ Worker 有新版待更新</div>':'';
      const workerChecked=worker?.lastUpdateCheckAt?`<div class="mt-1">Last update check: ${escapeHtml(worker.lastUpdateCheckAt)}</div>`:'';
      const summary=`<div class="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-950"><b>背景教材處理</b><div class="mt-1">Worker：${workerLabel}　${escapeHtml(workerDetail)}</div>${workerBuild}${workerUpdate}${workerChecked}<div class="mt-1">Pending ${Number(d.pendingJobs||0)} · Processing ${Number(d.processingJobs||0)} · Retry ${Number(d.retryJobs||0)} · Failed ${Number(d.failedJobs||0)}</div></div>`;
      if(!jobs.length){
        host.innerHTML=summary+'<p class="text-xs text-slate-400">目前沒有背景教材工作。</p>';
        window.scheduleMaterialJobsRefresh(false);
        return;
      }
      host.innerHTML=summary+jobs.map(j=>{
        const pct=Math.max(0,Math.min(100,Number(j.progress||0)));
        const retry=j.status==='failed'&&j.attempts>=j.maxAttempts;
        return `<div class="rounded-xl border bg-white p-3"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-2 flex-wrap"><span class="text-[10px] border rounded-full px-2 py-0.5 font-bold ${window.materialJobStatusClass(j.status)}">${escapeHtml(window.materialJobStatusLabel(j.status))}</span><b class="text-xs text-slate-800 truncate">${escapeHtml(j.result?.title||j.title||j.result?.filename||j.originalName||j.id)}</b><span class="text-[10px] text-slate-400">${formatFileBytes(j.sourceBytes||0)}</span></div><p class="text-[11px] text-slate-600 mt-1">${escapeHtml(j.stage||'')}｜${escapeHtml(j.detail||'')}</p>${j.error?`<p class="text-[10px] text-rose-600 mt-1">${escapeHtml(j.error)}</p>`:''}</div><div class="flex gap-1 shrink-0">${retry?`<button onclick="retryMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold">重新處理</button>`:''}${['queued','retry_wait'].includes(j.status)?`<button onclick="cancelMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600">取消</button>`:''}</div></div><div class="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden"><div class="h-full bg-sky-500 transition-all" style="width:${j.status==='completed'?100:pct}%"></div></div><div class="mt-1 text-[10px] text-slate-400">工作 ${escapeHtml(j.id)} · 第 ${Number(j.attempts||0)}/${Number(j.maxAttempts||3)} 次${j.materialId?` · 教材 ${escapeHtml(j.materialId)}`:''}</div></div>`;
      }).join('');
      window.scheduleMaterialJobsRefresh(jobs.some(j=>['queued','retry_wait','processing'].includes(j.status)));
    }catch(err){
      host.innerHTML=`<p class="text-xs text-rose-600">❌ ${escapeHtml(err.message)}</p>`;
      window.scheduleMaterialJobsRefresh(false);
    }
  };

  window.retryMaterialJob = async function(id){
    const key=await getAdminKey();
    if(!key) return;
    const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/retry`,{method:'POST',headers:{'X-Admin-Key':key}});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){
      alert(d.error||'重新處理失敗');
      return;
    }
    await window.renderMaterialJobs(true);
  };

  window.cancelMaterialJob = async function(id){
    if(!confirm('確定取消尚未開始的教材背景工作？')) return;
    const key=await getAdminKey();
    if(!key) return;
    const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/cancel`,{method:'POST',headers:{'X-Admin-Key':key}});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){
      alert(d.error||'取消失敗');
      return;
    }
    await window.renderMaterialJobs(true);
  };
})();
