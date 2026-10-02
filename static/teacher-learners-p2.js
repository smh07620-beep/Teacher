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
  const CONTEXT_KEY='teacher:p2:clinical-assessment-context';
  let latest={learners:[],summary:{},scope:{}};
  let competencyCache=null;
  let competencyLoadedAt=0;
  let analyticsCache=null;
  let analyticsLoadedAt=0;
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
          <button type="button" data-p2-competency="${index}" class="rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 text-[11px] font-bold text-teal-700">能力追蹤</button>
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
        <div class="flex items-center gap-3"><button id="teacher-analytics-open-p2" type="button" class="text-[11px] font-bold text-teal-700">📊 教學分析</button><button id="teacher-learners-refresh-p2" type="button" class="text-[11px] font-bold text-indigo-700">↻ 更新</button></div>
      </div>
      <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div class="rounded-xl bg-slate-50 p-2"><b class="block text-lg text-slate-950">${Number(summary.learners||0)}</b><span class="text-[10px] text-slate-500">學員</span></div>
        <div class="rounded-xl bg-indigo-50 p-2"><b class="block text-lg text-indigo-900">${Number(summary.awaitingTeacher||0)}</b><span class="text-[10px] text-indigo-600">待教師</span></div>
        <div class="rounded-xl bg-amber-50 p-2"><b class="block text-lg text-amber-900">${Number(summary.awaitingLeader||0)}</b><span class="text-[10px] text-amber-700">待複核</span></div>
        <div class="rounded-xl bg-rose-50 p-2"><b class="block text-lg text-rose-900">${Number(summary.overdueAssignments||0)}</b><span class="text-[10px] text-rose-700">逾期</span></div>
      </div>
      <div class="mt-3 space-y-2">${rows.length?rows.map(learnerRow).join(''):'<div class="rounded-xl border border-dashed border-slate-200 p-4 text-xs text-slate-500">目前沒有伺服器指派給你的學員。</div>'}</div>
      <section id="teacher-competency-detail-p2" class="hidden mt-4 rounded-xl border border-teal-100 bg-teal-50/30 p-4"></section>
      <section id="teacher-teaching-analytics-p2" class="hidden mt-4 rounded-xl border border-sky-100 bg-sky-50/30 p-4"></section>`;
    section.querySelector('#teacher-learners-refresh-p2')?.addEventListener('click',()=>load(true));
    section.querySelector('#teacher-analytics-open-p2')?.addEventListener('click',openTeachingAnalytics);
    section.querySelectorAll('[data-p2-results]').forEach(button=>button.addEventListener('click',openResults));
    section.querySelectorAll('[data-p2-competency]').forEach(button=>button.addEventListener('click',openCompetency));
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

  async function loadCompetency(force=false){
    if(!force&&competencyCache&&competencyLoadedAt&&Date.now()-competencyLoadedAt<TTL)return competencyCache;
    competencyCache=await getJSON('/api/training-command-center/teacher-competency');
    competencyLoadedAt=Date.now();
    return competencyCache;
  }

  async function loadAnalytics(force=false){
    if(!force&&analyticsCache&&analyticsLoadedAt&&Date.now()-analyticsLoadedAt<TTL)return analyticsCache;
    analyticsCache=await getJSON('/api/training-command-center/teacher-analytics');
    analyticsLoadedAt=Date.now();
    return analyticsCache;
  }

  function competencyScore(value){
    const number=Number(value);
    return value===null||value===undefined||value===''||!Number.isFinite(number)?'—':number.toFixed(1);
  }

  async function openCompetency(event){
    const learner=latest.learners?.[Number(event.currentTarget?.dataset?.p2Competency)];
    const panel=document.getElementById('teacher-competency-detail-p2');
    if(!learner||!panel)return;
    panel.classList.remove('hidden');
    panel.innerHTML='<div class="text-xs text-slate-500">讀取正式能力評量紀錄中…</div>';
    try{
      const matrix=await loadCompetency(false);
      const row=(Array.isArray(matrix?.learners)?matrix.learners:[]).find(item=>String(item?.username||'')===String(learner.username||''));
      if(!row){
        panel.innerHTML='<div class="text-xs text-slate-500">目前沒有這位學員的正式能力評量紀錄。</div>';
        return;
      }
      const typeLabels=new Map((matrix.assessmentTypes||[]).map(item=>[item.key,item.label]));
      const cells=Object.entries(row.competencies||{}).map(([key,cell])=>{
        const count=Number(cell?.count||0);
        const latest=competencyScore(cell?.latestScore);
        return `<div class="rounded-xl border border-slate-200 bg-white p-3"><div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-900">${escapeHtml(typeLabels.get(key)||key)}</b><span class="text-[10px] text-slate-400">${count} 次</span></div><div class="mt-1 text-sm font-black text-teal-800">${latest}${latest==='—'?'':' / 5'}</div><div class="mt-1 text-[10px] text-slate-400">最近 ${escapeHtml(cell?.latestDate||'—')}</div></div>`;
      }).join('');
      panel.innerHTML=`
        <div class="flex items-start justify-between gap-3">
          <div><h5 class="text-sm font-black text-slate-950">📈 能力追蹤 · ${escapeHtml(row.name||learner.name||learner.username)}</h5><p class="mt-1 text-[11px] text-slate-500">依正式 DOPS、MINI-CEX、CBD、CHECKLIST 等紀錄與 PGY 指派完成度呈現；不合併成 AI 能力總分。</p></div>
          <button id="teacher-competency-close-p2" type="button" class="text-[11px] font-bold text-slate-600">關閉</button>
        </div>
        <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
          <div class="rounded-xl bg-white p-2"><b class="block text-base text-slate-950">${Number(row.progress?.assignmentsCompleted||0)} / ${Number(row.progress?.assignmentsTotal||0)}</b><span class="text-[10px] text-slate-500">PGY 指派完成</span></div>
          <div class="rounded-xl bg-white p-2"><b class="block text-base text-rose-800">${Number(row.progress?.assignmentsOverdue||0)}</b><span class="text-[10px] text-slate-500">逾期指派</span></div>
          <div class="rounded-xl bg-white p-2"><b class="block text-base text-indigo-900">${Number(row.assessmentSummary?.count||0)}</b><span class="text-[10px] text-slate-500">正式評量</span></div>
          <div class="rounded-xl bg-white p-2"><b class="block text-base text-teal-900">${competencyScore(row.assessmentSummary?.averageScore)}</b><span class="text-[10px] text-slate-500">正式評量平均</span></div>
        </div>
        <div class="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-2">${cells}</div>`;
      panel.querySelector('#teacher-competency-close-p2')?.addEventListener('click',()=>panel.classList.add('hidden'));
      panel.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(error){
      panel.innerHTML=`<div class="text-xs text-rose-700">❌ ${escapeHtml(error.message||'能力追蹤讀取失敗')}</div>`;
    }
  }

  function analyticNumber(value,digits=1){
    if(value===null||value===undefined||value==='')return'—';
    const number=Number(value);return Number.isFinite(number)?number.toFixed(digits):'—';
  }

  async function openTeachingAnalytics(){
    const panel=document.getElementById('teacher-teaching-analytics-p2');if(!panel)return;
    panel.classList.remove('hidden');panel.innerHTML='<div class="text-xs text-slate-500">讀取目前教學範圍分析中…</div>';
    try{
      const data=await loadAnalytics(false),summary=data?.summary||{},rows=Array.isArray(data?.learners)?data.learners:[],timeline=(Array.isArray(data?.timeline)?data.timeline:[]).slice(-6);
      const rowHtml=rows.map(row=>{const materials=row.materials||{},exams=row.exams||{},pgy=row.pgy||{};return `<article class="rounded-xl border border-slate-200 bg-white p-3"><div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"><div><b class="text-xs text-slate-900">${escapeHtml(row.name||row.empId||row.username)}</b><div class="text-[10px] text-slate-400">${escapeHtml(row.empId||'')} · ${escapeHtml(row.group||'')}</div></div><div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]"><span>教材 <b>${analyticNumber(materials.averageProgress)}%</b><br><i class="not-italic text-slate-400">${Number(materials.completed||0)}/${Number(materials.tracked||0)} 完成</i></span><span>考試 <b>${analyticNumber(exams.averageScore)}</b><br><i class="not-italic text-slate-400">${Number(exams.pendingReview||0)} 待批改</i></span><span>PGY <b>${analyticNumber(pgy.completionRate)}%</b><br><i class="not-italic text-slate-400">${Number(pgy.completedAssignments||0)}/${Number(pgy.assignments||0)} 完成</i></span><span>正式評量 <b>${analyticNumber(pgy.assessmentAverage)}</b><br><i class="not-italic text-slate-400">${Number(pgy.assessments||0)} 筆</i></span></div></div></article>`}).join('');
      const timelineHtml=timeline.map(month=>`<div class="rounded-lg border border-slate-100 bg-white p-2"><b class="text-[10px] text-slate-700">${escapeHtml(month.month||'')}</b><div class="mt-1 text-[9px] text-slate-400">教材 ${Number(month.materials||0)} · 考試 ${Number(month.exams||0)} · PGY ${Number(month.pgy||0)} · 評量 ${Number(month.assessments||0)}</div></div>`).join('');
      panel.innerHTML=`<div class="flex items-start justify-between gap-3"><div><h5 class="text-sm font-black text-slate-950">📊 教學分析</h5><p class="mt-1 text-[11px] text-slate-500">依目前伺服器 scope 的教材、考試、PGY 指派與正式評量紀錄呈現；只描述既有資料，不產生 AI 能力總分或預測。</p></div><button id="teacher-analytics-close-p2" type="button" class="text-[11px] font-bold text-slate-600">關閉</button></div>
        <div class="mt-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-center"><div class="rounded-xl bg-white p-2"><b class="block text-base text-slate-950">${Number(summary.learners||0)}</b><span class="text-[10px] text-slate-500">學員</span></div><div class="rounded-xl bg-white p-2"><b class="block text-base text-teal-900">${analyticNumber(summary.materialCompletionRate)}%</b><span class="text-[10px] text-slate-500">教材完成率</span></div><div class="rounded-xl bg-white p-2"><b class="block text-base text-indigo-900">${analyticNumber(summary.averageExamScore)}</b><span class="text-[10px] text-slate-500">考試平均</span></div><div class="rounded-xl bg-white p-2"><b class="block text-base text-amber-800">${Number(summary.examPendingReview||0)}</b><span class="text-[10px] text-slate-500">待批改考試</span></div><div class="rounded-xl bg-white p-2"><b class="block text-base text-sky-900">${analyticNumber(summary.pgyCompletionRate)}%</b><span class="text-[10px] text-slate-500">PGY 完成率</span></div><div class="rounded-xl bg-white p-2"><b class="block text-base text-emerald-900">${analyticNumber(summary.averagePgyAssessmentScore)}</b><span class="text-[10px] text-slate-500">正式評量平均</span></div></div>
        <div class="mt-3 space-y-2">${rowHtml||'<div class="rounded-xl border border-dashed border-slate-200 bg-white p-4 text-xs text-slate-500">目前沒有可分析的學員紀錄。</div>'}</div><div class="mt-3"><div class="mb-2 text-[10px] font-black text-slate-500">近 6 個月活動</div><div class="grid sm:grid-cols-3 lg:grid-cols-6 gap-2">${timelineHtml||'<span class="text-xs text-slate-400">尚無近期活動。</span>'}</div></div>`;
      panel.querySelector('#teacher-analytics-close-p2')?.addEventListener('click',()=>panel.classList.add('hidden'));panel.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(error){panel.innerHTML=`<div class="text-xs text-rose-700">❌ ${escapeHtml(error.message||'教學分析讀取失敗')}</div>`}
  }

  async function openResults(event){
    const item=latest.learners?.[Number(event.currentTarget?.dataset?.p2Results)];
    if(!item)return;
    await window.switchAdminWorkspace?.('results',true);
    const search=document.getElementById('admin-results-search');
    if(search)search.value=item.empId||item.name||item.username||'';
    if(typeof window.renderAdminTable==='function')await window.renderAdminTable();
  }

  function pgyLearningUrl(fromLearners=false,item=null){
    const url=new URL(window.location.href);
    url.searchParams.set('area','pgy');
    url.searchParams.set('group',item?.group||'grpBio');
    url.searchParams.set('module','assessment');
    if(fromLearners)url.searchParams.set('from','teacher-learners');
    else url.searchParams.delete('from');
    for(const key of ['admin','workspace','persona','teacherMode'])url.searchParams.delete(key);
    return `${url.pathname}${url.search}${url.hash}`;
  }

  async function openPgyLearningSurface(item=null){
    const pageMode=Boolean(window.isAdminWorkspacePage?.());
    if((typeof currentTrainingArea!=='undefined'&&currentTrainingArea!=='pgy')||pageMode){
      window.location.assign(pgyLearningUrl(false,item));
      return false;
    }
    if(typeof switchGroup==='function'&&item?.group) switchGroup(item.group);
    await window.toggleAdminModal?.(false);
    window.switchLearningModule?.('assessment');
    document.getElementById('panel-assessment')?.scrollIntoView({behavior:'smooth',block:'start'});
    return true;
  }

  function storeClinicalContext(item){
    if(!item)return;try{sessionStorage.setItem(CONTEXT_KEY,JSON.stringify({username:String(item.username||''),empId:String(item.empId||''),name:String(item.name||''),group:String(item.group||'grpBio')}))}catch(_){}
  }
  function clinicalContext(){try{return JSON.parse(sessionStorage.getItem(CONTEXT_KEY)||'null')}catch(_){return null}}
  function teacherAssessmentWorkspaceUrl(item=null){
    const url=new URL(window.location.href);url.searchParams.set('area','pgy');url.searchParams.set('group',item?.group||'grpBio');url.searchParams.set('admin','1');url.searchParams.set('workspace','assessment');url.searchParams.set('persona','teacher');for(const key of ['from','module'])url.searchParams.delete(key);return `${url.pathname}${url.search}${url.hash}`;
  }

  async function enterClinicalAssessment(item){
    if(!item)return;storeClinicalContext(item);
    const pageMode=Boolean(window.isAdminWorkspacePage?.());
    if((typeof currentTrainingArea!=='undefined'&&currentTrainingArea!=='pgy')||pageMode){
      try{sessionStorage.setItem(RESUME_KEY,String(item.username||''));}catch(_){}
      window.location.assign(pgyLearningUrl(true,item));
      return;
    }
    const ready=await openPgyLearningSurface(item);
    if(ready===false)return;
    if(typeof initPgyAssessmentCenter==='function') await initPgyAssessmentCenter();
    const name=document.getElementById('pgy-assess-name');
    const empId=document.getElementById('pgy-assess-empid');
    if(name)name.value=item.name||'';
    if(empId)empId.value=item.empId||'';
    if(typeof selectPgyAssessmentType==='function')selectPgyAssessmentType('dops');
    const status=document.getElementById('pgy-assess-status');
    if(status)status.textContent=`已選擇 ${item.name||item.username}；請選擇評量類型並完成各項評分。`;
    document.getElementById('pgy-assessment-form')?.scrollIntoView({behavior:'smooth',block:'start'});
  }

  async function openClinicalAssessment(event){
    const item=latest.learners?.[Number(event.currentTarget?.dataset?.p2Clinical)];
    await enterClinicalAssessment(item);
  }

  async function openPgy(event){
    const item=latest.learners?.[Number(event.currentTarget?.dataset?.p2Pgy)]||null;
    await openPgyLearningSurface(item);
  }

  function invalidateTeacherInsights(){competencyCache=null;competencyLoadedAt=0;analyticsCache=null;analyticsLoadedAt=0;loadedAt=0}
  function onClinicalAssessmentSaved(event){
    const context=clinicalContext(),detail=event?.detail||{};if(!context||!context.empId||String(context.empId)!==String(detail.empId||''))return;invalidateTeacherInsights();
    const status=document.getElementById('pgy-assess-status');if(!status)return;let button=document.getElementById('teacher-p2-return-after-assessment');
    if(!button){button=document.createElement('button');button.id='teacher-p2-return-after-assessment';button.type='button';button.className='rounded-xl border border-teal-200 bg-teal-50 px-4 py-2 text-xs font-black text-teal-800 hover:bg-teal-100';button.textContent='← 返回我的學員並更新';status.insertAdjacentElement('afterend',button)}
    button.onclick=()=>{const current=clinicalContext()||context;try{sessionStorage.removeItem(CONTEXT_KEY)}catch(_){}window.location.assign(teacherAssessmentWorkspaceUrl(current))}
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
    if(params.get('workspace')==='assessment')mountWhenReady();
  }

  let mountTimer=0;
  function mountWhenReady(attempt=0){
    const params=new URLSearchParams(window.location.search);
    if(params.get('workspace')!=='assessment')return;
    const section=ensureSection();
    if(section){
      if(mountTimer){clearTimeout(mountTimer);mountTimer=0}
      load(false);
      return;
    }
    if(attempt>=80)return;
    if(mountTimer)clearTimeout(mountTimer);
    mountTimer=setTimeout(()=>{mountTimer=0;mountWhenReady(attempt+1)},125);
  }

  function bootstrap(){
    mountWhenReady();
    resumeClinicalAssessment();
  }

  window.addEventListener('pgy:assessment-saved',onClinicalAssessmentSaved);
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',bootstrap,{once:true});
  }else{
    bootstrap();
  }
  window.addEventListener('pageshow',()=>mountWhenReady());
  window.AdminWorkspaceShell?.addAfterWorkspace?.(()=>refreshPlacement());
  window.TeacherLearnersP2=Object.freeze({load,mount:mountWhenReady});
})();
