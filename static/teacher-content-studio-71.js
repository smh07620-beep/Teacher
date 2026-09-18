/* Teacher 7.1: task-first content authoring hub for teaching roles.
 * This is a presentation/orchestration layer only. It routes teachers into the
 * existing canonical exam, question, material, external-media and Atlas flows;
 * server-side RBAC remains authoritative for every mutation.
 */
(function(){
  'use strict';

  const esc = value => (window.escapeHtml ? window.escapeHtml(String(value ?? '')) : String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const rbac = () => window.TeacherRBAC681 || {};
  const has = permission => typeof rbac().hasPermission === 'function' ? !!rbac().hasPermission(permission) : false;
  const canQuestion = () => has('question.manage') || has('exam.manage');
  const canMaterial = () => has('material.manage') || has('course.manage');
  const canCourse = () => has('course.manage');
  const canOpen = () => canQuestion() || canMaterial();
  const studioId = 'teacher-content-studio-71';
  const launcherId = 'teacher-content-studio-launcher-71';
  const aiMount = {section:null, placeholder:null, catId:''};
  const courseMount = {root:null, placeholder:null};
  const materialHubMount = {root:null, placeholder:null};

  function scope(){
    return {
      area: document.getElementById('admin-quiz-area')?.value || document.getElementById('admin-material-area')?.value || window.currentTrainingArea || 'internal',
      group: document.getElementById('admin-quiz-group')?.value || document.getElementById('admin-material-group')?.value || window.currentGroupKey || 'grpBio',
    };
  }

  function setSelectByValueOrText(select, wanted){
    if(!select) return false;
    const options = [...select.options];
    let option = options.find(o => o.value === wanted);
    if(!option && wanted === 'video') option = options.find(o => String(o.value).startsWith('video_')) || options.find(o => /影片|影音/.test(o.textContent || ''));
    if(!option && wanted === 'image') option = options.find(o => o.value === 'image') || options.find(o => /圖片/.test(o.textContent || ''));
    if(!option && wanted === 'standard') option = options.find(o => ['standard','file','document'].includes(o.value)) || options.find(o => /一般|教材|文件/.test(o.textContent || ''));
    if(!option && wanted === 'video-material') option = options.find(o => ['video','media'].includes(o.value)) || options.find(o => /影音|影片/.test(o.textContent || ''));
    if(!option) return false;
    select.value = option.value;
    select.dispatchEvent(new Event('change', {bubbles:true}));
    return true;
  }

  function card(action, icon, title, desc, tone='indigo'){
    return `<button type="button" data-studio-action="${esc(action)}" class="group text-left rounded-2xl border border-slate-200 bg-white p-4 hover:border-${tone}-300 hover:shadow-md transition"><div class="flex items-start gap-3"><span class="text-2xl" aria-hidden="true">${icon}</span><span class="min-w-0"><span class="block font-black text-slate-900">${esc(title)}</span><span class="mt-1 block text-xs leading-5 text-slate-500">${esc(desc)}</span></span></div></button>`;
  }

  function baseBody(){
    const questionCards = canQuestion() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📝 出題與考核</h4><p class="text-xs text-slate-500 mt-1">先管理考卷；選定考卷後才建立或管理題目。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('exam','📋','考卷管理','管理既有考卷、建立新考卷，並在考卷內加入一般題、圖片題、影片題或 AI 題。','indigo')}
        </div>
      </section>` : '';
    const materialCards = canMaterial() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📚 教材與課程</h4><p class="text-xs text-slate-500 mt-1">先進入課程容器，再管理教材、影音、圖譜與對應考卷。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('materials-manager','📚','教材與課程管理','管理既有課程與教材；新增內容先從課程開始，避免未歸類教材持續增加。','teal')}
        </div>
      </section>` : '';
    return `<div class="space-y-6">${questionCards}${materialCards}</div>`;
  }

  function ensureStudio(){
    let root = document.getElementById(studioId);
    if(root) return root;
    root = document.createElement('div');
    root.id = studioId;
    root.className = 'hidden fixed inset-0 z-[140] bg-slate-950/55 backdrop-blur-sm overflow-y-auto p-3 sm:p-6';
    root.innerHTML = `<div class="mx-auto max-w-5xl rounded-3xl bg-slate-50 shadow-2xl border border-white/60 overflow-hidden"><div class="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur"><div><p class="text-xs font-black tracking-wide text-teal-700">TEACHER CONTENT STUDIO</p><h3 class="text-xl font-black text-slate-950 mt-1">＋ 建立教學內容</h3><p class="text-xs text-slate-500 mt-1">選擇要完成的工作；進階欄位只在需要時才出現。</p></div><button type="button" data-studio-close class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-bold text-slate-600 hover:bg-slate-50">關閉</button></div><div id="teacher-content-studio-body-71" class="p-5 sm:p-6"></div></div>`;
    document.body.appendChild(root);
    root.addEventListener('click', event => {
      const close = event.target.closest('[data-studio-close]');
      if(close){ closeStudio(); return; }
      const action = event.target.closest('[data-studio-action]')?.dataset.studioAction;
      if(action) launch(action);
      const examOpen = event.target.closest('[data-exam-open]');
      if(examOpen){ renderExamContainer(examOpen.dataset.examOpen); return; }
      if(event.target.closest('[data-exam-create-open]')){ renderCreateExam(); return; }
      if(event.target.closest('[data-exam-create-submit]')){ createExamFromStudio(); return; }
      const examAction = event.target.closest('[data-exam-action]');
      if(examAction){ dispatchExamAction(examAction.dataset.examAction, examAction.dataset.examId); return; }
      if(event.target.closest('[data-course-studio-back]')){ restoreCourseWizard(); renderHome(); return; }
      const back = event.target.closest('[data-studio-back]');
      if(back) renderHome();
      const confirmQuestion = event.target.closest('[data-studio-question-confirm]');
      if(confirmQuestion) confirmQuestionPreset(confirmQuestion.dataset.preset || 'choice');
      const confirmAi = event.target.closest('[data-studio-ai-confirm]');
      if(confirmAi) mountAiPanel(document.getElementById('teacher-studio-ai-exam-75')?.value || '');
    });
    root.addEventListener('click', event => { if(event.target === root) closeStudio(); });
    return root;
  }

  function renderHome(){
    restoreAiPanel();
    restoreCourseWizard();
    restoreMaterialHub();
    const body = document.getElementById('teacher-content-studio-body-71');
    if(body) body.innerHTML = baseBody();
  }

  function openStudio(){
    if(!canOpen()) return;
    const root = ensureStudio();
    renderHome();
    root.classList.remove('hidden');
    document.body.dataset.teacherContentStudioOpen = '1';
  }

  function closeStudio(){
    restoreAiPanel();
    restoreCourseWizard();
    restoreMaterialHub();
    document.getElementById(studioId)?.classList.add('hidden');
    delete document.body.dataset.teacherContentStudioOpen;
  }

  async function loadCategories(){
    const {area, group} = scope();
    const response = await fetch(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`, {credentials:'same-origin'});
    const data = await response.json().catch(() => []);
    if(!response.ok) throw new Error(data.error || '無法讀取考卷清單');
    return Array.isArray(data) ? data : [];
  }

  function timeout77(promise,ms,label){
    return Promise.race([
      Promise.resolve(promise),
      new Promise((_,reject)=>setTimeout(()=>reject(new Error(`${label}逾時，請重新嘗試。`)),ms))
    ]);
  }

  function aiPrepare77(host,label,detail=''){
    if(!host)return;
    host.innerHTML=`<div class="rounded-2xl border border-violet-100 bg-violet-50 p-5"><div class="text-sm font-black text-violet-800">${esc(label)}</div>${detail?`<div class="mt-1 text-xs text-violet-600">${esc(detail)}</div>`:''}<div class="mt-3 h-1.5 overflow-hidden rounded-full bg-violet-100"><div class="h-full w-1/2 animate-pulse rounded-full bg-violet-500"></div></div></div>`;
  }

  async function prepareAssessment77(selectedScope=scope(),force=false){
    if(!document.getElementById('admin-quiz-categories-list')){
      await timeout77(window.openAdminWorkspace?.('assessment'),2200,'切換考卷管理');
    }
    const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');
    if(area)area.value=selectedScope.area;
    if(group)group.value=selectedScope.group;
    if(force) await timeout77(window.renderAdminQuizCategories?.(true),2800,'讀取考卷');
    return selectedScope;
  }

  async function renderExamManager(message=''){
    restoreAiPanel(); restoreCourseWizard();
    const host=document.getElementById('teacher-content-studio-body-71'); if(!host)return;
    host.innerHTML='<p class="text-sm text-slate-500">正在讀取考卷…</p>';
    try{
      const categories=await loadCategories();
      host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="flex items-start justify-between gap-3 flex-wrap"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回建立首頁</button><h4 class="mt-2 text-xl font-black text-slate-950">📋 考卷管理</h4><p class="mt-1 text-xs text-slate-500">先選考卷，再在該考卷內建立與管理題目。</p></div><button type="button" data-exam-create-open class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-black text-white">＋ 建立考卷</button></div>${message?`<div class="mt-4 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">${esc(message)}</div>`:''}<div class="mt-5 grid gap-3">${categories.length?categories.map(c=>`<button type="button" data-exam-open="${esc(c.id)}" class="w-full rounded-2xl border border-slate-200 bg-white p-4 text-left hover:border-indigo-300 hover:shadow-sm"><div class="flex items-center justify-between gap-3"><div class="min-w-0"><div class="font-black text-slate-900">${esc(c.title||c.id)}</div><div class="mt-1 text-xs text-slate-500">${esc(c.desc||'尚未填寫考卷說明')}</div></div><span class="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-bold text-indigo-700">題庫 ${Number(c.questionCount||0)} 題</span></div></button>`).join(''):'<div class="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">目前還沒有考卷。請先建立第一份考卷。</div>'}</div></div>`;
    }catch(error){host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3"><button type="button" data-studio-action="exam" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">重新讀取</button></div></div>`;}
  }

  function renderCreateExam(){
    const host=document.getElementById('teacher-content-studio-body-71'); if(!host)return;
    host.innerHTML=`<div class="mx-auto max-w-2xl"><button type="button" data-studio-action="exam" class="text-sm font-bold text-slate-500">← 返回考卷管理</button><div class="mt-4 rounded-2xl border border-indigo-200 bg-white p-5"><div class="text-xs font-black tracking-wide text-indigo-700">建立新考卷</div><h4 class="mt-1 text-lg font-black text-slate-950">先建立考卷容器</h4><p class="mt-1 text-xs leading-5 text-slate-500">建立後再進入考卷加入一般題、圖片題、影片題或 AI 題。</p><label class="mt-4 block text-sm font-bold text-slate-700">考卷名稱<input id="teacher77-exam-title" maxlength="120" class="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm" placeholder="例如：2026 生化組基礎訓練考核"></label><div id="teacher77-exam-create-status" class="mt-2 text-xs text-slate-500"></div><div class="mt-5 flex justify-end gap-2"><button type="button" data-studio-action="exam" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button type="button" data-exam-create-submit class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-black text-white">建立考卷</button></div></div></div>`;
    setTimeout(()=>document.getElementById('teacher77-exam-title')?.focus(),50);
  }

  async function createExamFromStudio(){
    const title=document.getElementById('teacher77-exam-title')?.value.trim()||'';
    const status=document.getElementById('teacher77-exam-create-status');
    if(!title){if(status)status.textContent='請輸入考卷名稱。';return;}
    const selectedScope=scope();
    try{
      if(status)status.textContent='⏳ 建立考卷中…';
      await prepareAssessment77(selectedScope,false);
      const titleInput=document.getElementById('admin-new-category-title');
      if(!titleInput)throw new Error('考卷建立器尚未載入');
      titleInput.value=title;
      await timeout77(window.adminCreateQuizCategory?.(),3500,'建立考卷');
      await renderExamManager(`已建立「${title}」，請進入考卷加入題目。`);
    }catch(error){if(status)status.textContent=`❌ ${error.message}`;}
  }

  async function renderExamContainer(catId){
    if(!catId)return renderExamManager();
    restoreAiPanel(); restoreCourseWizard();
    const host=document.getElementById('teacher-content-studio-body-71'); if(!host)return;
    host.innerHTML='<p class="text-sm text-slate-500">正在開啟考卷…</p>';
    try{
      const categories=await loadCategories(); const exam=categories.find(c=>String(c.id)===String(catId));
      if(!exam)throw new Error('找不到此考卷，可能已被移除。');
      host.innerHTML=`<div class="mx-auto max-w-4xl"><button type="button" data-studio-action="exam" class="text-sm font-bold text-slate-500">← 返回考卷管理</button><div class="mt-4 rounded-2xl border border-indigo-200 bg-white p-5"><div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black tracking-wide text-indigo-700">目前考卷</div><h4 class="mt-1 text-xl font-black text-slate-950">${esc(exam.title||catId)}</h4><p class="mt-1 text-xs text-slate-500">所有出題動作都直接加入這份考卷，不需要再次選考卷。</p></div><span class="rounded-full bg-indigo-50 px-3 py-1 text-xs font-bold text-indigo-700">題庫 ${Number(exam.questionCount||0)} 題</span></div><div class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><button type="button" data-exam-action="question" data-exam-id="${esc(catId)}" class="rounded-xl border border-slate-200 p-4 text-left hover:border-indigo-300"><b>✏️ 一般考題</b><span class="mt-1 block text-xs text-slate-500">手動建立一般題目。</span></button><button type="button" data-exam-action="image" data-exam-id="${esc(catId)}" class="rounded-xl border border-slate-200 p-4 text-left hover:border-rose-300"><b>🖼️ 圖片判讀題</b><span class="mt-1 block text-xs text-slate-500">圖片、顯微鏡或血球判讀。</span></button><button type="button" data-exam-action="video" data-exam-id="${esc(catId)}" class="rounded-xl border border-slate-200 p-4 text-left hover:border-violet-300"><b>🎬 影片互動題</b><span class="mt-1 block text-xs text-slate-500">依影片流程建立互動題。</span></button><button type="button" data-exam-action="ai" data-exam-id="${esc(catId)}" class="rounded-xl border border-violet-200 bg-violet-50/40 p-4 text-left hover:border-violet-400"><b>✨ AI 輔助出題</b><span class="mt-1 block text-xs text-slate-500">自動讀取本考卷關聯教材，再選用途與題數。</span></button><button type="button" data-exam-action="questions" data-exam-id="${esc(catId)}" class="rounded-xl border border-slate-200 p-4 text-left hover:border-teal-300"><b>🧠 題目管理</b><span class="mt-1 block text-xs text-slate-500">搜尋、編輯與批次管理既有題目。</span></button><button type="button" data-exam-action="settings" data-exam-id="${esc(catId)}" class="rounded-xl border border-slate-200 p-4 text-left hover:border-slate-400"><b>⚙️ 考卷設定</b><span class="mt-1 block text-xs text-slate-500">抽題、及格分數、審核與發布。</span></button></div></div></div>`;
    }catch(error){host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3"><button type="button" data-studio-action="exam" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">返回考卷管理</button></div></div>`;}
  }

  function showExamActionFailure(catId,error){
    const root=ensureStudio();
    const host=document.getElementById('teacher-content-studio-body-71');
    root?.classList.remove('hidden');
    if(root)document.body.dataset.teacherContentStudioOpen='1';
    if(!host)return;
    host.innerHTML=`<div class="mx-auto max-w-4xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700"><div class="font-black">❌ 考卷功能暫時無法開啟</div><div class="mt-1">${esc(error?.message||String(error||'未知錯誤'))}</div><div class="mt-4 flex gap-2 flex-wrap"><button type="button" data-exam-open="${esc(catId)}" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 返回此考卷</button><button type="button" data-studio-action="exam" class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回考卷管理</button></div></div>`;
  }

  const examActionHandlers=new Map();

  function registerExamActions(actions,handler){
    if(typeof handler!=='function')return;
    (Array.isArray(actions)?actions:[actions]).forEach(action=>examActionHandlers.set(String(action),handler));
  }

  function dispatchExamAction(action,catId){
    const handler=examActionHandlers.get(String(action));
    try{
      const result=handler?handler(action,catId):runExamAction(action,catId);
      Promise.resolve(result).catch(error=>showExamActionFailure(catId,error));
    }catch(error){
      showExamActionFailure(catId,error);
    }
  }
  async function runExamAction(action,catId){
    if(action==='question')return confirmQuestionPreset('choice',catId);
    if(action==='image')return confirmQuestionPreset('image',catId);
    if(action==='video')return confirmQuestionPreset('video',catId);
    if(action==='ai')return mountAiPanel(catId);
    const selectedScope=scope();
    closeStudio();
    await prepareAssessment77(selectedScope,true);
    if(action==='settings')return window.adminEditQuizCategory?.(catId);
    if(action==='questions'){
      const panel=document.getElementById(`qpanel-${catId}`);
      if(panel?.classList.contains('hidden'))await window.toggleQuizQuestionsPanel?.(catId);
      panel?.scrollIntoView({behavior:'smooth',block:'start'});
    }
  }

  function restoreMaterialHub(){
    if(!materialHubMount.root)return;
    if(materialHubMount.placeholder?.isConnected)materialHubMount.placeholder.replaceWith(materialHubMount.root);
    else materialHubMount.root.remove();
    materialHubMount.root=null; materialHubMount.placeholder=null;
  }

  async function mountMaterialManagerInStudio(){
    restoreAiPanel();restoreCourseWizard();restoreMaterialHub();
    const host=document.getElementById('teacher-content-studio-body-71');if(!host)return;
    host.innerHTML='<div class="rounded-2xl border border-teal-100 bg-teal-50 p-5 text-sm text-teal-700">正在整理課程與教材…</div>';
    try{
      let root=document.getElementById('admin-course-material-hub');
      if(!root){await timeout77(window.openAdminWorkspace?.('course-materials'),2200,'開啟教材與課程管理');root=await waitFor77('#admin-course-material-hub',2400);}
      if(!root)throw new Error('教材與課程管理尚未載入，請重新嘗試。');
      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher78MaterialHubPlaceholder='1';root.before(placeholder);materialHubMount.root=root;materialHubMount.placeholder=placeholder;
      host.innerHTML=`<div class="mx-auto max-w-5xl"><div class="mb-4 flex items-start justify-between gap-3 flex-wrap"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回建立首頁</button><h4 class="mt-2 text-xl font-black text-slate-950">📚 教材與課程管理</h4><p class="mt-1 text-xs text-slate-500">先選課程，再管理該課程的教材與考卷；未歸類內容只保留作為整理入口。</p></div>${canCourse()?'<button type="button" data-studio-action="course" class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">＋ 建立課程</button>':''}</div><div data-material-refresh-status-79 class="mb-3 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-xs text-teal-700">正在背景更新課程與教材…</div><div data-material-hub-host-78></div></div>`;
      host.querySelector('[data-material-hub-host-78]')?.appendChild(root);
      const refreshStatus=host.querySelector('[data-material-refresh-status-79]');
      timeout77(window.renderAdminCourseMaterialHub?.(false),8000,'更新課程與教材').then(()=>refreshStatus?.remove()).catch(error=>{if(refreshStatus){refreshStatus.className='mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700';refreshStatus.textContent=`⚠️ ${error.message}；目前畫面仍可使用，可稍後按更新重試。`;}});
    }catch(error){restoreMaterialHub();host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3 flex gap-2"><button type="button" data-studio-action="materials-manager" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;}
  }

  function restoreCourseWizard(){
    if(!courseMount.root)return;
    if(courseMount.placeholder?.isConnected)courseMount.placeholder.replaceWith(courseMount.root);
    else courseMount.root.remove();
    courseMount.root=null; courseMount.placeholder=null;
  }

  async function waitFor77(selector,ms=2600){
    const started=Date.now();
    while(Date.now()-started<ms){const node=document.querySelector(selector);if(node)return node;await new Promise(r=>setTimeout(r,80));}
    return null;
  }

  async function mountCourseWizardInStudio(){
    restoreAiPanel(); restoreCourseWizard(); restoreMaterialHub();
    const host=document.getElementById('teacher-content-studio-body-71'); if(!host)return;
    const selectedScope=scope();
    host.innerHTML='<div class="rounded-2xl border border-violet-100 bg-violet-50 p-5 text-sm text-violet-700">正在準備課程建立流程…</div>';
    try{
      let root=document.getElementById('course-wizard-681');
      if(!root){
        await timeout77(window.openAdminWorkspace?.('course-materials'),2200,'開啟課程建立器');
        root=await waitFor77('#course-wizard-681',2400);
      }
      if(!root)throw new Error('課程建立器尚未載入，請重新嘗試。');
      const area=document.getElementById('wizard-area'),group=document.getElementById('wizard-group');
      if(area)area.value=selectedScope.area;
      if(group)group.value=selectedScope.group;
      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher77CoursePlaceholder='1';root.before(placeholder);
      courseMount.root=root;courseMount.placeholder=placeholder;
      host.innerHTML='<div class="mx-auto max-w-4xl"><div class="mb-4"><button type="button" data-course-studio-back class="text-sm font-bold text-slate-500">← 返回建立首頁</button><h4 class="mt-2 text-xl font-black text-slate-950">🪄 建立課程</h4><p class="mt-1 text-xs text-slate-500">課程、教材與考卷都在這個建立視窗完成，不會跳離目前工作。</p></div><div data-course-wizard-host-77></div></div>';
      host.querySelector('[data-course-wizard-host-77]')?.appendChild(root);
      requestAnimationFrame(()=>root.scrollIntoView({behavior:'smooth',block:'start'}));
    }catch(error){restoreCourseWizard();host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3 flex gap-2"><button type="button" data-studio-action="course" class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;}
  }


  function restoreAiPanel(){
    const section = aiMount.section;
    if(!section) return;
    const placeholder = aiMount.placeholder;
    const panel = document.getElementById(`qpanel-${aiMount.catId}`);
    if(placeholder?.isConnected) placeholder.replaceWith(section);
    else if(panel) panel.appendChild(section);
    else section.remove();
    aiMount.section = null;
    aiMount.placeholder = null;
    aiMount.catId = '';
  }

  const AI_PRESETS_76 = {
    auto: {label:'自動均衡', type:'mixed_all', count:5, difficulty:'standard', strategy:'auto', focus:'依教材重點自動配置單選、多選、填空與問答題。'},
    newcomer: {label:'新人基礎考核', type:'mixed_choice_multi', count:10, difficulty:'basic', strategy:'balanced', focus:'以基礎概念、流程與常見注意事項為主；單選題為主，多選題少量，避免過度刁鑽。'},
    pgy: {label:'PGY 核心能力', type:'mixed_all', count:10, difficulty:'standard', strategy:'balanced', focus:'涵蓋核心知識、操作判斷、臨床情境與反思；混合單選、多選、填空與問答。'},
    case: {label:'案例判讀', type:'mixed', count:5, difficulty:'advanced', strategy:'scenario', focus:'以案例資訊整合、判讀依據與下一步處置為主；情境單選與問答混合。'},
    quality: {label:'品質管理／異常處理', type:'mixed_all', count:10, difficulty:'standard', strategy:'safety', focus:'聚焦 QC、異常辨識、故障排除、通報與病人安全；混合單選、多選與問答。'},
    advanced: {label:'進階組內訓練', type:'mixed_all', count:10, difficulty:'advanced', strategy:'scenario', focus:'提高多步推理與情境整合比例，增加多選與問答，避免只考記憶。'},
    image: {label:'圖片判讀', type:'choice', count:5, difficulty:'standard', strategy:'recognition', focus:'優先根據圖片／Atlas 視覺證據出題，要求辨識特徵與判讀依據。'},
    video: {label:'影片互動', type:'video_mixed', count:5, difficulty:'standard', strategy:'workflow', focus:'依影片流程與關鍵操作時間點設計互動題，混合選擇、填空與問答。'},
  };

  function setAiControl76(catId, name, value){
    const el=document.getElementById(`ai-${name}-${catId}`); if(!el) return false;
    if(el.tagName==='SELECT' && ![...el.options].some(o=>String(o.value)===String(value))){
      const option=document.createElement('option'); option.value=String(value); option.textContent=String(value); el.appendChild(option);
    }
    el.value=String(value); el.dispatchEvent(new Event('change',{bubbles:true})); return true;
  }

  function applyAiPreset76(catId,key){
    const preset=AI_PRESETS_76[key]||AI_PRESETS_76.auto;
    setAiControl76(catId,'type',preset.type); setAiControl76(catId,'count',preset.count); setAiControl76(catId,'difficulty',preset.difficulty); setAiControl76(catId,'strategy',preset.strategy);
    const focus=document.getElementById(`ai-focus-${catId}`); if(focus) focus.value=preset.focus;
    const note=document.querySelector(`[data-ai-preset-note-76="${CSS.escape(String(catId))}"]`); if(note) note.textContent=`${preset.label}：${preset.focus}`;
    const custom=document.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`); custom?.classList.add('hidden');
  }

  function applyAiCustomMix76(catId){
    const root=document.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`); if(!root) return;
    const counts={choice:0,multi:0,fill:0,essay:0};
    Object.keys(counts).forEach(type=>{counts[type]=Math.max(0,Number(root.querySelector(`[data-mix-type="${type}"]`)?.value||0));});
    const active=Object.entries(counts).filter(([,n])=>n>0),total=active.reduce((sum,[,n])=>sum+n,0);
    if(!total){alert('請至少設定一種題型的題數');return;}
    let type='mixed_all';
    if(active.length===1) type=active[0][0];
    else if(active.every(([t])=>['choice','multi'].includes(t))) type='mixed_choice_multi';
    else if(active.every(([t])=>['choice','essay'].includes(t))) type='mixed';
    setAiControl76(catId,'type',type); setAiControl76(catId,'count',total);
    const labels={choice:'單選',multi:'多選',fill:'填空',essay:'問答'};
    const request=active.map(([t,n])=>`${labels[t]} ${n} 題`).join('、');
    const focus=document.getElementById(`ai-focus-${catId}`); if(focus) focus.value=`[自訂題型配置] 目標共 ${total} 題：${request}。請盡量嚴格依此配置產生，題目內容仍須完全根據所選教材。`;
    const note=document.querySelector(`[data-ai-preset-note-76="${CSS.escape(String(catId))}"]`); if(note) note.textContent=`自訂混搭：${request}（共 ${total} 題）`;
  }

  function aiPresetPanel76(catId){
    return `<section data-ai-ux-76 class="mb-4 rounded-2xl border border-violet-200 bg-violet-50/50 p-4"><div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black tracking-wide text-violet-700">STEP 2 / 3 · 出題策略</div><h5 class="mt-1 font-black text-slate-900">依教學需求自動混搭題型</h5><p class="mt-1 text-xs text-slate-500">先選用途快速套用；需要精準配置時再使用自訂混搭。</p></div><span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-violet-700 border border-violet-100">產生後進入 STEP 3 審核</span></div><div class="mt-3 grid sm:grid-cols-[1fr_140px_auto] gap-2"><select data-ai-preset-select-76 class="w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm"><option value="auto">✨ 自動均衡</option><option value="newcomer">🌱 新人基礎考核</option><option value="pgy">🎯 PGY 核心能力</option><option value="case">🧩 案例判讀</option><option value="quality">🛡️ 品質管理／異常處理</option><option value="advanced">🧠 進階組內訓練</option><option value="image">🖼️ 圖片判讀</option><option value="video">🎬 影片互動</option><option value="custom">⚙️ 自訂混搭</option></select><select data-ai-primary-count-77 class="w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm"><option value="5">5 題</option><option value="10" selected>10 題</option><option value="15">15 題</option><option value="20">20 題</option></select><button type="button" data-ai-apply-preset-76 class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">套用</button></div><p data-ai-preset-note-76="${esc(catId)}" class="mt-2 text-[11px] leading-5 text-violet-700">自動均衡：系統依教材重點配置題型。</p><div data-ai-custom-mix-76="${esc(catId)}" class="hidden mt-3 rounded-xl border border-violet-100 bg-white p-3"><div class="grid grid-cols-2 sm:grid-cols-4 gap-2">${[['choice','單選',4],['multi','多選',2],['fill','填空',2],['essay','問答',2]].map(([t,l,n])=>`<label class="text-xs font-bold text-slate-600">${l}<input data-mix-type="${t}" type="number" min="0" max="30" value="${n}" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"></label>`).join('')}</div><button type="button" data-ai-apply-custom-76 class="mt-3 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white">套用自訂題型配置</button><p class="mt-2 text-[10px] leading-4 text-slate-400">自訂混搭會沿用同一支 AI 出題服務，以總題數＋明確配置要求產生候選題；教師仍需在匯入前審核。</p></div></section>`;
  }

  async function waitForAiSection76(catId,timeout=6500){
    const started=Date.now();
    while(Date.now()-started<timeout){
      const panel=document.getElementById(`qpanel-${catId}`); const section=panel?.querySelector('[data-ai-question-studio]');
      if(section) return section;
      await new Promise(resolve=>setTimeout(resolve,120));
    }
    return null;
  }

  async function mountAiPanel(catId){
    if(!catId)return;
    const host=document.getElementById('teacher-content-studio-body-71');if(!host)return;
    const selectedScope=scope(); restoreAiPanel(); restoreCourseWizard();
    const deadline=Date.now()+6000;
    const remaining=()=>Math.max(350,deadline-Date.now());
    try{
      let panel=document.getElementById(`qpanel-${catId}`);
      if(!panel){
        aiPrepare77(host,'正在切換考卷工作區…','準備目前考卷的題庫與 AI 工具');
        await timeout77(window.openAdminWorkspace?.('assessment'),Math.min(1800,remaining()),'切換考卷工作區');
        const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');if(area)area.value=selectedScope.area;if(group)group.value=selectedScope.group;
        aiPrepare77(host,'正在讀取考卷…','同步題庫與關聯教材');
        await timeout77(window.renderAdminQuizCategories?.(true),Math.min(2300,remaining()),'讀取考卷');
        panel=document.getElementById(`qpanel-${catId}`);
      }
      if(!panel)throw new Error('找不到指定考卷，請返回考卷管理重新選擇。');
      if(panel.classList.contains('hidden')){
        aiPrepare77(host,'正在開啟題庫…','載入本考卷題目與關聯教材');
        await timeout77(window.toggleQuizQuestionsPanel?.(catId),Math.min(2200,remaining()),'開啟題庫');
      }
      aiPrepare77(host,'正在掛載 AI 出題工作室…','即將完成');
      let section=panel.querySelector('[data-ai-question-studio]');
      if(!section)section=await waitForAiSection76(catId,Math.min(1400,remaining()));
      if(!section)throw new Error('AI 出題工作室載入逾時，請重新嘗試。');
      const placeholder=document.createElement('div');placeholder.hidden=true;placeholder.dataset.teacher75AiPlaceholder=String(catId);section.before(placeholder);aiMount.section=section;aiMount.placeholder=placeholder;aiMount.catId=String(catId);
      host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="mb-4"><button type="button" data-exam-open="${esc(catId)}" class="text-sm font-bold text-slate-500">← 返回考卷</button><h4 class="mt-2 text-xl font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">已鎖定目前考卷；關聯教材會自動帶入，教師只需選用途與題數。</p></div>${aiPresetPanel76(catId)}<div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      const materialBox=section.querySelector(`#ai-materials-${CSS.escape(String(catId))}`);const materialBlock=materialBox?.closest('.lg\:col-span-3');
      if(materialBlock&&!materialBlock.closest('[data-ai-material-details-77]')){const details=document.createElement('details');details.dataset.aiMaterialDetails77='1';details.className='rounded-xl border border-violet-100 bg-white';const summary=document.createElement('summary');summary.className='cursor-pointer list-none px-3 py-2 text-xs font-bold text-violet-800';summary.textContent='📚 已自動帶入考卷關聯教材（最多 4 份）｜查看／調整';materialBlock.before(details);details.appendChild(summary);details.appendChild(materialBlock);}
      const controls=['type','difficulty','strategy','focus'].map(name=>document.getElementById(`ai-${name}-${catId}`)?.parentElement).filter(Boolean);
      if(controls.length&&!section.querySelector('[data-ai-advanced-77]')){const details=document.createElement('details');details.dataset.aiAdvanced77='1';details.className='rounded-xl border border-slate-200 bg-white';details.innerHTML='<summary class="cursor-pointer list-none px-3 py-2 text-xs font-bold text-slate-600">⚙️ 進階設定（題型／難度／策略／重點）</summary><div data-ai-advanced-host-77 class="grid gap-3 p-3 sm:grid-cols-2"></div>';const first=controls[0];first.parentElement?.insertBefore(details,first);const advanced=details.querySelector('[data-ai-advanced-host-77]');controls.forEach(node=>advanced?.appendChild(node));}
      const presetSelect=host.querySelector('[data-ai-preset-select-76]'),presetButton=host.querySelector('[data-ai-apply-preset-76]'),customBox=host.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`),primaryCount=host.querySelector('[data-ai-primary-count-77]');
      presetSelect?.addEventListener('change',()=>customBox?.classList.toggle('hidden',presetSelect.value!=='custom'));
      presetButton?.addEventListener('click',()=>{if(presetSelect?.value==='custom'){customBox?.classList.remove('hidden');return;}applyAiPreset76(catId,presetSelect?.value||'auto');if(primaryCount)setAiControl76(catId,'count',primaryCount.value);});
      primaryCount?.addEventListener('change',()=>setAiControl76(catId,'count',primaryCount.value));
      host.querySelector('[data-ai-apply-custom-76]')?.addEventListener('click',()=>applyAiCustomMix76(catId));applyAiPreset76(catId,'auto');if(primaryCount)setAiControl76(catId,'count',primaryCount.value);
    }catch(error){restoreAiPanel();host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message||'AI 出題工作室開啟失敗')}<div class="mt-3 flex gap-2 flex-wrap"><button type="button" data-ai-retry-76 class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-exam-open="${esc(catId)}" class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回考卷</button></div></div>`;host.querySelector('[data-ai-retry-76]')?.addEventListener('click',()=>mountAiPanel(catId));}
  }

  async function confirmQuestionPreset(preset, catIdOverride=''){
    const catId = catIdOverride || document.getElementById('teacher-studio-question-exam-71')?.value;
    if(!catId) return;
    const selectedScope = scope();
    closeStudio();
    await window.openAdminWorkspace?.('assessment');
    const area = document.getElementById('admin-quiz-area');
    const group = document.getElementById('admin-quiz-group');
    if(area) area.value = selectedScope.area;
    if(group) group.value = selectedScope.group;
    await window.renderAdminQuizCategories?.(true);
    const panel = document.getElementById(`qpanel-${catId}`);
    if(panel?.classList.contains('hidden')) await window.toggleQuizQuestionsPanel?.(catId);
    const typeSelect = document.getElementById(`qform-${catId}-type`);
    if(preset === 'image') setSelectByValueOrText(typeSelect, 'image');
    else if(preset === 'video') setSelectByValueOrText(typeSelect, 'video');
    else setSelectByValueOrText(typeSelect, 'choice');
    window.updateManualQuestionType?.(catId);
    const question = document.getElementById(`qform-${catId}-question`);
    question?.scrollIntoView({behavior:'smooth', block:'center'});
    setTimeout(() => question?.focus(), 250);
  }

  async function openMaterialUpload(kind){
    closeStudio();
    await window.openAdminWorkspace?.('course-materials');
    const type = document.getElementById('admin-material-type');
    setSelectByValueOrText(type, kind === 'video' ? 'video-material' : 'standard');
    window.updateAdminMaterialTypeFields?.();
    const input = document.getElementById('admin-pptx-upload-input');
    input?.scrollIntoView({behavior:'smooth', block:'center'});
    setTimeout(() => input?.focus(), 250);
  }

  async function openAtlas(){
    closeStudio();
    await window.toggleAdminModal?.(false);
    window.switchLearningModule?.('atlas');
    if(typeof window.renderFormalAtlas === 'function') await window.renderFormalAtlas();
    setTimeout(() => window.openAtlasCreate?.(), 150);
  }

  async function launch(action){
    if(action==='exam')return renderExamManager();
    if(action==='course')return mountCourseWizardInStudio();
    if(action==='materials-manager')return mountMaterialManagerInStudio();
    if(action==='material')return openMaterialUpload('standard');
    if(action==='video-material')return openMaterialUpload('video');
    if(action==='external'){closeStudio();await window.openAdminWorkspace?.('course-materials');await window.openExternalMaterialCreateDrawer?.();return;}
    if(action==='atlas')return openAtlas();
  }

  window.teacherContentStudioExamAction=(action,catId)=>dispatchExamAction(action,catId);
  window.TeacherContentStudio71=Object.freeze({registerExamActions});
  window.openTeacherContentExam=async function(catId){openStudio();await renderExamContainer(catId);};

  function hideMaterialExecutorNode(node){
    if(!node) return;
    node.dataset.teacher72MaterialExecutor='1';
    node.classList.add('hidden');
    node.setAttribute('aria-hidden','true');
  }

  function consolidateMaterialWorkspace(){
    const root=document.getElementById('admin-material-workspace');
    if(!root) return;
    // RC 7.5: this DOM remains the canonical upload executor, but it is not a daily management surface.
    root.dataset.teacher75MaterialExecutorRoot='1';
    root.classList.add('hidden');
    root.setAttribute('aria-hidden','true');

    const fileInput=document.getElementById('admin-pptx-upload-input');
    hideMaterialExecutorNode(fileInput?.parentElement);
    hideMaterialExecutorNode(document.getElementById('admin-material-title')?.closest('.grid'));
    hideMaterialExecutorNode(document.getElementById('admin-atlas-fields'));
    hideMaterialExecutorNode(document.getElementById('admin-upload-btn')?.parentElement);

    const external=[...root.querySelectorAll('button')].find(button=>(button.getAttribute('onclick')||'').includes('openExternalMaterialCreateDrawer'));
    hideMaterialExecutorNode(external);
  }

  function ensureLauncher(){
    if(!canOpen()) return;
    const modal = document.getElementById('admin-modal');
    const workspace = document.getElementById('admin-workspace-content');
    if(!modal || !workspace || document.getElementById(launcherId)) return;
    const bar = document.createElement('div');
    bar.id = launcherId;
    bar.className = 'mb-4 flex items-center justify-between gap-3 rounded-2xl border border-teal-200 bg-gradient-to-r from-teal-50 to-white p-3 sm:p-4';
    bar.innerHTML = `<div class="min-w-0"><div class="font-black text-teal-950">＋ 建立教學內容</div><div class="text-xs text-teal-700 mt-0.5">考題、教材、影音與圖譜從同一入口開始。</div></div><button type="button" class="shrink-0 rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white shadow-sm hover:bg-teal-600">開始建立</button>`;
    bar.querySelector('button').addEventListener('click', openStudio);
    workspace.parentNode?.insertBefore(bar, workspace);
  }

  function mount(){
    ensureStudio();
    ensureLauncher();
    consolidateMaterialWorkspace();
    window.teacherContentStudioOpen = openStudio;
    window.teacherContentStudioClose = closeStudio;
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once:true});
  else mount();

  const observer = new MutationObserver(() => {
    ensureLauncher();
    consolidateMaterialWorkspace();
  });
  document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('admin-modal');
    if(modal) observer.observe(modal, {childList:true, subtree:true});
  }, {once:true});
})();
