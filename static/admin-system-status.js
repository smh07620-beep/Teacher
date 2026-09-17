/* Teacher 7.4 · System status presentation.
 * Storage migration actions remain in admin-system.js. This module owns only
 * the health/storage/AI overview that previously lived in system-admin.js.
 */
(function(){
  'use strict';

  function systemStatusCard(icon,title,state,detail,tone='slate'){
    const classes={
      emerald:'border-emerald-200 bg-emerald-50 text-emerald-900',
      amber:'border-amber-200 bg-amber-50 text-amber-900',
      rose:'border-rose-200 bg-rose-50 text-rose-900',
      slate:'border-slate-200 bg-slate-50 text-slate-900'
    };
    return `<div class="rounded-xl border p-4 ${classes[tone]||classes.slate}"><div class="text-sm font-black">${icon} ${escapeHtml(title)}</div><div class="text-xs font-bold mt-2">${escapeHtml(state)}</div><div class="text-[11px] opacity-75 mt-1 break-all">${escapeHtml(detail||'')}</div></div>`;
  }

  async function renderAdminSystemStatus(force=false){
    const cards=document.getElementById('admin-system-health');
    const storage=document.getElementById('admin-system-storage');
    if(!cards||!storage)return;
    cards.innerHTML='<div class="col-span-full text-xs text-slate-400">檢查服務中…</div>';
    storage.textContent='讀取儲存狀態中…';
    const key=await getAdminKey();
    if(!key)return;
    try{
      const [healthResponse,storageResponse,aiResponse]=await Promise.all([
        fetch('/health'),
        fetch(`/api/storage-status${force?'?refresh=1':''}`,{headers:{'X-Admin-Key':key}}),
        fetch('/api/ai-questions/status',{headers:{'X-Admin-Key':key}})
      ]);
      const health=await healthResponse.json().catch(()=>({}));
      const state=await storageResponse.json().catch(()=>({}));
      const ai=await aiResponse.json().catch(()=>({}));
      const dbOk=!!health.ok;
      cards.innerHTML=
        systemStatusCard('🖥️','Render / Web',dbOk?'正常':'異常',health.service||'',dbOk?'emerald':'rose')+
        systemStatusCard('🗄️','Supabase / Database',dbOk?'可連線':'待確認','健康檢查已通過即表示 Flask 與初始化流程正常',dbOk?'emerald':'amber')+
        systemStatusCard('🟣','MEGA',state.megaConfigured?(state.megaError?'已設定但檢查失敗':'已設定'):'未設定',state.megaSpace?`${state.megaSpace.usedGb??'?'} / ${state.megaSpace.totalGb??'?'} GB；網站上限 ${state.megaFreeLimitGb||18} GB`:(state.megaError||''),state.megaConfigured&&!state.megaError?'emerald':(state.megaConfigured?'amber':'rose'))+
        systemStatusCard('🤖','Groq AI',ai.configured?'已設定':'未設定',`${ai.provider||''} ${ai.model||''}`,ai.configured?'emerald':'amber');
      const drive=state.gdriveConfigured?
        (state.gdriveConnected?'✅ Google Drive 備援已連線':((state.activeBackend||state.configuredMode)==='gdrive'?'⚠️ Google Drive 目前使用中，但連線尚未驗證':'ℹ️ Google Drive 備援已設定，尚未執行連線測試（不影響目前主要儲存）')):
        '○ Google Drive 備援未設定';
      storage.innerHTML=`<div class="font-black text-slate-900">教材儲存策略</div><div class="mt-2">主要：<b>${escapeHtml(state.activeBackend||state.configuredMode||'')}</b>　｜　備援：<b>${escapeHtml(state.fallbackBackend||'')}</b>　｜　免費模式：<b>${state.megaFreeOnly?'是':'否'}</b></div><div class="mt-2">${drive}</div><div class="mt-2 text-xs text-slate-500">MEGA ${state.materials?.mega||0} 份、Google Drive ${state.materials?.gdrive||0} 份、R2 ${state.materials?.r2||0} 份、本機 ${state.materials?.local||0} 份</div>${state.error?`<div class="mt-2 text-rose-600">${escapeHtml(state.error)}</div>`:''}`;
    }catch(error){
      cards.innerHTML=systemStatusCard('⚠️','系統狀態','檢查失敗',error.message,'rose');
      storage.textContent='無法讀取儲存狀態';
    }
  }

  window.renderAdminSystemStatus=renderAdminSystemStatus;
})();
