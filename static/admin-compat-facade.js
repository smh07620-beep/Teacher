/* Final convergence compatibility facade.
 *
 * Canonical feature owners live in the extracted admin modules and
 * course-wizard-681.js. This file preserves legacy HTML/window entry points
 * while routing them to their canonical owners. Do not add new business logic
 * here.
 */
(function(){
  'use strict';

  function callOwner(name,args){
    const fn=window[name];
    if(typeof fn!=='function'){
      console.error(`Compatibility owner unavailable: ${name}`);
      return undefined;
    }
    return fn.apply(window,args||[]);
  }

  // Legacy Course Wizard HTML contracts. The canonical owner is
  // course-wizard-681.js; the old implementation in system-admin.js is now a
  // fallback only and is deliberately shadowed after all feature modules load.
  window.adminCreateCourseBundle=function(){
    return callOwner('courseWizard681Create',arguments);
  };
  window.resetCourseWizardForm=function(){
    return callOwner('courseWizard681Reset',arguments);
  };

  window.__teacherAdminCompatibilityFacade=Object.freeze({
    version:'final-convergence-1',
    owners:Object.freeze({
      adminCreateCourseBundle:'courseWizard681Create',
      resetCourseWizardForm:'courseWizard681Reset'
    })
  });
})();

// RC 7.11 presentation hotfix.
// AI / 題目管理在 dedicated panel runtime 載入完成前先排隊，避免舊的
// mountAiPanel() 被搶先呼叫而再次碰到 Tailwind selector 的 closest() 錯誤。
(function loadTeacherContentToolPanels711(){
  'use strict';

  const previousExamAction=window.teacherContentStudioExamAction;
  let resolveReady;
  let rejectReady;
  const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
  window.__teacherContentToolPanelsReady711=ready;

  function showLoadError(catId,action,error){
    const host=document.getElementById('teacher-content-studio-body-71');
    if(!host)return;
    const label=action==='ai'?'AI 輔助出題':'題目管理';
    const message=error?.message||'功能面板載入失敗，請重新整理後再試。';
    host.innerHTML=`<div class="mx-auto max-w-4xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700"><div class="font-black">❌ ${label}暫時無法開啟</div><div class="mt-1">${window.escapeHtml?window.escapeHtml(message):message}</div><div class="mt-4"><button type="button" class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold" onclick="window.openTeacherContentExam?.('${String(catId||'').replace(/'/g,"\\'")}')">返回考卷</button></div></div>`;
  }

  // Until the dedicated runtime arrives, never fall through AI/questions to the
  // old Studio implementation. Other exam actions keep their original owner.
  window.teacherContentStudioExamAction=async function(action,catId){
    if(action!=='ai'&&action!=='questions'){
      return typeof previousExamAction==='function'?previousExamAction(action,catId):undefined;
    }
    try{
      await ready;
      const api=window.TeacherContentToolPanels710;
      if(!api)throw new Error('專用功能面板尚未完成初始化。');
      return action==='ai'?api.openAi(catId):api.openQuestions(catId);
    }catch(error){
      showLoadError(catId,action,error);
      return undefined;
    }
  };

  const existing=document.querySelector('script[data-teacher-tool-panels-710]');
  if(existing){
    if(window.TeacherContentToolPanels710){resolveReady(window.TeacherContentToolPanels710);return;}
    existing.addEventListener('load',()=>resolveReady(window.TeacherContentToolPanels710),{once:true});
    existing.addEventListener('error',()=>rejectReady(new Error('專用功能面板下載失敗。')),{once:true});
    return;
  }

  const script=document.createElement('script');
  script.src='/teacher-content-tool-panels-710.js?v=7110';
  script.async=false;
  script.dataset.teacherToolPanels710='1';
  script.addEventListener('load',()=>resolveReady(window.TeacherContentToolPanels710),{once:true});
  script.addEventListener('error',()=>rejectReady(new Error('專用功能面板下載失敗。')),{once:true});
  document.head.appendChild(script);
})();
