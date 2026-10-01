/* Phase 3H · Canonical admin material jobs/Worker queue runtime. */
(function(){
  'use strict';

  let materialJobsRefreshTimer = null;

  window.materialJobStatusLabel = function(status){
    return ({
      queued:'等待處理',
      retry_wait:'等待處理',
      processing:'處理中',
      completed:'可使用',
      failed:'需要處理',
      cancelled:'需要處理'
    })[status]||'需要處理';
  };

  window.materialJobStatusClass = function(status){
    return status==='completed'?'text-emerald-700 bg-emerald-50 border-emerald-200':
      ['failed','cancelled'].includes(status)?'text-rose-700 bg-rose-50 border-rose-200':
      status==='processing'?'text-sky-700 bg-sky-50 border-sky-200':
      status==='retry_wait'?'text-amber-700 bg-amber-50 border-amber-200':
      'text-slate-600 bg-slate-50 border-slate-200';
  };

  function elapsedSeconds(job){
    const stamp=job.startedAt||job.createdAt||job.updatedAt;
    const parsed=new Date(stamp||Date.now()).getTime();
    if(!Number.isFinite(parsed))return 0;
    return Math.max(0,Math.round((Date.now()-parsed)/1000));
  }

  function durationLabel(seconds){
    const value=Math.max(0,Math.round(Number(seconds||0)));
    if(value<60)return `${value} 秒`;
    if(value<3600)return `${Math.floor(value/60)} 分 ${value%60} 秒`;
    return `${Math.floor(value/3600)} 小時 ${Math.floor((value%3600)/60)} 分`;
  }

  function progressProjection(job,averageSeconds){
    const elapsed=elapsedSeconds(job);
    const average=Math.max(0,Number(averageSeconds||0));
    if(job.status==='completed')return {pct:100,timing:`總耗時 ${durationLabel(elapsed)}`};
    if(job.status==='failed')return {pct:100,timing:`需要處理 · 已經過 ${durationLabel(elapsed)}`};
    if(job.status==='cancelled')return {pct:100,timing:'此工作已取消'};
    if(job.status==='queued')return {pct:8,timing:`已安全排隊 ${durationLabel(elapsed)}`};
    if(job.status==='retry_wait')return {pct:18,timing:`系統將自動再次處理 · 已等待 ${durationLabel(elapsed)}`};
    const pct=average>0?Math.max(25,Math.min(92,Math.round(25+(elapsed/average)*65))):45;
    const remaining=average>elapsed?`估計剩餘約 ${durationLabel(average-elapsed)}`:'已超過近期平均，Worker 仍在處理';
    return {pct,timing:`已處理 ${durationLabel(elapsed)} · ${average>0?remaining:'估計時間資料累積中'}`};
  }

  function humanJobHint(job){
    if(job.status==='completed')return '教材已完成處理，可以回到課程使用。';
    if(job.status==='processing')return 'Worker 正在處理教材，完成後會自動更新。';
    if(job.status==='retry_wait')return '前一次處理未完成，系統會自動再次處理；原始檔會保留。';
    if(job.status==='queued')return '教材已安全排隊；Worker 上線後會自動開始，不需要重新上傳。';
    if(job.status==='failed')return '處理尚未完成，請查看下方處理方式；若原始檔仍保留，可直接重新處理。';
    if(job.status==='cancelled')return '此背景工作已取消；教材尚未變成可使用狀態。';
    return '目前需要確認處理狀態。';
  }

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
    try{
      const r=await fetch(`/api/material-jobs?limit=20${force?'&refresh=1':''}`,{cache:'no-store'});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'背景工作讀取失敗');
      const jobs=d.jobs||[];
      const workerStatusAvailable=d.workerStatusAvailable!==false;
      const workers=workerStatusAvailable&&Array.isArray(d.workers)?d.workers:[];
      const worker=workers[0];
      const protocolBlocked=!!worker&&worker.protocolCompatible===false;
      const workerLabel=!workerStatusAvailable?'❌ 狀態讀取異常':protocolBlocked?'🔴 需更新':worker?(worker.status==='busy'?'🟡 Busy':worker.status==='online'?'🟢 Online':'⚪ Offline'):'⚪ Offline';
      const protocolText=worker&&Number.isFinite(Number(worker.protocolVersion))?`｜Protocol v${Number(worker.protocolVersion)} / 最低 v${Number(worker.minimumProtocolVersion||0)}`:'';
      const workerDetail=!workerStatusAvailable?(d.workerStatusError||'無法讀取本機 Worker 狀態；此訊息不代表 Worker 已離線。'):worker?`${worker.workerId}｜FFmpeg ${worker.ffmpeg?'✓':'✕'}｜LibreOffice ${worker.libreOffice?'✓':'✕'}${protocolText}`:'尚未收到本機 Worker heartbeat';
      const workerBuild=worker&&worker.workerVersion?`<div class="mt-1">Version ${escapeHtml(worker.workerVersion)} · SHA ${escapeHtml(worker.workerSha||'unknown')} · ${escapeHtml(worker.workerBranch||'unknown')}</div>`:'';
      const protocolWarning=protocolBlocked?'<div class="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 font-bold text-rose-800">⚠ 本機 Worker 協議版本過舊。系統已暫停讓它領取新教材；工作會安全留在佇列，不會因此增加重試次數。更新 Worker 後會自動恢復。</div>':'';
      const workerUpdate=worker?.updateAvailable&&!protocolBlocked?'<div class="mt-1 text-amber-800 font-bold">⚠ Worker 有新版待更新；目前協議仍相容，可繼續處理。</div>':'';
      const workerChecked=worker?.lastUpdateCheckAt?`<div class="mt-1">Last update check: ${escapeHtml(worker.lastUpdateCheckAt)}</div>`:'';
      const recentWorkerErrors=jobs.filter(j=>['retry_wait','failed'].includes(j.status)&&String(j.error||j.detail||'').trim()).length;
      const recentTerminalFailures=jobs.filter(j=>j.status==='failed').length;
      const summaryClass=workerStatusAvailable?'border-sky-200 bg-sky-50 text-sky-950':'border-rose-200 bg-rose-50 text-rose-800';
      const average=Math.max(0,Number(d.averageCompletedDurationSeconds||0));
      const averageText=average?` · 近期平均完成 ${durationLabel(average)}`:'';
      const technicalSummary=`Worker：${workerLabel}　${escapeHtml(workerDetail)}${workerBuild}${workerUpdate}${workerChecked}${protocolWarning}`;
      const summary=`<div class="rounded-xl border ${summaryClass} p-3 text-xs"><b>背景教材處理</b><div class="mt-2">等待處理 ${Number(d.pendingJobs||0)+Number(d.retryJobs||0)} · 處理中 ${Number(d.processingJobs||0)} · 需要處理 ${Number(d.failedJobs||0)}${averageText}</div><div class="mt-1 font-bold ${recentWorkerErrors?'text-amber-800':'text-emerald-700'}">${recentWorkerErrors?'有教材需要留意；原始檔仍保留時可直接重新處理。':'目前沒有需要人工處理的教材工作。'}</div><details class="mt-2 rounded-lg border border-slate-200 bg-white/70 p-2"><summary class="cursor-pointer font-bold text-slate-600">查看 Worker 技術狀態</summary><div class="mt-2 text-slate-600">${technicalSummary}<div class="mt-1">近期 Worker 錯誤／重試 ${recentWorkerErrors} · 近期最終失敗 ${recentTerminalFailures}</div></div></details></div>`;
      if(!jobs.length){
        host.innerHTML=summary+'<p class="text-xs text-slate-400">目前沒有背景教材工作。</p>';
        window.scheduleMaterialJobsRefresh(false);
        return;
      }
      host.innerHTML=summary+jobs.map(j=>{
        const projection=progressProjection(j,average);
        const retry=j.status==='failed'&&j.attempts>=j.maxAttempts;
        const barClass=j.status==='failed'?'bg-rose-500':j.status==='retry_wait'?'bg-amber-500':j.status==='completed'?'bg-emerald-500':'bg-sky-500';
        const retained=j.stagingBackend==='r2'&&['retry_wait','failed'].includes(j.status)?'<p class="mt-1 text-[10px] font-bold text-violet-700">☁ 原始檔仍安全保留，可直接重新處理，不必重新上傳；成功完成後才會清除暫存。</p>':'';
        const diagnostic=`<details class="mt-2 rounded-lg border border-slate-200 bg-slate-50/70 p-2 text-[10px] text-slate-600"><summary class="cursor-pointer font-bold">查看處理細節</summary><div class="mt-2 space-y-1"><div><b>階段：</b>${escapeHtml(j.stage||'—')}</div>${j.detail?`<div><b>詳細資訊：</b>${escapeHtml(j.detail)}</div>`:''}${j.error?`<div class="text-rose-700"><b>Worker 錯誤：</b>${escapeHtml(j.error)}</div>`:''}<div>工作 ${escapeHtml(j.id)} · 第 ${Number(j.attempts||0)}/${Number(j.maxAttempts||3)} 次${j.materialId?` · 教材 ${escapeHtml(j.materialId)}`:''}</div></div></details>`;
        return `<div class="rounded-xl border bg-white p-3"><div class="flex items-start justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-2 flex-wrap"><span class="text-[10px] border rounded-full px-2 py-0.5 font-bold ${window.materialJobStatusClass(j.status)}">${escapeHtml(window.materialJobStatusLabel(j.status))}</span><b class="text-xs text-slate-800 truncate">${escapeHtml(j.result?.title||j.title||j.result?.filename||j.originalName||j.id)}</b><span class="text-[10px] text-slate-400">${formatFileBytes(j.sourceBytes||0)}</span></div><p class="text-[11px] text-slate-600 mt-1">${escapeHtml(humanJobHint(j))}</p>${retained}${diagnostic}</div><div class="flex gap-1 shrink-0">${retry?`<button data-csp-click="retryMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold">直接重新處理</button>`:''}${['queued','retry_wait'].includes(j.status)?`<button data-csp-click="cancelMaterialJob('${escapeHtml(j.id)}')" class="text-[10px] px-2 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600">取消</button>`:''}</div></div><div class="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500"><span>處理進度 ${projection.pct}%</span><span>${escapeHtml(projection.timing)}</span></div><div class="mt-1 h-1.5 rounded-full bg-slate-100 overflow-hidden"><div class="h-full ${barClass} transition-all" style="width:${projection.pct}%"></div></div></div>`;
      }).join('');
      window.scheduleMaterialJobsRefresh(jobs.some(j=>['queued','retry_wait','processing'].includes(j.status)));
    }catch(err){
      host.innerHTML=`<p class="text-xs text-rose-600">⚠ 無法讀取教材處理狀態：${escapeHtml(err.message)}</p>`;
      window.scheduleMaterialJobsRefresh(false);
    }
  };

  window.retryMaterialJob = async function(id){
    const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/retry`,{method:'POST',});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){
      alert(d.error||'重新處理失敗');
      return;
    }
    await window.renderMaterialJobs(true);
  };

  window.cancelMaterialJob = async function(id){
    if(!confirm('確定取消尚未開始的教材背景工作？')) return;
    const r=await fetch(`/api/material-jobs/${encodeURIComponent(id)}/cancel`,{method:'POST',});
    const d=await r.json().catch(()=>({}));
    if(!r.ok){
      alert(d.error||'取消失敗');
      return;
    }
    await window.renderMaterialJobs(true);
  };
})();