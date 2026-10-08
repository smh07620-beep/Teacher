/* Teacher 7.3: guided course -> material -> exam flow using session RBAC. */
(function(){
'use strict';

const MODE_META={
  later:{label:'稍後建立',next:'這次先不建立考卷，可直接前往確認與發布。'},
  bank:{label:'自己出題',next:'開啟考卷工作區，可逐題建立，也可從既有題庫加入。'},
  ai:{label:'AI 協助出題',next:'開啟 AI 出題工作區；AI 可協助產生單選、多選、是非、填空、問答與影音互動候選題。'},
  blueprint:{label:'Blueprint（進階）',next:'題型配額與抽題規則保留在考卷進階設定，不放在主要建立流程。'}
};
const AI_PLAN_META={
  none:{label:'不需要 AI 製作',detail:'直接使用目前教材；未來仍可從課程管理再次進入 AI 製作。'},
  presentation:{label:'AI PowerPoint',detail:'以目前教材或額外資料建立投影片；完成後回到本頁，再加入這門課。'},
  narration:{label:'講稿與配音',detail:'以教材建立講稿、修改、核准、試聽與產生配音；完成後回到本頁。'},
  video:{label:'AI 教學影片',detail:'以教材、投影片或其他來源製作影片；完成後回到本頁確認。'}
};
const WORKFLOW_STORAGE_KEY='teacher.courseWizard.bundleWorkflow.v1';
const state={editing:false,step:1,files:[],fileMeta:{},existing:[],examMode:'later',aiPlan:'none',assignPermission:null,assignmentEnabled:false,assigneeType:'group',assigneeKey:'',assignmentRequired:true,dueAt:'',audienceOptions:null,course:null,categoryId:'',materials:[],busy:false,publicationBusy:false,workflowId:'',workflowFingerprint:'',created:false,failedUploads:[],queuedJobs:[],queuedMaterialIds:[],expectedMaterialIds:[],linksVerified:false,expectedJobs:0,jobRows:[],jobEstimateSeconds:0,workerProtocolBlocked:false,completedMaterials:[],atlasCandidates:{},aiProducts:[],resultHtml:'',watchToken:0};
const esc=v=>(window.escapeHtml?window.escapeHtml(String(v??'')):String(v??''));
const el=id=>document.getElementById(id);

function loginRedirect(){
  const next=encodeURIComponent(location.pathname+location.search);
  location.href=`/login?next=${next}`;
}

async function api(url,options={}){
  const headers={...(options.headers||{})};
  if(options.body && !(options.body instanceof FormData) && !headers['Content-Type'])headers['Content-Type']='application/json';
  const response=await fetch(url,{...options,headers,credentials:'same-origin'});
  const data=await response.json().catch(()=>({}));
  if(response.status===401){loginRedirect();throw new Error('登入已逾時，請重新登入。');}
  if(response.status===403)throw new Error(data.error||'此帳號沒有這項操作權限。');
  if(!response.ok)throw new Error(data.error||`操作失敗（HTTP ${response.status}）`);
  return data;
}

function scope(){
  return {area:el('wizard-area')?.value||'pgy',group:el('wizard-group')?.value||'grpBio'};
}

function mode(){return MODE_META[state.examMode]||MODE_META.later;}
function aiPlan(){return AI_PLAN_META[state.aiPlan]||AI_PLAN_META.none;}
function canAssignLearning(){return state.assignPermission===true;}
async function resolveAssignmentPermission(){
  try{
    const current=window.TeacherRBAC681;
    if(typeof current?.hasPermission==='function'){
      state.assignPermission=Boolean(current.hasPermission('learning.assign'));
    }else{
      const ready=await (window.TeacherRBAC681Ready||Promise.resolve(null));
      state.assignPermission=Boolean(typeof ready?.hasPermission==='function'&&ready.hasPermission('learning.assign'));
    }
  }catch(_error){
    state.assignPermission=false;
  }
  if(state.step===1&&!state.busy)render();
}
function queuedIds(){return [...new Set((state.queuedJobs||[]).filter(Boolean).map(String))];}
function canLeaveCourse(){
  if(!state.created||state.failedUploads.length)return false;
  if(state.expectedMaterialIds.length&&!state.linksVerified)return false;
  if(state.expectedJobs<=0)return true;
  const ids=queuedIds();
  if(ids.length<state.expectedJobs)return false;
  const byId=new Map((state.jobRows||[]).map(row=>[String(row.id||''),row]));
  return ids.every(id=>byId.get(id)?.status==='completed');
}
function syncCompletionControls(){
  const ready=canLeaveCourse();
  const finish=el('cw681-finish');
  if(finish){
    finish.disabled=!ready||state.publicationBusy;
    finish.textContent=ready?'儲存草稿並離開':state.failedUploads.length?'⚠️ 先完成教材上傳':'⏳ 等待教材正式完成後才能離開';
  }
  const publish=el('cw681-publish');
  if(publish){
    publish.disabled=!ready||state.publicationBusy;
    publish.textContent=state.publicationBusy?'⏳ 處理中…':(state.editing&&String(state.course?.lifecycleStatus||'')==='published'?'✅ 完成並返回課程':'🟢 確認並正式發布');
  }
  ['cw681-next-destination','cw681-reset-next'].forEach(id=>{const node=el(id);if(node)node.disabled=!ready||state.publicationBusy;});
}
function setBusy(value){
  state.busy=!!value;
  const button=el('cw681-create');
  if(button){
    button.disabled=state.busy;
    button.textContent=state.busy?(state.created?'⏳ 重試上傳中…':'⏳ 建立中…'):(state.created?'重試未完成教材':'建立課程與關聯');
  }
}

function bundleFingerprint(payload){
  return JSON.stringify([payload.area,payload.group,payload.title,payload.desc,payload.examMode,payload.examTitle]);
}

function newWorkflowId(){
  if(window.crypto?.randomUUID)return `cw-${window.crypto.randomUUID()}`;
  return `cw-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,12)}`;
}

function ensureWorkflowId(payload){
  const fingerprint=bundleFingerprint(payload);
  if(state.workflowId&&state.workflowFingerprint===fingerprint)return state.workflowId;
  try{
    const saved=JSON.parse(sessionStorage.getItem(WORKFLOW_STORAGE_KEY)||'{}');
    if(saved.workflowId&&saved.fingerprint===fingerprint){
      state.workflowId=String(saved.workflowId);
      state.workflowFingerprint=fingerprint;
      return state.workflowId;
    }
  }catch(_e){}
  state.workflowId=newWorkflowId();
  state.workflowFingerprint=fingerprint;
  try{sessionStorage.setItem(WORKFLOW_STORAGE_KEY,JSON.stringify({workflowId:state.workflowId,fingerprint}));}catch(_e){}
  return state.workflowId;
}

function clearWorkflowId(){
  state.workflowId='';state.workflowFingerprint='';
  try{sessionStorage.removeItem(WORKFLOW_STORAGE_KEY);}catch(_e){}
}

function mount(){
  const old=el('course-wizard-legacy-fields'),actions=el('wizard-create-btn')?.parentElement,host=el('admin-courses-list');
  if(!old||!host||el('course-wizard-681'))return;
  old.classList.add('hidden');actions?.classList.add('hidden');
  host.insertAdjacentHTML('beforebegin','<div id="course-wizard-681" class="space-y-4"></div>');
  window.courseWizard681Next=next;
  window.courseWizard681Back=back;
  window.courseWizard681SetMode=value=>{state.examMode=value;syncExamInput();render();};
  window.courseWizard681Create=create;
  window.courseWizard681EditCourse=editCourse;
  window.courseWizard681StartNew=startNewCourse;
  window.courseWizard681AddFiles=addFilesToCourse;
  window.courseWizard681CreateAndPublish=createAndPublish;
  window.courseWizard681OpenAiAuthoring=openAiAuthoring;
  window.courseWizard681OpenAssessmentAuthoring=openAssessmentAuthoring;
  window.courseWizard681AttachAiProducts=attachAiProducts;
  window.courseWizard681ResumeStep=value=>{state.step=Math.max(1,Math.min(4,Number(value)||1));render();if(state.step===2)void loadMaterials();};
  window.courseWizard681RefreshMaterials=loadMaterials;
  window.courseWizard681SelectExisting=()=>{if(!state.created)state.existing=[...document.querySelectorAll('.cw681-existing:checked')].map(x=>x.value);};
  window.courseWizard681FilesChanged=input=>{if(state.created&&!state.editing)return;state.files=[...(input?.files||[])];state.fileMeta={};renderFileSummary();};
  window.courseWizard681SetFileMeta=(index,field,value)=>{if(!state.created)state.fileMeta[index]={...(state.fileMeta[index]||{}),[field]:value};};
  window.courseWizard681Continue=continueToAssessment;
  window.courseWizard681OpenCourse=openCourseWorkspace;
  window.courseWizard681PublishAndOpen=publishAndOpenCourseWorkspace;
  window.courseWizard681OpenAtlasImport=openCourseAtlasImport;
  window.courseWizard681Reset=reset;
  render();void resolveAssignmentPermission();loadMaterials();
}

function actionFooter(){
  if(state.step<4){
    const blocked=state.busy||(state.created&&!canLeaveCourse());
    return `<button ${blocked?'disabled':''} data-csp-click="courseWizard681Next()" class="rounded bg-violet-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">${state.created?'下一步':'下一步'}</button>`;
  }
  if(!state.created)return `<button id="cw681-create" ${state.busy?'disabled':''} data-csp-click="courseWizard681CreateAndPublish()" class="rounded bg-emerald-700 px-4 py-2 text-sm font-black text-white disabled:opacity-50">${state.busy?'⏳ 建立中…':'🟢 建立並發布課程'}</button>`;
  const retry=state.failedUploads.length?`<button id="cw681-create" ${state.busy?'disabled':''} data-csp-click="courseWizard681Create()" class="rounded border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-bold text-amber-800 disabled:opacity-50">${state.busy?'⏳ 重試上傳中…':'重試未完成教材'}</button>`:'';
  const ready=canLeaveCourse();
  const publishLabel=state.publicationBusy?'⏳ 發布中…':'🟢 確認並正式發布';
  return `<div class="flex flex-wrap justify-end gap-2">${retry}<button id="cw681-finish" type="button" ${ready&&!state.publicationBusy?'':'disabled'} data-csp-click="courseWizard681OpenCourse()" class="rounded border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:opacity-40">儲存草稿並離開</button><button id="cw681-publish" type="button" ${ready&&!state.publicationBusy?'':'disabled'} data-csp-click="courseWizard681PublishAndOpen()" class="rounded bg-emerald-700 px-4 py-2 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-40">${publishLabel}</button></div>`;
}

function render(){
  const root=el('course-wizard-681');if(!root)return;
  const steps=['課程設定','教材＋AI','評量／考卷','確認發布'];
  root.innerHTML=`<div class="flex flex-wrap gap-2">${steps.map((name,i)=>`<span class="rounded-full px-3 py-1 text-xs font-bold ${state.step===i+1?'bg-violet-700 text-white':state.step>i+1?'bg-violet-100 text-violet-800':'bg-slate-100 text-slate-500'}">${i+1} ${name}</span>`).join('')}</div><div class="rounded-xl border border-violet-200 bg-violet-50/30 p-4"><div id="cw681-step"></div><div class="mt-4 flex justify-between gap-2"><button ${state.step===1||state.busy?'disabled':''} data-csp-click="courseWizard681Back()" class="rounded border px-4 py-2 text-sm disabled:opacity-40">上一步</button>${actionFooter()}</div><div id="cw681-status" class="mt-3 text-xs text-violet-900"></div></div>`;
  const box=el('cw681-step');
  if(state.step===1){box.innerHTML=stepOne();bindStepOneControls();}
  if(state.step===2){box.innerHTML=stepTwo();paintMaterials();renderFileSummary();bindStepTwoControls();}
  if(state.step===3){box.innerHTML=stepThree();bindStepThreeControls();}
  if(state.step===4)box.innerHTML=stepFour();
  const status=el('cw681-status');if(status&&state.resultHtml)status.innerHTML=state.resultHtml;
  syncCompletionControls();
}

function stepOne(){
  const s=scope(),options=[...document.querySelectorAll('#wizard-group option')],permissionPending=state.assignPermission===null,canAssign=canAssignLearning(),locked=state.created?'disabled':'';
  const editNote=state.editing?`<div class="md:col-span-2 rounded-xl border border-violet-200 bg-violet-50 p-3 text-xs text-violet-900"><b>✏️ 正在編輯既有課程</b><p class="mt-1">可直接點上方步驟跳到想修改的地方。課程名稱、訓練區與組別已鎖定；要調整名稱、學習目標、日期或教材順序，請按下方按鈕。</p><button type="button" data-csp-click="teachingEditCourse('${esc(state.course?.id||'')}')" class="mt-2 rounded-lg border border-violet-300 bg-white px-3 py-1.5 font-bold text-violet-800">調整課程安排（名稱、目標、日期、教材順序）</button></div>`:'';
  const checkpointNote=state.editing?editNote:state.created?'<div class="md:col-span-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800"><b>✓ 課程草稿 checkpoint 已建立</b><p class="mt-1">課程名稱、訓練區與組別已鎖定；學習對象、學習要求與期限仍可在發布前調整。</p></div>':'';
  const assignmentPanel=permissionPending?`<section class="md:col-span-2 rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800"><b>學習對象與期限</b><p class="mt-1">正在確認你的學習指派權限…</p></section>`:canAssign?`<section class="md:col-span-2 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
    <label class="flex items-center gap-2 text-xs font-black text-teal-950"><input id="cw681-assignment-enabled" type="checkbox" ${state.assignmentEnabled?'checked':''}> 發布後立即建立學習指派</label>
    <p class="mt-1 text-[11px] text-teal-800">課程可見範圍仍由上方訓練區／組別控制；這裡設定誰需要完成、學習要求與期限。</p>
    <div class="mt-3 grid gap-3 md:grid-cols-4">
      <label class="text-xs font-bold">指派對象<select id="cw681-assignee-type" class="mt-1 w-full rounded border bg-white p-2"></select></label>
      <label class="text-xs font-bold">人員／組別<select id="cw681-assignee-key" class="mt-1 w-full rounded border bg-white p-2"></select></label>
      <label class="text-xs font-bold">學習要求<select id="cw681-required" class="mt-1 w-full rounded border bg-white p-2"><option value="required" ${state.assignmentRequired?'selected':''}>指定完成</option><option value="elective" ${!state.assignmentRequired?'selected':''}>自由選讀</option></select></label>
      <label class="text-xs font-bold">完成期限<input id="cw681-due-at" type="date" value="${esc(state.dueAt)}" class="mt-1 w-full rounded border bg-white p-2"></label>
    </div>
    <p id="cw681-audience-status" class="mt-2 text-[11px] text-slate-500">正在讀取可指派對象…</p>
  </section>`:`<section class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600"><b>學習對象與期限</b><p class="mt-1">此帳號沒有「學習指派」權限；課程可見範圍仍會依上方訓練區與組別生效。</p></section>`;
  return `<h5 class="font-black">1. 課程設定</h5><p class="mt-1 text-xs text-slate-500">先一次決定課程範圍、名稱，以及有權限時的學習對象與期限；之後不必再回外層補設定。</p><div class="mt-3 grid gap-3 md:grid-cols-2"><label class="text-xs font-bold">訓練區<select id="cw681-area" ${locked} class="mt-1 w-full rounded border p-2 disabled:bg-slate-100"><option value="pgy" ${s.area==='pgy'?'selected':''}>PGY訓練區</option><option value="internal" ${s.area==='internal'?'selected':''}>內部教育訓練區</option></select></label><label class="text-xs font-bold">組別<select id="cw681-group" ${locked} class="mt-1 w-full rounded border p-2 disabled:bg-slate-100">${options.map(o=>`<option value="${esc(o.value)}" ${o.value===s.group?'selected':''}>${esc(o.textContent)}</option>`).join('')}</select></label><label class="text-xs font-bold md:col-span-2">課程名稱<input id="cw681-title" ${locked} value="${esc(el('wizard-course-title')?.value||'')}" class="mt-1 w-full rounded border p-2 disabled:bg-slate-100" placeholder="例如：血液鏡檢基礎訓練"></label><label class="text-xs font-bold md:col-span-2">課程說明<textarea id="cw681-desc" ${locked} class="mt-1 w-full rounded border p-2 disabled:bg-slate-100" placeholder="學習目標、適用對象或完成條件">${esc(el('wizard-course-desc')?.value||'')}</textarea></label>${checkpointNote}${assignmentPanel}</div>`;
}

function personLabel(person){
  const name=String(person?.name||person?.username||'').trim(),emp=String(person?.empId||'').trim();
  return name+(emp?'｜'+emp:'');
}

function paintWizardAudienceOptions(){
  if(!canAssignLearning())return;
  const type=el('cw681-assignee-type'),key=el('cw681-assignee-key'),status=el('cw681-audience-status');
  if(!type||!key)return;
  const options=state.audienceOptions||{},allowed=Array.isArray(options.allowedAssigneeTypes)&&options.allowedAssigneeTypes.length?options.allowedAssigneeTypes:['group'];
  const labels={group:'目前組別',user:'指定人員',all:'全體人員'};
  const previousType=allowed.includes(state.assigneeType)?state.assigneeType:(allowed.includes('group')?'group':allowed[0]);
  type.replaceChildren(...allowed.map(value=>new Option(labels[value]||value,value)));
  type.value=previousType;state.assigneeType=previousType;

  if(previousType==='all'){
    key.replaceChildren(new Option('全體人員',''));key.disabled=true;state.assigneeKey='';
  }else if(previousType==='user'){
    const people=Array.isArray(options.people)?options.people:[];
    key.disabled=false;
    key.replaceChildren(new Option('請選擇人員',''),...people.map(person=>new Option(personLabel(person),person.username||'')));
    if([...key.options].some(option=>option.value===state.assigneeKey))key.value=state.assigneeKey;
  }else{
    const current=String(options.group||el('cw681-group')?.value||scope().group||'');
    const groups=(Array.isArray(options.groups)?options.groups:[]).filter(item=>!current||String(item.key)===current);
    key.disabled=false;
    key.replaceChildren(...(groups.length?groups:[{key:current,label:el('cw681-group')?.selectedOptions?.[0]?.textContent||current}]).map(item=>new Option(item.label||item.key,item.key)));
    if([...key.options].some(option=>option.value===(state.assigneeKey||current)))key.value=state.assigneeKey||current;
    state.assigneeKey=key.value||current;
  }
  const enabled=Boolean(el('cw681-assignment-enabled')?.checked);
  [type,key,el('cw681-required'),el('cw681-due-at')].filter(Boolean).forEach(node=>node.disabled=!enabled||(node===key&&previousType==='all'));
  if(status)status.textContent=enabled?'發布完成後會自動建立這筆指派。':'未啟用；只建立／發布課程，不額外建立學習指派。';
}

async function loadWizardAudienceOptions(){
  if(!canAssignLearning())return;
  const area=el('cw681-area')?.value||scope().area,group=el('cw681-group')?.value||scope().group,status=el('cw681-audience-status');
  try{
    const options=await api(`/api/learning-assignments/audience-options?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`);
    state.audienceOptions=options||{};paintWizardAudienceOptions();
  }catch(error){if(status)status.textContent='指派對象暫時無法讀取：'+error.message;}
}

function bindStepOneControls(){
  const enabled=el('cw681-assignment-enabled');
  enabled?.addEventListener('change',()=>{state.assignmentEnabled=enabled.checked;paintWizardAudienceOptions();});
  el('cw681-assignee-type')?.addEventListener('change',event=>{state.assigneeType=event.target.value;state.assigneeKey='';paintWizardAudienceOptions();});
  el('cw681-assignee-key')?.addEventListener('change',event=>{state.assigneeKey=event.target.value;});
  [el('cw681-area'),el('cw681-group')].filter(Boolean).forEach(node=>node.addEventListener('change',()=>{
    if(el('wizard-area'))el('wizard-area').value=el('cw681-area')?.value||'pgy';
    if(el('wizard-group'))el('wizard-group').value=el('cw681-group')?.value||el('wizard-group').value;
    state.audienceOptions=null;state.assigneeKey='';void loadWizardAudienceOptions();
  }));
  paintWizardAudienceOptions();
  void loadWizardAudienceOptions();
}

function stepTwo(){
  const products=(state.aiProducts||[]).map(item=>`<div class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2"><div><b class="text-emerald-950">✅ ${esc(item.title||'AI 製作產物')}</b><div class="mt-0.5 text-[11px] text-emerald-700">${esc(item.kind||'AI')}｜${item.derived?'附於來源教材，已隨課程發布':item.linked?'已加入本課程':'等待加入本課程'}</div></div>${item.derived?'<span class="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-bold text-emerald-800">已發布</span>':`<button type="button" data-csp-click="courseWizard681AttachAiProducts()" class="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-bold text-emerald-800">${item.linked?'已加入':'加入本課程教材'}</button>`}</div>`).join('');
  return `<h5 class="font-black">2. 教材與 AI 製作</h5><p class="mt-1 text-xs text-slate-500">先匯入／選擇教材並確認系統判定；需要 AI 時，再從本步驟進入對應製作區，完成後回到這裡。</p>
  <div class="mt-3 grid gap-4 lg:grid-cols-2"><div><label class="block text-xs font-bold">上傳新教材<input id="cw681-files" type="file" multiple ${state.created&&!state.editing?'disabled':''} class="mt-1 w-full text-sm disabled:opacity-50" data-csp-change="courseWizard681FilesChanged(this)"></label><div id="cw681-file-summary" class="mt-2 text-xs text-slate-500"></div>${state.editing?'<button type="button" data-csp-click="courseWizard681AddFiles()" class="mt-2 rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-bold text-white">上傳到本課程</button>':''}</div><div><div class="flex justify-between"><b class="text-xs">既有教材</b><button type="button" data-csp-click="courseWizard681RefreshMaterials()" class="text-xs text-violet-700">更新</button></div><div id="cw681-materials" class="mt-2 max-h-48 overflow-auto rounded border bg-white p-2 text-xs">讀取中…</div></div></div>
  <p class="mt-3 text-xs text-violet-800">${state.editing?'編輯模式：選好檔案後按「上傳到本課程」，教材處理完成會自動掛入這門課；也可以用下方 AI 製作新增內容。':state.created?'✓ 原始教材已寫入課程草稿；如需新增內容，可使用下方 AI 製作。':'外部連結請先用「＋新增單一教材 → 外部連結」建立，之後可在這裡直接掛入課程。'}</p>
  <section class="mt-5 border-t border-violet-100 pt-4"><div><b class="text-sm text-slate-900">需要 AI 協助製作嗎？</b><p class="mt-1 text-xs text-slate-500">AI 是教材製作工具，不是發布條件；選「不需要」即可直接下一步。</p></div><div class="mt-3 grid gap-2 md:grid-cols-2">${Object.entries(AI_PLAN_META).map(([id,meta])=>`<button type="button" data-cw-ai-plan="${id}" class="rounded-xl border p-3 text-left text-sm ${state.aiPlan===id?'border-teal-500 bg-teal-50':'bg-white'}"><b>${esc(meta.label)}</b><span class="mt-1 block text-xs text-slate-500">${esc(meta.detail)}</span></button>`).join('')}</div>${state.aiPlan!=='none'?`<div class="mt-3 flex items-center justify-between gap-3 rounded-xl border border-teal-200 bg-teal-50 p-3"><p class="text-xs text-teal-900">選擇「${esc(aiPlan().label)}」後，可先建立安全草稿 checkpoint，再在同一個全頁 Studio 開啟製作區。</p><button type="button" data-csp-click="courseWizard681OpenAiAuthoring()" class="shrink-0 rounded-xl bg-teal-700 px-4 py-2 text-xs font-black text-white">開啟 ${esc(aiPlan().label)} →</button></div>`:''}${products?`<div class="mt-3 space-y-2"><b class="text-xs text-slate-700">本次 AI 製作產物</b>${products}</div>`:''}</section>`;
}

function bindStepTwoControls(){
  document.querySelectorAll('[data-cw-ai-plan]').forEach(button=>button.addEventListener('click',()=>{
    state.aiPlan=button.dataset.cwAiPlan||'none';render();loadMaterials();
  }));
}

function stepThree(){
  const primary=['later','bank','ai'];
  return `<h5 class="font-black">3. 評量／考卷</h5><p class="mt-1 text-xs text-slate-500">這一步只處理考卷。可以稍後建立、自己出題，或讓 AI 協助產生候選題；Blueprint 收在進階設定。</p>
  <div class="mt-3 grid gap-2 md:grid-cols-3">${primary.map(id=>{const meta=MODE_META[id];return `<button type="button" data-csp-click="courseWizard681SetMode('${id}')" class="rounded-xl border p-3 text-left text-sm ${state.examMode===id?'border-violet-500 bg-violet-100':'bg-white'}"><b>${esc(meta.label)}</b><span class="mt-1 block text-xs text-slate-500">${esc(meta.next)}</span></button>`;}).join('')}</div>
  ${state.examMode==='later'?'':`<label class="mt-3 block text-xs font-bold">考卷名稱（必填）<input id="cw681-exam" value="${esc(el('wizard-exam-title')?.value||'')}" class="mt-1 w-full rounded border p-2" placeholder="例如：課後評量"></label><div class="mt-3 rounded-xl border border-indigo-200 bg-indigo-50 p-3 flex flex-wrap items-center justify-between gap-3"><p class="text-xs text-indigo-900">${state.categoryId?'✅ 考卷草稿已建立，可繼續編輯。':'系統會先建立這門課的考卷草稿，再開啟完整出題工作區。'}</p><button type="button" data-csp-click="courseWizard681OpenAssessmentAuthoring()" class="rounded-xl bg-indigo-700 px-4 py-2 text-xs font-black text-white">${state.examMode==='ai'?'✨ 開啟 AI 出題':'✍️ 開啟自己出題'} →</button></div>`}
  <details class="mt-4 rounded-xl border border-slate-200 bg-white p-3"><summary class="cursor-pointer text-xs font-bold text-slate-600">進階：Blueprint／題型配額</summary><p class="mt-2 text-xs text-slate-500">Blueprint 不列在主要流程；需要抽題規則與題型配額時，可在考卷工作區的進階設定中使用。</p></details>`;
}

function bindStepThreeControls(){}

function assignmentSummary(){
  if(!canAssignLearning()||!state.assignmentEnabled)return '不建立額外學習指派';
  const type={group:'目前組別',user:'指定人員',all:'全體人員'}[state.assigneeType]||state.assigneeType;
  return `${type}${state.assigneeKey?' · '+state.assigneeKey:''} · ${state.assignmentRequired?'指定完成':'自由選讀'}${state.dueAt?' · '+state.dueAt+' 前完成':' · 無期限'}`;
}

function stepFour(){
  const s=scope(),title=el('wizard-course-title')?.value||state.course?.title||'',desc=el('wizard-course-desc')?.value||state.course?.desc||'',exam=el('wizard-exam-title')?.value||'';
  const aiCount=(state.aiProducts||[]).filter(item=>item.linked).length;
  const completionNote=state.created
    ? (canLeaveCourse()?'✅ 課程草稿、教材與選定評量已準備完成；這一步是唯一正式發布點。':'⏳ 新教材仍在背景處理；全部完成前不會讓學員看到課程。')
    : '按下發布時會先安全建立草稿 checkpoint；只有發布檢查通過後才會讓學員看見。';
  return `<h5 class="font-black">4. 確認與發布</h5><div class="mt-3 rounded-xl border border-violet-100 bg-white p-4"><dl class="grid gap-3 text-sm md:grid-cols-2"><div><dt class="text-xs text-slate-500">課程</dt><dd class="font-bold">${esc(title||'（未填）')}</dd></div><div><dt class="text-xs text-slate-500">可見範圍</dt><dd>${esc(s.area)} · ${esc(el('wizard-group')?.selectedOptions?.[0]?.textContent||s.group)}</dd></div><div class="md:col-span-2"><dt class="text-xs text-slate-500">說明</dt><dd>${esc(desc||'—')}</dd></div><div><dt class="text-xs text-slate-500">教材</dt><dd>新上傳 ${state.files.length} 份；既有關聯 ${state.existing.length} 份；AI 產物 ${aiCount} 份</dd></div><div><dt class="text-xs text-slate-500">評量／考卷</dt><dd class="font-bold">${esc(mode().label)}${exam?' · '+esc(exam):''}</dd></div><div><dt class="text-xs text-slate-500">學習指派</dt><dd>${esc(assignmentSummary())}</dd></div><div><dt class="text-xs text-slate-500">AI 製作</dt><dd class="font-bold">${esc(aiPlan().label)}${aiCount?' · 已加入 '+aiCount+' 份產物':''}</dd></div><div class="md:col-span-2"><dt class="text-xs text-slate-500">既有教材</dt><dd>${state.existing.map(id=>esc((state.materials||[]).find(m=>String(m.id)===String(id))?.title||id)).join('、')||'—'}</dd></div></dl><p class="mt-3 rounded-lg bg-violet-50 px-3 py-2 text-xs font-bold text-violet-800">${completionNote}</p></div>`;
}

function fileMeta(index,file){return {title:file.name.replace(/\.[^.]+$/,''),materialType:'auto',...(state.fileMeta[index]||{})};}

function renderFileSummary(){
  const box=el('cw681-file-summary');if(!box)return;
  box.innerHTML=state.files.length?state.files.map((file,index)=>{const meta=fileMeta(index,file);return `<div class="mt-2 rounded border bg-white p-2"><b>${esc(file.name)}</b><div class="mt-1 grid gap-1 sm:grid-cols-2"><input value="${esc(meta.title)}" ${state.created?'disabled':''} data-csp-input="courseWizard681SetFileMeta(${index},'title',this.value)" class="rounded border p-1 disabled:bg-slate-100" aria-label="教材名稱"><select ${state.created?'disabled':''} data-csp-change="courseWizard681SetFileMeta(${index},'materialType',this.value)" class="rounded border p-1 disabled:bg-slate-100" aria-label="教材類型"><option value="auto" ${meta.materialType==='auto'?'selected':''}>✨ 自動判定</option><option value="standard" ${meta.materialType==='standard'?'selected':''}>一般教材／投影片</option><option value="atlas" ${meta.materialType==='atlas'?'selected':''}>🔬 Atlas 圖譜教材</option><option value="infographic" ${meta.materialType==='infographic'?'selected':''}>📊 資訊圖表／流程圖</option><option value="troubleshooting" ${meta.materialType==='troubleshooting'?'selected':''}>🧰 Troubleshooting</option><option value="case" ${meta.materialType==='case'?'selected':''}>🩸 案例分析</option><option value="sop" ${meta.materialType==='sop'?'selected':''}>📑 SOP</option><option value="video" ${meta.materialType==='video'?'selected':''}>🎬 影音教材</option></select></div></div>`;}).join(''):'尚未選擇新檔案。';
}

function paintMaterials(){
  const box=el('cw681-materials');if(!box)return;
  if(!state.materials.length){box.textContent='沒有可用教材';return;}
  box.innerHTML=state.materials.map(m=>`<label class="block rounded px-1 py-1 hover:bg-violet-50"><input class="cw681-existing" data-csp-change="courseWizard681SelectExisting()" type="checkbox" value="${esc(m.id)}" ${state.existing.includes(String(m.id))?'checked':''} ${state.created?'disabled':''}> ${esc(m.title||m.filename||m.id)}</label>`).join('');
}

function syncExamInput(){
  const input=el('cw681-exam');if(input&&el('wizard-exam-title'))el('wizard-exam-title').value=input.value;
}

function syncInputs(){
  if(state.step===1){
    if(el('wizard-course-title'))el('wizard-course-title').value=el('cw681-title')?.value||'';
    if(el('wizard-course-desc'))el('wizard-course-desc').value=el('cw681-desc')?.value||'';
    if(el('wizard-area'))el('wizard-area').value=el('cw681-area')?.value||'pgy';
    if(el('wizard-group'))el('wizard-group').value=el('cw681-group')?.value||el('wizard-group').value;
    if(canAssignLearning()){
      state.assignmentEnabled=Boolean(el('cw681-assignment-enabled')?.checked);
      state.assigneeType=el('cw681-assignee-type')?.value||state.assigneeType||'group';
      state.assigneeKey=state.assigneeType==='all'?'':(el('cw681-assignee-key')?.value||state.assigneeKey||'');
      state.assignmentRequired=(el('cw681-required')?.value||'required')==='required';
      state.dueAt=el('cw681-due-at')?.value||'';
    }
  }
  if(state.step===3)syncExamInput();
}

async function next(){
  if(state.busy||(state.created&&!canLeaveCourse()))return;
  if(state.step===2&&!state.created){
    state.files=[...(el('cw681-files')?.files||state.files)];
    state.existing=[...document.querySelectorAll('.cw681-existing:checked')].map(x=>x.value);
  }
  syncInputs();
  if(state.step===1&&!String(el('wizard-course-title')?.value||'').trim())return alert('請輸入課程名稱');
  if(state.step===3&&state.examMode!=='later'){
    if(!String(el('wizard-exam-title')?.value||'').trim())return alert('請輸入考卷名稱，或改選「稍後建立」。');
    const ready=await ensureAssessmentDraft();
    if(!ready)return;
  }
  state.step=Math.min(4,state.step+1);render();
  if(state.step===2)void loadMaterials();
}

function back(){
  if(state.busy)return;
  syncInputs();
  state.step=Math.max(1,state.step-1);render();
  if(state.step===2)void loadMaterials();
}

async function loadMaterials(){
  const box=el('cw681-materials');if(box)box.textContent='讀取中…';
  try{
    const {area,group}=scope(),rows=await api(`/api/slides?area=${encodeURIComponent(area)}`);
    state.materials=(Array.isArray(rows)?rows:[]).filter(m=>String(m.group)===String(group)&&m.active!==false&&!m.isBuiltin);
    state.existing=state.existing.filter(id=>state.materials.some(m=>String(m.id)===String(id)));
    paintMaterials();
  }catch(error){if(box)box.textContent='讀取失敗：'+error.message;}
}

async function refreshWorkspaceData(){
  try{window.invalidateAdminMaterialsCache?.();}catch(_e){}
  const jobs=[];
  if(typeof window.renderAdminCourses==='function')jobs.push(window.renderAdminCourses(true));
  if(typeof window.renderAdminMaterials==='function')jobs.push(window.renderAdminMaterials(true));
  if(typeof window.renderAdminQuizCategories==='function')jobs.push(window.renderAdminQuizCategories(true));
  if(typeof window.refreshAdminMaterialCategoryOptions==='function')jobs.push(window.refreshAdminMaterialCategoryOptions());
  await Promise.allSettled(jobs);
  if(typeof window.renderAdminCourseMaterialHub==='function')await window.renderAdminCourseMaterialHub(true).catch(()=>{});
}

function elapsedSeconds(value){
  const then=new Date(value||Date.now()).getTime();
  return Number.isFinite(then)?Math.max(0,Math.round((Date.now()-then)/1000)):0;
}

function elapsedLabel(value){
  const seconds=typeof value==='number'?Math.max(0,Math.round(value)):elapsedSeconds(value);
  if(seconds<60)return `${seconds} 秒`;
  if(seconds<3600)return `${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;
  return `${Math.floor(seconds/3600)} 小時 ${Math.floor((seconds%3600)/60)} 分`;
}

const COURSE_UPLOAD_PHASES=['R2 接收','等待 Worker','下載／驗證','轉檔／預覽','正式發布','完成'];

function courseUploadPhaseIndex(row){
  if(row?.status==='completed')return 5;
  if(['queued','retry_wait'].includes(row?.status))return 1;
  const stage=String(row?.stage||'');
  if(['下載原始檔','驗證教材','內容準備'].includes(stage))return 2;
  if(['轉檔處理','建立預覽'].includes(stage))return 3;
  if(['正式發布','發布確認','完成確認'].includes(stage))return 4;
  if(row?.status==='processing')return 2;
  return 1;
}

function courseUploadTimeline(row){
  const current=courseUploadPhaseIndex(row),failed=['failed','cancelled'].includes(row?.status);
  return `<div class="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-6">${COURSE_UPLOAD_PHASES.map((label,index)=>{const done=row?.status==='completed'||index<current;const active=index===current&&row?.status!=='completed';const cls=failed&&active?'border-rose-300 bg-rose-50 text-rose-700':done?'border-emerald-200 bg-emerald-50 text-emerald-700':active?'border-sky-300 bg-sky-50 text-sky-800':'border-slate-200 bg-slate-50 text-slate-400';const mark=done?'✓':failed&&active?'!':active?'●':String(index+1);return `<div class="rounded-lg border px-2 py-1 text-[10px] font-bold ${cls}"><span class="mr-1">${mark}</span>${esc(label)}</div>`;}).join('')}</div>`;
}

function progressProjection(row,estimateSeconds){
  const elapsed=elapsedSeconds(row.startedAt||row.createdAt);
  const estimate=Math.max(0,Number(estimateSeconds||0));
  const actual=Math.max(0,Math.min(100,Number(row.progressPercent||0)));
  if(row.status==='completed')return {pct:100,timing:`完成 · ${elapsedLabel(elapsed)}`};
  if(row.status==='failed')return {pct:actual||100,timing:`失敗前已處理 ${elapsedLabel(elapsed)}`};
  if(row.status==='cancelled')return {pct:actual||100,timing:'已取消'};
  if(row.status==='queued')return {pct:actual||25,timing:`R2 已接收 · 等待 Worker ${elapsedLabel(elapsed)}`};
  if(row.status==='retry_wait')return {pct:actual||25,timing:`等待自動重試 · 已經過 ${elapsedLabel(elapsed)}`};
  const pct=actual||30;
  const eta=estimate>elapsed?`估計剩餘約 ${elapsedLabel(estimate-elapsed)}`:'已超過近期平均，Worker 仍在處理';
  return {pct,timing:`${row.stage||'Worker 處理中'} · 已處理 ${elapsedLabel(elapsed)} · ${estimate>0?eta:'估計時間資料累積中'}`};
}

function backgroundJobsHtml(rows,metrics={}){
  if(!rows.length)return '';
  const allDone=rows.every(row=>row.status==='completed');
  const hasProblem=rows.some(row=>['retry_wait','failed','cancelled'].includes(row.status));
  const workers=Array.isArray(metrics.workers)?metrics.workers:[];
  const protocolBlocked=workers.some(worker=>worker.protocolCompatible===false&&['online','busy'].includes(worker.status));
  const heading=allDone?'✅ 所有教材已正式完成':hasProblem?'⚠️ 教材處理需要注意':'⚙️ 背景教材處理中';
  const leaveHint=allDone?'現在可以安全返回課程。':'請等到全部教材顯示「已完成」再離開；系統會每 3 秒更新。';
  const protocolWarning=protocolBlocked?'<div class="mb-2 rounded-lg border border-rose-200 bg-rose-50 p-2 font-bold text-rose-800">本機 Worker 協議版本過舊，系統已停止派發新工作。教材會保持排隊，不會因版本問題反覆失敗；請更新 Worker 後再等待自動接續。</div>':'';
  return `<div class="mt-3 rounded-xl border ${hasProblem&&!allDone?'border-amber-200 bg-amber-50':'border-sky-200 bg-sky-50'} p-3 text-left text-sky-950"><div class="flex flex-wrap items-center justify-between gap-2"><b>${heading}</b><span class="text-[11px] text-sky-700">${leaveHint}</span></div>${protocolWarning}<div class="mt-2 space-y-2">${rows.map(row=>{const failed=row.status==='failed';const done=row.status==='completed';const projection=progressProjection(row,metrics.averageCompletedDurationSeconds);const label=done?'✅ 已完成':failed?'❌ 失敗':row.status==='retry_wait'?'🔁 等待重試':row.status==='processing'?`⚙️ ${row.stage||'Worker 處理中'}`:row.status==='cancelled'?'⛔ 已取消':'⏳ R2 已接收／等待 Worker';const detail=(failed||row.status==='retry_wait')?(row.error||row.detail||'未提供失敗原因'):(row.detail||row.stage||'');const retained=row.stagingBackend==='r2'&&['retry_wait','failed'].includes(row.status)?'<div class="mt-1 font-bold text-violet-700">☁ R2 原始檔仍保留，可直接重新處理，不必重新上傳；成功後才會清除 staging。</div>':'';const retry=failed&&Number(row.attempts||0)>=Number(row.maxAttempts||0)?`<button type="button" data-csp-click="retryMaterialJob('${esc(row.id)}')" class="mt-2 rounded border border-amber-300 bg-white px-2 py-1 text-[11px] font-bold text-amber-800">直接重新處理</button>`:'';const barClass=failed?'bg-rose-500':row.status==='retry_wait'?'bg-amber-500':done?'bg-emerald-500':'bg-sky-600';return `<div class="rounded-lg border ${failed?'border-rose-200 bg-rose-50':'border-sky-100 bg-white'} p-2"><div class="flex flex-wrap justify-between gap-2"><span><b>${esc(row.title||row.originalName||row.id)}</b> · ${label}</span><span class="text-[11px] text-slate-500">${esc(projection.timing)}</span></div><div class="mt-1 text-[11px] ${failed?'text-rose-700':'text-slate-600'}">${esc(row.stage||'')} ${detail?`｜${esc(detail)}`:''}</div>${courseUploadTimeline(row)}${retained}<div class="mt-2 flex items-center justify-between text-[10px] text-slate-500"><span>處理進度 ${projection.pct}%</span><span>依 Worker 真實回報階段顯示；頁數／R2 上傳量會即時持久化，剩餘時間僅為近期平均估算</span></div><div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100"><div class="h-full ${barClass} transition-all" style="width:${projection.pct}%"></div></div>${retry}</div>`;}).join('')}</div></div>`;
}

async function verifyCreatedCourseMaterials(){
  const courseId=String(state.course?.id||'');
  const expected=[...new Set((state.expectedMaterialIds||[]).filter(Boolean).map(String))];
  if(!courseId||!expected.length){state.linksVerified=true;return true;}
  let list=await api('/api/slides/admin');
  list=Array.isArray(list)?list:[];
  for(const id of expected){
    const material=list.find(item=>String(item.id||'')===id);
    if(!material)throw new Error('教材已完成處理，但教材清單找不到 '+id+'；請在 Worker / Job 狀態確認發布結果。');
    if(String(material.courseId||'')!==courseId||material.active===false){
      await api('/api/slides/'+encodeURIComponent(id),{
        method:'PATCH',
        body:JSON.stringify({courseId,active:true})
      });
    }
  }
  list=await api('/api/slides/admin');
  list=Array.isArray(list)?list:[];
  const unresolved=expected.filter(id=>{
    const material=list.find(item=>String(item.id||'')===id);
    return !material||String(material.courseId||'')!==courseId||material.active===false;
  });
  if(unresolved.length)throw new Error('教材已上傳，但尚未正確掛入課程；已停止離開流程以避免學員看到 0 份教材。');
  state.linksVerified=true;
  return true;
}

const MATERIAL_TYPE_LABELS={
  standard:'一般教材',
  atlas:'Atlas 圖譜教材',
  infographic:'資訊圖表／流程圖',
  video:'影音教材',
  troubleshooting:'Troubleshooting',
  case:'案例分析',
  sop:'SOP'
};

function materialFileName(item){
  return String(item?.filename||item?.storageFilename||'');
}

function renderCompletedMaterialInsights(){
  const host=el('cw681-material-insights');
  if(!host)return;
  const materials=Array.isArray(state.completedMaterials)?state.completedMaterials:[];
  const atlasEntries=Object.entries(state.atlasCandidates||{});
  if(!materials.length&&!atlasEntries.length){
    host.innerHTML='';
    return;
  }
  const classificationRows=materials.map(item=>{
    const type=String(item.materialType||'standard');
    const meta=item.storageMeta?.materialClassification||{};
    const method=String(meta.method||'');
    const reason=String(meta.reason||'');
    const requested=String(meta.requested||'');
    const decision=requested==='auto'
      ? `自動判定：${esc(method||'規則分類')}${reason?'｜'+esc(reason):''}`
      : `教師指定：${esc(MATERIAL_TYPE_LABELS[type]||type)}`;
    return `<div class="rounded-lg border border-emerald-100 bg-white p-2"><div class="flex flex-wrap items-center justify-between gap-2"><b>${esc(item.title||item.filename||item.id)}</b><span class="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-black text-emerald-700">${esc(MATERIAL_TYPE_LABELS[type]||type)}</span></div><p class="mt-1 text-[11px] text-slate-500">${decision}</p></div>`;
  }).join('');
  const atlasRows=atlasEntries.map(([materialId,info])=>`<div class="rounded-lg border border-teal-200 bg-teal-50 p-3"><div class="flex flex-wrap items-center justify-between gap-2"><div><b class="text-teal-950">🔬 Word 內偵測到 ${Number(info.count||0)} 張可獨立整理的圖片</b><p class="mt-1 text-[11px] text-teal-800">${esc(info.title||materialId)}｜原 Word 會保留；只會把你勾選的圖片另外建立 Atlas 草稿。</p></div><button type="button" data-csp-click="courseWizard681OpenAtlasImport('${esc(materialId)}')" class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-black text-white">檢視並建立 Atlas 草稿</button></div></div>`).join('');
  host.innerHTML=`<div class="mt-3 space-y-2"><div class="rounded-xl border border-emerald-200 bg-emerald-50 p-3"><b class="text-emerald-900">✅ 教材自動歸類結果</b><div class="mt-2 grid gap-2 md:grid-cols-2">${classificationRows}</div></div>${atlasRows}</div>`;
}

async function hydrateCompletedMaterialInsights(materialIds){
  const ids=new Set((materialIds||[]).map(String).filter(Boolean));
  if(!ids.size)return;
  try{
    const list=await api('/api/slides/admin');
    const rows=(Array.isArray(list)?list:[]).filter(item=>ids.has(String(item.id||'')));
    state.completedMaterials=rows;
    const nextCandidates={};
    for(const item of rows.filter(row=>/\.docx$/i.test(materialFileName(row)))){
      try{
        const preview=await api('/api/atlas/import-docx/'+encodeURIComponent(item.id)+'/preview',{method:'POST'});
        const images=Array.isArray(preview?.preview?.images)?preview.preview.images:[];
        if(images.length){
          nextCandidates[String(item.id)]={
            count:images.length,
            title:item.title||item.filename||item.id,
            warnings:preview?.preview?.warnings||[]
          };
        }
      }catch(error){
        console.warn('DOCX Atlas candidate scan skipped',item.id,error);
      }
    }
    state.atlasCandidates=nextCandidates;
    renderCompletedMaterialInsights();
  }catch(error){
    console.warn('Course material classification summary unavailable',error);
  }
}

async function openCourseAtlasImport(materialId){
  const id=String(materialId||'').trim();
  if(!id)return;
  const host=el('cw681-atlas-import');
  if(!host)return alert('Atlas 匯入區尚未載入，請重新整理後再試。');
  if(typeof window.openAtlasDocxWizard!=='function')return alert('DOCX → Atlas 工具尚未載入，請重新整理後再試。');
  host.classList.remove('hidden');
  await window.openAtlasDocxWizard('cw681-atlas-import',id);
  host.scrollIntoView({behavior:'smooth',block:'start'});
}

async function watchQueuedJobs(jobIds){
  const unique=[...new Set((jobIds||[]).filter(Boolean).map(String))];
  if(!unique.length){state.jobRows=[];syncCompletionControls();return;}
  const token=++state.watchToken;
  while(token===state.watchToken){
    let metrics={};
    try{metrics=await api('/api/material-jobs?limit=20');}catch(_e){}
    const rows=(await Promise.all(unique.map(async id=>{
      try{return await api(`/api/material-jobs/${encodeURIComponent(id)}`);}
      catch(error){return {id,status:'unknown',stage:'狀態讀取失敗',detail:error.message,createdAt:new Date().toISOString()};}
    }))).filter(Boolean);
    state.jobRows=rows;
    state.jobEstimateSeconds=Math.max(0,Number(metrics.averageCompletedDurationSeconds||0));
    state.workerProtocolBlocked=(Array.isArray(metrics.workers)?metrics.workers:[]).some(worker=>worker.protocolCompatible===false&&['online','busy'].includes(worker.status));
    const host=el('cw681-background-jobs');
    if(host)host.innerHTML=backgroundJobsHtml(rows,metrics);
    syncCompletionControls();
    if(rows.length===unique.length&&rows.every(row=>row.status==='completed')){
      const completedMaterialIds=rows.map(row=>String(row.materialId||'')).filter(Boolean);
      state.expectedMaterialIds=[...new Set([...state.expectedMaterialIds,...completedMaterialIds])];
      try{
        await verifyCreatedCourseMaterials();
        await refreshWorkspaceData();
        await hydrateCompletedMaterialInsights(completedMaterialIds);
      }catch(error){
        state.linksVerified=false;
        const host=el('cw681-background-jobs');
        if(host)host.insertAdjacentHTML('beforeend',`<div class="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-2 text-xs font-bold text-rose-700">❌ ${esc(error.message)}</div>`);
      }
      syncCompletionControls();
      break;
    }
    await new Promise(resolve=>setTimeout(resolve,3000));
  }
}

function buildUploadForm(file,index,meta,{area,group,desc,courseId,categoryId,workflowId}){
  const form=new FormData();
  form.append('file',file);
  form.append('title',String(meta.title||file.name.replace(/\.[^.]+$/,'')).trim());
  form.append('desc',desc);
  form.append('group',group);
  form.append('area',area);
  form.append('courseId',courseId);
  form.append('category',categoryId);
  form.append('materialType',meta.materialType||'auto');
  form.append('bundleWorkflowId',workflowId);
  form.append('bundleFileIndex',String(index));
  form.append('bundleFileSize',String(file.size||0));
  form.append('bundleFileLastModified',String(file.lastModified||0));
  return form;
}

async function uploadEntries(entries,context,status){
  if(!entries.length)return {uploaded:0,errors:[],jobs:[],materials:[]};
  if(!window.MaterialUploadClient?.enqueue)throw new Error('教材背景上傳元件尚未載入，請重新整理後再試。');
  const loaded=new Map();
  const totalBytes=Math.max(1,entries.reduce((sum,item)=>sum+Number(item.file.size||0),0));
  const errors=[],jobs=[],materials=[];
  let uploaded=0;
  for(let order=0;order<entries.length;order++){
    const item=entries[order],file=item.file,meta=fileMeta(item.index,file);
    const form=buildUploadForm(file,item.index,meta,context);
    try{
      const result=await window.MaterialUploadClient.enqueue(form,{
        fileName:file.name,
        fallbackToSameOriginQueue:false,
        onUnauthorized:loginRedirect,
        onProgress:progress=>{
          loaded.set(item.index,Math.max(0,Math.min(Number(file.size||0),Number(progress.loaded||0))));
          const totalLoaded=[...loaded.values()].reduce((sum,value)=>sum+value,0);
          const overall=Math.max(0,Math.min(100,Math.round(totalLoaded/totalBytes*100)));
          status.innerHTML=`<div class="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sky-950"><div class="flex justify-between gap-2"><b>⬆️ 上傳至 R2：${esc(file.name)}</b><span>${overall}%</span></div><div class="mt-2 h-2 overflow-hidden rounded-full bg-sky-100"><div class="h-full bg-sky-600 transition-all" style="width:${overall}%"></div></div><div class="mt-1 text-[11px]">檔案 ${order+1}/${entries.length}；R2 完成後還會等待 Worker 轉檔與正式發布，請勿提前離開。</div></div>`;
        }
      });
      loaded.set(item.index,Number(file.size||0));
      uploaded++;
      if(result?.jobId)jobs.push(String(result.jobId));
      if(result?.materialId)materials.push(String(result.materialId));
    }catch(error){
      const reason=String(error?.message||'未知上傳錯誤');
      errors.push({index:item.index,fileName:file.name,reason});
      console.warn('Course wizard material upload failed',file.name,error);
    }
  }
  return {uploaded,errors,jobs,materials};
}

async function retryFailedUploads(){
  if(state.busy||!state.created||!state.course?.id||!state.failedUploads.length)return;
  const status=el('cw681-status');setBusy(true);
  try{
    const {area,group}=scope(),desc=String(el('wizard-course-desc')?.value||'').trim();
    const entries=state.failedUploads.map(item=>({index:item.index,file:state.files[item.index]})).filter(item=>item.file);
    const result=await uploadEntries(entries,{area,group,desc,courseId:state.course.id,categoryId:state.categoryId,workflowId:state.workflowId},status);
    state.failedUploads=result.errors;
    state.expectedJobs+=result.uploaded;
    state.queuedJobs.push(...result.jobs);
    state.queuedMaterialIds.push(...(result.materials||[]));
    state.expectedMaterialIds=[...new Set([...state.expectedMaterialIds,...(result.materials||[])])];
    state.linksVerified=false;
    const retryText=state.failedUploads.length?`仍有 ${state.failedUploads.length} 份教材上傳失敗。`:'未完成教材已重新送入背景佇列；請等到 Worker 正式完成。';
    state.resultHtml=`<span class="font-bold ${state.failedUploads.length?'text-amber-700':'text-sky-700'}">${state.failedUploads.length?'⚠️':'⏳'} ${esc(retryText)}</span><div id="cw681-background-jobs"></div><button id="cw681-reset-next" type="button" disabled data-csp-click="courseWizard681Reset()" class="mt-2 text-slate-500 underline disabled:cursor-not-allowed disabled:opacity-40">建立下一門課</button>`;
    render();
    watchQueuedJobs(queuedIds());
  }catch(error){
    state.resultHtml=`<span class="font-bold text-rose-700">❌ ${esc(error.message)}</span>`;render();
  }finally{setBusy(false);}
}

async function create(){
  if(state.busy)return;
  if(state.created){if(state.failedUploads.length)await retryFailedUploads();return state.created;}
  syncInputs();
  const {area,group}=scope(),title=String(el('wizard-course-title')?.value||'').trim(),desc=String(el('wizard-course-desc')?.value||'').trim(),files=state.files;
  if(!title)return false;
  const bundlePayload={area,group,title,desc,examMode:'later',examTitle:'',existingMaterialCount:state.existing.length,uploadCount:files.length};
  bundlePayload.workflowId=ensureWorkflowId(bundlePayload);
  const status=el('cw681-status');setBusy(true);
  try{
    status.textContent='⏳ 安全建立課程草稿 checkpoint…';
    const bundle=await api('/api/course-bundles',{method:'POST',body:JSON.stringify(bundlePayload)});
    const course=bundle.course||{};
    if(!course.id)throw new Error('課程建立結果不完整，請使用相同流程重新嘗試。');
    state.course=course;
    let linked=0;
    for(const id of state.existing){
      const material=state.materials.find(m=>String(m.id)===String(id));if(!material)continue;
      status.textContent=`⏳ 關聯既有教材 ${linked+1}/${state.existing.length}…`;
      const linkedMaterial=await api('/api/slides/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({title:material.title||material.filename||'',desc:material.desc||'',courseId:course.id,category:state.categoryId||material.category||'',active:true,group,area,materialType:material.materialType||'standard',atlasMeta:material.atlasMeta||{},bundleWorkflowId:bundlePayload.workflowId,bundleLinkKey:String(id)})});
      if(linkedMaterial?.ok===false)throw new Error('既有教材關聯失敗：'+String(material.title||material.filename||id));
      linked++;
    }
    const entries=files.map((file,index)=>({file,index}));
    const upload=await uploadEntries(entries,{area,group,desc,courseId:course.id,categoryId:state.categoryId,workflowId:bundlePayload.workflowId},status);
    state.failedUploads=upload.errors;
    state.queuedJobs=upload.jobs;
    state.queuedMaterialIds=upload.materials||[];
    state.expectedMaterialIds=[...new Set([...state.existing,...state.queuedMaterialIds].map(String).filter(Boolean))];
    state.linksVerified=false;
    state.expectedJobs=upload.uploaded;
    state.jobRows=[];
    status.textContent='⏳ 同步課程與教材清單…';await refreshWorkspaceData();
    state.created=true;
    if(state.expectedJobs<=0)await verifyCreatedCourseMaterials();
    const ready=canLeaveCourse();
    const retryNote=bundle.reused?'（本次安全沿用既有課程草稿，未重複建立）':'';
    const uploadErrors=state.failedUploads.length?`<div class="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-left text-amber-900"><b>⚠️ 以下教材尚未進入 Worker：</b><ul class="mt-1 list-disc pl-5">${state.failedUploads.map(item=>`<li><b>${esc(item.fileName)}</b>：${esc(item.reason)}</li>`).join('')}</ul><p class="mt-2">請使用下方「重試未完成教材」。課程本身已鎖定完成，不會重複建立。</p></div>`:'';
    const failed=state.failedUploads.length;
    const summaryClass=failed?'font-bold text-amber-700':upload.uploaded?'font-bold text-sky-700':'font-bold text-emerald-700';
    const summaryIcon=failed?'⚠️':upload.uploaded?'⏳':'✅';
    const uploadSummary=failed?`已排入背景佇列 ${upload.uploaded} 份新教材；${failed} 份上傳失敗`:upload.uploaded?`R2 上傳已完成／排入背景佇列 ${upload.uploaded} 份，現在等待 Worker 正式處理`:'沒有新教材需要背景處理';
    state.resultHtml=`<div class="space-y-2"><div><span class="${summaryClass}">${summaryIcon} 「${esc(title)}」課程草稿${failed?'已建立，但教材上傳未完整完成':upload.uploaded?'已建立，教材仍在背景處理':'建立完成'}${retryNote}。</span> 已關聯 ${linked} 份既有教材、${uploadSummary}。</div>${uploadErrors}<div class="rounded-lg border border-sky-200 bg-sky-50 p-2 font-bold text-sky-900">新教材必須全部顯示「已完成」後才可離開；課程目前仍是草稿；教材完成後即可繼續第 3、4 步；只有第 4 步發布檢查通過後才會讓學員看見。</div><div id="cw681-material-insights"></div><div id="cw681-atlas-import" class="hidden"></div><div class="text-xs font-bold text-emerald-800">${ready?'✓ 草稿 checkpoint 已可繼續下一步。':'教材完成後即可繼續。'}</div><div id="cw681-background-jobs"></div></div>`;
    render();
    watchQueuedJobs(state.queuedJobs);
    return true;
  }catch(error){
    state.resultHtml=`<span class="font-bold text-rose-700">❌ ${esc(error.message)}（未變更內容時可直接重試，系統會沿用同一建立流程。）</span>`;render();
    return false;
  }finally{setBusy(false);}
}


async function ensureCourseDraft(){
  if(state.step===2&&!state.created){
    state.files=[...(el('cw681-files')?.files||state.files)];
    state.existing=[...document.querySelectorAll('.cw681-existing:checked')].map(x=>x.value);
  }
  if(!state.created){
    const ok=await create();
    if(!ok||!state.created)return false;
  }
  if(!canLeaveCourse()){
    alert(state.failedUploads.length
      ? '仍有教材上傳失敗，請先重試未完成教材。'
      : '教材正在 R2／Worker 背景處理。完成後即可進入 AI 或考卷工作區。');
    return false;
  }
  return true;
}

async function linkedCourseMaterialIds(){
  const courseId=String(state.course?.id||'');
  if(!courseId)return [];
  const rows=await api('/api/slides/admin');
  return (Array.isArray(rows)?rows:[])
    .filter(item=>String(item.courseId||'')===courseId&&item.active!==false)
    .map(item=>String(item.id||'')).filter(Boolean);
}

async function ensureAssessmentDraft(){
  syncExamInput();
  if(state.examMode==='later')return true;
  const title=String(el('wizard-exam-title')?.value||'').trim();
  if(!title){alert('請輸入考卷名稱，或改選「稍後建立」。');return false;}
  if(!await ensureCourseDraft())return false;
  if(!state.categoryId){
    const {area,group}=scope();
    try{
      const category=await api('/api/quiz-categories',{
        method:'POST',
        body:JSON.stringify({area,group,courseId:state.course.id,title,desc:`${state.course?.title||''} 課後評量`,passingScore:80,drawCount:0})
      });
      state.categoryId=String(category?.id||'');
      if(!state.categoryId)throw new Error('考卷草稿建立結果不完整。');
    }catch(error){
      alert('考卷草稿建立失敗：'+error.message);
      return false;
    }
  }
  try{
    const materialIds=await linkedCourseMaterialIds();
    if(materialIds.length){
      await api('/api/quiz-categories/'+encodeURIComponent(state.categoryId)+'/materials',{
        method:'PUT',body:JSON.stringify({materialIds})
      });
    }
  }catch(error){
    console.warn('Assessment material link refresh skipped',error);
  }
  await refreshWorkspaceData();
  if(state.step===3)render();
  return true;
}

async function attachAiProducts(){
  if(!state.course?.id)return false;
  const pending=(state.aiProducts||[]).filter(item=>item.materialId&&!item.linked);
  if(!pending.length)return true;
  try{
    for(const item of pending){
      await api('/api/slides/'+encodeURIComponent(item.materialId),{
        method:'PATCH',
        body:JSON.stringify({courseId:state.course.id,active:true})
      });
      item.linked=true;
      state.expectedMaterialIds=[...new Set([...state.expectedMaterialIds,String(item.materialId)])];
    }
    state.linksVerified=false;
    await verifyCreatedCourseMaterials();
    await refreshWorkspaceData();
    await loadMaterials();
    if(state.categoryId){
      const materialIds=await linkedCourseMaterialIds();
      await api('/api/quiz-categories/'+encodeURIComponent(state.categoryId)+'/materials',{
        method:'PUT',body:JSON.stringify({materialIds})
      }).catch(()=>{});
    }
    if(state.step===2)render();
    return true;
  }catch(error){
    alert('AI 產物加入課程失敗：'+error.message);
    return false;
  }
}

async function openAiAuthoring(){
  if(state.aiPlan==='none')return;
  if(!await ensureCourseDraft())return;
  await attachAiProducts();
  const mode={presentation:'presentation',narration:'narration',video:'video'}[state.aiPlan]||'presentation';
  if(typeof window.openTeacherCourseMediaAuthoring==='function'){
    await window.openTeacherCourseMediaAuthoring(mode);
    return;
  }
  await window.TeacherWorkspace1014?.openMedia?.();
  window.TeacherAIMediaStudio1018?.showMode?.(mode);
}

async function openAssessmentAuthoring(){
  if(state.examMode==='later')return;
  if(!await ensureAssessmentDraft())return;
  if(typeof window.openTeacherCourseAssessmentAuthoring==='function'){
    await window.openTeacherCourseAssessmentAuthoring(state.categoryId,state.examMode);
    return;
  }
  await window.openTeacherContentExam?.(state.categoryId);
  if(state.examMode==='ai')window.teacherContentStudioExamAction?.('ai',state.categoryId);
}

function clearWizardState(){
  state.watchToken++;
  state.editing=false;state.step=1;state.files=[];state.fileMeta={};state.existing=[];state.examMode='later';state.aiPlan='none';state.assignmentEnabled=false;state.assigneeType='group';state.assigneeKey='';state.assignmentRequired=true;state.dueAt='';state.audienceOptions=null;
  state.course=null;state.categoryId='';state.materials=[];state.busy=false;state.publicationBusy=false;state.created=false;
  state.failedUploads=[];state.queuedJobs=[];state.queuedMaterialIds=[];state.expectedMaterialIds=[];state.linksVerified=false;state.expectedJobs=0;state.jobRows=[];
  state.jobEstimateSeconds=0;state.workerProtocolBlocked=false;state.completedMaterials=[];state.atlasCandidates={};state.aiProducts=[];state.resultHtml='';
  clearWorkflowId();
}

// 編輯既有課程：把既有課程帶入精靈，讓老師從任一步繼續（教材、AI、考卷、指派、發布）。
async function editCourse(courseId,step=2){
  courseId=String(courseId||'').trim();
  if(!courseId)return false;
  const sameCourse=state.editing&&String(state.course?.id||'')===courseId;
  if(state.busy||(state.created&&!canLeaveCourse())){
    alert('目前課程的教材仍在處理或上傳失敗，請先完成後再編輯。');
    return false;
  }
  if(sameCourse){
    state.step=Math.max(1,Math.min(4,Number(step)||2));render();
    if(state.step===2)void loadMaterials();
    return true;
  }
  if(state.created&&!state.editing){
    alert('目前有一門新建立的課程尚未離開精靈，請先完成或發布它，再編輯其他課程。');
    return false;
  }
  try{
    const plan=await api('/api/courses/'+encodeURIComponent(courseId)+'/plan');
    const course=plan?.course||{};
    if(!course.id)throw new Error('找不到這門課程。');
    clearWizardState();
    state.course=course;state.created=true;state.editing=true;
    const areaSelect=el('wizard-area'),groupSelect=el('wizard-group');
    if(areaSelect)areaSelect.value=course.area||areaSelect.value;
    if(groupSelect){
      if(course.group&&![...groupSelect.options].some(option=>option.value===course.group))groupSelect.add(new Option(course.group,course.group));
      if(course.group)groupSelect.value=course.group;
    }
    if(el('wizard-course-title'))el('wizard-course-title').value=course.title||'';
    if(el('wizard-course-desc'))el('wizard-course-desc').value=course.desc||'';
    const linked=(Array.isArray(plan.materials)?plan.materials:[]).filter(item=>item&&item.active!==false).map(item=>String(item.id||'')).filter(Boolean);
    state.existing=linked;state.expectedMaterialIds=linked;
    try{
      const {area,group}=scope();
      const cats=await api(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`);
      const category=(Array.isArray(cats)?cats:[]).find(item=>String(item.courseId||'')===courseId);
      if(category){
        state.categoryId=String(category.id||'');
        state.examMode='bank';
        if(el('wizard-exam-title'))el('wizard-exam-title').value=category.title||'';
      }
    }catch(error){console.warn('Course wizard edit: exam lookup skipped',error);}
    await verifyCreatedCourseMaterials();
    state.step=Math.max(1,Math.min(4,Number(step)||2));
    render();
    if(state.step===2)void loadMaterials();
    return true;
  }catch(error){
    alert('無法開啟課程編輯：'+(error.message||'未知錯誤'));
    return false;
  }
}

// 離開編輯模式、回到乾淨的「建立新課程」：避免上一門被編輯的課程鎖住新課程的欄位。
function startNewCourse(){
  if(!state.editing)return true;
  if(state.busy||!canLeaveCourse()){
    alert('目前課程的教材仍在處理或上傳失敗，請先完成後再建立新課程。');
    return false;
  }
  clearWizardState();
  ['wizard-course-title','wizard-course-desc','wizard-exam-title'].forEach(id=>{if(el(id))el(id).value='';});
  render();void loadMaterials();
  return true;
}

// 編輯模式：把新選的教材檔案上傳到這門既有課程。
async function addFilesToCourse(){
  if(state.busy||!state.editing||!state.course?.id)return;
  const input=el('cw681-files'),picked=[...(input?.files||[])];
  if(!picked.length)return alert('請先選擇要上傳的教材檔案。');
  const base=state.files.length;
  state.files=[...state.files,...picked];
  const entries=picked.map((file,offset)=>({file,index:base+offset}));
  const {area,group}=scope(),desc=String(state.course.desc||'');
  const status=el('cw681-status');setBusy(true);
  try{
    const result=await uploadEntries(entries,{area,group,desc,courseId:state.course.id,categoryId:state.categoryId,workflowId:newWorkflowId()},status);
    state.failedUploads=[...state.failedUploads,...result.errors];
    state.expectedJobs+=result.uploaded;
    state.queuedJobs.push(...result.jobs);
    state.queuedMaterialIds.push(...(result.materials||[]));
    state.expectedMaterialIds=[...new Set([...state.expectedMaterialIds,...(result.materials||[])])];
    state.linksVerified=false;
    const note=state.failedUploads.length?`有 ${state.failedUploads.length} 份教材上傳失敗，可按重試。`:`已排入背景處理 ${result.uploaded} 份教材；請等到全部完成再前往下一步。`;
    state.resultHtml=`<span class="font-bold ${state.failedUploads.length?'text-amber-700':'text-sky-700'}">${state.failedUploads.length?'⚠️':'⏳'} ${esc(note)}</span><div id="cw681-background-jobs"></div>`;
    render();
    watchQueuedJobs(queuedIds());
  }catch(error){
    state.resultHtml=`<span class="font-bold text-rose-700">❌ ${esc(error.message)}</span>`;render();
  }finally{setBusy(false);}
}

async function createAndPublish(){
  const ready=await ensureCourseDraft();
  if(!ready)return;
  await publishAndOpenCourseWorkspace();
}

function recordAiProduct(detail={},kind='AI PowerPoint',derived=false){
  const materialId=String(detail.materialId||'').trim();
  const videoId=String(detail.videoId||'').trim();
  const key=materialId||(videoId?'video:'+videoId:'');
  if(!key)return;
  const existing=(state.aiProducts||[]).find(item=>String(item.key||item.materialId)===key);
  const product={key,materialId:derived&&!materialId?'':materialId,title:String(detail.title||kind),kind,presentationId:String(detail.presentationId||''),derived,linked:derived?true:Boolean(existing?.linked)};
  if(existing)Object.assign(existing,product);
  else state.aiProducts.push(product);
  if(state.step===2)render();
}

window.addEventListener('teacher-ai-presentation-published',event=>recordAiProduct(event.detail||{}));
window.addEventListener('teacher-ai-narration-published',event=>recordAiProduct(event.detail||{},'AI 講稿配音'));
window.addEventListener('teacher-ai-video-published',event=>recordAiProduct(event.detail||{},'AI 教學影片',true));

async function continueToAssessment(){
  if(!canLeaveCourse())return alert('新教材尚未全部完成處理。請等到所有教材顯示「已完成」後再前往下一步。');
  if(!state.categoryId)return openCourseWorkspace();
  state.watchToken++;
  if(typeof window.switchAdminWorkspace==='function')await window.AppWorkspaceRoutes.show('assessment',true);
  if(typeof window.renderAdminQuizCategories==='function')await window.renderAdminQuizCategories(true).catch(()=>{});
  const targets=[`qpanel-${state.categoryId}`,`qcard-${state.categoryId}`,`quiz-${state.categoryId}`];
  let target=null;for(const id of targets){target=el(id);if(target)break;}
  target?.classList.remove('hidden');target?.scrollIntoView({behavior:'smooth',block:'start'});
}

function publicationBlockerText(readiness){
  const blockers=Array.isArray(readiness?.blockers)?readiness.blockers:[];
  return blockers.length
    ? blockers.map(item=>'• '+String(item?.message||item?.code||'尚未完成')).join('\n')
    : '課程尚未符合發布條件。';
}

function publicationStatusNode(){
  const status=el('cw681-status');
  if(!status)return null;
  let box=el('cw681-publication-status');
  if(!box){
    box=document.createElement('div');
    box.id='cw681-publication-status';
    box.className='mb-2';
    status.prepend(box);
  }
  return box;
}

async function createWizardAssignment(courseId){
  if(!canAssignLearning()||!state.assignmentEnabled)return {skipped:true};
  const assigneeType=state.assigneeType||'group';
  const assigneeKey=assigneeType==='all'?'':(state.assigneeKey||(assigneeType==='group'?scope().group:''));
  if(assigneeType==='user'&&!assigneeKey)throw new Error('尚未選擇要指派的人員。');
  const response=await fetch('/api/learning-assignments',{
    method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({courseId,assigneeType,assigneeKey,required:state.assignmentRequired!==false,dueAt:state.dueAt||''})
  });
  const data=await response.json().catch(()=>({}));
  if(response.status===409&&data.code==='ASSIGNMENT_EXISTS')return {reused:true,data};
  if(response.status===401){loginRedirect();throw new Error('登入已逾時，請重新登入。');}
  if(response.status===403)throw new Error(data.error||'此帳號沒有建立學習指派的權限。');
  if(!response.ok)throw new Error(data.error||'課程已發布，但學習指派建立失敗。');
  return {created:true,data};
}

async function publishAndOpenCourseWorkspace(){
  if(state.publicationBusy)return;
  if(!canLeaveCourse())return alert('教材尚未正式完成。請等到所有教材完成並確認已掛入課程後再發布。');
  const courseId=String(state.course?.id||'');
  if(!courseId)return alert('找不到剛建立的課程，請重新整理課程清單後再試。');

  state.publicationBusy=true;
  syncCompletionControls();
  const publicationBox=publicationStatusNode();
  if(publicationBox)publicationBox.innerHTML='<div class="rounded-lg border border-emerald-200 bg-emerald-50 p-2 font-bold text-emerald-800">⏳ 正在檢查課程是否可發布…</div>';

  try{
    await verifyCreatedCourseMaterials();
    let readiness=await api('/api/courses/'+encodeURIComponent(courseId)+'/readiness');
    if(!readiness?.ready){
      const blocker=publicationBlockerText(readiness);
      if(publicationBox)publicationBox.innerHTML=`<div class="rounded-lg border border-amber-200 bg-amber-50 p-2 font-bold text-amber-900">⚠️ 尚未能正式發布<br>${esc(blocker).replace(/\n/g,'<br>')}</div>`;
      alert('目前還不能發布：\n'+blocker);
      return;
    }

    let lifecycle=String(readiness.lifecycleStatus||state.course?.lifecycleStatus||(state.course?.active?'published':'draft'));
    if(lifecycle==='draft'){
      const marked=await api('/api/courses/'+encodeURIComponent(courseId)+'/lifecycle',{
        method:'POST',
        body:JSON.stringify({action:'mark_ready'})
      });
      lifecycle=String(marked?.course?.lifecycleStatus||'ready');
    }
    if(lifecycle==='ready'){
      const published=await api('/api/courses/'+encodeURIComponent(courseId)+'/lifecycle',{
        method:'POST',
        body:JSON.stringify({action:'publish'})
      });
      const publishedCourse=published?.course||{};
      if(String(publishedCourse.lifecycleStatus||'')!=='published'||publishedCourse.active!==true){
        throw new Error('課程發布回應未確認為學員可見狀態，已停止返回流程。');
      }
      state.course={...state.course,...publishedCourse,lifecycleStatus:'published',active:true};
    }else if(lifecycle!=='published'){
      throw new Error('課程目前狀態為 '+lifecycle+'，不能由建立精靈直接發布。');
    }

    let assignmentResult={skipped:true};
    try{
      assignmentResult=await createWizardAssignment(courseId);
    }catch(error){
      if(publicationBox)publicationBox.innerHTML=`<div class="rounded-lg border border-amber-200 bg-amber-50 p-2 font-bold text-amber-900">⚠️ 課程已正式發布，但學習指派尚未完成：${esc(error.message||'建立失敗')}。請修正本頁設定後再次按發布，系統不會重複建立課程。</div>`;
      alert('課程已發布，但學習指派尚未完成：\n'+(error.message||'建立失敗'));
      return;
    }
    const assignmentNote=assignmentResult.created?'；學習指派已建立':assignmentResult.reused?'；既有學習指派已沿用':'';
    if(publicationBox)publicationBox.innerHTML=`<div class="rounded-lg border border-emerald-200 bg-emerald-50 p-2 font-bold text-emerald-800">✅ 課程已正式發布${assignmentNote}。</div>`;
    await refreshWorkspaceData();
    await openCourseWorkspace();
  }catch(error){
    if(publicationBox)publicationBox.innerHTML=`<div class="rounded-lg border border-rose-200 bg-rose-50 p-2 font-bold text-rose-700">❌ ${esc(error.message||'課程發布失敗')}</div>`;
    alert(error.message||'課程發布失敗');
  }finally{
    state.publicationBusy=false;
    syncCompletionControls();
  }
}

async function openCourseWorkspace(){
  if(state.publicationBusy)return;
  if(!canLeaveCourse())return alert('教材尚未正式完成。請留在此頁等待 Worker 完成，避免回到課程後看不到教材。');
  state.watchToken++;

  // The wizard is mounted inside Teacher Content Studio. Switching only the
  // underlying workspace leaves the studio visible and makes this button look inert.
  window.teacherContentStudioClose?.(false);
  if(typeof window.switchAdminWorkspace==='function')await window.AppWorkspaceRoutes.show('course-materials',true);
  if(typeof window.renderAdminCourseMaterialHub==='function')await window.renderAdminCourseMaterialHub(true).catch(()=>{});
  el('admin-course-material-hub')?.scrollIntoView({behavior:'smooth',block:'start'});

  // Do not leak a completed course into the next create-course flow.
  state.editing=false;state.step=1;state.files=[];state.fileMeta={};state.existing=[];state.examMode='later';state.aiPlan='none';state.assignmentEnabled=false;state.assigneeType='group';state.assigneeKey='';state.assignmentRequired=true;state.dueAt='';state.audienceOptions=null;
  state.course=null;state.categoryId='';state.materials=[];state.busy=false;state.publicationBusy=false;state.created=false;
  state.failedUploads=[];state.queuedJobs=[];state.queuedMaterialIds=[];state.expectedMaterialIds=[];state.linksVerified=false;state.expectedJobs=0;state.jobRows=[];
  state.jobEstimateSeconds=0;state.workerProtocolBlocked=false;state.completedMaterials=[];state.atlasCandidates={};state.aiProducts=[];state.resultHtml='';
  clearWorkflowId();
  render();
  loadMaterials();
}

function reset(){
  if(state.created&&!canLeaveCourse())return alert('目前教材尚未全部完成，請先等待或處理失敗工作。');
  state.watchToken++;
  state.editing=false;state.step=1;state.files=[];state.fileMeta={};state.existing=[];state.examMode='later';state.aiPlan='none';state.assignmentEnabled=false;state.assigneeType='group';state.assigneeKey='';state.assignmentRequired=true;state.dueAt='';state.audienceOptions=null;state.course=null;state.categoryId='';state.materials=[];state.busy=false;state.publicationBusy=false;state.created=false;state.failedUploads=[];state.queuedJobs=[];state.queuedMaterialIds=[];state.expectedMaterialIds=[];state.linksVerified=false;state.expectedJobs=0;state.jobRows=[];state.jobEstimateSeconds=0;state.workerProtocolBlocked=false;state.completedMaterials=[];state.atlasCandidates={};state.aiProducts=[];state.resultHtml='';clearWorkflowId();
  ['wizard-course-title','wizard-course-desc','wizard-exam-title'].forEach(id=>{if(el(id))el(id).value='';});
  render();loadMaterials();
}

window.courseWizard681HasPending=()=>Boolean(state.busy||(state.created&&!canLeaveCourse()));
window.courseWizard681PendingMessage=()=>state.busy&&!state.created
  ? '課程與教材正在建立／上傳中，請先不要離開此工作畫面。'
  : state.failedUploads.length
    ? '課程已建立，但仍有教材尚未完成。請先重試失敗教材或確認處理狀態。'
    : '課程已建立，教材仍在上傳／排隊／轉檔／發布中。請等到全部顯示「已完成」再離開。';

window.addEventListener('beforeunload',event=>{
  if(!window.courseWizard681HasPending())return;
  event.preventDefault();
  event.returnValue='';
});

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();