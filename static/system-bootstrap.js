/* V5.9.0 · 頁面初始化與全域事件 */
window.addEventListener('DOMContentLoaded', () => {
    // Learner exam identity still needs the hidden inputs, but the visible
    // "考核紀錄資訊" card is intentionally omitted from the assessment page.
    const examRecordInfo=document.getElementById('exam-evaluator-summary')?.closest('section');
    if(examRecordInfo){
        const identityInputs=['examinee-name','examinee-id'].map(id=>document.getElementById(id)).filter(Boolean);
        examRecordInfo.before(...identityInputs);
        examRecordInfo.remove();
    }

    // Exam draw rules and "create this in admin" guidance belong to the
    // teacher/admin workflow, not the learner-facing assessment page.
    const learnerExamTabs=document.getElementById('dynamic-exam-tabs');
    const examAdminHint=learnerExamTabs?.querySelector(':scope > .mb-3.rounded-xl');
    if(examAdminHint) examAdminHint.remove();
    const examEmptyAdminHint=document.getElementById('dynamic-exam-tabs-empty');
    if(examEmptyAdminHint){
        examEmptyAdminHint.textContent='';
        examEmptyAdminHint.setAttribute('aria-hidden','true');
        const syncLearnerExamTabsVisibility=()=>{
            const noAvailableExams=!examEmptyAdminHint.classList.contains('hidden');
            if(learnerExamTabs) learnerExamTabs.style.display=noAvailableExams?'none':'';
        };
        new MutationObserver(syncLearnerExamTabsVisibility).observe(examEmptyAdminHint,{attributes:true,attributeFilter:['class']});
        syncLearnerExamTabsVisibility();
    }

    const areaLabelEl=document.getElementById("area-banner-label"); if(areaLabelEl) areaLabelEl.textContent=trainingAreaLabel;
    loadRememberedLearnerFields();
    syncLinkedLearnerUI();
    ['examinee-name','examinee-id','progress-name','progress-empid','pgy-assess-name','pgy-assess-empid'].forEach(id=>{
        const el=document.getElementById(id); if(el) el.addEventListener('change',rememberLearnerFields);
    });
    switchGroup(GROUPS[initialGroupFromUrl] ? initialGroupFromUrl : 'grpBio');
    const initialModule=(LEARNING_MODULES[initialModuleFromUrl] && !(initialModuleFromUrl==='assessment' && currentTrainingArea!=='pgy')) ? initialModuleFromUrl : 'materials';
    switchLearningModule(initialModule);
    if(urlParams.get('admin')==='1') setTimeout(async()=>{
        // Deferred workspace integrations may register after this bootstrap
        // handler. Wait briefly for the canonical router rather than applying
        // admin-page styling and leaving the user with an empty surface.
        for(let attempt=0;attempt<20 && typeof window.toggleAdminModal!=='function';attempt+=1){
            await new Promise(resolve=>setTimeout(resolve,25));
        }
        if(typeof window.toggleAdminModal!=='function'){
            document.body?.classList.remove('admin-page-mode');
            return;
        }
        const opened=await window.toggleAdminModal(true);
        if(opened===false){
            document.body?.classList.remove('admin-page-mode');
            return;
        }
        const ws=urlParams.get('workspace');
        if(['course-materials','courses','materials','assessment','questions','exams','teacher','scoring','results','compliance','pgy','word','people','system','maintenance','audit','worker'].includes(ws) && typeof window.switchAdminWorkspace==='function'){
            await window.switchAdminWorkspace(ws,true);
        }
    },0);
});
document.addEventListener('change', (e) => {
    if (e.target?.id === 'admin-material-area') { refreshAdminMaterialCategoryOptions(); refreshAdminMaterialCourses(); }
    if (e.target?.id === 'wizard-area' || e.target?.id === 'wizard-group') renderAdminCourses();
    if (e.target?.id === 'admin-quiz-area') renderAdminQuizCategories(false);
});
(()=>{const b=document.getElementById('back-to-top');if(!b)return;const sync=()=>{const show=window.scrollY>420;b.classList.toggle('opacity-0',!show);b.classList.toggle('pointer-events-none',!show);b.classList.toggle('translate-y-3',!show)};window.addEventListener('scroll',sync,{passive:true});sync();b.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));})();
