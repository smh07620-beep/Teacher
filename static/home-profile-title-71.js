/* Teacher 7.2 · presentation-only signed-in identity renderer.
 * One profile source owns both the home and /system header presentation so
 * legacy scripts cannot leave users with different title / employee-id views.
 * This file never grants permissions and never writes role state.
 */
(function(){
  'use strict';

  const ROLE_LABELS={
    student:'學員',
    clinical_teacher:'醫檢師',
    group_leader:'組長',
    education_admin:'教學管理者',
    system_admin:'系統管理者',
    auditor:'稽核／唯讀'
  };
  const TARGETS=[
    ['v561-header-name','v561-header-id'],
    ['v573-system-user-name','v573-system-user-id']
  ];
  let cachedProfile=null;
  let scheduled=false;

  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  function displayTitle(profile){
    const explicit=String(profile?.professionalTitle||'').trim();
    if(explicit) return explicit;
    const primary=String(profile?.role||'').trim();
    if(ROLE_LABELS[primary]) return ROLE_LABELS[primary];
    const roles=Array.isArray(profile?.roles)?profile.roles:[];
    const priority=['system_admin','education_admin','group_leader','clinical_teacher','auditor','student'];
    const fallback=priority.find(role=>roles.includes(role));
    return ROLE_LABELS[fallback]||'醫檢師';
  }

  function renderTarget(nameEl,metaEl,profile){
    if(!nameEl||!metaEl||!profile) return;
    const name=String(profile.name||profile.username||'使用者').trim()||'使用者';
    const title=displayTitle(profile);
    const emp=String(profile.empId||profile.username||'').trim();
    const signature=`${name}|${title}|${emp}`;
    const expectedMeta=emp?`工號 ${emp}`:'工號未設定';
    const currentSignature=nameEl.dataset.teacherIdentitySignature||'';
    const currentTitle=nameEl.querySelector('[data-teacher-title-badge]')?.textContent?.trim()||'';
    const currentName=nameEl.querySelector('[data-teacher-display-name]')?.textContent?.trim()||nameEl.textContent.trim();
    if(currentSignature===signature&&currentName===name&&currentTitle===title&&metaEl.textContent.trim()===expectedMeta) return;

    nameEl.dataset.teacherIdentitySignature=signature;
    nameEl.style.display='flex';
    nameEl.style.alignItems='center';
    nameEl.style.gap='0.35rem';
    nameEl.style.minWidth='0';
    nameEl.innerHTML=`<span data-teacher-display-name style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(name)}</span><span data-teacher-title-badge style="flex:none;border:1px solid #bae6fd;background:#f0f9ff;color:#075985;border-radius:999px;padding:1px 6px;font-size:10px;font-weight:800;line-height:1.45">${esc(title)}</span>`;
    metaEl.textContent=expectedMeta;
    metaEl.style.display='block';
    metaEl.style.marginTop='2px';
    metaEl.style.whiteSpace='nowrap';
  }

  function apply(){
    scheduled=false;
    if(!cachedProfile) return;
    TARGETS.forEach(([nameId,metaId])=>renderTarget(
      document.getElementById(nameId),
      document.getElementById(metaId),
      cachedProfile
    ));
  }

  function scheduleApply(){
    if(scheduled) return;
    scheduled=true;
    requestAnimationFrame(apply);
  }

  async function load(){
    try{
      const response=await fetch('/api/training-command-center/profile',{credentials:'same-origin',cache:'no-store'});
      if(response.status===401) return;
      const profile=await response.json().catch(()=>({}));
      if(!response.ok) return;
      cachedProfile=profile;
      apply();
      // Compatibility scripts may paint the legacy name/id after this asset.
      // Re-apply only when observed text actually diverges from this profile.
      setTimeout(apply,350);
      setTimeout(apply,1200);
    }catch(_){ /* presentation enhancement must never block the page */ }
  }

  function installObserver(){
    if(!document.body||document.body.dataset.teacherIdentityObserved==='1') return;
    document.body.dataset.teacherIdentityObserved='1';
    new MutationObserver(()=>{ if(cachedProfile) scheduleApply(); }).observe(document.body,{
      childList:true,subtree:true,characterData:true
    });
  }

  function init(){installObserver();load();}
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();

  window.TeacherIdentity72=Object.freeze({refresh:load,apply});
})();
