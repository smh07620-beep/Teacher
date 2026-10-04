/* Phase F3-2 · evidence-gated teacher intervention controls. */
(function(){
  'use strict';

  const ACTIVE=new Set(['open','in_progress','ready_for_retest']);
  const ABNORMAL=new Set(['overdue','retraining','remediation']);
  const labels={
    open:'待處理',
    in_progress:'處理中',
    ready_for_retest:'準備再測',
    resolved:'已結案',
    cancelled:'已取消'
  };
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));

  async function request(url,options={}){
    const response=await fetch(url,{
      credentials:'same-origin',
      cache:'no-store',
      headers:{'Content-Type':'application/json',...(options.headers||{})},
      ...options
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      const error=new Error(data.error||'介入追蹤操作失敗');
      error.code=data.code||'';
      error.data=data;
      throw error;
    }
    return data;
  }

  function filterQuery(){
    const query=new URLSearchParams();
    const area=document.getElementById('admin-compliance-area')?.value||'';
    const group=document.getElementById('admin-compliance-group')?.value||'';
    const courseId=document.getElementById('admin-compliance-course')?.value||'';
    if(area)query.set('area',area);
    if(group)query.set('group',group);
    if(courseId)query.set('courseId',courseId);
    return query;
  }

  function ensureOverview(){
    const view=document.getElementById('admin-competency-matrix-view');
    const summary=document.getElementById('admin-competency-matrix-summary');
    if(!view||!summary)return null;
    let host=document.getElementById('admin-training-intervention-overview-f3');
    if(host)return host;
    host=document.createElement('section');
    host.id='admin-training-intervention-overview-f3';
    host.className='mb-3 rounded-xl border border-indigo-100 bg-indigo-50/30 p-3';
    host.innerHTML='<div class="text-xs text-slate-500">正在讀取介入成效…</div>';
    summary.before(host);
    return host;
  }

  async function loadOverview(){
    const host=ensureOverview();
    if(!host)return;
    try{
      const data=await request('/api/training-interventions?'+filterQuery().toString());
      const s=data.summary||{};
      const avg=s.averageResolutionHours===null||s.averageResolutionHours===undefined?'—':Number(s.averageResolutionHours).toFixed(1)+' 小時';
      host.innerHTML=
        '<div class="flex items-center justify-between gap-2"><div><b class="text-xs text-slate-900">🧭 介入追蹤成效</b><p class="mt-1 text-[10px] text-slate-500">只統計正式介入案件；結案仍需真實學習／考核證據解除異常。</p></div><button type="button" data-intervention-overview-refresh class="text-[10px] font-bold text-indigo-700">↻ 更新</button></div>'+
        '<div class="mt-2 grid grid-cols-2 md:grid-cols-5 gap-2">'+[
          ['處理中',s.active||0],
          ['可結案',s.readyToResolve||0],
          ['已結案',s.resolved||0],
          ['結案率',Number(s.resolutionRate||0).toFixed(1)+'%'],
          ['平均結案時間',avg]
        ].map(([label,value])=>'<div class="rounded-lg border border-indigo-100 bg-white px-2.5 py-2"><div class="text-[9px] text-slate-400">'+label+'</div><div class="mt-0.5 text-sm font-black text-slate-900">'+esc(value)+'</div></div>').join('')+
        '</div>';
      host.querySelector('[data-intervention-overview-refresh]')?.addEventListener('click',()=>void loadOverview());
    }catch(error){
      if(error.code==='FORBIDDEN'){
        host.remove();
        return;
      }
      host.innerHTML='<div class="text-xs text-rose-700">❌ '+esc(error.message||'介入成效讀取失敗')+'</div>';
    }
  }

  function planHtml(caseItem){
    const plan=caseItem?.plan||{};
    const materials=Array.isArray(plan.reviewMaterials)?plan.reviewMaterials:[];
    const parts=[];
    if(plan.type==='remediation'){
      parts.push('<div class="text-[11px] text-orange-800">最近考核 '+esc(plan.score??'—')+' / 及格 '+esc(plan.passingScore??'—')+'；差距 '+esc(plan.scoreGap??'—')+' 分。</div>');
    }
    if(plan.type==='overdue'&&plan.dueAt){
      parts.push('<div class="text-[11px] text-rose-700">原截止：'+esc(String(plan.dueAt).slice(0,10))+'</div>');
    }
    if(materials.length){
      parts.push('<div class="mt-2 flex flex-wrap gap-1.5">'+materials.map(item=>'<span class="rounded-full border border-indigo-100 bg-white px-2 py-1 text-[10px] text-slate-700">'+esc(item.title||item.id)+'</span>').join('')+'</div>');
    }
    return parts.join('');
  }

  function actions(caseItem,item){
    const status=String(caseItem?.status||'');
    const buttons=[];
    if(status==='open'){
      buttons.push(['開始追蹤','in_progress','bg-indigo-700 text-white']);
    }
    if(status==='in_progress'&&caseItem?.kind==='remediation'){
      buttons.push(['準備再測','ready_for_retest','bg-orange-600 text-white']);
    }
    if(status==='ready_for_retest'){
      buttons.push(['回到處理中','in_progress','border border-slate-200 bg-white text-slate-700']);
    }
    if(ACTIVE.has(status)){
      buttons.push(['嘗試結案','resolved','bg-emerald-700 text-white']);
      buttons.push(['取消案件','cancelled','border border-rose-200 bg-white text-rose-700']);
    }
    return buttons.map(([label,target,classes])=>
      '<button type="button" data-intervention-status="'+esc(target)+'" class="rounded-lg px-2.5 py-1.5 text-[11px] font-bold '+classes+'">'+esc(label)+'</button>'
    ).join('');
  }

  async function loadFor(item,host){
    const courseId=String(item?.courseId||'');
    const username=String(item?.username||'').toLowerCase();
    if(!courseId||!username)return;
    host.innerHTML='<div class="text-xs text-slate-500">正在讀取介入追蹤…</div>';
    try{
      const data=await request('/api/training-interventions?courseId='+encodeURIComponent(courseId));
      const rows=(data.items||[]).filter(row=>String(row.username||'').toLowerCase()===username);
      const active=rows.find(row=>ACTIVE.has(String(row.status||'')))||null;
      render(host,item,active,rows);
    }catch(error){
      if(error.code==='FORBIDDEN'){
        host.innerHTML='<div class="text-[11px] text-slate-500">目前帳號可查看證據，但沒有介入案件管理權限。</div>';
        return;
      }
      host.innerHTML='<div class="text-xs text-rose-700">❌ '+esc(error.message||'介入追蹤讀取失敗')+'</div>';
    }
  }

  function render(host,item,active,history){
    const currentStatus=String(item?.status||'');
    if(!active){
      const recent=(history||[])[0]||null;
      host.innerHTML=
        '<div class="flex flex-wrap items-start justify-between gap-3"><div><b class="text-xs text-slate-900">🧭 教學介入追蹤</b><p class="mt-1 text-[11px] text-slate-500">'+
        (ABNORMAL.has(currentStatus)
          ? '目前狀態可建立正式介入案件；案件只記錄追蹤，不會改寫學習／考試證據。'
          : '目前真實證據沒有逾期、重訓或補強狀態。')+
        '</p></div>'+
        (ABNORMAL.has(currentStatus)?'<button type="button" data-intervention-create class="rounded-lg bg-indigo-700 px-3 py-1.5 text-[11px] font-bold text-white">建立介入追蹤</button>':'')+
        '</div>'+
        (recent?'<div class="mt-2 text-[10px] text-slate-400">最近案件：'+esc(labels[recent.status]||recent.status)+' · '+esc(String(recent.updatedAt||'').slice(0,10))+'</div>':'');
      bind(host,item,null);
      return;
    }

    const eligibility=active?.resolutionEligible
      ? '<div class="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-2 text-[11px] font-bold text-emerald-700">✓ 真實證據已解除原異常，目前可以結案。</div>'
      : '';
    host.innerHTML=
      '<div class="flex flex-wrap items-start justify-between gap-3">'+
        '<div><div class="flex items-center gap-2"><b class="text-xs text-slate-900">🧭 教學介入追蹤</b><span class="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold text-indigo-700">'+esc(labels[active.status]||active.status)+'</span></div>'+
        '<p class="mt-1 text-[11px] text-slate-500">案件 '+esc(active.id)+' · 來源狀態 '+esc(active.sourceStatus||active.kind)+'</p></div>'+
        '<div class="flex flex-wrap gap-2">'+actions(active,item)+'</div>'+
      '</div>'+
      '<div class="mt-3 grid lg:grid-cols-2 gap-3">'+
        '<label class="text-[11px] font-bold text-slate-600">給學員的訊息<textarea data-intervention-learner-message rows="3" class="learning-input mt-1 w-full">'+esc(active.learnerMessage||'')+'</textarea></label>'+
        '<label class="text-[11px] font-bold text-slate-600">內部追蹤備註<textarea data-intervention-internal-note rows="3" class="learning-input mt-1 w-full">'+esc(active.internalNote||'')+'</textarea></label>'+
      '</div>'+
      planHtml(active)+eligibility+
      '<div class="mt-3 flex items-center gap-2"><button type="button" data-intervention-save class="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-[11px] font-bold text-indigo-700">儲存訊息／備註</button><span data-intervention-feedback class="text-[10px] text-slate-400"></span></div>';
    bind(host,item,active);
  }

  function bind(host,item,active){
    host.querySelector('[data-intervention-create]')?.addEventListener('click',async()=>{
      const button=host.querySelector('[data-intervention-create]');
      if(button)button.disabled=true;
      try{
        await request('/api/training-interventions',{
          method:'POST',
          body:JSON.stringify({username:item.username,courseId:item.courseId})
        });
        await loadFor(item,host);
        await loadOverview();
      }catch(error){
        alert(error.message||'建立介入追蹤失敗');
        if(button)button.disabled=false;
      }
    });

    host.querySelector('[data-intervention-save]')?.addEventListener('click',async()=>{
      if(!active)return;
      const feedback=host.querySelector('[data-intervention-feedback]');
      try{
        await request('/api/training-interventions/'+encodeURIComponent(active.id),{
          method:'PATCH',
          body:JSON.stringify({
            learnerMessage:host.querySelector('[data-intervention-learner-message]')?.value||'',
            internalNote:host.querySelector('[data-intervention-internal-note]')?.value||''
          })
        });
        if(feedback)feedback.textContent='✓ 已儲存';
        await loadFor(item,host);
        await loadOverview();
      }catch(error){
        if(feedback)feedback.textContent='❌ '+(error.message||'儲存失敗');
      }
    });

    host.querySelectorAll('[data-intervention-status]').forEach(button=>button.addEventListener('click',async()=>{
      if(!active)return;
      const target=button.dataset.interventionStatus;
      if(target==='cancelled'&&!confirm('確定取消這筆介入追蹤？原始學習／考試紀錄不會被更動。'))return;
      button.disabled=true;
      try{
        await request('/api/training-interventions/'+encodeURIComponent(active.id),{
          method:'PATCH',
          body:JSON.stringify({
            status:target,
            learnerMessage:host.querySelector('[data-intervention-learner-message]')?.value||active.learnerMessage||'',
            internalNote:host.querySelector('[data-intervention-internal-note]')?.value||active.internalNote||''
          })
        });
        await loadFor(item,host);
        await loadOverview();
      }catch(error){
        alert(error.message||'介入狀態更新失敗');
        button.disabled=false;
      }
    }));
  }

  for(const id of ['admin-compliance-area','admin-compliance-group','admin-compliance-course']){
    document.getElementById(id)?.addEventListener('change',()=>void loadOverview());
  }

  document.addEventListener('training-intervention:evidence',event=>{
    const item=event.detail?.item;
    const host=document.getElementById('admin-training-intervention-f3');
    if(item&&host)void loadFor(item,host);
  });

  window.TrainingInterventionF3=Object.freeze({loadFor,loadOverview});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>void loadOverview(),{once:true});
  else void loadOverview();
})();
