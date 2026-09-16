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

  window.paintAdminQuizCategories = function(cats){
    const box=document.getElementById('admin-quiz-categories-list');
    if(!box) return;
    if(!cats.length){
      box.innerHTML='<p class="text-xs text-slate-500 py-2">本組別尚未建立任何考題頁籤，請於上方輸入頁籤名稱後點擊「➕ 新增」。</p>';
      return;
    }
    box.innerHTML=cats.map(quizCategoryCardHTML).join('');
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
})();
