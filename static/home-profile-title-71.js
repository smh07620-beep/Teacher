/* Teacher 7.1 · presentation-only signed-in professional title badge. */
(function(){
  'use strict';
  const ROLE_LABELS={student:'學員',clinical_teacher:'臨床教師',group_leader:'組長',education_admin:'教學管理者',system_admin:'系統管理者',auditor:'稽核／唯讀'};

  async function init(){
    const nameEl=document.getElementById('v561-header-name');
    const metaEl=document.getElementById('v561-header-id');
    if(!nameEl||!metaEl) return;
    try{
      const response=await fetch('/api/training-command-center/profile',{credentials:'same-origin',cache:'no-store'});
      if(response.status===401) return;
      const profile=await response.json().catch(()=>({}));
      if(!response.ok) return;
      if(profile.name) nameEl.textContent=profile.name;
      const title=String(profile.professionalTitle||ROLE_LABELS[profile.role]||'醫檢師').trim();
      const emp=String(profile.empId||'').trim();
      metaEl.textContent=[title,emp?`工號 ${emp}`:''].filter(Boolean).join(' · ');
    }catch(_){ /* presentation enhancement must never block the home page */ }
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
