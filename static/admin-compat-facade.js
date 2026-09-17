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

// RC 7.10 presentation hotfix. Load after every canonical Teacher/admin owner
// so the Studio can route AI and question-management into dedicated panels
// without changing persistence or RBAC ownership.
(function loadTeacherContentToolPanels710(){
  if(document.querySelector('script[data-teacher-tool-panels-710]'))return;
  const script=document.createElement('script');
  script.src='/teacher-content-tool-panels-710.js?v=7101';
  script.async=false;
  script.dataset.teacherToolPanels710='1';
  document.head.appendChild(script);
})();
