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
