/* Teacher 6.9: guided course -> material -> exam flow using session RBAC. */
(function(){
'use strict';

const MODE_META={
  later:{label:'稍後建立',next:'課程建立後先回課程總覽，之後再補考卷。'},
  bank:{label:'從題庫選',next:'建立考卷後直接前往「題庫與考卷」加入既有題目。'},
  ai:{label:'AI 草稿',next:'建立考卷後直接前往「題庫與考卷」選教材並產生 AI 草稿。'},
  blueprint:{label:'Blueprint',next:'建立考卷後直接前往「題庫與考卷」設定 Blueprint 與題型配額。'}
};
const state={step:1,files:[],existing:[],examMode:'later',course:null,categoryId:'',materials:[],busy:false};
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
function setBusy(value){state.busy=!!value;const button=el('cw681-create');if(button){button.disabled=state.busy;button.textContent=state.busy?'⏳ 建立中…':'建立課程與關聯';}}

function mount(){
  const old=el('wizard-area')?.closest('.grid'),actions=el('wizard-create-btn')?.parentElement,host=el('admin-courses-list');
  if(!old||!host||el('course-wizard-681'))return;
  old.classList.add('hidden');actions?.classList.add('hidden');
  host.insertAdjacentHTML('beforebegin','<div id="course-wizard-681" class="space-y-4"></div>');
  window.courseWizard681Next=next;
  window.courseWizard681Back=back;
  window.courseWizard681SetMode=value=>{state.examMode=value;syncExamInput();render();};
  window.courseWizard681Create=create;
  window.courseWizard681RefreshMaterials=loadMaterials;
  window.courseWizard681SelectExisting=()=>{state.existing=[...document.querySelectorAll('.cw681-existing:checked')].map(x=>x.value);};
  window.courseWizard681FilesChanged=input=>{state.files=[...(input?.files||[])];renderFileSummary();};
  window.courseWizard681Continue=continueToAssessment;
  window.courseWizard681OpenCourse=openCourseWorkspace;
  window.courseWizard681Reset=reset;
  render();loadMaterials();
}

function render(){
  const root=el('course-wizard-681');if(!root)return;
  const steps=['基本資料','教材','題目與考卷','確認建立'];
  root.innerHTML=`<div class="flex flex-wrap gap-2">${steps.map((name,i)=>`<span class="rounded-full px-3 py-1 text-xs font-bold ${state.step===i+1?'bg-violet-700 text-white':state.step>i+1?'bg-violet-100 text-violet-800':'bg-slate-100 text-slate-500'}">${i+1} ${name}</span>`).join('')}</div><div class="rounded-xl border border-violet-200 bg-violet-50/30 p-4"><div id="cw681-step"></div><div class="mt-4 flex justify-between gap-2"><button ${state.step===1||state.busy?'disabled':''} onclick="courseWizard681Back()" class="rounded border px-4 py-2 text-sm disabled:opacity-40">返回</button>${state.step<4?`<button ${state.busy?'disabled':''} onclick="courseWizard681Next()" class="rounded bg-violet-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">下一步</button>`:`<button id="cw681-create" ${state.busy?'disabled':''} onclick="courseWizard681Create()" class="rounded bg-violet-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">${state.busy?'⏳ 建立中…':'建立課程與關聯'}</button>`}</div><div id="cw681-status" class="mt-3 text-xs text-violet-900"></div></div>`;
  const box=el('cw681-step');
  if(state.step===1)box.innerHTML=stepOne();
  if(state.step===2){box.innerHTML=stepTwo();paintMaterials();renderFileSummary();}
  if(state.step===3)box.innerHTML=stepThree();
  if(state.step===4)box.innerHTML=stepFour();
}

function stepOne(){
  const s=scope(),options=[...document.querySelectorAll('#wizard-group option')];
  return `<h5 class="font-black">1. 基本資料</h5><p class="mt-1 text-xs text-slate-500">先決定訓練區、組別與課程名稱；組長／臨床教師會自動鎖定自己的組別。</p><div class="mt-3 grid gap-3 md:grid-cols-2"><label class="text-xs font-bold">訓練區<select id="cw681-area" class="mt-1 w-full rounded border p-2"><option value="pgy" ${s.area==='pgy'?'selected':''}>PGY訓練區</option><option value="internal" ${s.area==='internal'?'selected':''}>內部教育訓練區</option></select></label><label class="text-xs font-bold">組別<select id="cw681-group" class="mt-1 w-full rounded border p-2">${options.map(o=>`<option value="${esc(o.value)}" ${o.value===s.group?'selected':''}>${esc(o.textContent)}</option>`).join('')}</select></label><label class="text-xs font-bold md:col-span-2">課程名稱<input id="cw681-title" value="${esc(el('wizard-course-title')?.value||'')}" class="mt-1 w-full rounded border p-2" placeholder="例如：血液鏡檢基礎訓練"></label><label class="text-xs font-bold md:col-span-2">課程說明<textarea id="cw681-desc" class="mt-1 w-full rounded border p-2" placeholder="學習目標、適用對象或完成條件">${esc(el('wizard-course-desc')?.value||'')}</textarea></label></div>`;
}

function stepTwo(){
  return `<h5 class="font-black">2. 教材</h5><p class="mt-1 text-xs text-slate-500">可同時上傳新教材並掛入既有教材；檔案會在最後確認後才送出。</p><div class="mt-3 grid gap-4 lg:grid-cols-2"><div><label class="block text-xs font-bold">上傳新教材<input id="cw681-files" type="file" multiple class="mt-1 w-full text-sm" onchange="courseWizard681FilesChanged(this)"></label><div id="cw681-file-summary" class="mt-2 text-xs text-slate-500"></div></div><div><div class="flex justify-between"><b class="text-xs">既有教材</b><button type="button" onclick="courseWizard681RefreshMaterials()" class="text-xs text-violet-700">更新</button></div><div id="cw681-materials" class="mt-2 max-h-48 overflow-auto rounded border bg-white p-2 text-xs">讀取中…</div></div></div><p class="mt-3 text-xs text-violet-800">外部連結請先用「＋新增單一教材 → 外部連結」建立，之後可在這裡直接掛入課程。</p>`;
}

function stepThree(){
  return `<h5 class="font-black">3. 題目與考卷</h5><p class="mt-1 text-xs text-slate-500">先決定建立後要接到哪一種出題流程；系統只建立考卷骨架，不會把未審題目直接發布。</p><div class="mt-3 grid gap-2 md:grid-cols-2">${Object.entries(MODE_META).map(([id,meta])=>`<button type="button" onclick="courseWizard681SetMode('${id}')" class="rounded border p-3 text-left text-sm ${state.examMode===id?'border-violet-500 bg-violet-100':'bg-white'}"><b>${esc(meta.label)}</b><span class="block mt-1 text-xs text-slate-500">${esc(meta.next)}</span></button>`).join('')}</div><label class="mt-4 block text-xs font-bold">考卷名稱${state.examMode==='later'?'（可留白）':'（必填）'}<input id="cw681-exam" value="${esc(el('wizard-exam-title')?.value||'')}" class="mt-1 w-full rounded border p-2" placeholder="例如：課後評量"></label>`;
}

function stepFour(){
  const s=scope(),title=el('wizard-course-title')?.value||'',desc=el('wizard-course-desc')?.value||'',exam=el('wizard-exam-title')?.value||'';
  return `<h5 class="font-black">4. 確認建立</h5><div class="mt-3 rounded-xl border border-violet-100 bg-white p-4"><dl class="grid gap-3 text-sm md:grid-cols-2"><div><dt class="text-xs text-slate-500">課程</dt><dd class="font-bold">${esc(title||'（未填）')}</dd></div><div><dt class="text-xs text-slate-500">範圍</dt><dd>${esc(s.area)} · ${esc(el('wizard-group')?.selectedOptions?.[0]?.textContent||s.group)}</dd></div><div class="md:col-span-2"><dt class="text-xs text-slate-500">說明</dt><dd>${esc(desc||'—')}</dd></div><div><dt class="text-xs text-slate-500">教材</dt><dd>新上傳 ${state.files.length} 份；既有關聯 ${state.existing.length} 份</dd></div><div><dt class="text-xs text-slate-500">出題流程</dt><dd class="font-bold">${esc(mode().label)}${exam?' · '+esc(exam):''}</dd></div><div class="md:col-span-2"><dt class="text-xs text-slate-500">既有教材</dt><dd>${state.existing.map(id=>esc((state.materials||[]).find(m=>String(m.id)===String(id))?.title||id)).join('、')||'—'}</dd></div></dl><p class="mt-3 rounded-lg bg-violet-50 px-3 py-2 text-xs text-violet-800">建立完成後：${esc(mode().next)}</p></div>`;
}

function renderFileSummary(){
  const box=el('cw681-file-summary');if(!box)return;
  box.innerHTML=state.files.length?`已選 ${state.files.length} 份：${state.files.map(f=>esc(f.name)).join('、')}`:'尚未選擇新檔案。';
}

function paintMaterials(){
  const box=el('cw681-materials');if(!box)return;
  if(!state.materials.length){box.textContent='沒有可用教材';return;}
  box.innerHTML=state.materials.map(m=>`<label class="block rounded px-1 py-1 hover:bg-violet-50"><input class="cw681-existing" onchange="courseWizard681SelectExisting()" type="checkbox" value="${esc(m.id)}" ${state.existing.includes(String(m.id))?'checked':''}> ${esc(m.title||m.filename||m.id)}</label>`).join('');
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
  }
  if(state.step===3)syncExamInput();
}

function next(){
  if(state.busy)return;
  if(state.step===2){state.files=[...(el('cw681-files')?.files||state.files)];state.existing=[...document.querySelectorAll('.cw681-existing:checked')].map(x=>x.value);}
  syncInputs();
  if(state.step===1&&!String(el('wizard-course-title')?.value||'').trim())return alert('請輸入課程名稱');
  if(state.step===3&&state.examMode!=='later'&&!String(el('wizard-exam-title')?.value||'').trim())return alert('請輸入考卷名稱，或改選「稍後建立」。');
  state.step=Math.min(4,state.step+1);render();
  if(state.step===2)loadMaterials();
}

function back(){if(state.busy)return;syncInputs();state.step=Math.max(1,state.step-1);render();if(state.step===2)loadMaterials();}

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

async function create(){
  if(state.busy)return;
  syncInputs();
  const {area,group}=scope(),title=String(el('wizard-course-title')?.value||'').trim(),desc=String(el('wizard-course-desc')?.value||'').trim(),exam=String(el('wizard-exam-title')?.value||'').trim(),files=state.files;
  if(!title)return alert('請輸入課程名稱');
  if(state.examMode!=='later'&&!exam)return alert('請輸入考卷名稱，或改選「稍後建立」。');
  const status=el('cw681-status');setBusy(true);
  try{
    status.textContent='⏳ 建立課程…';
    const course=await api('/api/courses',{method:'POST',body:JSON.stringify({area,group,title,desc})});
    state.course=course;state.categoryId='';
    if(state.examMode!=='later'){
      status.textContent='⏳ 建立並連結考卷…';
      const category=await api('/api/quiz-categories',{method:'POST',body:JSON.stringify({area,group,title:exam,desc:`${title} 課後評量`,courseId:course.id})});
      state.categoryId=String(category.id||'');
    }
    let linked=0;
    for(const id of state.existing){
      const material=state.materials.find(m=>String(m.id)===String(id));if(!material)continue;
      status.textContent=`⏳ 關聯既有教材 ${linked+1}/${state.existing.length}…`;
      await api('/api/slides/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({title:material.title||material.filename||'',desc:material.desc||'',courseId:course.id,category:state.categoryId||material.category||'',active:material.active!==false,group,area,materialType:material.materialType||'standard',atlasMeta:material.atlasMeta||{}})});linked++;
    }
    let uploaded=0;
    for(const file of files){
      status.textContent=`⏳ 上傳新教材 ${uploaded+1}/${files.length}：${file.name}`;
      const form=new FormData();form.append('file',file);form.append('title',file.name.replace(/\.[^.]+$/,''));form.append('desc',desc);form.append('group',group);form.append('area',area);form.append('courseId',course.id);form.append('category',state.categoryId);form.append('materialType','auto');
      await api('/api/slides/upload',{method:'POST',body:form});uploaded++;
    }
    status.textContent='⏳ 同步課程、教材與考卷清單…';await refreshWorkspaceData();
    const nextButton=state.categoryId?'<button type="button" onclick="courseWizard681Continue()" class="ml-2 rounded-lg bg-violet-700 px-3 py-1.5 font-bold text-white">前往題庫與考卷 →</button>':'<button type="button" onclick="courseWizard681OpenCourse()" class="ml-2 rounded-lg bg-teal-700 px-3 py-1.5 font-bold text-white">查看課程總覽 →</button>';
    status.innerHTML=`<span class="font-bold text-emerald-700">✅ 「${esc(title)}」建立完成。</span> 已關聯 ${linked} 份既有教材、上傳 ${uploaded} 份新教材${state.categoryId?'，並建立考卷「'+esc(exam)+'」':''}。${nextButton}<button type="button" onclick="courseWizard681Reset()" class="ml-2 text-slate-500 underline">建立下一門課</button>`;
  }catch(error){status.textContent='❌ '+error.message;}
  finally{setBusy(false);}
}

async function continueToAssessment(){
  if(!state.categoryId)return openCourseWorkspace();
  if(typeof window.switchAdminWorkspace==='function')await window.switchAdminWorkspace('assessment',true);
  if(typeof window.renderAdminQuizCategories==='function')await window.renderAdminQuizCategories(true).catch(()=>{});
  const targets=[`qpanel-${state.categoryId}`,`qcard-${state.categoryId}`,`quiz-${state.categoryId}`];
  let target=null;for(const id of targets){target=el(id);if(target)break;}
  target?.classList.remove('hidden');target?.scrollIntoView({behavior:'smooth',block:'start'});
}

async function openCourseWorkspace(){
  if(typeof window.switchAdminWorkspace==='function')await window.switchAdminWorkspace('course-materials',true);
  if(typeof window.renderAdminCourseMaterialHub==='function')await window.renderAdminCourseMaterialHub(true).catch(()=>{});
  el('admin-course-material-hub')?.scrollIntoView({behavior:'smooth',block:'start'});
}

function reset(){
  state.step=1;state.files=[];state.existing=[];state.examMode='later';state.course=null;state.categoryId='';state.materials=[];state.busy=false;
  ['wizard-course-title','wizard-course-desc','wizard-exam-title'].forEach(id=>{if(el(id))el(id).value='';});
  render();loadMaterials();
}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
