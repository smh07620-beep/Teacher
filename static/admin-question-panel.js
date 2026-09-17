/* Phase 3V · Question-bank panel/category shell runtime.
 * CRUD/editor details live in the other extracted question modules; this slice
 * owns category create/delete plus panel/manual-form orchestration.
 */
(function(){
  'use strict';

  window.updateManualQuestionType = function(catId){
    const raw=document.getElementById(`qform-${catId}-type`)?.value||'choice';
    const isVideo=raw.startsWith('video_');
    const type=isVideo?raw.slice(6):raw;
    const needs=['choice','multi','image'].includes(type);
    document.getElementById(`qform-${catId}-choice-options`)?.classList.toggle('hidden',!needs);
    document.getElementById(`qform-${catId}-choice-answer`)?.classList.toggle('hidden',!['choice','image'].includes(type));
    document.getElementById(`qform-${catId}-advanced-answer`)?.classList.toggle('hidden',!['multi','true_false','fill'].includes(type)&&!isVideo);
    document.getElementById(`qform-${catId}-multi-config`)?.classList.toggle('hidden',type!=='multi');
    document.getElementById(`qform-${catId}-truefalse-config`)?.classList.toggle('hidden',type!=='true_false');
    document.getElementById(`qform-${catId}-fill-config`)?.classList.toggle('hidden',type!=='fill');
    document.getElementById(`qform-${catId}-video-config`)?.classList.toggle('hidden',!isVideo);
    const exp=document.getElementById(`qform-${catId}-explain`);
    if(exp) exp.placeholder=type==='essay'?'評分重點／參考答案（選填）':(type==='true_false'?'答案依據／解析（選填）':(type==='fill'?'答案解析（選填）':'詳解（選填，作答後顯示）'));
  };

  window.loadQuizQuestionCountOnly = async function(catId){
    try{
      const res=await fetch(`/api/quiz-questions?category=${encodeURIComponent(catId)}`);
      const qs=await res.json().catch(()=>[]);
      if(!res.ok) return;
      const el=document.getElementById(`qcount-${catId}`);
      if(el) el.textContent=(Array.isArray(qs)?qs:[]).filter(q=>q.active!==false).length;
    }catch(_err){
      // Count refresh is best-effort and must not disrupt current editing state.
    }
  };

  window.toggleQuizQuestionsPanel = function(catId){
    const panel=document.getElementById(`qpanel-${catId}`);
    if(!panel) return Promise.resolve(null);
    const wasHidden=panel.classList.contains('hidden');
    panel.classList.toggle('hidden');
    if(!wasHidden) return Promise.resolve(panel);

    // RC 7.10: opening the panel must be immediate. Question rows, linked
    // materials and AI provider status are independent secondary hydrations;
    // waiting for them serially caused 2–5 minute apparent freezes on Render.
    const jobs=[
      Promise.resolve().then(()=>window.loadQuizQuestionsIntoPanel(catId)),
      Promise.resolve().then(()=>typeof window.loadAiMaterialOptions==='function' ? window.loadAiMaterialOptions(catId) : null),
      Promise.resolve().then(()=>typeof window.refreshAiQuestionStatus==='function' ? window.refreshAiQuestionStatus(catId) : null)
    ];
    panel._questionPanelHydration=Promise.allSettled(jobs);
    return Promise.resolve(panel);
  };

  window.adminCreateQuizCategory = async function(){
    const key=await getAdminKey();
    if(!key) return;
    const group=document.getElementById('admin-quiz-group')?.value;
    const titleInput=document.getElementById('admin-new-category-title');
    const title=titleInput?.value.trim()||'';
    if(!group||!title){ alert('請輸入頁籤名稱'); return; }
    const area=document.getElementById('admin-quiz-area')?.value||currentTrainingArea;
    const res=await fetch('/api/quiz-categories',{
      method:'POST',
      headers:{'Content-Type':'application/json','X-Admin-Key':key},
      body:JSON.stringify({group,area,title})
    });
    const data=await res.json().catch(()=>({}));
    if(!res.ok){ alert(data.error||'新增失敗'); return; }
    titleInput.value='';
    Object.keys(dynamicCategoriesCache).filter(k=>k.endsWith(':'+group)).forEach(k=>delete dynamicCategoriesCache[k]);
    window.optimisticInsertQuizCategory({...data,questionCount:0},area,group);
    Promise.allSettled([
      window.renderAdminQuizCategories(true),
      document.getElementById('admin-material-group')?.value===group ? window.refreshAdminMaterialCategoryOptions() : Promise.resolve()
    ]);
  };

  window.adminDeleteQuizCategory = async function(catId){
    if(!confirm('確定刪除此考題頁籤？頁籤內所有題目也會一併刪除，此操作無法復原。')) return;
    const key=await getAdminKey();
    if(!key) return;
    const group=document.getElementById('admin-quiz-group')?.value||currentGroupKey;
    const res=await fetch(`/api/quiz-categories/${encodeURIComponent(catId)}`,{method:'DELETE',headers:{'X-Admin-Key':key}});
    const data=await res.json().catch(()=>({}));
    if(!res.ok){ alert(data.error||'刪除失敗'); return; }
    Object.keys(dynamicCategoriesCache).filter(k=>k.endsWith(':'+group)).forEach(k=>delete dynamicCategoriesCache[k]);
    delete allQuizData[catId];
    adminQuizCategoriesCache.delete(adminScopeKey(document.getElementById('admin-quiz-area')?.value||currentTrainingArea,group));
    await window.renderAdminQuizCategories(true);
    await window.refreshAdminMaterialCategoryOptions();
  };
})();