/* P2 · 我的學員
 * Read-only trainee projection inside the existing assessment workspace.
 * Server-side assignment/group/organization scope remains authoritative.
 */
(async function(){
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const has = permission => Boolean(R?.hasPermission?.(permission));
  if (!['student.view_assigned','student.view_group','student.view_all'].some(has)) return;

  const ID='teacher-learners-p2';
  const RESUME_KEY='teacher:p2:clinical-assessment-learner';
  let latest={learners:[],summary:{},scope:{}};
  let loadedAt=0;
  const TTL=30000;
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  function host(){return document.getElementById('admin-section-quiz');}

  function ensureSection(){
    const panel=host();if(!panel)return null;
    let section=document.getElementById(ID);
    if(!section){
      section=document.createElement('section');
      section.id=ID;
      section.dataset.productSection='current-work';
      section.className='rounded-2xl border border-indigo-100 bg-white p-4 shadow-sm';
      section.innerHTML='<div class="text-sm text-slate-500">讀取負責學員中…</div>';
    }
    const queue=document.getElementById('teacher-action-queue-1024');
    if(queue?.parentElement===panel){
      if(queue.nextElementSibling!==section)queue.after(section);
    }else if(section.parentElement!==panel){
      panel.insertBefore(section,panel.firstChild);
    }
    return section;
  }

  function scopeLabel(scope){
    if(scope?.kind==='organization')return'跨組教學協調';
    if(scope?.kind==='group')return `本組 · ${scope.group||'目前組別'}`;
    return'我的指派學員';
  }

  function learnerRow(item,index){
    const reviewButton=has('evaluation.review')
      ? `<button type="button" data-p2-results="${index}" class="rounded-lg border border-indigo-200 bg-white px-2.5 py-1.5 text-[11px] font-bold text-indigo-700">查看考核紀錄</button>`
      : '';
    const flags=[
      Number(item.awaitingTeacher||0)>0?`待教師 ${Number(item.awaitingTeacher)}`:'',
      Number(item.awaitingLeader||0)>0?`待複核 ${Number(item.awaitingLeader)}`:'',
      Number(item.awaitingFinalize||0)>0?`待確認 ${Number(item.awaitingFinalize)}`:'',
      Number(item.overdueAssignments||0)>0?`逾期 ${Number(item.overdueAssignments)}`:'',
    ].filter(Boolean);
    return `<article class="rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <b class="text-sm text-slate-900">${escapeHtml(item.name||item.username)}</b>
            ${item.empId?`<span class="text-[10px] text-slate-500">${escapeHtml(item.empId)}</span>`:''}
            <span class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700">${escapeHtml(item.group||'')}</span>
            ${item.active===false?'<span class="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600">停用帳號</span>':''}
          </div>
          <p class="mt-1 text-[11px] text-slate-500">PGY 指派 ${Number(item.assignmentCount||0)} · 已完成 ${Number(item.completedAssignments||0)} · 最新狀態 ${escapeHtml(item.latestStatusLabel||'—')}</p>
          ${flags.length?`<div class="mt-2 flex flex-wrap gap-1.5">${flags.map(flag=>`<span class="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">${escapeHtml(flag)}</span>`).join('')}</div>`:''}
        </div>
        <div class="flex flex-wrap gap-2 shrink-0">
          ${reviewButton}
          ${has('evaluation.sign')
            ? `<button type="button" data-p2-clinical="${index}" class="rounded-lg bg-indigo-700 px-2.5 py-1.5 text-[11px] font-bold text-white">開始臨床技能評核</button>`
            : `<button type="button" data-p2-pgy="${index}" class="rounded-lg bg-indigo-700 px-2.5 py-1.5 text-[11px] font-bold text-white">進入 PGY 工作流程</button>`}
        </div>
      </div>
    </article>`;
  }

  function render(section,data){
    latest=data||{learners:[],summary:{},scope:{}};
    const rows=Array.isArray(latest.learners)?latest.learners:[];
    const summary=latest.summary||{};
    section.innerHTML=`
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <h4 class="text-base font-black text-slate-950">👥 我的學員</h4>
            <span class="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-bold text-indigo-700">${escapeHtml(scopeLabel(latest.scope))}</span>
          </div>
          <p class="mt-1 text-xs text-slate-500">只顯示伺服器判定你可查看的學員；這裡不新增臨床簽核權限。</p>
        </div>
        <button id="teacher-learners-refresh-p2" type="button" class="text-[11px] font-bold text-indigo-700">↻ 更新</button>
      </div>
      <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div class="rounded-xl bg-slate-50 p-2"><b class="block text-lg text-slate-950">${Number(summary.learners||0)}</b><span class="text-[10px] text-slate-500">學員</span></div>
        <div class="rounded-xl bg-indigo-50 p-2"><b class="block text-lg text-indigo-900">${Number(summary.awaitingTeacher||0)}</b><span class="text-[10px] text-indigo-600">待教師</span></div>
        <div class="rounded-xl bg-amber-50 p-2"><b class="block text-lg text-amber-900">${Number(summary.awaitingLeader||0)}</b><span class="text-[10px] text-amber-700">待複核</span></div>
        <div class="rounded-xl bg-rose-50 p-2"><b class="block text-lg text-rose-900">${Number(summary.overdueAssignments||0)}</b><span class="text-[10px] text-rose-700">逾期</span></div>
      </div>
      <div class="mt-3 space-y-2">${rows.length?rows.map(learnerRow).join(''):'<div class="rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">目前沒有伺服器指派給你的學員。</div>'}</div>`;
    section.querySelector('#teacher-learners-refresh-p2')?.addEventListener('click',()=>load(true));
    section.querySelectorAll('[data-p2-results]').forEach(button=>button.addEventListener('click',openResults));
    section.querySelectorAll('[data-p2-clinical]').forEach(button=>button.addEventListener('click',openClinicalAssessment));
    section.querySelectorAll('[data-p2-pgy]').forEach(button=>button.addEventListener('click',openPgy));
  }

  async function getJSON(url){
    const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
    const data=await response.json().catch(()=>null);
    if(!response.ok){const error=new Error(data?.error||`讀取失敗（${response.status}）`);error.status=response.status;throw error;}
    return data||{};
  }

  async function load(force=false){
    const section=ensureSection();if(!section)return;
    if(!force&&loadedAt&&Date.now()-loadedAt<TTL)return;
    try{
      const data=await getJSON('/api/training-command-center/teacher-learners');
      loadedAt=Date.now();
      render(section,data);
    }catch(error){
      if(error?.status===401||error?.status===403){section.classList.add('hidden');return;}
      section.classList.remove('hidden');
      section.innerHTML=`<div class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">❌ ${escapeHtml(error.message||'目前無法讀取負責學員')}</div>`;
    }
  }

  async function openResults(event){
    const item=latest.learners?.[Number(event.currentTarget?.dataset?.p2Results)];
    if(!item)return;
    await window.switchAdminWorkspace?.('results',true);
    const search=document.getElementById('admin-results-search');
    if(search)search.value=item.empId||item.name||item.username||'';
    if(typeof window.renderAdminTable==='function')await window.renderAdminTable();
  }

  async function enterClinicalAssessment(item){
    if(!item)return;
    if(typeof currentTrainingArea!=='undefined'&&currentTrainingArea!=='pgy'){
      try{sessionStorage.setItem(RESUME_KEY,String(item.username||''));}catch(_){}
      const url=new URL(window.location.href);
      url.searchParams.set('area','pgy');
      url.searchParams.set('group',item.group||'grpBio');
      url.searchParams.set('admin','1');
      url.searchParams.set('workspace','assessment');
      url.searchParams.set('persona','teacher');
      url.searchParams.set('from','teacher-learners');
      window.location.assign(`${url.pathname}${url.search}${url.hash}`);
      return;
    }
    if(typeof switchGroup==='function'&&item.group) switchGroup(item.group);
    await window.switchAdminWorkspace?.('teacher',true);
    await window.switchTeacherMode?.('pgy');
    if(typeof initPgyAssessmentCenter==='function') await initPgyAssessmentCenter();
    const name=document.getElementById('pgy-assess-name');
    const empId=document.getElementById('pgy-assess-empid');
    if(name)name.value=item.name||'';
    if(empId)empId.value=item.empId||'';
    if(typeof selectPgyAssessmentType==='function')selectPgyAssessmentType('dops');
    const status=document.getElementById('pgy-assess-status');
    if(status)status.textContent=`已選擇 ${item.name||item.username}；請選擇評量類型並完成各項評分。`;
    document.getElementById('panel-assessment')?.scrollIntoView({behavior:'smooth',block:'start'});
  }

  async function openClinicalAssessment(event){
    const item=latest.learners?.[Number(event.currentTarget?.dataset?.p2Clinical)];
    await enterClinicalAssessment(item);
  }

  async function openPgy(){
    await window.switchAdminWorkspace?.('teacher',true);
    await window.switchTeacherMode?.('pgy');
  }

  async function resumeClinicalAssessment(){
    const params=new URLSearchParams(window.location.search);
    if(params.get('from')!=='teacher-learners')return;
    let username='';
    try{username=String(sessionStorage.getItem(RESUME_KEY)||'');sessionStorage.removeItem(RESUME_KEY);}catch(_){}
    if(!username)return;
    try{
      const data=await getJSON('/api/training-command-center/teacher-learners');
      const item=(Array.isArray(data?.learners)?data.learners:[]).find(row=>String(row?.username||'')===username);
      if(item)await enterClinicalAssessment(item);
    }catch(_){}
  }

  function refreshPlacement(){
    const section=document.getElementById(ID);
    if(section)ensureSection();
    const params=new URLSearchParams(window.location.search);
    if(params.get('workspace')==='assessment')load(false);
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',()=>{ensureSection();load(false);resumeClinicalAssessment();},{once:true});
  }else{
    ensureSection();load(false);resumeClinicalAssessment();
  }
  window.AdminWorkspaceShell?.addAfterWorkspace?.(()=>refreshPlacement());
  window.TeacherLearnersP2=Object.freeze({load});
})();
