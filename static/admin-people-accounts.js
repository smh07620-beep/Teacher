/* Teacher 7.4 · Account list and people summary runtime.
 * Canonical profile editor remains admin-people.js; multi-role creation remains
 * roles-signing-66.js. This module owns the account list plus people summary
 * that previously lived in system-admin.js.
 */
(function(){
  'use strict';

  const AREA_LABELS={internal:'院內',pgy:'PGY'};

  async function renderAdminUserAccounts(){
    const body=document.getElementById('admin-user-accounts-body');
    const status=document.getElementById('admin-user-status');
    if(!body)return;
    body.innerHTML='<tr><td colspan="6" class="p-5 text-center text-slate-400">讀取帳號中…</td></tr>';
    const key=await getAdminKey();
    if(!key)return;
    try{
      const response=await fetch('/api/users',{headers:{'X-Admin-Key':key},cache:'no-store'});
      const rows=await response.json().catch(()=>[]);
      if(!response.ok)throw new Error(rows.error||'帳號讀取失敗');
      adminUserAccountsCache=Array.isArray(rows)?rows:[];
      body.innerHTML=adminUserAccountsCache.length?adminUserAccountsCache.map(user=>{
        const tags=adminProfileTags(user.responsibilityTags);
        const profile=`<div class="mt-1 text-[11px] text-slate-500">${user.professionalTitle?`職稱：${escapeHtml(user.professionalTitle)}`:'職稱：未設定'}</div>${tags.length?`<div class="mt-1 flex flex-wrap gap-1">${tags.map(tag=>`<span class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">${escapeHtml(tag)}</span>`).join('')}</div>`:''}`;
        return `<tr class="${user.active?'':'opacity-55'}"><td class="p-3"><b>${escapeHtml(user.username)}</b><div class="text-slate-500 mt-1">${escapeHtml(user.name)}</div></td><td class="p-3 font-mono">${escapeHtml(user.empId)}</td><td class="p-3"><div>${escapeHtml(adminUserRoleSummary(user))}</div>${profile}</td><td class="p-3">${AREA_LABELS[user.preferredArea]||''} · ${escapeHtml((GROUPS[user.preferredGroup]||GROUPS.grpBio).name)}</td><td class="p-3 text-slate-500">${escapeHtml((user.lastLoginAt||'尚未登入').slice(0,16).replace('T',' '))}</td><td class="p-3"><div class="flex flex-wrap gap-1.5"><button data-username="${escapeHtml(user.username)}" onclick="openAdminUserEditor(this.dataset.username)" class="text-[11px] border border-teal-200 bg-teal-50 text-teal-800 px-2.5 py-1.5 rounded-lg font-bold">編輯人員資料</button></div></td></tr>`;
      }).join(''):'<tr><td colspan="6" class="p-5 text-center text-slate-400">尚未建立登入帳號。請使用上方表單建立第一個帳號。</td></tr>';
      if(status)status.textContent=`共 ${adminUserAccountsCache.length} 個帳號；「主要職稱／額外職責」與系統角色權限分開管理。`;
    }catch(error){
      adminUserAccountsCache=[];
      body.innerHTML=`<tr><td colspan="6" class="p-5 text-center text-rose-600">❌ ${escapeHtml(error.message)}</td></tr>`;
    }
  }

  async function createAdminUserAccount(){
    const status=document.getElementById('admin-user-status');
    const key=await getAdminKey();
    if(!key)return;
    const payload={
      username:document.getElementById('admin-user-username')?.value||'',
      password:document.getElementById('admin-user-password')?.value||'',
      name:document.getElementById('admin-user-name')?.value||'',
      empId:document.getElementById('admin-user-empid')?.value||'',
      role:document.getElementById('admin-user-role')?.value||'student',
      preferredArea:document.getElementById('admin-user-area')?.value||'internal',
      preferredGroup:document.getElementById('admin-user-group')?.value||'grpBio',
      professionalTitle:document.getElementById('admin-user-professional-title')?.value||'',
      responsibilityTags:adminProfileTags(document.getElementById('admin-user-responsibility-tags')?.value||'')
    };
    if(status)status.textContent='⏳ 建立帳號中…';
    const response=await fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok){if(status)status.textContent='❌ '+(data.error||'建立失敗');return;}
    ['admin-user-username','admin-user-password','admin-user-name','admin-user-empid','admin-user-professional-title','admin-user-responsibility-tags'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    if(status)status.textContent=`✅ 已建立 ${data.user.name}（${data.user.username}）`;
    await renderAdminUserAccounts();
  }

  async function renderAdminPeople(){
    await renderAdminUserAccounts();
    const body=document.getElementById('admin-people-body');
    const summary=document.getElementById('admin-people-summary');
    if(!body||!summary)return;
    body.innerHTML='<tr><td colspan="5" class="p-5 text-center text-slate-400">讀取中…</td></tr>';
    try{
      const records=await fetchAdminRecords();
      if(!records)return;
      const map=new Map();
      for(const record of records){
        const key=(record.empId||'')+'|'+(record.name||'');
        if(!key.replace('|',''))continue;
        const old=map.get(key)||{name:record.name||'',empId:record.empId||'',role:record.role||'',count:0,last:record.timestamp||''};
        old.count++;
        if((record.timestamp||'')>=(old.last||'')){old.last=record.timestamp||'';old.role=record.role||old.role;}
        map.set(key,old);
      }
      const list=[...map.values()].sort((a,b)=>(b.last||'').localeCompare(a.last||''));
      const roles=new Set(list.map(item=>item.role).filter(Boolean));
      summary.innerHTML=`<div class="rounded-xl bg-sky-50 border border-sky-100 p-4"><span class="text-xs text-sky-700">近期人員</span><b class="block text-2xl text-sky-950 mt-1">${list.length}</b></div><div class="rounded-xl bg-slate-50 border border-slate-200 p-4"><span class="text-xs text-slate-500">身份類型</span><b class="block text-2xl text-slate-900 mt-1">${roles.size}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">考核紀錄</span><b class="block text-2xl text-emerald-950 mt-1">${records.length}</b></div>`;
      body.innerHTML=list.length?list.map(item=>`<tr><td class="p-3 font-bold">${escapeHtml(item.name)}</td><td class="p-3 font-mono">${escapeHtml(item.empId)}</td><td class="p-3">${escapeHtml(item.role||'—')}</td><td class="p-3">${item.count}</td><td class="p-3 text-slate-500">${escapeHtml(item.last||'')}</td></tr>`).join(''):'<tr><td colspan="5" class="p-5 text-center text-slate-400">尚無考核人員資料</td></tr>';
    }catch(error){
      body.innerHTML=`<tr><td colspan="5" class="p-5 text-center text-rose-500">❌ ${escapeHtml(error.message)}</td></tr>`;
    }
  }

  window.renderAdminUserAccounts=renderAdminUserAccounts;
  window.createAdminUserAccount=createAdminUserAccount;
  window.renderAdminPeople=renderAdminPeople;
})();
