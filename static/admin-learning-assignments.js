/* Canonical general learning-assignment admin UI.
 * Uses only same-origin session RBAC; no browser credential or authorization logic lives here.
 */
(function(){
  'use strict';

  const PANEL_ID='admin-learning-assignments';
  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const json=async(response)=>{const body=await response.json().catch(()=>({}));if(!response.ok){const error=new Error(body.error||`操作失敗（${response.status}）`);error.status=response.status;throw error;}return body;};
  const scopeNow=()=>({
    area:document.getElementById('wizard-area')?.value||window.currentTrainingArea||'internal',
    group:document.getElementById('wizard-group')?.value||window.currentGroupKey||'grpBio'
  });
  let state={courses:[],courseId:'',assignments:[],users:[],canAssignAll:false,busy:false};

  function mount(){
    let panel=document.getElementById(PANEL_ID); if(panel)return panel;
    const hub=document.getElementById('admin-course-material-hub'); if(!hub)return null;
    panel=document.createElement('section');
    panel.id=PANEL_ID;
    panel.className='rounded-2xl border border-sky-100 bg-sky-50/40 p-4 mb-4';
    panel.innerHTML=`<div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="text-sm font-black text-slate-900">📌 課程指派</h3><p class="text-[11px] text-slate-500 mt-1">設定個人／組別／全體學習、必修狀態與截止時間。首頁待辦與完成率會依正式指派計算。</p></div><button type="button" data-la-refresh class="text-[11px] font-bold text-sky-700">↻ 更新</button></div><div data-la-body class="mt-4 text-xs text-slate-500">讀取中…</div>`;
    hub.before(panel);
    panel.querySelector('[data-la-refresh]').addEventListener('click',()=>load(true));
    return panel;
  }

  function formatDue(value){if(!value)return'無期限';const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString('zh-TW',{hour12:false});}
  function assigneeLabel(item){
    if(item.assigneeType==='all')return'全體人員';
    if(item.assigneeType==='group')return`本組（${item.group||item.assigneeKey||''}）`;
    const user=item.assignee||{};return user.name?`${user.name}${user.empId?` · ${user.empId}`:''}`:(item.assigneeKey||'個人');
  }

  function render(){
    const panel=mount(),body=panel?.querySelector('[data-la-body]');if(!body)return;
    if(!state.courses.length){body.innerHTML='<div class="rounded-xl bg-white border border-slate-100 p-3">此範圍尚無可指派課程。</div>';return;}
    if(!state.courseId||!state.courses.some(c=>c.id===state.courseId))state.courseId=state.courses[0].id;
    const options=state.courses.map(c=>`<option value="${escapeHtml(c.id)}" ${c.id===state.courseId?'selected':''}>${escapeHtml(c.title||'未命名課程')}</option>`).join('');
    const users=state.users.map(u=>`<option value="${escapeHtml(u.username)}">${escapeHtml(u.name||u.username)}${u.empId?` · ${escapeHtml(u.empId)}`:''}${u.group?` · ${escapeHtml(u.group)}`:''}</option>`).join('');
    const rows=state.assignments.length?state.assignments.map(item=>`<div class="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white border border-slate-100 px-3 py-2"><div><b class="text-xs text-slate-800">${escapeHtml(assigneeLabel(item))}</b><div class="text-[10px] text-slate-500 mt-1">${item.required?'必修':'選修'} · 截止 ${escapeHtml(formatDue(item.dueAt))}</div></div><button type="button" data-la-deactivate="${escapeHtml(item.id)}" class="text-[10px] font-bold text-rose-600">取消指派</button></div>`).join(''):'<div class="rounded-xl bg-white border border-slate-100 p-3 text-slate-400">此課程尚未建立正式指派；學員端仍沿用既有組別範圍。</div>';
    body.innerHTML=`<div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"><label class="text-[11px] font-bold text-slate-600">課程<select data-la-course class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2">${options}</select></label><form data-la-form class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 items-end"><label class="text-[11px] font-bold text-slate-600">指派對象<select data-la-type class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2"><option value="group">本組</option><option value="user">個人</option>${state.canAssignAll?'<option value="all">全體</option>':''}</select></label><label data-la-user-wrap class="hidden text-[11px] font-bold text-slate-600">學員<select data-la-user class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2">${users}</select></label><label class="text-[11px] font-bold text-slate-600">截止時間<input data-la-due type="datetime-local" class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2"></label><label class="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-slate-600"><input data-la-required type="checkbox" checked> 必修</label><button type="submit" class="rounded-xl bg-sky-700 text-white px-4 py-2 text-xs font-bold sm:col-span-2 lg:col-span-4" ${state.busy?'disabled':''}>建立／更新指派</button></form></div><div class="mt-4"><div class="text-[11px] font-black text-slate-700 mb-2">目前指派</div><div class="space-y-2">${rows}</div></div>`;
    const course=body.querySelector('[data-la-course]');course.addEventListener('change',async()=>{state.courseId=course.value;await loadCourse();});
    const type=body.querySelector('[data-la-type]'),userWrap=body.querySelector('[data-la-user-wrap]');
    type.addEventListener('change',()=>userWrap.classList.toggle('hidden',type.value!=='user'));
    body.querySelector('[data-la-form]').addEventListener('submit',submitAssignment);
    body.querySelectorAll('[data-la-deactivate]').forEach(button=>button.addEventListener('click',()=>deactivate(button.dataset.laDeactivate)));
  }

  async function loadCourses(){
    const {area,group}=scopeNow();
    const response=await fetch(`/api/courses/admin?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{credentials:'same-origin',cache:'no-store'});
    if(response.status===403){mount()?.classList.add('hidden');return false;}
    const data=await json(response);state.courses=Array.isArray(data)?data:[];mount()?.classList.remove('hidden');
    if(!state.courses.some(c=>c.id===state.courseId))state.courseId=state.courses[0]?.id||'';
    return true;
  }

  async function loadCourse(){
    if(!state.courseId){state.assignments=[];state.users=[];render();return;}
    const [assignments,candidates]=await Promise.all([
      fetch(`/api/learning-assignments?courseId=${encodeURIComponent(state.courseId)}`,{credentials:'same-origin',cache:'no-store'}).then(json),
      fetch(`/api/learning-assignments/candidates?courseId=${encodeURIComponent(state.courseId)}`,{credentials:'same-origin',cache:'no-store'}).then(json)
    ]);
    state.assignments=Array.isArray(assignments.assignments)?assignments.assignments:[];
    state.users=Array.isArray(candidates.users)?candidates.users:[];
    state.canAssignAll=!!candidates.canAssignAll;render();
  }

  async function load(force=false){
    const panel=mount();if(!panel)return;
    const body=panel.querySelector('[data-la-body]');if(body&&(force||!state.courses.length))body.textContent='讀取課程指派中…';
    try{if(!(await loadCourses()))return;await loadCourse();}catch(error){if(body)body.innerHTML=`<div class="rounded-xl border border-rose-100 bg-rose-50 p-3 text-rose-700">❌ ${escapeHtml(error.message)}</div>`;}
  }

  async function submitAssignment(event){
    event.preventDefault();if(state.busy||!state.courseId)return;
    const form=event.currentTarget,type=form.querySelector('[data-la-type]').value,user=form.querySelector('[data-la-user]').value,due=form.querySelector('[data-la-due]').value,required=form.querySelector('[data-la-required]').checked;
    if(type==='user'&&!user){alert('請選擇學員。');return;}
    state.busy=true;
    try{await json(await fetch('/api/learning-assignments',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({courseId:state.courseId,assigneeType:type,assigneeKey:type==='user'?user:type==='group'?(scopeNow().group):'*',required,dueAt:due||''})}));await loadCourse();if(typeof window.renderAdminCourseMaterialHub==='function')window.renderAdminCourseMaterialHub(true).catch(()=>{});}catch(error){alert(error.message);}finally{state.busy=false;}
  }

  async function deactivate(id){
    if(!id||!confirm('取消這筆課程指派？既有學習紀錄不會刪除。'))return;
    try{await json(await fetch(`/api/learning-assignments/${encodeURIComponent(id)}`,{method:'DELETE',credentials:'same-origin'}));await loadCourse();}catch(error){alert(error.message);}
  }

  function bindScopeChanges(){['wizard-area','wizard-group'].forEach(id=>document.getElementById(id)?.addEventListener('change',()=>{state={courses:[],courseId:'',assignments:[],users:[],canAssignAll:false,busy:false};load(true);}));}
  function init(){if(mount()){bindScopeChanges();load();}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
  window.refreshLearningAssignments=()=>load(true);
})();
