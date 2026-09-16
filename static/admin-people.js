/* Phase 3C · Admin people/profile module.
 * Profile metadata is deliberately separated from canonical RBAC roles.
 * Teacher 7.1 adds an explicit PGY learner training-audience flag; it never
 * grants signing or management permissions.
 */
(function(){
  'use strict';

  const PROFILE_COMMON_TAGS=['品管','臨床教師','POCT','儀器管理','教學負責'];
  const USER_ROLE_LABELS={student:'學員',clinical_teacher:'臨床教師',group_leader:'組長',education_admin:'教學管理者',system_admin:'系統管理者',auditor:'稽核／唯讀',learner:'學員',teacher:'臨床教師',manager:'教學管理者'};
  const USER_AREA_LABELS={internal:'院內',pgy:'PGY'};

  function adminProfileTags(value){
    const raw=Array.isArray(value)?value:String(value||'').split(/[,，、;；\n]+/);
    const out=[];
    raw.forEach(item=>{
      const tag=String(item||'').trim();
      if(tag&&!out.includes(tag)) out.push(tag);
    });
    return out.slice(0,12);
  }

  function adminUserRoleSummary(u){
    const primary=USER_ROLE_LABELS[u?.role]||String(u?.role||'—');
    const roles=Array.isArray(u?.roles)?u.roles:[];
    const extras=roles.filter(r=>r&&r!==u?.role).map(r=>USER_ROLE_LABELS[r]||r);
    return extras.length?`${primary}（另有：${extras.join('、')}）`:primary;
  }

  function ensureAdminUserEditor(){
    if(document.getElementById('admin-user-editor-modal')) return;
    const common=PROFILE_COMMON_TAGS.map(tag=>`<label class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700"><input type="checkbox" data-admin-profile-tag value="${escapeHtml(tag)}" onchange="adminSetProfileTag(this.value,this.checked)" class="rounded">${escapeHtml(tag)}</label>`).join('');
    document.body.insertAdjacentHTML('beforeend',`<div id="admin-user-editor-modal" class="hidden fixed inset-0 z-[120] bg-slate-950/50 p-4 overflow-y-auto" onclick="if(event.target===this)closeAdminUserEditor()"><div class="mx-auto mt-10 max-w-2xl rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden"><div class="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4"><div><h3 class="font-black text-slate-900">👤 編輯人員資料</h3><p class="mt-1 text-xs text-slate-500">職稱用於畫面顯示；PGY 學員為訓練內容分類。兩者都不會額外授予簽核或管理權限。</p></div><button type="button" onclick="closeAdminUserEditor()" class="text-slate-400 hover:text-slate-700 text-xl">×</button></div><div class="p-5 space-y-4"><input id="admin-user-editor-username" type="hidden"><div class="grid sm:grid-cols-2 gap-3"><div class="rounded-xl bg-slate-50 border border-slate-200 p-3"><div class="text-[11px] font-bold text-slate-500">帳號</div><div id="admin-user-editor-account" class="mt-1 font-mono text-sm font-bold text-slate-900"></div></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-3"><div class="text-[11px] font-bold text-slate-500">系統角色／權限</div><div id="admin-user-editor-role" class="mt-1 text-sm font-bold text-slate-900"></div></div></div><div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">🔒 系統角色與組別權限不在此區變更；職稱、職責標籤與 PGY 學員分類都不參與 RBAC 判斷。</div><div class="grid sm:grid-cols-2 gap-3"><label class="text-xs font-bold text-slate-600">姓名<input id="admin-user-editor-name" class="learning-input mt-1" maxlength="100"></label><label class="text-xs font-bold text-slate-600">工號<input id="admin-user-editor-empid" class="learning-input mt-1" maxlength="100"></label></div><div class="grid sm:grid-cols-2 gap-3"><div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><div class="text-[11px] font-bold text-slate-500">預設訓練區／組別</div><div id="admin-user-editor-scope" class="mt-1 text-sm font-bold text-slate-800"></div><div class="mt-1 text-[10px] text-slate-500">這是權限範圍資訊，本視窗只讀。</div></div><label class="text-xs font-bold text-slate-600">主要職稱<input id="admin-user-editor-professional-title" list="admin-professional-title-options" class="learning-input mt-1" maxlength="100" placeholder="例如：品管醫檢師"><datalist id="admin-professional-title-options"><option value="醫檢師"><option value="資深醫檢師"><option value="品管醫檢師"><option value="臨床教師"><option value="組長"></datalist><span class="block mt-1 text-[10px] font-normal text-slate-400">顯示於登入者姓名旁，可直接輸入自訂職稱。</span></label></div><label class="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-3"><input id="admin-user-editor-pgy-learner" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-indigo-300"><span><b class="block text-xs text-indigo-900">PGY 學員</b><span class="block mt-1 text-[10px] leading-4 text-indigo-700">勾選後，此帳號才會在 M1/M2/M3 額外看到 PGY 學員資料。此分類不會授予教師簽核、組長複核或管理權限。</span></span></label><div><label class="text-xs font-bold text-slate-600">額外職責</label><div class="mt-2 flex flex-wrap gap-2">${common}</div><input id="admin-user-editor-responsibility-tags" oninput="adminSyncProfileTagChecks()" class="learning-input mt-2" placeholder="可輸入其他職責，以逗號分隔"><p class="mt-1 text-[10px] text-slate-400">最多 12 個標籤；例如：品管、POCT、儀器管理、教學負責。</p></div><div id="admin-user-editor-status" class="text-xs text-slate-500"></div></div><div class="flex justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-4"><button type="button" onclick="closeAdminUserEditor()" class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-600">取消</button><button id="admin-user-editor-save" type="button" onclick="saveAdminUserEditor()" class="rounded-xl bg-teal-700 hover:bg-teal-600 px-4 py-2 text-sm font-bold text-white">💾 儲存人員資料</button></div></div></div>`);
  }

  function adminSyncProfileTagChecks(){
    const tags=adminProfileTags(document.getElementById('admin-user-editor-responsibility-tags')?.value||'');
    document.querySelectorAll('#admin-user-editor-modal [data-admin-profile-tag]').forEach(cb=>{ cb.checked=tags.includes(cb.value); });
  }

  function adminSetProfileTag(tag,checked){
    const input=document.getElementById('admin-user-editor-responsibility-tags');
    if(!input) return;
    const tags=adminProfileTags(input.value);
    const idx=tags.indexOf(tag);
    if(checked&&idx<0) tags.push(tag);
    if(!checked&&idx>=0) tags.splice(idx,1);
    input.value=tags.slice(0,12).join('、');
    adminSyncProfileTagChecks();
  }

  async function openAdminUserEditor(username){
    const u=adminUserAccountsCache.find(row=>String(row.username)===String(username));
    if(!u){ alert('找不到帳號資料，請重新整理人員清單。'); return; }
    ensureAdminUserEditor();
    document.getElementById('admin-user-editor-username').value=u.username||'';
    document.getElementById('admin-user-editor-account').textContent=`${u.username||''}｜${u.name||''}`;
    document.getElementById('admin-user-editor-role').textContent=adminUserRoleSummary(u);
    document.getElementById('admin-user-editor-name').value=u.name||'';
    document.getElementById('admin-user-editor-empid').value=u.empId||'';
    document.getElementById('admin-user-editor-scope').textContent=`${USER_AREA_LABELS[u.preferredArea]||u.preferredArea||'—'} · ${(GROUPS[u.preferredGroup]||GROUPS.grpBio).name}`;
    document.getElementById('admin-user-editor-professional-title').value=u.professionalTitle||'';
    document.getElementById('admin-user-editor-responsibility-tags').value=adminProfileTags(u.responsibilityTags).join('、');
    const pgy=document.getElementById('admin-user-editor-pgy-learner'); if(pgy){pgy.checked=false;pgy.disabled=true;}
    const status=document.getElementById('admin-user-editor-status'); if(status)status.textContent='讀取 PGY 學員分類中…';
    adminSyncProfileTagChecks();
    document.getElementById('admin-user-editor-modal').classList.remove('hidden');
    try{
      const r=await fetch(`/api/users/${encodeURIComponent(u.username)}/training-audience`,{credentials:'same-origin',cache:'no-store'});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'無法讀取 PGY 學員分類');
      if(pgy) pgy.checked=Boolean(d.pgyLearner);
      if(status) status.textContent='';
    }catch(e){ if(status)status.textContent=`⚠️ ${e.message}`; }
    finally{ if(pgy)pgy.disabled=false; }
    setTimeout(()=>document.getElementById('admin-user-editor-professional-title')?.focus(),0);
  }

  function closeAdminUserEditor(){
    document.getElementById('admin-user-editor-modal')?.classList.add('hidden');
  }

  async function saveAdminUserEditor(){
    const username=document.getElementById('admin-user-editor-username')?.value||'';
    const name=document.getElementById('admin-user-editor-name')?.value.trim()||'';
    const empId=document.getElementById('admin-user-editor-empid')?.value.trim()||'';
    const professionalTitle=document.getElementById('admin-user-editor-professional-title')?.value.trim()||'';
    const responsibilityTags=adminProfileTags(document.getElementById('admin-user-editor-responsibility-tags')?.value||'');
    const pgyLearner=Boolean(document.getElementById('admin-user-editor-pgy-learner')?.checked);
    const status=document.getElementById('admin-user-editor-status');
    const btn=document.getElementById('admin-user-editor-save');
    if(!username||!name||!empId){ if(status) status.textContent='❌ 姓名與工號不可空白。'; return; }
    const key=await getAdminKey();
    if(!key) return;
    const payload={name,empId,professionalTitle,responsibilityTags};
    try{
      if(btn) btn.disabled=true;
      if(status) status.textContent='⏳ 儲存人員資料中…';
      const r=await fetch(`/api/users/${encodeURIComponent(username)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'儲存失敗');
      const audienceResponse=await fetch(`/api/users/${encodeURIComponent(username)}/training-audience`,{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({pgyLearner})});
      const audienceData=await audienceResponse.json().catch(()=>({}));
      if(!audienceResponse.ok) throw new Error(audienceData.error||'PGY 學員分類儲存失敗');
      if(status) status.textContent='✅ 人員資料與訓練分類已儲存；系統角色與權限未變更。';
      await renderAdminUserAccounts();
      setTimeout(()=>closeAdminUserEditor(),450);
    }catch(e){
      if(status) status.textContent=`❌ ${e.message}`;
    }finally{
      if(btn) btn.disabled=false;
    }
  }

  window.adminProfileTags=adminProfileTags;
  window.adminUserRoleSummary=adminUserRoleSummary;
  window.ensureAdminUserEditor=ensureAdminUserEditor;
  window.adminSyncProfileTagChecks=adminSyncProfileTagChecks;
  window.adminSetProfileTag=adminSetProfileTag;
  window.openAdminUserEditor=openAdminUserEditor;
  window.closeAdminUserEditor=closeAdminUserEditor;
  window.saveAdminUserEditor=saveAdminUserEditor;
})();
