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
  const AI_PREPARE_DEADLINE_77 = 6000;

  function withTimeout77(task,ms,label){
    const promise=Promise.resolve(task);
    return Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(new Error(`${label}逾時，請重新嘗試。`)),Math.max(250,ms||250)))]);
  }

  function aiPrepareStatus77(host,label,detail=''){
    if(!host) return;
    host.innerHTML=`<div class="rounded-2xl border border-violet-100 bg-violet-50 p-5 text-sm text-violet-700"><div class="font-black">${esc(label)}</div>${detail?`<div class="mt-1 text-xs text-violet-500">${esc(detail)}</div>`:''}</div>`;
  }

  function compactAiStudio77(section,catId){
    if(!section) return;
    const search=document.getElementById(`ai-material-search-${catId}`);
    const materialBlock=search?.closest('[class*="lg:col-span-3"]');
    const selectedBox=document.getElementById(`ai-selected-${catId}`);
    if(materialBlock&&selectedBox&&!section.querySelector('[data-ai-material-summary-77]')){
      const compact=document.createElement('div');
      compact.dataset.aiMaterialSummary77='1';
      compact.className='lg:col-span-3 rounded-2xl border border-violet-100 bg-violet-50/50 p-3';
      compact.innerHTML=`<div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black text-violet-900">📚 出題教材</div><div class="mt-1 text-[11px] text-slate-500">依所選考卷自動帶入最多 3 份關聯教材；影片最多 1 支。</div></div><button type="button" data-ai-adjust-materials-77 class="rounded-lg border border-violet-200 bg-white px-3 py-2 text-xs font-bold text-violet-700">調整教材</button></div><div data-ai-linked-summary-77 class="mt-2"></div>`;
      materialBlock.before(compact);
      compact.querySelector('[data-ai-linked-summary-77]')?.appendChild(selectedBox);
      materialBlock.classList.add('hidden');
      compact.querySelector('[data-ai-adjust-materials-77]')?.addEventListener('click',()=>materialBlock.classList.toggle('hidden'));
    }

    const controlNames=['type','difficulty','count','strategy','focus'];
    const wrappers=[...new Set(controlNames.map(name=>document.getElementById(`ai-${name}-${catId}`)?.parentElement).filter(Boolean))];
    if(wrappers.length&&!section.querySelector('[data-ai-advanced-77]')){
      const parent=wrappers[0].parentElement;
      const details=document.createElement('details');
      details.dataset.aiAdvanced77='1';
      details.className='lg:col-span-3 rounded-xl border border-slate-200 bg-slate-50 p-3';
      details.innerHTML='<summary class="cursor-pointer text-xs font-black text-slate-700">⚙️ 進階設定（題型／難度／題數／策略／出題重點）</summary><div data-ai-advanced-grid-77 class="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-3"></div>';
      parent?.insertBefore(details,wrappers[0]);
      const grid=details.querySelector('[data-ai-advanced-grid-77]');
      wrappers.forEach(node=>grid?.appendChild(node));
    }
  }

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
          ${canCourse()?card('course','🪄','建立課程','建立課程並視需要串接教材與考卷；進階欄位只在流程中出現。','violet'):''}
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
      const confirmAi = event.target.closest('[data-studio-ai-confirm]');
      if(confirmAi) mountAiPanel(document.getElementById('teacher-studio-ai-exam-75')?.value || '');
    });
    root.addEventListener('click', event => { if(event.target === root) closeStudio(); });
    return root;
  }

  function renderHome(){
    restoreAiPanel();
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
    return `<section data-ai-ux-76 class="mb-4 rounded-2xl border border-violet-200 bg-violet-50/50 p-4"><div class="flex items-start justify-between gap-3 flex-wrap"><div><div class="text-xs font-black tracking-wide text-violet-700">STEP 2 / 3 · 出題策略</div><h5 class="mt-1 font-black text-slate-900">依教學需求自動混搭題型</h5><p class="mt-1 text-xs text-slate-500">先選用途快速套用；需要精準配置時再使用自訂混搭。</p></div><span class="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-violet-700 border border-violet-100">產生後進入 STEP 3 審核</span></div><div class="mt-3 grid sm:grid-cols-[1fr_auto] gap-2"><select data-ai-preset-select-76 class="w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm"><option value="auto">✨ 自動均衡</option><option value="newcomer">🌱 新人基礎考核</option><option value="pgy">🎯 PGY 核心能力</option><option value="case">🧩 案例判讀</option><option value="quality">🛡️ 品質管理／異常處理</option><option value="advanced">🧠 進階組內訓練</option><option value="image">🖼️ 圖片判讀</option><option value="video">🎬 影片互動</option><option value="custom">⚙️ 自訂混搭</option></select><button type="button" data-ai-apply-preset-76 class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">套用</button></div><p data-ai-preset-note-76="${esc(catId)}" class="mt-2 text-[11px] leading-5 text-violet-700">自動均衡：系統依教材重點配置題型。</p><div data-ai-custom-mix-76="${esc(catId)}" class="hidden mt-3 rounded-xl border border-violet-100 bg-white p-3"><div class="grid grid-cols-2 sm:grid-cols-4 gap-2">${[['choice','單選',4],['multi','多選',2],['fill','填空',2],['essay','問答',2]].map(([t,l,n])=>`<label class="text-xs font-bold text-slate-600">${l}<input data-mix-type="${t}" type="number" min="0" max="30" value="${n}" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"></label>`).join('')}</div><button type="button" data-ai-apply-custom-76 class="mt-3 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white">套用自訂題型配置</button><p class="mt-2 text-[10px] leading-4 text-slate-400">自訂混搭會沿用同一支 AI 出題服務，以總題數＋明確配置要求產生候選題；教師仍需在匯入前審核。</p></div></section>`;
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

  async function chooseExamForAi(){
    restoreAiPanel();
    const host = document.getElementById('teacher-content-studio-body-71');
    if(!host) return;
    host.innerHTML = '<p class="text-sm text-slate-500">正在讀取可使用 AI 出題的考卷…</p>';
    try{
      const categories = await loadCategories();
      if(!categories.length){
        host.innerHTML = `<div class="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h4 class="font-black text-amber-950">目前組別還沒有考卷</h4><p class="mt-1 text-sm text-amber-800">AI 候選題必須先指定要加入的考卷。</p><div class="mt-4 flex gap-2"><button type="button" data-studio-action="exam" class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">建立考卷</button><button type="button" data-studio-back class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">返回</button></div></div>`;
        return;
      }
      host.innerHTML = `<div class="mx-auto max-w-2xl"><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 返回內容類型</button><div class="mt-4 rounded-2xl border border-violet-200 bg-white p-5"><div class="text-xs font-black tracking-wide text-violet-700">STEP 1 / 3 · 目標考卷</div><h4 class="mt-1 text-lg font-black text-slate-900">先選擇要加入的考卷</h4><p class="mt-1 text-xs leading-5 text-slate-500">下一步仍留在「建立教學內容」視窗，直接使用既有 AI 教材出題工作室，不會跳離目前流程。</p><label class="block mt-4 text-sm font-bold text-slate-700">加入哪一份考卷？<select id="teacher-studio-ai-exam-75" class="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">${categories.map(c => `<option value="${esc(c.id)}">${esc(c.title || c.id)}</option>`).join('')}</select></label><div class="mt-5 flex flex-wrap justify-end gap-2"><button type="button" data-studio-back class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button type="button" data-studio-ai-confirm class="rounded-xl bg-violet-700 px-4 py-2 text-sm font-black text-white">下一步：AI 出題設定</button></div></div></div>`;
    }catch(error){
      host.innerHTML = `<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}<div class="mt-3"><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
    }
  }

  async function mountAiPanel(catId){
    if(!catId) return;
    const host=document.getElementById('teacher-content-studio-body-71');
    if(!host) return;
    const selectedScope=scope(),deadline=Date.now()+AI_PREPARE_DEADLINE_77;
    const remain=()=>Math.max(250,deadline-Date.now());
    const bounded=(task,label,maxMs=2600)=>withTimeout77(task,Math.min(maxMs,remain()),label);
    restoreAiPanel();
    try{
      let panel=document.getElementById(`qpanel-${catId}`);
      if(!panel){
        aiPrepareStatus77(host,'正在切換到考核工作區…','只在需要時建立考卷／題庫 DOM。');
        await bounded(window.openAdminWorkspace?.('assessment'),'切換考核工作區',1800);
        const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');
        if(area) area.value=selectedScope.area;
        if(group) group.value=selectedScope.group;
        panel=document.getElementById(`qpanel-${catId}`);
        if(!panel){
          aiPrepareStatus77(host,'正在讀取考卷…','同步目前組別的考卷與關聯教材。');
          await bounded(window.renderAdminQuizCategories?.(true),'讀取考卷',2600);
          panel=document.getElementById(`qpanel-${catId}`);
        }
      }
      if(!panel) throw new Error('找不到指定考卷，請重新選擇。');
      if(panel.classList.contains('hidden')){
        aiPrepareStatus77(host,'正在開啟題庫…','準備既有 AI 出題工作室。');
        await bounded(window.toggleQuizQuestionsPanel?.(catId),'開啟題庫',1600);
      }
      aiPrepareStatus77(host,'正在掛載 AI 出題工作室…','完成後會自動帶入本考卷關聯教材。');
      let section=panel.querySelector('[data-ai-question-studio]');
      if(!section) section=await waitForAiSection76(catId,Math.min(1400,remain()));
      if(!section) throw new Error('AI 出題工作室載入逾時，請按「重新嘗試」。');
      const placeholder=document.createElement('div');
      placeholder.hidden=true;
      placeholder.dataset.teacher75AiPlaceholder=String(catId);
      section.before(placeholder);
      aiMount.section=section;
      aiMount.placeholder=placeholder;
      aiMount.catId=String(catId);
      host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="mb-4 flex items-start justify-between gap-3"><div><button type="button" data-studio-back class="text-sm font-bold text-slate-500">← 重新選擇考卷</button><h4 class="mt-2 text-lg font-black text-slate-950">✨ AI 輔助出題</h4><p class="mt-1 text-xs text-slate-500">教材依考卷關聯自動帶入；常用設定由用途 preset 管理，細節需要時再展開。</p></div></div>${aiPresetPanel76(catId)}<div data-teacher75-ai-host></div></div>`;
      host.querySelector('[data-teacher75-ai-host]')?.appendChild(section);
      compactAiStudio77(section,catId);
      const presetSelect=host.querySelector('[data-ai-preset-select-76]'),presetButton=host.querySelector('[data-ai-apply-preset-76]'),customBox=host.querySelector(`[data-ai-custom-mix-76="${CSS.escape(String(catId))}"]`);
      presetSelect?.addEventListener('change',()=>customBox?.classList.toggle('hidden',presetSelect.value!=='custom'));
      presetButton?.addEventListener('click',()=>{if(presetSelect?.value==='custom'){customBox?.classList.remove('hidden');return;}applyAiPreset76(catId,presetSelect?.value||'auto');});
      host.querySelector('[data-ai-apply-custom-76]')?.addEventListener('click',()=>applyAiCustomMix76(catId));
      applyAiPreset76(catId,'auto');
      requestAnimationFrame(()=>host.querySelector('[data-ai-ux-76]')?.scrollIntoView({behavior:'smooth',block:'start'}));
    }catch(error){
      restoreAiPanel();
      host.innerHTML=`<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message||'AI 出題工作室開啟失敗')}<div class="mt-3 flex gap-2 flex-wrap"><button type="button" data-ai-retry-76 class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-studio-back class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回</button></div></div>`;
      host.querySelector('[data-ai-retry-76]')?.addEventListener('click',()=>mountAiPanel(catId));
    }
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
    if(action === 'ai-question') return chooseExamForAi();
    if(action === 'course'){
      closeStudio();
      await window.openAdminWorkspace?.('course-materials');
      window.teacher75OpenCourseWizard?.();
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
    // RC 7.5: this DOM remains the canonical upload executor, but it is not a daily management surface.
    root.dataset.teacher75MaterialExecutorRoot='1';
    root.classList.add('hidden');
    root.setAttribute('aria-hidden','true');

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
