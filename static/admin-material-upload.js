/* Phase 3I · Canonical admin material upload/mutation runtime. */
(function(){
  'use strict';

  window.updateAdminMaterialTypeFields = function(){
    const type=document.getElementById('admin-material-type')?.value||'standard';
    document.getElementById('admin-atlas-fields')?.classList.toggle('hidden',type!=='atlas');
  };

  window.uploadAdminMaterialRequest = function(fd,progressId,fileName,status){
    if(!window.MaterialUploadClient?.enqueue) return Promise.reject(new Error('教材上傳元件尚未載入'));
    return window.MaterialUploadClient.enqueue(fd,{
      fileName,
      fallbackToSameOriginQueue:true,
      onFallback:()=>{
        if(status){
          status.innerHTML=`⬆️ ${escapeHtml(fileName)}｜雲端直傳暫時無法使用，改由安全相容接收<span class="block text-[11px] text-slate-500 mt-1">25MB 以下教材會由網站安全接收後排入同一個背景 Worker；不會改成同步轉檔。</span>`;
        }
      },
      onProgress:e=>{
        if(status){
          const pct=e.percent;
          status.innerHTML=`<b>① 上傳至 R2：${escapeHtml(fileName)}｜${pct}%</b><span class="block text-[11px] text-slate-500 mt-1">${(e.loaded/1024/1024).toFixed(1)} / ${(e.total/1024/1024).toFixed(1)} MB；R2 接收完成後會進入「② 等待 Worker」，直到正式發布完成才算完成。</span>`;
        }
      }
    });
  };

  window.sha256File = async function(file){
    if(!window.MaterialUploadClient?.sha256Blob) throw new Error('教材上傳元件尚未載入');
    return window.MaterialUploadClient.sha256Blob(file);
  };

  window.directR2MaterialUpload = async function(file,meta,status){
    if(!window.MaterialUploadClient?.directUpload) throw new Error('教材上傳元件尚未載入');
    const fd=new FormData();
    fd.append('file',file);
    Object.entries(meta||{}).forEach(([name,value])=>fd.append(name,String(value??'')));
    return window.MaterialUploadClient.directUpload(fd,{fileName:file.name,onProgress:e=>{
      if(status) status.textContent=`⬆️ ${file.name}｜R2 直傳 ${e.percent}%`;
    }});
  };

  let materialUploadCompletionPending=false;
  let materialUploadGuardDepth=0;
  let materialUploadPendingMessage='教材仍在上傳或由 Worker 處理中，請等到正式完成再離開。';

  function beginMaterialUploadGuard(message=''){
    materialUploadGuardDepth+=1;
    if(message)materialUploadPendingMessage=String(message);
    materialUploadCompletionPending=true;
  }

  function endMaterialUploadGuard(){
    materialUploadGuardDepth=Math.max(0,materialUploadGuardDepth-1);
    materialUploadCompletionPending=materialUploadGuardDepth>0;
  }

  window.isTeacherMaterialUploadPending=()=>materialUploadCompletionPending;
  window.teacherMaterialUploadPendingMessage=()=>materialUploadPendingMessage;
  window.beginTeacherMaterialUploadGuard=beginMaterialUploadGuard;
  window.endTeacherMaterialUploadGuard=endMaterialUploadGuard;

  function materialUploadLeaveGuard(event){
    if(!materialUploadCompletionPending)return;
    event.preventDefault();
    event.returnValue='';
    return '';
  }
  window.addEventListener('beforeunload',materialUploadLeaveGuard);

  function materialUploadDurationLabel(seconds){
    const value=Math.max(0,Math.round(Number(seconds||0)));
    if(value<60)return value+' 秒';
    if(value<3600)return Math.floor(value/60)+' 分 '+(value%60)+' 秒';
    return Math.floor(value/3600)+' 小時 '+Math.floor((value%3600)/60)+' 分';
  }

  function materialUploadElapsedSeconds(job){
    const stamp=job?.startedAt||job?.createdAt||job?.updatedAt;
    const parsed=new Date(stamp||Date.now()).getTime();
    return Number.isFinite(parsed)?Math.max(0,Math.round((Date.now()-parsed)/1000)):0;
  }

  function materialUploadProgress(job,averageSeconds){
    const elapsed=materialUploadElapsedSeconds(job);
    const average=Math.max(0,Number(averageSeconds||0));
    const actual=Math.max(0,Math.min(100,Number(job.progressPercent||0)));
    if(job.status==='completed')return {pct:100,label:'完成 · '+materialUploadDurationLabel(elapsed)};
    if(job.status==='failed')return {pct:actual||100,label:'需要處理 · '+materialUploadDurationLabel(elapsed)};
    if(job.status==='cancelled')return {pct:actual||100,label:'已取消'};
    if(job.status==='queued')return {pct:actual||25,label:'R2 已接收 · 等待 Worker '+materialUploadDurationLabel(elapsed)};
    if(job.status==='retry_wait')return {pct:actual||25,label:'等待自動重試 · '+materialUploadDurationLabel(elapsed)};
    const pct=actual||30;
    const remaining=average>elapsed?'估計剩餘約 '+materialUploadDurationLabel(average-elapsed):'已超過近期平均，Worker 仍在處理';
    return {pct,label:(job.stage||'Worker 處理中')+' · 已處理 '+materialUploadDurationLabel(elapsed)+' · '+(average>0?remaining:'估計時間資料累積中')};
  }

  function materialUploadJobLabel(state){
    return ({queued:'等待處理',retry_wait:'等待重試',processing:'處理中',completed:'已完成',failed:'需要處理',cancelled:'已取消'})[state]||'確認狀態中';
  }

  const MATERIAL_UPLOAD_PHASES=['R2 接收','等待 Worker','下載／驗證','轉檔／預覽','正式發布','完成'];

  function materialUploadPhaseIndex(job){
    if(job?.status==='completed')return 5;
    if(['queued','retry_wait'].includes(job?.status))return 1;
    const stage=String(job?.stage||'');
    if(['下載原始檔','驗證教材','內容準備'].includes(stage))return 2;
    if(['轉檔處理','建立預覽'].includes(stage))return 3;
    if(['正式發布','發布確認','完成確認'].includes(stage))return 4;
    if(job?.status==='processing')return 2;
    return 1;
  }

  function renderMaterialUploadTimeline(job){
    const current=materialUploadPhaseIndex(job);
    const failed=['failed','cancelled'].includes(job?.status);
    return '<div class="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-6">'+MATERIAL_UPLOAD_PHASES.map((label,index)=>{
      const done=job?.status==='completed'||index<current;
      const active=index===current&&job?.status!=='completed';
      const cls=failed&&active?'border-rose-300 bg-rose-50 text-rose-700':done?'border-emerald-200 bg-emerald-50 text-emerald-700':active?'border-sky-300 bg-sky-50 text-sky-800':'border-slate-200 bg-slate-50 text-slate-400';
      const mark=done?'✓':failed&&active?'!':active?'●':String(index+1);
      return '<div class="rounded-lg border px-2 py-1 text-[10px] font-bold '+cls+'"><span class="mr-1">'+mark+'</span>'+escapeHtml(label)+'</div>';
    }).join('')+'</div>';
  }

  function renderAdminMaterialUploadJobs(rows,metrics,status){
    if(!status)return;
    const workers=Array.isArray(metrics?.workers)?metrics.workers:[];
    const blocked=workers.find(worker=>worker?.protocolCompatible===false&&['online','busy'].includes(String(worker?.status||'')));
    const onlineCompatible=workers.some(worker=>worker?.protocolCompatible!==false&&['online','busy'].includes(String(worker?.status||'')));
    const average=Math.max(0,Number(metrics?.averageCompletedDurationSeconds||0));
    let warning='';
    if(blocked){
      warning='<div class="mb-2 rounded-lg border border-rose-200 bg-rose-50 p-2 font-bold text-rose-800">⚠ 院內 Worker 協議版本過舊（目前 v'+Number(blocked.protocolVersion||0)+'，系統最低 v'+Number(blocked.minimumProtocolVersion||0)+'）。教材已安全排隊，但不會交給舊版 Worker；請更新院內 Worker 後等待自動接續，不必重新上傳。</div>';
    }else if(!onlineCompatible&&workers.length===0){
      warning='<div class="mb-2 rounded-lg border border-amber-200 bg-amber-50 p-2 font-bold text-amber-800">⚠ 目前尚未收到院內 Worker heartbeat。教材已安全排隊，Worker 上線後會自動接續；請先不要重複上傳。</div>';
    }
    const cards=rows.map(job=>{
      const progress=materialUploadProgress(job,average);
      const failed=['failed','cancelled'].includes(job.status);
      const retryWait=job.status==='retry_wait';
      const retained=job.stagingBackend==='r2'&&['retry_wait','failed'].includes(job.status)
        ? '<div class="mt-1 font-bold text-violet-700">☁ R2 原始檔仍安全保留，可直接重新處理，不必重新上傳；正式完成後才會清除暫存。</div>'
        : '';
      const detail=(failed||retryWait)?(job.error||job.detail||'請查看 Worker / Job 狀態'):(job.detail||job.stage||'');
      const barClass=failed?'bg-rose-500':retryWait?'bg-amber-500':job.status==='completed'?'bg-emerald-500':'bg-sky-600';
      return '<div class="rounded-lg border '+(failed?'border-rose-200 bg-rose-50':'border-sky-100 bg-white')+' p-2"><div class="flex flex-wrap items-center justify-between gap-2"><span><b>'+escapeHtml(job.title||job.originalName||job.id||'教材')+'</b> · '+escapeHtml(materialUploadJobLabel(job.status))+'</span><span class="text-[11px] text-slate-500">'+escapeHtml(progress.label)+'</span></div><div class="mt-1 text-[11px] '+(failed?'text-rose-700':'text-slate-600')+'">'+escapeHtml(detail)+'</div>'+renderMaterialUploadTimeline(job)+retained+'<div class="mt-2 flex items-center justify-between text-[10px] text-slate-500"><span>處理進度 '+progress.pct+'%</span><span>依 Worker 真實回報階段顯示；進度已持久化，剩餘時間僅為近期平均估算</span></div><div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div class="h-full '+barClass+' transition-all" style="width:'+progress.pct+'%"></div></div></div>';
    }).join('');
    const allDone=rows.length>0&&rows.every(job=>job.status==='completed');
    const terminal=rows.length>0&&rows.every(job=>['completed','failed','cancelled'].includes(job.status));
    const heading=allDone?'✅ 教材已正式完成':terminal?'⚠ 教材處理需要注意':'⏳ 正在等待教材正式完成';
    const hint=allDone?'現在可以安全返回課程。':terminal?'請先處理失敗工作；已保留的 R2 原始檔不必重傳。':'請等到全部教材顯示「已完成」再離開；系統會自動更新。';
    status.innerHTML='<div class="rounded-xl border '+(terminal&&!allDone?'border-amber-200 bg-amber-50':'border-sky-200 bg-sky-50')+' p-3 text-left"><div class="flex flex-wrap items-center justify-between gap-2"><b>'+heading+'</b><span class="text-[11px] text-slate-600">'+hint+'</span></div>'+warning+'<div class="mt-2 space-y-2">'+cards+'</div></div>';
  }

  async function fetchAdminMaterialUploadMetrics(){
    try{
      const response=await fetch('/api/material-jobs?limit=20',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      return response.ok?data:{};
    }catch(_error){
      return {};
    }
  }

  async function fetchAdminMaterialUploadJob(id){
    const response=await fetch('/api/material-jobs/'+encodeURIComponent(id),{credentials:'same-origin',cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||('工作 '+id+' 狀態讀取失敗'));
    return data;
  }

  window.waitForAdminMaterialJobs=async function(jobIds,status){
    const unique=[...new Set((jobIds||[]).filter(Boolean).map(String))];
    if(!unique.length)return {rows:[],metrics:{},allDone:true};
    const pollMs=Math.max(500,Number(window.__TEACHER_MATERIAL_UPLOAD_POLL_MS__||3000));
    beginMaterialUploadGuard('教材仍在 Worker 正式處理中，請等到全部顯示「已完成」再離開。');
    try{
      while(true){
        const metrics=await fetchAdminMaterialUploadMetrics();
        const rows=await Promise.all(unique.map(async id=>{
          try{return await fetchAdminMaterialUploadJob(id);}
          catch(error){return {id,status:'unknown',stage:'狀態讀取失敗',detail:error.message,createdAt:new Date().toISOString()};}
        }));
        renderAdminMaterialUploadJobs(rows,metrics,status);
        if(rows.every(job=>job.status==='completed'))return {rows,metrics,allDone:true};
        if(rows.every(job=>['completed','failed','cancelled'].includes(job.status)))return {rows,metrics,allDone:false};
        await new Promise(resolve=>setTimeout(resolve,pollMs));
      }
    }finally{
      endMaterialUploadGuard();
    }
  };

  window.adminUploadMaterials = async function(){
    const input=document.getElementById('admin-pptx-upload-input');
    const files=Array.from(input?.files||[]);
    if(!files.length){ alert('請先選擇要上傳的教材檔案。'); return; }
    const title=document.getElementById('admin-material-title').value.trim();
    const desc=document.getElementById('admin-material-desc').value.trim();
    const group=document.getElementById('admin-material-group').value;
    const category=document.getElementById('admin-material-category').value;
    const status=document.getElementById('admin-upload-status');
    const btn=document.getElementById('admin-upload-btn');
    btn.disabled=true;
    beginMaterialUploadGuard('教材正在上傳至 R2 或等待 Worker 正式完成，請先不要關閉教材工作畫面。');
    try{
    let queued=0;
    const queuedJobs=[];
    const failed=[];
    status.innerHTML='⏳ 準備安全接收 '+files.length+' 份教材…';
    for(let n=0;n<files.length;n++){
      const file=files[n];
      const progressId='manual-'+Date.now()+'-'+n+'-'+Math.random().toString(36).slice(2,8);
      status.innerHTML='⏳ '+(n+1)+'/'+files.length+' 接收「'+escapeHtml(file.name)+'」<span class="block text-[11px] text-slate-500 mt-1">先傳到 R2／安全暫存，再由院內 Worker 轉檔與正式發布；全部正式完成前請先不要離開。</span>';
      const area=document.getElementById('admin-material-area')?.value||currentTrainingArea;
      const courseId=document.getElementById('admin-material-course')?.value||'';
      const materialType=document.getElementById('admin-material-type')?.value||'standard';
      const fd=new FormData();
      fd.append('file',file);
      fd.append('title',title);
      fd.append('desc',desc);
      fd.append('category',category);
      fd.append('group',group);
      fd.append('area',area);
      fd.append('courseId',courseId);
      fd.append('materialType',materialType);
      fd.append('progressId',progressId);
      fd.append('atlasCategory',document.getElementById('admin-atlas-category')?.value||'');
      fd.append('atlasMagnification',document.getElementById('admin-atlas-magnification')?.value||'');
      fd.append('atlasInterpretation',document.getElementById('admin-atlas-interpretation')?.value||'');
      fd.append('atlasClinical',document.getElementById('admin-atlas-clinical')?.value||'');
      fd.append('atlasDifferential',document.getElementById('admin-atlas-differential')?.value||'');
      fd.append('atlasNormality',document.getElementById('admin-atlas-normality')?.value||'');
      fd.append('atlasTags',document.getElementById('admin-atlas-tags')?.value||'');
      try{
        const data=await window.uploadAdminMaterialRequest(fd,progressId,file.name,status);
        queued++;
        if(data.jobId)queuedJobs.push(String(data.jobId));
        status.innerHTML='⏳ ② 等待 Worker｜'+(n+1)+'/'+files.length+'「'+escapeHtml(file.name)+'」已安全接收<span class="block text-[11px] mt-1">'+escapeHtml(data.jobId||'')+'｜R2 接收完成不等於教材已完成；接下來會依序顯示下載／驗證、轉檔／預覽、正式發布與完成。</span>';
      }catch(err){
        failed.push({name:file.name,error:err.message});
        status.innerHTML='❌ '+escapeHtml(file.name)+'：'+escapeHtml(err.message)+'<span class="block text-[11px] mt-1">其他檔案會繼續接收。</span>';
      }
    }

    let outcome={rows:[],metrics:{},allDone:queuedJobs.length===0};
    if(queuedJobs.length){
      status.innerHTML='⏳ 已安全接收 '+queued+'/'+files.length+' 份教材，正在等待 Worker 正式完成。<span class="block text-[11px] mt-1">請等到全部教材顯示「已完成」再離開；若 Worker 版本過舊或離線，這裡會直接顯示。</span>';
      outcome=await window.waitForAdminMaterialJobs(queuedJobs,status);
    }

    const workerFailures=(outcome.rows||[]).filter(job=>['failed','cancelled'].includes(job.status));
    if(outcome.allDone&&!failed.length){
      status.innerHTML='✅ '+queued+' 份教材已正式完成並寫入教材清單。現在可以安全離開或返回課程。';
      document.getElementById('admin-material-title').value='';
      document.getElementById('admin-material-desc').value='';
      ['admin-atlas-category','admin-atlas-magnification','admin-atlas-interpretation','admin-atlas-clinical','admin-atlas-differential','admin-atlas-tags'].forEach(id=>{
        const field=document.getElementById(id);
        if(field)field.value='';
      });
    }else{
      const intakeFailureHtml=failed.length?'<details class="mt-2"><summary class="cursor-pointer font-bold">查看 '+failed.length+' 份接收失敗</summary><div class="mt-1 space-y-1">'+failed.map(item=>'<div>• '+escapeHtml(item.name)+'：'+escapeHtml(item.error)+'</div>').join('')+'</div></details>':'';
      const workerFailureHtml=workerFailures.length?'<details class="mt-2"><summary class="cursor-pointer font-bold">查看 '+workerFailures.length+' 份 Worker 需要處理</summary><div class="mt-1 space-y-1">'+workerFailures.map(job=>'<div>• '+escapeHtml(job.title||job.originalName||job.id)+'：'+escapeHtml(job.error||job.detail||materialUploadJobLabel(job.status))+(job.stagingBackend==='r2'?'｜R2 原始檔仍保留，可直接重新處理':'')+'</div>').join('')+'</div></details>':'';
      status.innerHTML='⚠️ 教材尚未全部正式完成；已完成 '+(outcome.rows||[]).filter(job=>job.status==='completed').length+'/'+queued+' 份。'+intakeFailureHtml+workerFailureHtml+'<div class="mt-2 text-[11px] font-bold">請到 Worker / Job 狀態處理失敗工作；不要直接重複上傳已安全接收的檔案。</div>';
    }

    input.value='';
    await renderMaterialJobs(true);
    }finally{
      endMaterialUploadGuard();
      btn.disabled=false;
    }
  };

  window.editAdminMaterial = async function(id){
    const materials = await fetchAdminMaterials();
    const m = materials?.find(x => x.id === id);
    if (!m) return;
    const title = prompt('教材名稱：', m.title || '');
    if (title === null) return;
    const desc = prompt('教材說明：', m.desc || '');
    if (desc === null) return;
    const groupOptions = Object.entries(GROUPS).filter(([k,g])=>(m.area||'internal')==='pgy'||!g.pgyOnly).map(([k, g]) => `${k}=${g.label}`).join('、');
    const group = prompt(`所屬組別代碼（${groupOptions}）：`, m.group || 'grpBio');
    if (group === null) return;
    const category = prompt('對應考卷代碼（可於「建立考卷與智慧題庫」查看；留白代表未分類）：', m.category || '');
    if (category === null) return;
    const atlasMeta={...(m.atlasMeta||{})};
    if((m.materialType||'standard')==='atlas'){
      const fields=[['category','圖譜分類'],['magnification','倍率 / 染色'],['interpretation','判讀重點'],['clinical','臨床意義'],['differential','常見鑑別點'],['normality','正／異常標記'],['tags','標籤（逗號分隔）']];
      for(const [k,label] of fields){
        const v=prompt(`${label}：`,atlasMeta[k]||'');
        if(v===null) return;
        atlasMeta[k]=v.trim();
      }
    }
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,desc,category,group,materialType:m.materialType||'standard',atlasMeta})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '修改失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.toggleAdminMaterial = async function(id,active){
    const res = await fetch(`/api/slides/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({active})});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '更新失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };

  window.publishMaterialVersion = async function(id){
    const materials = await fetchAdminMaterials();
    const material = materials?.find(x=>x.id===id);
    if(!material) return alert('找不到教材資料。');
    const nextVersion = Number(material.currentVersion||1)+1;
    const reason = prompt(`發布 V${nextVersion}｜請輸入本次版本變更原因：`, '');
    if(reason===null) return;
    if(!reason.trim()) return alert('版本變更原因不可空白。');
    const requiresRetraining = confirm('這次改版是否要求相關學員重新完成教育訓練？\n\n「確定」＝要求重訓；「取消」＝保留既有完成資格。');
    const finalMessage = requiresRetraining
      ? `將發布 V${nextVersion}，並把相關學員既有完成狀態標記為需重新訓練。歷史完成紀錄不會刪除。\n\n確定繼續？`
      : `將發布 V${nextVersion}，既有完成資格仍有效。\n\n確定繼續？`;
    if(!confirm(finalMessage)) return;
    const res = await fetch(`/api/slides/${encodeURIComponent(id)}/versions`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      credentials:'same-origin',
      body:JSON.stringify({changeReason:reason.trim(),requiresRetraining})
    });
    const data=await res.json().catch(()=>({}));
    if(!res.ok) return alert(data.error||'版本發布失敗');
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    alert(`✅ 已發布 V${Number(data.version||nextVersion)}${requiresRetraining?'，並要求重新訓練。':'。'}`);
  };

  window.viewMaterialVersions = async function(id){
    const res=await fetch(`/api/slides/${encodeURIComponent(id)}/versions`,{credentials:'same-origin'});
    const data=await res.json().catch(()=>[]);
    if(!res.ok) return alert(data.error||'讀取版本紀錄失敗');
    const rows=Array.isArray(data)?data:[];
    if(!rows.length) return alert('目前沒有版本紀錄。');
    const text=rows.slice(0,20).map(v=>{
      const retraining=v.requiresRetraining?'｜要求重訓':'';
      const who=v.publishedBy?`｜${v.publishedBy}`:'';
      const when=v.publishedAt?`｜${v.publishedAt}`:'';
      return `V${Number(v.version||1)}${retraining}${who}${when}\n${v.changeReason||'未填寫變更原因'}`;
    }).join('\n\n');
    alert(`教材版本紀錄\n\n${text}`);
  };

  window.deleteAdminMaterial = async function(id){
    if (!confirm('確定刪除這份教材嗎？教材檔案與轉換圖片都會刪除，此操作無法復原。')) return;
    const res = await fetch(`/api/slides/${id}`, {method:'DELETE',});
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { alert(data.error || '刪除失敗'); return; }
    invalidateAdminMaterialsCache();
    await renderAdminMaterials(true);
    await renderAdminCourseMaterialHub(true);
    await renderSlidesGrid();
  };
})();