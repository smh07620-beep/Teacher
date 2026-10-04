/* Phase F6-5 · live post-deploy Production Ready gate. */
(async function(){
  'use strict';
  const R=await (window.TeacherRBAC681Ready||Promise.resolve(window.TeacherRBAC681||{}));
  const roles=R.roles instanceof Set?R.roles:new Set();
  if(!roles.has('system_admin'))return;

  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));

  async function load(){
    const response=await fetch('/api/production-readiness',{credentials:'same-origin',cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||'正式環境驗收狀態讀取失敗');
    return data;
  }

  function ensureHost(){
    const panel=document.getElementById('admin-section-worker');
    if(!panel)return null;
    let host=document.getElementById('production-readiness-f6');
    if(!host){
      host=document.createElement('section');
      host.id='production-readiness-f6';
      host.className='rounded-2xl border border-slate-200 bg-white p-4 shadow-sm';
      panel.prepend(host);
    }
    return host;
  }

  function render(host,data){
    const checks=Array.isArray(data.checks)?data.checks:[];
    const gate=Boolean(data.gate&&data.gate.productionReady);
    const recovery=data.recovery||{};
    const backup=data.backup||{};
    const cards=checks.map(item=>{
      const ok=Boolean(item.ok);
      return '<div class="rounded-xl border '+(ok?'border-emerald-100 bg-emerald-50/60':'border-rose-200 bg-rose-50')+' px-3 py-2">'+
        '<div class="flex items-center justify-between gap-2"><b class="text-xs '+(ok?'text-emerald-800':'text-rose-800')+'">'+(ok?'✓ ':'✕ ')+esc(item.label||item.key||'檢查')+'</b>'+
        '<span class="text-[9px] font-bold text-slate-400">'+(item.required===false?'警告':'必要')+'</span></div>'+
        (item.detail?'<div class="mt-1 text-[10px] text-slate-500">'+esc(item.detail)+'</div>':'')+'</div>';
    }).join('');
    host.className='rounded-2xl border '+(gate?'border-emerald-200':'border-rose-200')+' bg-white p-4 shadow-sm space-y-3';
    host.innerHTML='<div class="flex flex-wrap items-start justify-between gap-3"><div><h5 class="font-black text-slate-900">✅ F6 Production Readiness</h5>'+
      '<p class="mt-1 text-[11px] text-slate-500">CI 全綠是預部署 gate；此處另外驗證正式 Render、Supabase、shared storage、院內 Worker、備份演練與斷鏈。</p></div>'+
      '<div class="flex items-center gap-2"><span class="rounded-full px-2.5 py-1 text-[10px] font-black '+(gate?'bg-emerald-100 text-emerald-800':'bg-rose-100 text-rose-800')+'">'+(gate?'PRODUCTION READY':'BLOCKED')+'</span>'+
      '<button type="button" data-production-readiness-refresh class="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-bold text-slate-700">↻ 更新</button></div></div>'+
      '<div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">'+cards+'</div>'+
      '<div class="grid sm:grid-cols-3 gap-2 text-[11px]">'+
        '<div class="rounded-xl bg-slate-50 p-2.5">Backup：<b>'+(backup.ok?'可建立':'失敗')+'</b><div class="text-[10px] text-slate-400">Restore rehearsal '+(backup.restoreRehearsalOk?'✓':'✕')+'</div></div>'+
        '<div class="rounded-xl bg-slate-50 p-2.5">斷鏈：<b>'+Number(recovery.errorCount||0)+'</b><div class="text-[10px] text-slate-400">warnings '+Number(recovery.warningCount||0)+'</div></div>'+
        '<div class="rounded-xl bg-slate-50 p-2.5">Worker：<b>'+Number((data.worker||{}).active||0)+' 台在線</b><div class="text-[10px] text-slate-400">shared '+esc((data.storage||{}).backend||'—')+'</div></div>'+
      '</div>';
    host.querySelector('[data-production-readiness-refresh]')?.addEventListener('click',()=>void refresh(true));
  }

  async function refresh(force=false){
    const params=new URLSearchParams(location.search);
    const workerVisible=params.get('workspace')==='worker'||!document.getElementById('admin-section-worker')?.classList.contains('hidden');
    if(!force&&!workerVisible)return;
    const host=ensureHost();
    if(!host)return;
    host.innerHTML='<div class="text-sm text-slate-500">正在驗證正式環境…</div>';
    try{render(host,await load());}
    catch(error){host.innerHTML='<div class="text-sm text-rose-700">❌ '+esc(error.message||'正式環境驗收讀取失敗')+'</div>';}
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(()=>void refresh(false));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>void refresh(false),{once:true});
  else void refresh(false);
  window.ProductionReadinessF6=Object.freeze({refresh});
})();
