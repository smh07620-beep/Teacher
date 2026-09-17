/* Phase 3G · Admin question-bank category runtime.
 * Loaded after the legacy admin bundle so these functions become the
 * canonical runtime implementation while system-admin.js remains a
 * compatibility fallback during the incremental split.
 */
(function(){
  'use strict';

  window.groupOptionsForArea = function(area){
    return Object.entries(GROUPS)
      .filter(([k,g])=>area==='pgy'||!g.pgyOnly)
      .map(([k,g])=>`<option value="${k}">${escapeHtml(g.label)}</option>`)
      .join('');
  };

  window.populateAdminGroupSelects = function(){
    const opts = window.groupOptionsForArea(currentTrainingArea);
    const matSel = document.getElementById('admin-material-group');
    const quizSel = document.getElementById('admin-quiz-group');
    const wizardSel = document.getElementById('wizard-group');
    if (matSel) matSel.innerHTML = opts;
    const matArea=document.getElementById('admin-material-area');
    const quizArea=document.getElementById('admin-quiz-area');
    if(matArea){
      matArea.value=currentTrainingArea;
      matArea.onchange=()=>{
        if(matSel) matSel.innerHTML=window.groupOptionsForArea(matArea.value);
        window.onAdminMaterialGroupChange();
      };
    }
    if(quizArea){
      quizArea.value=currentTrainingArea;
      quizArea.onchange=()=>{
        if(quizSel) quizSel.innerHTML=window.groupOptionsForArea(quizArea.value);
        window.renderAdminQuizCategories();
      };
    }
    if (quizSel) quizSel.innerHTML = opts;
    if (wizardSel) {
      wizardSel.innerHTML = window.groupOptionsForArea(document.getElementById('wizard-area')?.value || currentTrainingArea);
      wizardSel.onchange=()=>{ renderAdminCourses(true); renderAdminCourseMaterialHub(true); };
    }
    const wizardArea=document.getElementById('wizard-area');
    if(wizardArea){
      wizardArea.onchange=()=>{
        if(wizardSel){
          wizardSel.innerHTML=window.groupOptionsForArea(wizardArea.value);
          wizardSel.value=wizardSel.options[0]?.value||'';
        }
        renderAdminCourses(true);
        renderAdminCourseMaterialHub(true);
      };
    }
  };

  window.onAdminMaterialGroupChange = function(){
    window.refreshAdminMaterialCategoryOptions();
    refreshAdminMaterialCourses();
  };

  window.refreshAdminMaterialCategoryOptions = async function(){
    const group = document.getElementById('admin-material-group').value;
    const sel = document.getElementById('admin-material-category');
    if (!sel) return;
    sel.innerHTML = '<option value="">未分類 / 一般補充教材</option>';
    try {
      const res = await fetch(`/api/quiz-categories?group=${group}&area=${document.getElementById('admin-material-area')?.value || currentTrainingArea}`);
      const cats = await res.json();
      sel.innerHTML += cats.map(c => `<option value="${c.id}">${escapeHtml(c.title)}</option>`).join('');
    } catch (err) {
      // 保留「未分類」選項；既有 server-side policy 仍是權限邊界。
    }
  };

  window.onAdminQuizGroupChange = function(){
    window.renderAdminQuizCategories(false);
  };

  window.exposeQuestionDeleteActions = function(root=document){
    if(!root?.querySelectorAll) return;

    root.querySelectorAll('button[onclick*="adminDeleteQuizQuestion"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除') btn.textContent='🗑️ 刪除';
      btn.className='text-[11px] bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-2.5 py-1.5 rounded-lg font-bold';
    });

    root.querySelectorAll('button[onclick*="adminBulkDeleteQuestions"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除已選題目') btn.textContent='🗑️ 刪除已選題目';
      btn.className='text-[11px] bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-1.5 rounded-lg font-bold';
    });

    root.querySelectorAll('button[onclick*="adminDeleteQuizCategory"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除考卷') btn.textContent='🗑️ 刪除考卷';
      btn.className='text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg font-bold';
      const details=btn.closest('details');
      const actions=details?.parentElement;
      if(details&&actions){
        actions.insertBefore(btn,details);
        details.remove();
      }
    });
  };

  function startQuestionDeleteVisibilityObserver(){
    const box=document.getElementById('admin-quiz-categories-list');
    if(!box||box.dataset.questionDeleteVisibilityObserver==='1') return;
    box.dataset.questionDeleteVisibilityObserver='1';
    window.exposeQuestionDeleteActions(box);
    const observer=new MutationObserver(()=>window.exposeQuestionDeleteActions(box));
    observer.observe(box,{childList:true,subtree:true});
  }

  window.paintAdminQuizCategories = function(cats){
    const box=document.getElementById('admin-quiz-categories-list');
    if(!box) return;
    if(!cats.length){
      box.innerHTML='<p class="text-xs text-slate-500 py-2">本組別尚未建立任何考題頁籤，請於上方輸入頁籤名稱後點擊「➕ 新增」。</p>';
      return;
    }
    box.innerHTML=cats.map(quizCategoryCardHTML).join('');
    window.exposeQuestionDeleteActions(box);
    updateQuizWorkspacePresentation();
  };

  window.optimisticInsertQuizCategory = function(cat, area, group){
    const k=adminScopeKey(area,group);
    const cached=adminQuizCategoriesCache.get(k)?.data||[];
    const next=[{...cat,questionCount:Number(cat.questionCount||0)},...cached.filter(c=>c.id!==cat.id)];
    adminQuizCategoriesCache.set(k,{data:next,at:Date.now()});
    const curArea=document.getElementById('admin-quiz-area')?.value||currentTrainingArea;
    const curGroup=document.getElementById('admin-quiz-group')?.value||currentGroupKey;
    if(curArea===area&&curGroup===group){
      window.paintAdminQuizCategories(next);
      setAdminQuizSyncStatus('剛建立・背景同步中','indigo');
    }
  };

  window.patchVisibleQuizCounts = function(cats){
    for(const c of cats||[]){
      const el=document.getElementById(`qcount-${c.id}`);
      if(el) el.textContent=Number(c.questionCount||0);
    }
  };

  window.renderAdminQuizCategories = async function(force=false){
    const box=document.getElementById('admin-quiz-categories-list');
    const group=document.getElementById('admin-quiz-group')?.value;
    const area=document.getElementById('admin-quiz-area')?.value||currentTrainingArea;
    if(!box||!group) return;
    const k=adminScopeKey(area,group);
    const cached=adminQuizCategoriesCache.get(k);
    const now=Date.now();
    if(cached?.data) window.paintAdminQuizCategories(cached.data);
    if(!force && cached?.data && (now-cached.at)<ADMIN_QUIZ_CACHE_MS){
      setAdminQuizSyncStatus('已快取・可立即操作','emerald');
      return;
    }
    const key=await getAdminKey();
    if(!key) return;
    const hasVisibleData=!!cached?.data?.length || !!box.querySelector('article');
    if(!hasVisibleData){
      box.innerHTML='<div class="space-y-3"><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div></div>';
    } else {
      box.classList.add('opacity-75');
    }
    setAdminQuizSyncStatus('背景同步中…','indigo');
    try{
      const res=await fetch(`/api/quiz-categories/admin?group=${group}&area=${area}`,{headers:{'X-Admin-Key':key}});
      const cats=await res.json().catch(()=>[]);
      if(!res.ok) throw new Error((cats&&cats.error)||'讀取失敗');
      const list=Array.isArray(cats)?cats:[];
      adminQuizCategoriesCache.set(k,{data:list,at:Date.now()});
      if(adminHasExpandedQuestionEditor(box)){
        window.patchVisibleQuizCounts(list);
        setAdminQuizSyncStatus('已同步・保留目前編輯','emerald');
      } else {
        window.paintAdminQuizCategories(list);
        setAdminQuizSyncStatus('剛剛同步完成','emerald');
      }
    }catch(err){
      setAdminQuizSyncStatus('同步失敗','rose');
      if(!hasVisibleData) box.innerHTML=`<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`;
    }finally{
      box.classList.remove('opacity-75');
    }
  };

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',startQuestionDeleteVisibilityObserver,{once:true});
  else startQuestionDeleteVisibilityObserver();

  // Final convergence: canonical owner migrated from system-admin.js.
  function setAdminQuizSyncStatus(text, tone='slate'){
      const el=document.getElementById('admin-quiz-sync-status'); if(!el)return;
      const tones={slate:'bg-slate-100 text-slate-500',indigo:'bg-indigo-50 text-indigo-700',emerald:'bg-emerald-50 text-emerald-700',rose:'bg-rose-50 text-rose-700',amber:'bg-amber-50 text-amber-700'};
      el.className=`text-[11px] px-2.5 py-1 rounded-full font-bold ${tones[tone]||tones.slate}`; el.textContent=text;
  }

  function adminHasExpandedQuestionEditor(box){
      return !!box?.querySelector('[id^="qedit-"]:not(.hidden), textarea[id^="qedit-"]:focus, input[id^="qedit-"]:focus');
  }

  function quizCategoryCardHTML(c) {
      return `
          <article class="border border-slate-200 rounded-2xl bg-white shadow-sm overflow-hidden">
              <div class="p-4 flex items-start justify-between gap-3 flex-wrap bg-gradient-to-r from-white to-slate-50">
                  <div class="min-w-0">
                      <div class="flex items-center gap-2 flex-wrap">
                          <span class="font-black text-base text-slate-900 break-all">${escapeHtml(c.title)}</span>
                          <span class="text-[11px] px-2 py-0.5 rounded-full ${c.active?'bg-emerald-50 text-emerald-700':(c.reviewStatus==='approved'?'bg-sky-50 text-sky-700':'bg-amber-100 text-amber-800')} font-bold">${c.active?'已發布':(c.reviewStatus==='approved'?'已審核・待發布':'草稿・待審核')}</span>${c.blindMode?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-slate-900 text-white font-bold">導師設定：盲測</span>':''}
                      </div>
                      <div class="text-xs text-slate-500 mt-1">${escapeHtml(c.desc || '尚未填寫考卷說明')}</div>
                      <div class="flex flex-wrap gap-1.5 mt-2"><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">👤 ${escapeHtml(examAudienceLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">🧠 題庫 ${Number(c.questionCount||0)} 題</span><span class="text-[10px] px-2 py-1 rounded-full bg-teal-50 text-teal-700">📋 ${escapeHtml(examDrawLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-emerald-50 text-emerald-700">🎯 及格 ${Number(c.passingScore||80)} 分</span>${c.publicationHash?`<span class="text-[10px] px-2 py-1 rounded-full bg-violet-50 text-violet-700" title="發布快照 SHA-256：${escapeHtml(c.publicationHash)}">🔒 快照 ${escapeHtml(c.publicationHash.slice(0,10))}</span>`:''}</div>
                  </div>
                  <div class="flex gap-2 shrink-0 flex-wrap">
                      <button data-admin-role="questions-action" onclick="toggleQuizQuestionsPanel('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🧠 題庫／AI（<span id="qcount-${c.id}">${Number.isFinite(Number(c.questionCount)) ? Number(c.questionCount) : 0}</span>）</button>
                      <button data-admin-role="exam-action" onclick="adminEditQuizCategory('${c.id}')" class="text-xs bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">✏️ 考卷設定</button>
                      <button id="blind-toggle-${c.id}" onclick="adminToggleBlindMode('${c.id}',${c.blindMode?'false':'true'})" class="text-xs ${c.blindMode?'bg-slate-900 text-white border-slate-900':'bg-white text-slate-700 border-slate-300'} border hover:bg-slate-100 px-3 py-2 rounded-lg font-bold">🕶️ 盲測：${c.blindMode?'開啟':'關閉'}</button>
                      <button onclick="openQuizMaterialLinker('${c.id}')" class="text-xs bg-white border border-cyan-200 hover:bg-cyan-50 text-cyan-700 px-3 py-2 rounded-lg font-bold">🔗 關聯教材</button>
                      <details class="relative"><summary class="list-none cursor-pointer text-xs bg-white border border-slate-200 text-slate-500 px-3 py-2 rounded-lg">更多</summary><div class="absolute right-0 mt-1 z-30 w-40 bg-white border border-slate-200 shadow-xl rounded-xl p-2"><button onclick="adminDeleteQuizCategory('${c.id}')" class="w-full text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg">🗑️ 刪除考卷</button></div></details>
                  </div>
              </div>
              <div id="qpanel-${c.id}" class="hidden border-t border-slate-200 p-4 space-y-4 bg-slate-50/60">
                  <section id="qmaterial-link-${c.id}" class="hidden bg-cyan-50/60 rounded-xl border border-cyan-200 p-3 space-y-3">
                      <div class="flex items-start justify-between gap-3 flex-wrap"><div><p class="text-sm font-black text-cyan-950">🔗 重新關聯教材</p><p class="text-[11px] text-cyan-700 mt-1">勾選要綁定此考卷的教材。若教材原本綁定其他考卷，儲存後會改綁到目前考卷。</p></div><button onclick="closeQuizMaterialLinker('${c.id}')" class="text-[11px] text-slate-500 hover:text-slate-800">收合</button></div>
                      <div class="flex gap-2"><input id="qmaterial-search-${c.id}" oninput="filterQuizMaterialLinker('${c.id}')" placeholder="搜尋教材名稱…" class="flex-1 px-3 py-2 border border-cyan-200 rounded-xl text-xs bg-white"><button onclick="saveQuizMaterialLinks('${c.id}')" class="bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold px-4 py-2 rounded-xl">💾 儲存關聯</button></div>
                      <div id="qmaterial-list-${c.id}" class="max-h-72 overflow-auto space-y-1.5"><p class="text-xs text-slate-400">讀取教材中…</p></div><div id="qmaterial-status-${c.id}" class="text-[11px] text-cyan-700"></div>
                  </section>
                  <section class="bg-white rounded-xl border border-slate-200 p-3">
                      <div class="flex items-start justify-between gap-3 mb-3 flex-wrap"><div><p class="text-sm font-black text-slate-900">目前正式題庫</p><p class="text-[11px] text-slate-500">可單題快速編輯，也可全選後一次展開、批次套用分類或啟用狀態。</p></div><span id="qselected-${c.id}" class="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-bold">已選 0 題</span></div>
                      <div class="mb-3 rounded-xl border border-indigo-100 bg-indigo-50/40 p-2.5 grid sm:grid-cols-[1fr_auto_auto_auto] gap-2"><input id="qfilter-text-${c.id}" oninput="renderFilteredQuestionList('${c.id}')" placeholder="🔎 搜尋題目 / 分類 / 解析" class="px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white"><select id="qfilter-type-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部題型</option><option value="choice">單選</option><option value="multi">複選</option><option value="true_false">是非</option><option value="fill">填空</option><option value="essay">問答</option><option value="image">圖片</option><option value="video">影片</option></select><select id="qfilter-difficulty-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部難度</option><option value="basic">基礎</option><option value="standard">一般</option><option value="advanced">進階</option></select><select id="qfilter-active-${c.id}" onchange="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部狀態</option><option value="active">啟用</option><option value="inactive">停用</option></select></div>
                      <div id="qtoolbar-${c.id}" class="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 flex items-center gap-2 flex-wrap">
                          <label class="text-xs font-bold text-slate-700 inline-flex items-center gap-1.5"><input id="qselect-all-${c.id}" type="checkbox" onchange="adminSelectAllQuestions('${c.id}',this.checked)" class="rounded"> 全選</label>
                          <button onclick="adminEditSelectedQuestions('${c.id}',false)" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold">✏️ 編輯已選</button>
                          <button onclick="adminEditSelectedQuestions('${c.id}',true)" class="text-[11px] bg-violet-700 hover:bg-violet-600 text-white px-3 py-1.5 rounded-lg font-bold">📝 全選編輯</button>
                          <button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存展開編輯</button>
                          <span class="h-5 w-px bg-slate-300 hidden sm:block"></span>
                          <button onclick="adminBulkSetQuestionTag('${c.id}')" class="text-[11px] bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 px-3 py-1.5 rounded-lg">🏷️ 批次分類</button>
                          <button onclick="adminBulkSetQuestionActive('${c.id}',true)" class="text-[11px] bg-white border border-emerald-200 hover:bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg">▶ 批次啟用</button>
                          <button onclick="adminBulkSetQuestionActive('${c.id}',false)" class="text-[11px] bg-white border border-amber-200 hover:bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg">⏸ 批次停用</button>
                          <button onclick="adminBulkDeleteQuestions('${c.id}')" class="text-[11px] bg-white border border-slate-200 hover:bg-rose-50 text-slate-500 hover:text-rose-700 px-3 py-1.5 rounded-lg">更多：批次刪除</button>
                          <span id="qbulk-progress-${c.id}" class="text-[11px] text-slate-500"></span>
                      </div>
                      <div id="qlist-${c.id}" class="space-y-2"></div><div id="qsticky-save-${c.id}" class="sticky bottom-2 z-20 mt-3 rounded-xl border border-teal-200 bg-white/95 backdrop-blur shadow-lg p-2.5 flex items-center justify-between gap-3"><span class="text-[11px] text-slate-500">批次編輯後可直接在此儲存，不必回頁首。</span><button onclick="adminSaveExpandedQuestionEdits('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-4 py-2 rounded-lg font-bold">💾 儲存全部修改</button></div>
                  </section>

                  <section data-ai-question-studio="${c.id}" class="rounded-2xl border border-violet-200 bg-white overflow-hidden">
                      <div class="bg-gradient-to-r from-violet-800 to-indigo-800 text-white px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
                          <div><p class="font-black">✨ AI 教材出題工作室</p><p class="text-[11px] text-violet-100 mt-0.5">選教材 → 設定題型與難度 → 產生候選題 → 人工審核 → 匯入正式題庫</p></div>
                          <span id="ai-status-${c.id}" class="text-[11px] px-2.5 py-1 rounded-full bg-white/10 ring-1 ring-white/20">檢查 AI 設定中…</span>
                      </div>
                      <div class="p-4 space-y-4">
                          <div class="grid lg:grid-cols-3 gap-3">
                              <div class="lg:col-span-3">
                                  <div class="flex items-center justify-between gap-3 mb-2"><label class="block text-xs font-black text-violet-900">① 選擇 AI 要閱讀的教材（可複選）</label><span class="text-[11px] text-slate-500">最多 4 份；影片一次最多 1 支</span></div>
                                  <div class="rounded-xl border border-violet-100 bg-violet-50/40 p-3 space-y-2.5">
                                      <div class="flex flex-col lg:flex-row gap-2 lg:items-center">
                                          <div class="relative flex-1"><span class="absolute left-3 top-2.5 text-slate-400 text-xs">🔎</span><input id="ai-material-search-${c.id}" oninput="filterAiMaterials('${c.id}')" placeholder="搜尋教材名稱、檔名…" class="w-full pl-8 pr-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"></div>
                                          <select id="ai-material-scope-${c.id}" onchange="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="linked">優先：本考卷教材</option><option value="all">查看本組全部教材</option></select>
                                          <select id="ai-material-kind-${c.id}" onchange="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="all">全部類型</option><option value="text">📄 文件</option><option value="image">🖼️ 圖片 / Atlas</option><option value="video">🎬 影片</option><option value="audio">🎧 音訊</option><option value="subtitle">💬 字幕</option></select>
                                          <button type="button" onclick="recommendAiMaterials('${c.id}')" class="px-3 py-2 rounded-xl bg-white border border-violet-200 text-violet-700 text-xs font-bold hover:bg-violet-50">✨ 建議教材</button>
                                      </div>
                                      <div id="ai-selected-${c.id}" class="min-h-[34px] rounded-lg bg-white border border-violet-100 px-2.5 py-2 text-[11px] text-slate-500">尚未選擇教材</div>
                                      <div id="ai-materials-${c.id}" data-group="${c.group}" data-area="${c.area}" class="space-y-1.5"><div class="text-xs text-slate-400">讀取本組教材中…</div></div>
                                      <div class="flex items-center justify-between gap-2"><span id="ai-material-count-${c.id}" class="text-[11px] text-slate-400"></span><button id="ai-material-more-${c.id}" type="button" onclick="loadMoreAiMaterials('${c.id}')" class="hidden text-[11px] text-violet-700 font-bold hover:underline">顯示更多教材</button></div>
                                  </div>
                                  <div class="mt-2 text-[11px] text-slate-500">💡 圖片 / Atlas 會直接做視覺分析；影片會擷取代表畫面並結合語音逐字稿。也可把「影片＋字幕＋SOP/PDF」一起選做交叉出題。</div>
                              </div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">② 題型</label><select id="ai-type-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="mixed_all">單選＋多選＋填空＋問答</option><option value="mixed_choice_multi">單選＋多選</option><option value="choice">只出單選題</option><option value="multi">只出多選題</option><option value="fill">只出填空題</option><option value="essay">只出問答題</option><option value="mixed">單選＋問答混合</option><option value="video_choice">🎬 影片即時單選題</option><option value="video_multi">🎬 影片即時多選題</option><option value="video_fill">🎬 影片即時填空題</option><option value="video_essay">🎬 影片即時問答題</option><option value="video_mixed">🎬 影片混合互動題</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">③ 難度</label><select id="ai-difficulty-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="basic">基礎</option><option value="standard" selected>標準</option><option value="advanced">進階</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">④ 題數</label><select id="ai-count-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="3">3 題</option><option value="5" selected>5 題</option><option value="10">10 題</option><option value="15">15 題</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">⑤ 出題策略</label><select id="ai-strategy-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="auto" selected>✨ 自動依教材判斷</option><option value="balanced">均衡涵蓋</option><option value="workflow">操作流程</option><option value="scenario">情境／故障排除</option><option value="safety">安全／品質／通報</option><option value="recognition">辨識／圖像判讀</option><option value="regulation">法規／SOP</option></select></div>
                              <div class="lg:col-span-2"><label class="block text-xs font-bold text-slate-600 mb-1">⑥ 特別希望考哪些重點？（選填）</label><input id="ai-focus-${c.id}" type="text" maxlength="500" placeholder="例如：故障排除、QC 設定、法定傳染病通報；留白則由 AI 自動抓重點" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"></div>
                          </div>
                          <div class="flex items-center gap-3 flex-wrap"><button id="ai-generate-${c.id}" onclick="adminGenerateAiQuestions('${c.id}')" class="bg-violet-700 hover:bg-violet-600 text-white px-4 py-2.5 rounded-xl text-sm font-black">✨ 產生候選題</button><span id="ai-progress-${c.id}" class="text-xs text-violet-700"></span></div>
                          <div id="ai-progress-wrap-${c.id}" class="hidden rounded-xl border border-violet-100 bg-violet-50/70 p-3">
                              <div class="flex items-center justify-between gap-3 text-[11px]"><span id="ai-progress-label-${c.id}" class="font-bold text-violet-800">準備 AI 出題…</span><span id="ai-progress-percent-${c.id}" class="font-black text-violet-700">0%</span></div>
                              <div class="mt-2 h-2.5 rounded-full bg-violet-100 overflow-hidden"><div id="ai-progress-bar-${c.id}" class="h-full w-0 rounded-full bg-gradient-to-r from-violet-600 via-fuchsia-500 to-indigo-500 transition-[width] duration-500"></div></div>
                              <div id="ai-progress-detail-${c.id}" class="mt-2 text-[11px] text-violet-600">正在準備教材來源。</div>
                          </div>
                          <div id="ai-candidates-${c.id}" class="space-y-3"></div>
                      </div>
                  </section>

                  <details class="bg-white rounded-xl border border-slate-200 p-3">
                      <summary class="cursor-pointer text-sm font-black text-slate-800">➕ 其他建題方式：手動新增 / 公開連結批次匯入</summary>
                      <div class="mt-3 grid lg:grid-cols-2 gap-4">
                          <div class="rounded-xl bg-slate-50 p-3 space-y-2">
                              <p class="text-xs font-black text-slate-700">手動新增單題</p>
                              <input id="qform-${c.id}-question" type="text" placeholder="題目內容" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs">
                              <div class="flex gap-2 flex-wrap"><select id="qform-${c.id}-type" onchange="updateManualQuestionType('${c.id}')" class="px-2 py-2 border rounded-lg text-xs"><option value="choice">單選題</option><option value="multi">複選題</option><option value="true_false">是非題</option><option value="fill">填空題</option><option value="essay">問答題</option><option value="image">圖片判讀題</option><option value="video_choice">🎬 影片單選題</option><option value="video_multi">🎬 影片多選題</option><option value="video_fill">🎬 影片填空題</option><option value="video_essay">🎬 影片問答題</option></select><select id="qform-${c.id}-difficulty" class="px-2 py-2 border rounded-lg text-xs"><option value="basic">基礎</option><option value="standard" selected>一般</option><option value="advanced">進階</option></select><input id="qform-${c.id}-image" type="file" accept="image/*" class="text-xs max-w-[220px]"></div>
                              <div id="qform-${c.id}-choice-options" class="grid grid-cols-1 sm:grid-cols-2 gap-2"><input id="qform-${c.id}-opt0" type="text" placeholder="選項 A" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt1" type="text" placeholder="選項 B" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt2" type="text" placeholder="選項 C" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt3" type="text" placeholder="選項 D" class="px-2.5 py-1.5 border rounded-lg text-xs"></div>
                              <div id="qform-${c.id}-choice-answer" class="flex gap-2 items-center"><label class="text-xs text-slate-500">正解</label><select id="qform-${c.id}-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">A</option><option value="1">B</option><option value="2">C</option><option value="3">D</option></select><input id="qform-${c.id}-tag" type="text" placeholder="分類標籤" class="flex-1 px-2.5 py-1.5 border rounded-lg text-xs"></div>
                              <div id="qform-${c.id}-advanced-answer" class="hidden rounded-lg border border-slate-200 bg-white p-2 space-y-2"><div id="qform-${c.id}-multi-config" class="hidden text-xs"><label class="font-bold text-slate-600">複選正解（可複選）</label><div class="flex gap-3 mt-1">${[0,1,2,3].map(j=>`<label><input id="qform-${c.id}-multi${j}" type="checkbox" class="mr-1">${String.fromCharCode(65+j)}</label>`).join('')}</div></div><div id="qform-${c.id}-truefalse-config" class="hidden text-xs"><label class="font-bold text-slate-600 mr-2">正確答案</label><select id="qform-${c.id}-truefalse-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">是</option><option value="1">否</option></select></div><div id="qform-${c.id}-fill-config" class="hidden"><label class="text-xs font-bold text-slate-600">可接受答案</label><input id="qform-${c.id}-fill-answers" class="w-full mt-1 px-2 py-1.5 border rounded text-xs" placeholder="多個答案請用 | 分隔，例如：EDTA|乙二胺四乙酸"></div><div id="qform-${c.id}-video-config" class="hidden grid sm:grid-cols-2 gap-2"><input id="qform-${c.id}-media-url" class="px-2 py-1.5 border rounded text-xs" placeholder="影片網址 / 站內媒體網址"><input id="qform-${c.id}-pause-at" type="number" min="0" step="1" class="px-2 py-1.5 border rounded text-xs" placeholder="提示時間（秒）"></div></div>
                              <textarea id="qform-${c.id}-explain" rows="2" placeholder="詳解 / 問答題評分參考" class="w-full px-2.5 py-1.5 border rounded-lg text-xs"></textarea>
                              <button onclick="adminAddQuizQuestion('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-3 py-2 rounded-lg font-bold">＋ 新增此題</button>
                          </div>
                          <div class="rounded-xl bg-indigo-50 p-3 space-y-2 self-start"><p class="text-xs font-black text-indigo-900">由公開 JSON / CSV 連結批次匯入</p><p class="text-[11px] text-indigo-700">適合 Google Sheet 發布 CSV 或既有題庫檔案。匯入後仍可逐題修改與停用。</p><input id="qimport-${c.id}" type="url" placeholder="貼上公開 JSON / CSV 網址" class="w-full px-3 py-2 border border-indigo-200 rounded-lg text-xs bg-white"><button onclick="adminImportQuizUrl('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🔗 批次匯入</button></div>
                      </div>
                  </details>
              </div>
          </article>`;
  }

  function updateQuizWorkspacePresentation(){
      const title=document.querySelector('#admin-quiz-workspace h4'); const desc=document.querySelector('#admin-quiz-workspace h4 + p');
      if(title) title.textContent='📝 題庫與考卷';
      if(desc) desc.textContent='考卷、題庫、AI 出題、出題藍圖與題目分析集中管理；預設顯示考卷。';
      document.querySelectorAll('[data-admin-role="questions-action"],[data-admin-role="exam-action"]').forEach(x=>x.classList.remove('hidden'));
  }

  window.setAdminQuizSyncStatus=setAdminQuizSyncStatus;
  window.adminHasExpandedQuestionEditor=adminHasExpandedQuestionEditor;
  window.quizCategoryCardHTML=quizCategoryCardHTML;
  window.updateQuizWorkspacePresentation=updateQuizWorkspacePresentation;
})();
