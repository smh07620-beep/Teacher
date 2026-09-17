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
  const canOpen = () => canQuestion() || canMaterial();
  const studioId = 'teacher-content-studio-71';
  const launcherId = 'teacher-content-studio-launcher-71';

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
        <div class="mb-2"><h4 class="font-black text-slate-900">📝 出題與考核</h4><p class="text-xs text-slate-500 mt-1">先選你要完成的工作，系統會直接帶到對應編輯器。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('exam','📋','建立／管理考卷','設定考卷名稱、對象、抽題方式與發布流程。','indigo')}
          ${card('question','✏️','一般考題','快速建立單選題；題幹、選項、答案與解析優先。','indigo')}
          ${card('image-question','🖼️','圖片判讀題','直接進入圖片題模式，可上傳顯微鏡、血球或其他判讀圖片。','rose')}
          ${card('video-question','🎬','影片互動題','直接進入影片題模式，設定媒體網址與暫停作答時間。','violet')}
          ${card('ai-question','✨','AI 輔助出題','選教材與策略產生草稿，再由教師審核。','violet')}
        </div>
      </section>` : '';
    const materialCards = canMaterial() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📚 教材與媒體</h4><p class="text-xs text-slate-500 mt-1">所有新增動作都從這裡開始；舊版直接上傳表單只保留作為背景執行器。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('material','📄','上傳教材','PDF、PPTX、DOCX、圖片等檔案，使用統一建立流程。','teal')}
          ${card('video-material','🎥','上傳影音教材','影片與影音檔也從同一建立入口開始。','teal')}
          ${card('external','🔗','外部影音／連結','建立 YouTube、Shorts 或其他支援的外部教學連結。','sky')}
          ${card('atlas','🔬','顯微鏡／血球圖譜','建立顯微鏡、血球、尿液沉渣或菌落圖譜。','emerald')}
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
      const back = event.target.closest('[data-studio-back]');
      if(back) renderHome();
      const confirmQuestion = event.target.closest('[data-studio-question-confirm]');
      if(confirmQuestion) confirmQuestionPreset(confirmQuestion.dataset.preset || 'choice');
    });
    root.addEventListener('click', event => { if(event.target === root) closeStudio(); });
    return root;
  }

  function renderHome(){
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

  async function chooseExamForQuestion(preset){
    const body = document.getElementById('teacher-content-studio-body-71');
    if(!body) return;
    body.innerHTML = '<p class="text-sm text-slate-500">正在讀取目前組別的考卷…</p>';
    try{
      const categories = await loadCategories();
      if(!categories.length){
        body.innerHTML = `<div class="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h4 class="font-black text-amber-950">目前組別還沒有考卷</h4><p class="mt-1 text-sm text-amber-800">先建立考卷，再加入題目。</p><div class="mt-4 flex gap-2"><button type="button" data-studio-action="exam" class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">建立考卷</button><button type="button" data-studio-back class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">返回</button></div></div>`;
        return;
      }
      const title = preset === 'image' ? '圖片判讀題' : preset === 'video' ? '影片互動題' : '一般考題';
      body.innerHTML = `<div class="max-w-2xl mx-auto"><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回內容類型</button><div class="mt-4 rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black text-slate-900">${esc(title)} · 選擇考卷</h4><p class="mt-1 text-xs text-slate-500">題目會直接建立在所選考卷的題庫中。</p><label class="block mt-4 text-sm font-bold text-slate-700">加入哪一份考卷？<select id="teacher-studio-question-exam-71" class="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">${categories.map(c => `<option value="${esc(c.id)}">${esc(c.title || c.id)}</option>`).join('')}</select></label><div class="mt-5 flex flex-wrap justify-end gap-2"><button type="button" data-studio-back class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button type="button" data-studio-question-confirm data-preset="${esc(preset)}" class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-black text-white">下一步：開始出題</button></div></div></div>`;
    }catch(error){
      body.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3"><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
    }
  }

  async function confirmQuestionPreset(preset){
    const catId = document.getElementById('teacher-studio-question-exam-71')?.value;
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
    if(action === 'question') return chooseExamForQuestion('choice');
    if(action === 'image-question') return chooseExamForQuestion('image');
    if(action === 'video-question') return chooseExamForQuestion('video');
    if(action === 'exam'){
      closeStudio();
      await window.openAdminWorkspace?.('assessment');
      window.assessment681Tab?.('exams');
      const title = document.getElementById('admin-new-category-title');
      title?.scrollIntoView({behavior:'smooth', block:'center'});
      setTimeout(() => title?.focus(), 200);
      return;
    }
    if(action === 'ai-question'){
      closeStudio();
      await window.openAdminWorkspace?.('assessment');
      window.assessment681Tab?.('ai');
      document.getElementById('assessment-681')?.scrollIntoView({behavior:'smooth', block:'start'});
      return;
    }
    if(action === 'material') return openMaterialUpload('standard');
    if(action === 'video-material') return openMaterialUpload('video');
    if(action === 'external'){
      closeStudio();
      await window.openAdminWorkspace?.('course-materials');
      await window.openExternalMaterialDrawer?.();
      return;
    }
    if(action === 'atlas') return openAtlas();
  }

  function hideMaterialExecutorNode(node){
    if(!node) return;
    node.dataset.teacher72MaterialExecutor='1';
    node.classList.add('hidden');
    node.setAttribute('aria-hidden','true');
  }

  function consolidateMaterialWorkspace(){
    const root=document.getElementById('admin-material-workspace');
    if(!root) return;
    if(root.dataset.teacher72MaterialConsolidated!=='1'){
      root.dataset.teacher72MaterialConsolidated='1';
      const heading=root.querySelector('h4');
      const desc=heading?.parentElement?.querySelector('p');
      if(heading) heading.textContent='📚 教材處理與背景工作';
      if(desc) desc.textContent='新增教材與外部連結請使用「＋ 建立教學內容」；此區只保留儲存維護與背景處理狀態。';
      const note=document.createElement('div');
      note.dataset.teacher72MaterialNote='1';
      note.className='rounded-xl border border-teal-100 bg-teal-50/60 px-3 py-2 text-xs text-teal-800';
      note.textContent='建立入口已統一：一般教材、影音、外部連結與圖譜請從上方「＋ 建立教學內容」開始。';
      root.insertBefore(note,root.children[1]||null);
    }

    const fileInput=document.getElementById('admin-pptx-upload-input');
    hideMaterialExecutorNode(fileInput?.parentElement);
    hideMaterialExecutorNode(document.getElementById('admin-material-title')?.closest('.grid'));
    hideMaterialExecutorNode(document.getElementById('admin-atlas-fields'));
    hideMaterialExecutorNode(document.getElementById('admin-upload-btn')?.parentElement);

    const external=[...root.querySelectorAll('button')].find(button=>(button.getAttribute('onclick')||'').includes('openExternalMaterialDrawer'));
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