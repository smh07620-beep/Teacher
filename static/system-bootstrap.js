/* V5.9.0 · 頁面初始化與全域事件 */
window.addEventListener('DOMContentLoaded', () => {
    const areaLabelEl=document.getElementById("area-banner-label"); if(areaLabelEl) areaLabelEl.textContent=trainingAreaLabel;
    loadRememberedLearnerFields();
    syncLinkedLearnerUI();
    loadRememberedEvaluatorFields();
    ['examinee-name','examinee-id','progress-name','progress-empid','pgy-assess-name','pgy-assess-empid'].forEach(id=>{
        const el=document.getElementById(id); if(el) el.addEventListener('change',rememberLearnerFields);
    });
    const evaluatorNameEl = document.getElementById('evaluator-name');
    const evaluatorTitleEl = document.getElementById('evaluator-title');
    if (evaluatorNameEl) {
        evaluatorNameEl.addEventListener('input', applyRememberedEvaluatorTitle);
        evaluatorNameEl.addEventListener('change', () => { applyRememberedEvaluatorTitle(); rememberEvaluatorFields(); });
    }
    if (evaluatorTitleEl) evaluatorTitleEl.addEventListener('change', rememberEvaluatorFields);
    switchGroup(GROUPS[initialGroupFromUrl] ? initialGroupFromUrl : 'grpBio');
    const initialModule=(LEARNING_MODULES[initialModuleFromUrl] && !(initialModuleFromUrl==='assessment' && currentTrainingArea!=='pgy')) ? initialModuleFromUrl : 'materials';
    switchLearningModule(initialModule);
    if(urlParams.get('admin')==='1') setTimeout(async()=>{await toggleAdminModal(true);const ws=urlParams.get('workspace');if(['course-materials','courses','materials','questions','exams','teacher','scoring','results','pgy','word','people','system'].includes(ws))await switchAdminWorkspace(ws,true);},0);
});
document.addEventListener('change', (e) => {
    if (e.target?.id === 'admin-material-area') { refreshAdminMaterialCategoryOptions(); refreshAdminMaterialCourses(); }
    if (e.target?.id === 'wizard-area' || e.target?.id === 'wizard-group') renderAdminCourses();
    if (e.target?.id === 'admin-quiz-area') renderAdminQuizCategories(false);
});
(()=>{const b=document.getElementById('back-to-top');if(!b)return;const sync=()=>{const show=window.scrollY>420;b.classList.toggle('opacity-0',!show);b.classList.toggle('pointer-events-none',!show);b.classList.toggle('translate-y-3',!show)};window.addEventListener('scroll',sync,{passive:true});sync();b.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));})();
