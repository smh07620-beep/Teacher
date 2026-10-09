/* Phase 3G · Canonical admin question-bank category runtime. */
(function(){
  'use strict';

  const quizListView78={all:[],query:'',status:'all',visible:20};
  let wizardAreaRefreshQueued = false;

  function renderQuizOverview78(list=quizListView78.all){
    const rows=Array.isArray(list)?list:[];
    const published=rows.filter(c=>c.active).length;
    const approved=rows.filter(c=>!c.active&&c.reviewStatus==='approved').length;
    const draft=Math.max(0,rows.length-published-approved);
    const values={
      'admin-quiz-total-count':rows.length,
      'admin-quiz-published-count':published,
      'admin-quiz-approved-count':approved,
      'admin-quiz-draft-count':draft,
    };
    Object.entries(values).forEach(([id,value])=>{const node=document.getElementById(id);if(node)node.textContent=String(value);});
    document.querySelector('#admin-quiz-workspace .admin-quiz-summary-line')?.setAttribute('data-product-section','overview');
    const pending=rows.reduce((sum,c)=>sum+Number(c?.reviewSummary?.pending||0),0);
    window.__teacherAssessmentPending1030=pending;
    document.dispatchEvent(new CustomEvent('teacher-assessment-pending-1030',{detail:{pending}}));
  }

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
      // Keep the teacher course/material workspace on the route's canonical
      // training area.  The HTML default can otherwise remain "pgy" even when
      // the user entered /system?area=internal, causing a successful Worker
      // publication to disappear from the visible course hub.
      if ([...wizardArea.options].some(option => option.value === currentTrainingArea)) {
        wizardArea.value = currentTrainingArea;
      }
      if (wizardSel) {
        wizardSel.innerHTML = window.groupOptionsForArea(wizardArea.value || currentTrainingArea);
        if ([...wizardSel.options].some(option => option.value === currentGroupKey)) {
          wizardSel.value = currentGroupKey;
        }
      }
      wizardArea.onchange=()=>{
        if(wizardSel){
          wizardSel.innerHTML=window.groupOptionsForArea(wizardArea.value);
          wizardSel.value=wizardSel.options[0]?.value||'';
        }
        // The legacy course list still refreshes from system-bootstrap's
        // delegated change listener.  Coalesce the richer hub refresh here:
        // replacing its DOM for every duplicated handler was what made the
        // internal-area switch appear to freeze the entire workspace.
        if (!wizardAreaRefreshQueued) {
          wizardAreaRefreshQueued = true;
          queueMicrotask(() => {
            wizardAreaRefreshQueued = false;
            window.renderAdminCourseMaterialHub?.(true);
          });
        }
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

    root.querySelectorAll('button[data-csp-click*="adminDeleteQuizQuestion"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除') btn.textContent='🗑️ 刪除';
      btn.className='text-[11px] bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-2.5 py-1.5 rounded-lg font-bold';
    });

    root.querySelectorAll('button[data-csp-click*="adminBulkDeleteQuestions"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除已選題目') btn.textContent='🗑️ 刪除已選題目';
      btn.className='text-[11px] bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-1.5 rounded-lg font-bold';
    });

    root.querySelectorAll('button[data-csp-click*="adminDeleteQuizCategory"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除考卷') btn.textContent='🗑️ 刪除考卷';
      btn.className='w-full text-left text-xs bg-white hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg font-bold';
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

  function filteredQuizCategories78(){
    const q=quizListView78.query.trim().toLowerCase();
    return quizListView78.all.filter(c=>{
      const status=quizListView78.status;
      const statusOk=status==='all'||(status==='active'&&c.active)||(status==='approved'&&!c.active&&c.reviewStatus==='approved')||(status==='draft'&&!c.active&&c.reviewStatus!=='approved');
      const text=`${c.title||''} ${c.desc||''}`.toLowerCase();
      return statusOk&&(!q||text.includes(q));
    });
  }

  function collapseQuizPanels78(box=document.getElementById('admin-quiz-categories-list')){
    box?.querySelectorAll('[id^="qpanel-"]').forEach(panel=>panel.classList.add('hidden'));
  }

  window.teacher78DeleteListedDrafts=async function(){
    const list=filteredQuizCategories78().filter(c=>!c.active&&c.reviewStatus!=='approved');
    if(!list.length)return alert('目前沒有可刪除的草稿考卷');
    const names=list.slice(0,8).map(c=>'・'+(c.name||c.title||c.id)).join('\n')+(list.length>8?`\n…共 ${list.length} 份`:'');
    if(!confirm(`確定一次刪除以下 ${list.length} 份草稿考卷？\n裡面的題目也會一併刪除，無法復原。\n\n${names}`))return;
    let ok=0,fail=0;
    for(const c of list){
      try{const r=await fetch(`/api/quiz-categories/${encodeURIComponent(c.id)}`,{method:'DELETE'});if(r.ok){ok++;delete allQuizData[c.id];}else fail++;}catch(e){fail++;}
    }
    try{Object.keys(dynamicCategoriesCache).forEach(k=>delete dynamicCategoriesCache[k]);adminQuizCategoriesCache.clear();}catch(e){}
    await window.renderAdminQuizCategories(true);
    try{await window.refreshAdminMaterialCategoryOptions();}catch(e){}
    alert(`已刪除 ${ok} 份草稿考卷`+(fail?`，${fail} 份刪除失敗，請重試`:''));
  };
  function renderQuizList78(){
    const box=document.getElementById('admin-quiz-categories-list');if(!box)return;
    const filtered=filteredQuizCategories78(),shown=filtered.slice(0,quizListView78.visible);
    renderQuizOverview78();
    box.dataset.productSection='current-work';
    box.innerHTML=`<div data-quiz-list-tools-78 class="sticky top-0 z-10 rounded-xl border border-slate-200 bg-white/95 p-2 backdrop-blur"><div class="grid gap-2 sm:grid-cols-[1fr_150px_auto]"><input value="${escapeHtml(quizListView78.query)}" data-csp-input="teacher78FilterQuizCategories(this.value)" placeholder="🔎 搜尋考卷名稱…" class="w-full rounded-xl border border-slate-300 px-3 py-1.5 text-sm"><select data-csp-change="teacher78SetQuizStatus(this.value)" class="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-sm"><option value="all" ${quizListView78.status==='all'?'selected':''}>全部狀態</option><option value="active" ${quizListView78.status==='active'?'selected':''}>已發布</option><option value="approved" ${quizListView78.status==='approved'?'selected':''}>已審核</option><option value="draft" ${quizListView78.status==='draft'?'selected':''}>草稿</option></select><span class="self-center text-xs text-slate-400">${filtered.length} 份考卷</span></div>${quizListView78.status==='draft'&&filtered.length?`<button type="button" data-csp-click="teacher78DeleteListedDrafts()" class="mt-2 w-full rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-bold text-rose-700 hover:bg-rose-100">🗑️ 一鍵刪除目前列出的 ${filtered.length} 份草稿考卷</button>`:''}</div><div data-quiz-list-items-78 class="space-y-2">${shown.length?shown.map(quizCategoryCardHTML).join(''):'<div class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center text-sm text-slate-500">沒有符合條件的考卷。</div>'}</div>${shown.length<filtered.length?`<button type="button" data-csp-click="teacher78LoadMoreQuizCategories()" class="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-50">顯示更多（尚有 ${filtered.length-shown.length} 份）</button>`:''}`;
    window.exposeQuestionDeleteActions(box);
    updateQuizWorkspacePresentation();
    collapseQuizPanels78(box);
    setTimeout(()=>collapseQuizPanels78(box),0);
  }
  window.teacher78FilterQuizCategories=value=>{quizListView78.query=String(value||'');quizListView78.visible=20;renderQuizList78();};
  window.teacher78SetQuizStatus=value=>{quizListView78.status=String(value||'all');quizListView78.visible=20;renderQuizList78();};
  window.teacher78LoadMoreQuizCategories=()=>{quizListView78.visible+=20;renderQuizList78();};
  window.paintAdminQuizCategories=function(cats){quizListView78.all=Array.isArray(cats)?cats:[];quizListView78.visible=20;renderQuizOverview78(quizListView78.all);renderQuizList78();window.TeacherContentToolPanels710?.reconcileAfterPaint?.();};

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
    const hasVisibleData=!!cached?.data?.length || !!box.querySelector('article');
    if(!hasVisibleData){
      box.innerHTML='<div class="space-y-3"><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div><div class="h-20 rounded-2xl bg-slate-100 animate-pulse"></div></div>';
    } else {
      box.classList.add('opacity-75');
    }
    setAdminQuizSyncStatus('背景同步中…','indigo');
    try{
      const res=await fetch(`/api/quiz-categories/admin?group=${group}&area=${area}`,{});
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

  function quizTeacherStatus78(c) {
      const count=Number(c?.questionCount||0);
      if(c?.active){
        const now=Date.now(), opens=c?.examWindow?.opens_at ? new Date(c.examWindow.opens_at).getTime() : 0, closes=c?.examWindow?.closes_at ? new Date(c.examWindow.closes_at).getTime() : 0;
        if(opens&&now<opens)return {primary:'查看考卷',label:'尚未開始',tone:'bg-sky-50 text-sky-700',next:'等待開放時間／檢查發布設定'};
        if(closes&&now>closes){
          const pending=Number(c?.reviewSummary?.pending||0), total=Number(c?.reviewSummary?.total||0);
          if(pending>0)return {primary:'查看考卷',label:'待批改',tone:'bg-indigo-50 text-indigo-700',next:`尚有 ${pending} 份作答待人工批改`};
          if(total>0)return {primary:'查看考卷',label:'完成',tone:'bg-violet-50 text-violet-700',next:'查看考核結果與歷史紀錄'};
          return {primary:'查看考卷',label:'已截止',tone:'bg-slate-200 text-slate-700',next:'目前沒有待批改作答'};
        }
        return {primary:'查看考卷',label:'進行中',tone:'bg-emerald-50 text-emerald-700',next:'查看作答／待批改'};
      }
      if(c?.reviewStatus==='approved')return {primary:'發布',label:'待發布',tone:'bg-sky-50 text-sky-700',next:'確認對象、期限後發布'};
      if(count>0)return {primary:'繼續編輯',label:'題目準備中',tone:'bg-indigo-50 text-indigo-700',next:'完成題目並送審'};
      return {primary:'繼續編輯',label:'草稿',tone:'bg-amber-100 text-amber-800',next:'新增或 AI 產生題目'};
  }

  function quizCategoryCardHTML(c) {
      const teacherStatus=quizTeacherStatus78(c);
      return `
          <article class="border border-slate-200 rounded-2xl bg-white shadow-sm">
              <div class="px-4 py-3 flex items-center justify-between gap-3 flex-wrap rounded-t-2xl bg-gradient-to-r from-white to-slate-50" data-quiz-row-1030>
                  <div class="min-w-0">
                      <div class="flex items-center gap-2 flex-wrap">
                          <span class="font-black text-sm text-slate-900 break-all">${escapeHtml(c.title)}</span>
                          <span class="text-[11px] px-2 py-0.5 rounded-full ${teacherStatus.tone} font-bold">${teacherStatus.label}</span>${c.blindMode?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-slate-900 text-white font-bold">導師設定：盲測</span>':''}
                          <span class="text-[10px] font-bold text-indigo-700">下一步：${escapeHtml(teacherStatus.next)}</span>
                      </div>
                      <div class="flex flex-wrap gap-1.5 mt-1.5" title="${escapeHtml(c.desc || '尚未填寫考卷說明')}"><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">👤 ${escapeHtml(examAudienceLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-slate-100 text-slate-700">🧠 題庫 ${Number(c.questionCount||0)} 題</span><span class="text-[10px] px-2 py-1 rounded-full bg-teal-50 text-teal-700">📋 ${escapeHtml(examDrawLabel(c))}</span><span class="text-[10px] px-2 py-1 rounded-full bg-emerald-50 text-emerald-700">🎯 及格 ${Number(c.passingScore||80)} 分</span>${c.publicationHash?`<span class="text-[10px] px-2 py-1 rounded-full bg-violet-50 text-violet-700" title="發布快照 SHA-256：${escapeHtml(c.publicationHash)}">🔒 快照 ${escapeHtml(c.publicationHash.slice(0,10))}</span>`:''}</div>
                  </div>
                  <div class="flex gap-2 shrink-0 items-center whitespace-nowrap">
                       <button data-admin-role="questions-action" data-quiz-primary-1030 data-csp-click="${teacherStatus.primary==='發布'?`adminOpenExamPublish('${c.id}')`:`window.openTeacherContentExam?.('${c.id}') || toggleQuizQuestionsPanel('${c.id}')`}" class="whitespace-nowrap shrink-0 text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-4 py-2 rounded-lg font-black">${escapeHtml(teacherStatus.primary)}</button>
                      <details data-quiz-overflow-78 class="relative"><summary class="list-none cursor-pointer whitespace-nowrap text-xs bg-white border border-slate-200 text-slate-600 px-3 py-2 rounded-lg font-bold" aria-label="更多考卷操作">⋯</summary><div class="absolute right-0 mt-1 z-50 flex w-48 flex-col gap-0.5 whitespace-normal bg-white border border-slate-200 shadow-xl rounded-xl p-2"><button data-admin-role="exam-action" data-csp-click="adminEditQuizCategory('${c.id}')" class="w-full text-left text-xs hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">⚙️ 管理（設定／發布）</button><button data-csp-click="adminDeleteQuizCategory('${c.id}')" class="w-full text-left text-xs hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg">🗑️ 刪除考卷</button></div></details>
                  </div>
              </div>
              <div id="qpanel-${c.id}" class="hidden border-t border-slate-200 p-4 space-y-4 rounded-b-2xl bg-slate-50/60">
                  <section id="qmaterial-link-${c.id}" class="hidden bg-cyan-50/60 rounded-xl border border-cyan-200 p-3 space-y-3">
                      <div class="flex items-start justify-between gap-3 flex-wrap"><div><p class="text-sm font-black text-cyan-950">🔗 重新關聯教材</p><p class="text-[11px] text-cyan-700 mt-1">勾選要綁定此考卷的教材。若教材原本綁定其他考卷，儲存後會改綁到目前考卷。</p></div><button data-csp-click="closeQuizMaterialLinker('${c.id}')" class="text-[11px] text-slate-500 hover:text-slate-800">收合</button></div>
                      <div class="flex gap-2"><input id="qmaterial-search-${c.id}" data-csp-input="filterQuizMaterialLinker('${c.id}')" placeholder="搜尋教材名稱…" class="flex-1 px-3 py-2 border border-cyan-200 rounded-xl text-xs bg-white"><button data-csp-click="saveQuizMaterialLinks('${c.id}')" class="bg-cyan-700 hover:bg-cyan-600 text-white text-xs font-bold px-4 py-2 rounded-xl">💾 儲存關聯</button></div>
                      <div id="qmaterial-list-${c.id}" class="max-h-72 overflow-auto space-y-1.5"><p class="text-xs text-slate-400">讀取教材中…</p></div><div id="qmaterial-status-${c.id}" class="text-[11px] text-cyan-700"></div>
                  </section>
                  <section class="bg-white rounded-xl border border-slate-200 p-3">
                      <div class="flex items-start justify-between gap-3 mb-3 flex-wrap"><div><p class="text-sm font-black text-slate-900">目前正式題庫</p><p class="text-[11px] text-slate-500">可單題快速編輯，也可全選後一次展開、批次套用分類或啟用狀態。</p></div><span id="qselected-${c.id}" class="text-[11px] px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-bold">已選 0 題</span></div>
                      <div class="mb-3 rounded-xl border border-indigo-100 bg-indigo-50/40 p-2.5 grid sm:grid-cols-[1fr_auto_auto_auto] gap-2"><input id="qfilter-text-${c.id}" data-csp-input="renderFilteredQuestionList('${c.id}')" placeholder="🔎 搜尋題目 / 分類 / 解析" class="px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white"><select id="qfilter-type-${c.id}" data-csp-change="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部題型</option><option value="choice">單選</option><option value="multi">複選</option><option value="true_false">是非</option><option value="fill">填空</option><option value="essay">問答</option><option value="image">圖片</option><option value="video">影片</option></select><select id="qfilter-difficulty-${c.id}" data-csp-change="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部難度</option><option value="basic">基礎</option><option value="standard">一般</option><option value="advanced">進階</option></select><select id="qfilter-active-${c.id}" data-csp-change="renderFilteredQuestionList('${c.id}')" class="px-2 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="">全部狀態</option><option value="active">啟用</option><option value="inactive">停用</option></select></div>
                      <div id="qtoolbar-${c.id}" class="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-2.5 flex items-center gap-2 flex-wrap">
                          <label class="text-xs font-bold text-slate-700 inline-flex items-center gap-1.5"><input id="qselect-all-${c.id}" type="checkbox" data-csp-change="adminSelectAllQuestions('${c.id}',this.checked)" class="rounded"> 全選</label>
                          <span class="text-[11px] text-slate-400">勾選題目後顯示批次操作</span>
                          <div id="qbulk-actions-${c.id}" class="hidden flex items-center gap-2 flex-wrap">
                              <button data-csp-click="adminEditSelectedQuestions('${c.id}',false)" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded-lg font-bold">✏️ 編輯已選</button>
                              <button data-csp-click="adminSaveExpandedQuestionEdits('${c.id}')" class="text-[11px] bg-teal-700 hover:bg-teal-600 text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存修改</button>
                              <details class="relative"><summary class="list-none cursor-pointer text-[11px] bg-white border border-slate-300 text-slate-700 px-3 py-1.5 rounded-lg font-bold">⋯ 批次操作</summary><div class="absolute right-0 z-40 mt-1 w-40 rounded-xl border border-slate-200 bg-white p-2 shadow-xl space-y-1"><button data-csp-click="adminBulkSetQuestionTag('${c.id}')" class="w-full text-left text-[11px] hover:bg-slate-50 px-2 py-1.5 rounded-lg">🏷️ 分類</button><button data-csp-click="adminBulkSetQuestionActive('${c.id}',true)" class="w-full text-left text-[11px] hover:bg-emerald-50 text-emerald-700 px-2 py-1.5 rounded-lg">▶ 啟用</button><button data-csp-click="adminBulkSetQuestionActive('${c.id}',false)" class="w-full text-left text-[11px] hover:bg-amber-50 text-amber-700 px-2 py-1.5 rounded-lg">⏸ 停用</button><button data-csp-click="adminBulkDeleteQuestions('${c.id}')" class="w-full text-left text-[11px] hover:bg-rose-50 text-rose-700 px-2 py-1.5 rounded-lg">🗑️ 刪除</button></div></details>
                          </div>
                          <span id="qbulk-progress-${c.id}" class="text-[11px] text-slate-500"></span>
                      </div>
                      <div id="qlist-${c.id}" class="space-y-2"></div><div id="qsticky-save-${c.id}" class="sticky bottom-2 z-20 mt-3 rounded-xl border border-teal-200 bg-white/95 backdrop-blur shadow-lg p-2.5 flex items-center justify-between gap-3"><span id="qsticky-msg-${c.id}" class="text-[11px] text-slate-500">先按題目右邊的「編輯」修改內容，再按這裡一次儲存。</span><button data-csp-click="adminSaveExpandedQuestionEdits('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-4 py-2 rounded-lg font-bold">💾 儲存全部修改</button></div>
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
                                          <div class="relative flex-1"><span class="absolute left-3 top-2.5 text-slate-400 text-xs">🔎</span><input id="ai-material-search-${c.id}" data-csp-input="filterAiMaterials('${c.id}')" placeholder="搜尋教材名稱、檔名…" class="w-full pl-8 pr-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"></div>
                                          <select id="ai-material-scope-${c.id}" data-csp-change="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="linked">優先：本考卷教材</option><option value="all">查看本組全部教材</option></select>
                                          <select id="ai-material-kind-${c.id}" data-csp-change="filterAiMaterials('${c.id}',true)" class="px-3 py-2 border border-slate-300 rounded-xl text-xs bg-white"><option value="all">全部類型</option><option value="text">📄 文件</option><option value="image">🖼️ 圖片 / Atlas</option><option value="video">🎬 影片</option><option value="audio">🎧 音訊</option><option value="subtitle">💬 字幕</option></select>
                                          <button type="button" data-csp-click="recommendAiMaterials('${c.id}')" class="px-3 py-2 rounded-xl bg-white border border-violet-200 text-violet-700 text-xs font-bold hover:bg-violet-50">✨ 建議教材</button>
                                      </div>
                                      <div id="ai-selected-${c.id}" class="min-h-[34px] rounded-lg bg-white border border-violet-100 px-2.5 py-2 text-[11px] text-slate-500">尚未選擇教材</div>
                                      <div id="ai-materials-${c.id}" data-group="${c.group}" data-area="${c.area}" class="space-y-1.5"><div class="text-xs text-slate-400">讀取本組教材中…</div></div>
                                      <div class="flex items-center justify-between gap-2"><span id="ai-material-count-${c.id}" class="text-[11px] text-slate-400"></span><button id="ai-material-more-${c.id}" type="button" data-csp-click="loadMoreAiMaterials('${c.id}')" class="hidden text-[11px] text-violet-700 font-bold hover:underline">顯示更多教材</button></div>
                                  </div>
                                  <div class="mt-2 text-[11px] text-slate-500">💡 圖片 / Atlas 會直接做視覺分析；影片會擷取代表畫面並結合語音逐字稿。也可把「影片＋字幕＋SOP/PDF」一起選做交叉出題。</div>
                              </div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">② 題型</label><select id="ai-type-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><optgroup label="綜合出題（多種題型一起出）"><option value="mixed_all">綜合：單選＋多選＋是非＋填空＋問答</option><option value="mixed_choice_multi">選擇題：單選＋多選</option><option value="mixed">選擇＋問答：單選＋問答</option></optgroup><optgroup label="單一題型"><option value="choice">單選題</option><option value="multi">多選題</option><option value="true_false">是非題</option><option value="fill">填空題</option><option value="essay">問答題</option></optgroup><optgroup label="影片互動（需先勾選一支影片）"><option value="video_mixed">🎬 影片互動題（選擇＋填空＋問答混合）</option></optgroup></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">③ 難度</label><select id="ai-difficulty-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="basic">基礎</option><option value="standard" selected>標準</option><option value="advanced">進階</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">④ 題數</label><select id="ai-count-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="3">3 題</option><option value="5" selected>5 題</option><option value="10">10 題</option><option value="15">15 題</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">⑤ 題目使用範圍</label><select id="ai-audience-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="group_only" selected>🔒 本組限定（預設）</option><option value="all_staff">🌐 全科共用</option></select></div>
                              <div><label class="block text-xs font-bold text-slate-600 mb-1">⑥ 出題策略</label><select id="ai-strategy-${c.id}" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"><option value="auto" selected>✨ 自動依教材判斷</option><option value="balanced">均衡涵蓋</option><option value="workflow">操作流程</option><option value="scenario">情境／故障排除</option><option value="safety">安全／品質／通報</option><option value="recognition">辨識／圖像判讀</option><option value="regulation">法規／SOP</option></select></div>
                              <div class="lg:col-span-2"><label class="block text-xs font-bold text-slate-600 mb-1">⑦ 特別希望考哪些重點？（選填）</label><input id="ai-focus-${c.id}" type="text" maxlength="500" placeholder="例如：故障排除、QC 設定、法定傳染病通報；留白則由 AI 自動抓重點" class="w-full px-3 py-2 border border-slate-300 rounded-xl text-sm bg-white"></div>
                          </div>
                          <div class="flex items-center gap-3 flex-wrap"><button id="ai-generate-${c.id}" data-csp-click="adminGenerateAiQuestions('${c.id}')" class="bg-violet-700 hover:bg-violet-600 text-white px-4 py-2.5 rounded-xl text-sm font-black">✨ 產生候選題</button><span id="ai-progress-${c.id}" class="text-xs text-violet-700"></span></div>
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
                              <div class="flex gap-2 flex-wrap"><select id="qform-${c.id}-type" data-csp-change="updateManualQuestionType('${c.id}')" class="px-2 py-2 border rounded-lg text-xs"><option value="choice">單選題</option><option value="multi">複選題</option><option value="true_false">是非題</option><option value="fill">填空題</option><option value="essay">問答題</option><option value="image">圖片判讀題</option><option value="video_choice">🎬 影片單選題</option><option value="video_multi">🎬 影片多選題</option><option value="video_fill">🎬 影片填空題</option><option value="video_essay">🎬 影片問答題</option></select><select id="qform-${c.id}-difficulty" class="px-2 py-2 border rounded-lg text-xs"><option value="basic">基礎</option><option value="standard" selected>一般</option><option value="advanced">進階</option></select><input id="qform-${c.id}-image" type="file" accept="image/*" class="text-xs max-w-[220px]"></div>
                              <div id="qform-${c.id}-choice-options" class="grid grid-cols-1 sm:grid-cols-2 gap-2"><input id="qform-${c.id}-opt0" type="text" placeholder="選項 A" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt1" type="text" placeholder="選項 B" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt2" type="text" placeholder="選項 C" class="px-2.5 py-1.5 border rounded-lg text-xs"><input id="qform-${c.id}-opt3" type="text" placeholder="選項 D" class="px-2.5 py-1.5 border rounded-lg text-xs"></div>
                              <div id="qform-${c.id}-choice-answer" class="flex gap-2 items-center"><label class="text-xs text-slate-500">正解</label><select id="qform-${c.id}-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">A</option><option value="1">B</option><option value="2">C</option><option value="3">D</option></select><input id="qform-${c.id}-tag" type="text" placeholder="分類標籤" class="flex-1 px-2.5 py-1.5 border rounded-lg text-xs"><select id="qform-${c.id}-audience" title="題目使用範圍" class="px-2.5 py-1.5 border rounded-lg text-xs bg-white"><option value="group_only" selected>🔒 本組限定（預設）</option><option value="all_staff">🌐 全科共用</option></select></div>
                              <div id="qform-${c.id}-advanced-answer" class="hidden rounded-lg border border-slate-200 bg-white p-2 space-y-2"><div id="qform-${c.id}-multi-config" class="hidden text-xs"><label class="font-bold text-slate-600">複選正解（可複選）</label><div class="flex gap-3 mt-1">${[0,1,2,3].map(j=>`<label><input id="qform-${c.id}-multi${j}" type="checkbox" class="mr-1">${String.fromCharCode(65+j)}</label>`).join('')}</div></div><div id="qform-${c.id}-truefalse-config" class="hidden text-xs"><label class="font-bold text-slate-600 mr-2">正確答案</label><select id="qform-${c.id}-truefalse-correct" class="px-2 py-1.5 border rounded-lg text-xs"><option value="0">是</option><option value="1">否</option></select></div><div id="qform-${c.id}-fill-config" class="hidden"><label class="text-xs font-bold text-slate-600">可接受答案</label><input id="qform-${c.id}-fill-answers" class="w-full mt-1 px-2 py-1.5 border rounded text-xs" placeholder="多個答案請用 | 分隔，例如：EDTA|乙二胺四乙酸"></div><div id="qform-${c.id}-video-config" class="hidden grid sm:grid-cols-2 gap-2"><input id="qform-${c.id}-media-url" class="px-2 py-1.5 border rounded text-xs" placeholder="影片網址 / 站內媒體網址"><input id="qform-${c.id}-pause-at" type="number" min="0" step="1" class="px-2 py-1.5 border rounded text-xs" placeholder="提示時間（秒）"></div></div>
                              <textarea id="qform-${c.id}-explain" rows="2" placeholder="詳解 / 問答題評分參考" class="w-full px-2.5 py-1.5 border rounded-lg text-xs"></textarea>
                              <button data-csp-click="adminAddQuizQuestion('${c.id}')" class="text-xs bg-teal-700 hover:bg-teal-600 text-white px-3 py-2 rounded-lg font-bold">＋ 新增此題</button>
                          </div>
                          <div class="rounded-xl bg-indigo-50 p-3 space-y-2 self-start"><p class="text-xs font-black text-indigo-900">由公開 JSON / CSV 連結批次匯入</p><p class="text-[11px] text-indigo-700">適合 Google Sheet 發布 CSV 或既有題庫檔案。匯入後仍可逐題修改與停用。</p><input id="qimport-${c.id}" type="url" placeholder="貼上公開 JSON / CSV 網址" class="w-full px-3 py-2 border border-indigo-200 rounded-lg text-xs bg-white"><button data-csp-click="adminImportQuizUrl('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🔗 批次匯入</button></div>
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
  // 考卷卡片右邊的「⋯」更多操作：貼近畫面底部時改成往上展開，
  // 避免選單被底部固定列蓋住、還要再往下捲才點得到「考卷設定」。
  document.addEventListener('toggle',event=>{
    const details=event.target;
    if(!(details instanceof HTMLDetailsElement)||!details.matches('[data-quiz-overflow-78]'))return;
    const menu=details.querySelector(':scope > div');
    const summary=details.querySelector(':scope > summary');
    if(!menu||!summary)return;
    menu.classList.remove('bottom-full','mb-1');
    menu.classList.add('mt-1');
    if(!details.open)return;
    const box=summary.getBoundingClientRect();
    const need=menu.offsetHeight+72; // 72 ≈ 底部固定版本列的高度與留白
    const below=window.innerHeight-box.bottom;
    if(below<need&&box.top>below){
      menu.classList.remove('mt-1');
      menu.classList.add('bottom-full','mb-1');
    }
  },true);

  window.adminOpenExamPublish=async function(catId){
    // 「發布」直接進到該考卷的「設定與發布」，不用再多點一次。
    try{
      if(typeof window.openTeacherContentExam!=='function')return window.toggleQuizQuestionsPanel?.(catId);
      await window.openTeacherContentExam(catId);
      window.teacherContentStudioExamAction?.('settings',catId);
    }catch(e){alert(`❌ ${e.message||'無法開啟考卷設定'}`);}
  };
  window.adminQuickReviewExam=async function(catId){
    if(!confirm('確定送審這份考卷？系統會檢查所有啟用中的題目（題幹、選項、問答題評分參考）。通過後再按「發布」即可。'))return;
    try{
      const r=await fetch(`/api/quiz-categories/${encodeURIComponent(catId)}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(d.issues?.length?`${d.error}：${d.issues.join('、')}`:(d.error||'送審失敗'));
      alert(`✅ 審核完成（${d.reviewerName||'目前登入者'}）。接著請到「繼續編輯／設定」確認適用人員與考核期間後按「發布」。`);
    }catch(e){alert(`❌ ${e.message}`);}
    await window.renderAdminQuizCategories?.(true);
  };
  window.renderQuizOverview78=renderQuizOverview78;
  window.adminHasExpandedQuestionEditor=adminHasExpandedQuestionEditor;
  window.quizCategoryCardHTML=quizCategoryCardHTML;
  window.updateQuizWorkspacePresentation=updateQuizWorkspacePresentation;
})();
