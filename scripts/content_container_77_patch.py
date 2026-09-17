from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def write(path,text): (ROOT/path).write_text(text.rstrip()+'\n',encoding='utf-8')
def once(text,old,new,label):
    n=text.count(old); assert n==1,f'{label}: expected 1 match, got {n}'
    return text.replace(old,new,1)
def sub_once(text,pattern,repl,label):
    out,n=re.subn(pattern,repl,text,count=1,flags=re.S); assert n==1,f'{label}: expected 1 match, got {n}'
    return out

p=Path('static/teacher-content-studio-71.js'); s=read(p)
s=once(s,"  const aiMount = {section:null, placeholder:null, catId:''};","  const aiMount = {section:null, placeholder:null, catId:''};\n  const courseMount = {root:null, placeholder:null};",'course mount state')

s=sub_once(s,r"  function baseBody\(\)\{.*?\n  \}\n\n  function ensureStudio",'''  function baseBody(){
    const questionCards = canQuestion() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📝 出題與考核</h4><p class="text-xs text-slate-500 mt-1">先管理考卷；選定考卷後才建立或管理題目。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${card('exam','📋','考卷管理','管理既有考卷、建立新考卷，並在考卷內加入一般題、圖片題、影片題或 AI 題。','indigo')}
        </div>
      </section>` : '';
    const materialCards = canMaterial() ? `
      <section>
        <div class="mb-2"><h4 class="font-black text-slate-900">📚 教材與課程</h4><p class="text-xs text-slate-500 mt-1">課程與教材從同一建立流程開始。</p></div>
        <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          ${canCourse()?card('course','🪄','建立課程','在此完成課程、教材與考卷串接，不離開建立視窗。','violet'):''}
          ${card('material','📄','上傳教材','PDF、PPTX、DOCX、圖片等檔案，使用統一建立流程。','teal')}
          ${card('video-material','🎥','上傳影音教材','影片與影音檔也從同一建立入口開始。','teal')}
          ${card('external','🔗','外部影音／連結','建立 YouTube、Shorts 或其他支援的外部教學連結。','sky')}
          ${card('atlas','🔬','顯微鏡／血球圖譜','建立顯微鏡、血球、尿液沉渣或菌落圖譜。','emerald')}
        </div>
      </section>` : '';
    return `<div class="space-y-6">${questionCards}${materialCards}</div>`;
  }

  function ensureStudio''','base body convergence')

s=once(s,"      if(action) launch(action);\n      const back = event.target.closest('[data-studio-back]');",'''      if(action) launch(action);
      const examOpen = event.target.closest('[data-exam-open]');
      if(examOpen){ renderExamContainer(examOpen.dataset.examOpen); return; }
      if(event.target.closest('[data-exam-create-open]')){ renderCreateExam(); return; }
      if(event.target.closest('[data-exam-create-submit]')){ createExamFromStudio(); return; }
      const examAction = event.target.closest('[data-exam-action]');
      if(examAction){ runExamAction(examAction.dataset.examAction, examAction.dataset.examId); return; }
      if(event.target.closest('[data-course-studio-back]')){ restoreCourseWizard(); renderHome(); return; }
      const back = event.target.closest('[data-studio-back]');''','studio event delegation')

s=once(s,"  function renderHome(){\n    restoreAiPanel();","  function renderHome(){\n    restoreAiPanel();\n    restoreCourseWizard();",'render home restore')
s=once(s,"  function closeStudio(){\n    restoreAiPanel();","  function closeStudio(){\n    restoreAiPanel();\n    restoreCourseWizard();",'close restore')

insert=r'''
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
    restoreAiPanel(); restoreCourseWizard();
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
'''
s=once(s,"\n\n  function restoreAiPanel(){",insert+"\n\n  function restoreAiPanel(){",'insert container orchestration')

# remove legacy choose-exam AI and manual-question selector layers
s=sub_once(s,r"\n  async function chooseExamForAi\(\)\{.*?\n  \}\n\n  async function mountAiPanel",'\n  async function mountAiPanel','remove AI exam selector')
s=sub_once(s,r"\n  async function chooseExamForQuestion\(preset\)\{.*?\n  \}\n\n  async function confirmQuestionPreset",'\n  async function confirmQuestionPreset','remove manual exam selector')
s=once(s,"  async function confirmQuestionPreset(preset){\n    const catId = document.getElementById('teacher-studio-question-exam-71')?.value;","  async function confirmQuestionPreset(preset, catIdOverride=''){\n    const catId = catIdOverride || document.getElementById('teacher-studio-question-exam-71')?.value;",'direct exam question target')

# replace AI mounting with bounded staged fast-path and in-exam navigation
s=sub_once(s,r"  async function mountAiPanel\(catId\)\{.*?\n  \}\n\n  async function confirmQuestionPreset",'''  async function mountAiPanel(catId){
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
      const materialBox=section.querySelector(`#ai-materials-${CSS.escape(String(catId))}`);const materialBlock=materialBox?.closest('.lg\\:col-span-3');
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

  async function confirmQuestionPreset''','replace AI mount')

# add visible primary count to preset panel
s=once(s,"<div class=\"mt-3 grid sm:grid-cols-[1fr_auto] gap-2\"><select data-ai-preset-select-76", "<div class=\"mt-3 grid sm:grid-cols-[1fr_140px_auto] gap-2\"><select data-ai-preset-select-76",'preset grid')
s=once(s,"</select><button type=\"button\" data-ai-apply-preset-76", "</select><select data-ai-primary-count-77 class=\"w-full rounded-xl border border-violet-200 bg-white px-3 py-2 text-sm\"><option value=\"5\">5 題</option><option value=\"10\" selected>10 題</option><option value=\"15\">15 題</option><option value=\"20\">20 題</option></select><button type=\"button\" data-ai-apply-preset-76",'primary AI count')

# simplify launch routing
s=sub_once(s,r"  async function launch\(action\)\{.*?\n  \}\n\n  function hideMaterialExecutorNode",'''  async function launch(action){
    if(action==='exam')return renderExamManager();
    if(action==='course')return mountCourseWizardInStudio();
    if(action==='material')return openMaterialUpload('standard');
    if(action==='video-material')return openMaterialUpload('video');
    if(action==='external'){closeStudio();await window.openAdminWorkspace?.('course-materials');await window.openExternalMaterialDrawer?.();return;}
    if(action==='atlas')return openAtlas();
  }

  function hideMaterialExecutorNode''','launch convergence')
write(p,s)

# Auto-select up to four directly linked materials, respecting one-video rule.
p=Path('static/admin-ai-questions.js'); s=read(p)
old="const s=state(id);if(!s.selected.size){const linked=mats.find(m=>m.category===id);if(linked)s.selected.add(String(linked.id));}"
new="const s=state(id);if(!s.selected.size){const linked=mats.filter(m=>m.category===id),nonVideo=linked.filter(m=>kind(m)[0]!=='video').slice(0,4),video=linked.find(m=>kind(m)[0]==='video'),auto=[...nonVideo];if(video&&auto.length<4)auto.push(video);s.selected=new Set(auto.slice(0,4).map(m=>String(m.id)));}"
s=once(s,old,new,'AI linked material auto-selection')
write(p,s)

# Regression gate
Path('tests/test_content_container_convergence_77.py').write_text(r'''from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ContentContainerConvergence77Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.studio=ROOT.joinpath('static/teacher-content-studio-71.js').read_text(encoding='utf-8')
        cls.ai=ROOT.joinpath('static/admin-ai-questions.js').read_text(encoding='utf-8')

    def test_studio_outer_surface_only_exposes_exam_management(self):
        self.assertIn("'考卷管理'",self.studio)
        self.assertNotIn("card('question'",self.studio)
        self.assertNotIn("card('image-question'",self.studio)
        self.assertNotIn("card('video-question'",self.studio)
        self.assertNotIn("card('ai-question'",self.studio)

    def test_exam_is_question_container(self):
        for token in ('renderExamManager','renderExamContainer','data-exam-action="question"','data-exam-action="image"','data-exam-action="video"','data-exam-action="ai"','data-exam-action="questions"','data-exam-action="settings"'):
            self.assertIn(token,self.studio)
        self.assertIn("confirmQuestionPreset('choice',catId)",self.studio)
        self.assertIn("mountAiPanel(catId)",self.studio)

    def test_exam_creation_keeps_canonical_mutation_owner(self):
        self.assertIn('adminCreateQuizCategory',self.studio)
        self.assertNotIn("fetch('/api/quiz-categories'",self.studio)

    def test_course_wizard_is_mounted_inside_studio(self):
        self.assertIn('mountCourseWizardInStudio',self.studio)
        self.assertIn('data-course-wizard-host-77',self.studio)
        self.assertIn('restoreCourseWizard',self.studio)
        self.assertNotIn("closeStudio();\n      await window.openAdminWorkspace?.('course-materials');\n      window.teacher75OpenCourseWizard?.();",self.studio)

    def test_ai_uses_current_exam_and_has_bounded_prepare_flow(self):
        self.assertNotIn('chooseExamForAi',self.studio)
        self.assertIn('const deadline=Date.now()+6000',self.studio)
        for text in ('正在切換考卷工作區','正在讀取考卷','正在開啟題庫','正在掛載 AI 出題工作室','↻ 重新嘗試'):
            self.assertIn(text,self.studio)

    def test_ai_primary_surface_is_purpose_plus_count(self):
        self.assertIn('data-ai-primary-count-77',self.studio)
        self.assertIn('data-ai-material-details-77',self.studio)
        self.assertIn('data-ai-advanced-77',self.studio)

    def test_ai_auto_selects_up_to_four_linked_materials(self):
        self.assertIn("mats.filter(m=>m.category===id)",self.ai)
        self.assertIn("auto.slice(0,4)",self.ai)
        self.assertIn("kind(m)[0]!=='video'",self.ai)

if __name__=='__main__': unittest.main()
''',encoding='utf-8')
print('RC 7.7 content container patch applied')
