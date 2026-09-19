/* Phase 3C · Admin people/profile module.
 * Profile metadata is deliberately separated from canonical RBAC roles.
 * Teacher 7.1 adds an explicit PGY learner training-audience flag; it never
 * grants signing or management permissions.
 */
(function(){
  'use strict';

  let adminUserAccountsCache=[];
  const ADMIN_USER_AREA_LABELS={internal:'院內',pgy:'PGY'};

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
    const common=PROFILE_COMMON_TAGS.map(tag=>`<label class="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700"><input type="checkbox" data-admin-profile-tag value="${escapeHtml(tag)}" data-csp-change="adminSetProfileTag(this.value,this.checked)" class="rounded">${escapeHtml(tag)}</label>`).join('');
    document.body.insertAdjacentHTML('beforeend',`<div id="admin-user-editor-modal" class="hidden fixed inset-0 z-[120] bg-slate-950/50 p-4 overflow-y-auto" data-csp-click="if(event.target===this)closeAdminUserEditor()"><div class="mx-auto mt-10 max-w-2xl rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden"><div class="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4"><div><h3 class="font-black text-slate-900">👤 編輯人員資料</h3><p class="mt-1 text-xs text-slate-500">職稱用於畫面顯示；PGY 學員為訓練內容分類。兩者都不會額外授予簽核或管理權限。</p></div><button type="button" data-csp-click="closeAdminUserEditor()" class="text-slate-400 hover:text-slate-700 text-xl">×</button></div><div class="p-5 space-y-4"><input id="admin-user-editor-username" type="hidden"><div class="grid sm:grid-cols-2 gap-3"><div class="rounded-xl bg-slate-50 border border-slate-200 p-3"><div class="text-[11px] font-bold text-slate-500">帳號</div><div id="admin-user-editor-account" class="mt-1 font-mono text-sm font-bold text-slate-900"></div></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-3"><div class="text-[11px] font-bold text-slate-500">系統角色／權限</div><div id="admin-user-editor-role" class="mt-1 text-sm font-bold text-slate-900"></div></div></div><div class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">🔒 系統角色與組別權限不在此區變更；職稱、職責標籤與 PGY 學員分類都不參與 RBAC 判斷。</div><div class="grid sm:grid-cols-2 gap-3"><label class="text-xs font-bold text-slate-600">姓名<input id="admin-user-editor-name" class="learning-input mt-1" maxlength="100"></label><label class="text-xs font-bold text-slate-600">工號<input id="admin-user-editor-empid" class="learning-input mt-1" maxlength="100"></label></div><div class="grid sm:grid-cols-2 gap-3"><div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><div class="text-[11px] font-bold text-slate-500">預設訓練區／組別</div><div id="admin-user-editor-scope" class="mt-1 text-sm font-bold text-slate-800"></div><div class="mt-1 text-[10px] text-slate-500">這是權限範圍資訊，本視窗只讀。</div></div><label class="text-xs font-bold text-slate-600">主要職稱<input id="admin-user-editor-professional-title" list="admin-professional-title-options" class="learning-input mt-1" maxlength="100" placeholder="例如：品管醫檢師"><datalist id="admin-professional-title-options"><option value="醫檢師"><option value="資深醫檢師"><option value="品管醫檢師"><option value="臨床教師"><option value="組長"></datalist><span class="block mt-1 text-[10px] font-normal text-slate-400">顯示於登入者姓名旁，可直接輸入自訂職稱。</span></label></div><label class="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-3"><input id="admin-user-editor-pgy-learner" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-indigo-300"><span><b class="block text-xs text-indigo-900">PGY 學員</b><span class="block mt-1 text-[10px] leading-4 text-indigo-700">勾選後，此帳號才會在 M1/M2/M3 額外看到 PGY 學員資料。此分類不會授予教師簽核、組長複核或管理權限。</span></span></label><div><label class="text-xs font-bold text-slate-600">額外職責</label><div class="mt-2 flex flex-wrap gap-2">${common}</div><input id="admin-user-editor-responsibility-tags" data-csp-input="adminSyncProfileTagChecks()" class="learning-input mt-2" placeholder="可輸入其他職責，以逗號分隔"><p class="mt-1 text-[10px] text-slate-400">最多 12 個標籤；例如：品管、POCT、儀器管理、教學負責。</p></div><div id="admin-user-editor-status" class="text-xs text-slate-500"></div></div><div class="flex justify-end gap-2 border-t border-slate-100 bg-slate-50 px-5 py-4"><button type="button" data-csp-click="closeAdminUserEditor()" class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-600">取消</button><button id="admin-user-editor-save" type="button" data-csp-click="saveAdminUserEditor()" class="rounded-xl bg-teal-700 hover:bg-teal-600 px-4 py-2 text-sm font-bold text-white">💾 儲存人員資料</button></div></div></div>`);
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
    const payload={name,empId,professionalTitle,responsibilityTags};
    try{
      if(btn) btn.disabled=true;
      if(status) status.textContent='⏳ 儲存人員資料中…';
      const r=await fetch(`/api/users/${encodeURIComponent(username)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
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

  // Final convergence: canonical owner migrated from system-admin.js.
  async function renderAdminUserAccounts(){
      const body=document.getElementById('admin-user-accounts-body'),status=document.getElementById('admin-user-status');if(!body)return;body.innerHTML='<tr><td colspan="6" class="p-5 text-center text-slate-400">讀取帳號中…</td></tr>';
      try{const r=await fetch('/api/users',{cache:'no-store'}),rows=await r.json().catch(()=>[]);if(!r.ok)throw new Error(rows.error||'帳號讀取失敗');adminUserAccountsCache=Array.isArray(rows)?rows:[];
          body.innerHTML=adminUserAccountsCache.length?adminUserAccountsCache.map(u=>{const tags=adminProfileTags(u.responsibilityTags),profile=`<div class="mt-1 text-[11px] text-slate-500">${u.professionalTitle?`職稱：${escapeHtml(u.professionalTitle)}`:'職稱：未設定'}</div>${tags.length?`<div class="mt-1 flex flex-wrap gap-1">${tags.map(tag=>`<span class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">${escapeHtml(tag)}</span>`).join('')}</div>`:''}`;return `<tr class="${u.active?'':'opacity-55'}"><td class="p-3"><b>${escapeHtml(u.username)}</b><div class="text-slate-500 mt-1">${escapeHtml(u.name)}</div></td><td class="p-3 font-mono">${escapeHtml(u.empId)}</td><td class="p-3"><div>${escapeHtml(adminUserRoleSummary(u))}</div>${profile}</td><td class="p-3">${ADMIN_USER_AREA_LABELS[u.preferredArea]||''} · ${escapeHtml((GROUPS[u.preferredGroup]||GROUPS.grpBio).name)}</td><td class="p-3 text-slate-500">${escapeHtml((u.lastLoginAt||'尚未登入').slice(0,16).replace('T',' '))}</td><td class="p-3"><div class="flex flex-wrap gap-1.5"><button data-username="${escapeHtml(u.username)}" data-csp-click="openAdminUserEditor(this.dataset.username)" class="text-[11px] border border-teal-200 bg-teal-50 text-teal-800 px-2.5 py-1.5 rounded-lg font-bold">編輯人員資料</button><button data-username="${escapeHtml(u.username)}" data-csp-click="resetAdminUserPassword(this.dataset.username)" class="text-[11px] border border-slate-300 bg-white px-2.5 py-1.5 rounded-lg">重設密碼</button><button data-username="${escapeHtml(u.username)}" data-csp-click="toggleAdminUserAccount(this.dataset.username,${u.active?'false':'true'})" class="text-[11px] ${u.active?'text-rose-600 border-rose-200':'text-emerald-700 border-emerald-200'} border bg-white px-2.5 py-1.5 rounded-lg">${u.active?'停用':'啟用'}</button></div></td></tr>`;}).join(''):'<tr><td colspan="6" class="p-5 text-center text-slate-400">尚未建立登入帳號。請使用上方表單建立第一個帳號。</td></tr>';if(status)status.textContent=`共 ${adminUserAccountsCache.length} 個帳號；「主要職稱／額外職責」與系統角色權限分開管理。`;
      }catch(e){adminUserAccountsCache=[];body.innerHTML=`<tr><td colspan="6" class="p-5 text-center text-rose-600">❌ ${escapeHtml(e.message)}</td></tr>`;}
  }

  async function createAdminUserAccount(){
      const status=document.getElementById('admin-user-status');const payload={username:document.getElementById('admin-user-username')?.value||'',password:document.getElementById('admin-user-password')?.value||'',name:document.getElementById('admin-user-name')?.value||'',empId:document.getElementById('admin-user-empid')?.value||'',role:document.getElementById('admin-user-role')?.value||'student',preferredArea:document.getElementById('admin-user-area')?.value||'internal',preferredGroup:document.getElementById('admin-user-group')?.value||'grpBio',professionalTitle:document.getElementById('admin-user-professional-title')?.value||'',responsibilityTags:adminProfileTags(document.getElementById('admin-user-responsibility-tags')?.value||'')};status.textContent='⏳ 建立帳號中…';
      const r=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),d=await r.json().catch(()=>({}));if(!r.ok){status.textContent='❌ '+(d.error||'建立失敗');return;}['admin-user-username','admin-user-password','admin-user-name','admin-user-empid','admin-user-professional-title','admin-user-responsibility-tags'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});status.textContent=`✅ 已建立 ${d.user.name}（${d.user.username}）`;await renderAdminUserAccounts();
  }

  async function renderAdminPeople(force=false){
      await renderAdminUserAccounts();
      const body=document.getElementById('admin-people-body'),sum=document.getElementById('admin-people-summary');if(!body||!sum)return;body.innerHTML='<tr><td colspan="5" class="p-5 text-center text-slate-400">讀取中…</td></tr>';
      try{const records=await fetchAdminRecords();if(!records)return;const map=new Map();for(const r of records){const k=(r.empId||'')+'|'+(r.name||'');if(!k.replace('|',''))continue;const old=map.get(k)||{name:r.name||'',empId:r.empId||'',role:r.role||'',count:0,last:r.timestamp||''};old.count++;if((r.timestamp||'')>=(old.last||'')){old.last=r.timestamp||'';old.role=r.role||old.role;}map.set(k,old);}const list=[...map.values()].sort((a,b)=>(b.last||'').localeCompare(a.last||''));const roles=new Set(list.map(x=>x.role).filter(Boolean));sum.innerHTML=`<div class="rounded-xl bg-sky-50 border border-sky-100 p-4"><span class="text-xs text-sky-700">近期人員</span><b class="block text-2xl text-sky-950 mt-1">${list.length}</b></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-4"><span class="text-xs text-slate-500">身份類型</span><b class="block text-2xl text-slate-900 mt-1">${roles.size}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">考核紀錄</span><b class="block text-2xl text-emerald-950 mt-1">${records.length}</b></div>`;body.innerHTML=list.length?list.map(x=>`<tr><td class="p-3 font-bold">${escapeHtml(x.name)}</td><td class="p-3 font-mono">${escapeHtml(x.empId)}</td><td class="p-3">${escapeHtml(x.role||'—')}</td><td class="p-3">${x.count}</td><td class="p-3 text-slate-500">${escapeHtml(x.last||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="p-5 text-center text-slate-400">尚無考核人員資料</td></tr>';}
      catch(e){body.innerHTML=`<tr><td colspan="5" class="p-5 text-center text-rose-500">❌ ${escapeHtml(e.message)}</td></tr>`;}
  }

  window.renderAdminUserAccounts=renderAdminUserAccounts;
  window.createAdminUserAccount=createAdminUserAccount;
  window.renderAdminPeople=renderAdminPeople;
})();
