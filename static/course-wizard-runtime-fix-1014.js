/* Teacher 10/14 Course Wizard runtime convergence.
 *
 * Keeps the R2 direct-upload path idempotent from the browser perspective,
 * makes the finish action leave the authoring surface without re-render races,
 * and suppresses the older duplicate Worker failure card now that
 * worker-status-70.js owns that information canonically.
 */
(function(){
  'use strict';

  function patchUploadClient(){
    const client=window.MaterialUploadClient;
    const canonical=client?.enqueue;
    if(typeof canonical!=='function'||canonical.__teacherCourseWizardRuntimeFix1014)return;

    const guarded=async function(formData,options={}){
      try{
        return await canonical.call(client,formData,options);
      }catch(error){
        const body=error?.body&&typeof error.body==='object'?error.body:{};
        const existingJobId=String(body.existingJobId||'').trim();
        if(Number(error?.status)===409&&body.alreadyQueued===true&&existingJobId){
          const file=formData?.get?.('file');
          if(file instanceof Blob){
            options.onProgress?.({
              loaded:Number(file.size||0),
              total:Number(file.size||0),
              percent:100,
              fileName:options.fileName||file.name||'教材'
            });
          }
          return {
            accepted:true,
            reused:true,
            jobId:existingJobId,
            materialId:String(body.existingMaterialId||''),
            uploadId:String(body.existingUploadId||''),
            status:String(body.existingJobStatus||'queued')
          };
        }
        throw error;
      }
    };
    guarded.__teacherCourseWizardRuntimeFix1014=true;
    client.enqueue=guarded;
  }

  function patchFinishAction(){
    const canonical=window.courseWizard681OpenCourse;
    if(typeof canonical!=='function'||canonical.__teacherCourseWizardRuntimeFix1014)return;

    const safeFinish=async function(){
      const buttons=[...document.querySelectorAll('[data-csp-click="courseWizard681OpenCourse()"]')];
      buttons.forEach(button=>{button.disabled=true;button.setAttribute('aria-busy','true');});
      try{
        // Switching the workspace already owns its render lifecycle. Avoid a
        // second explicit course-hub render here because it can re-enter while
        // the background-job watcher still has callbacks in flight.
        if(typeof window.switchAdminWorkspace==='function'){
          await window.switchAdminWorkspace('course-materials',true);
        }else{
          const target='/system?module=course-materials';
          if(window.location.pathname+window.location.search!==target){
            window.location.assign(target);
            return;
          }
        }
        requestAnimationFrame(()=>{
          document.getElementById('admin-course-material-hub')?.scrollIntoView({behavior:'smooth',block:'start'});
        });
      }catch(error){
        console.error('Course Wizard finish navigation failed',error);
        window.location.assign('/system?module=course-materials');
      }finally{
        buttons.forEach(button=>{button.disabled=false;button.removeAttribute('aria-busy');});
      }
    };
    safeFinish.__teacherCourseWizardRuntimeFix1014=true;
    window.courseWizard681OpenCourse=safeFinish;
  }

  function suppressDuplicateFailurePanel(){
    const duplicate=document.getElementById('worker-recent-failures-1014');
    if(!duplicate)return;
    duplicate.hidden=true;
    duplicate.setAttribute('aria-hidden','true');
    duplicate.dataset.supersededBy='worker-status-70';
  }

  function converge(){
    patchUploadClient();
    patchFinishAction();
    suppressDuplicateFailurePanel();
  }

  const CONVERGENCE_SELECTOR='#course-wizard-681,#worker-recent-failures-1014,[data-csp-click="courseWizard681OpenCourse()"]';

  function nodeNeedsConverge(node){
    if(!(node instanceof Element))return false;
    return node.matches?.(CONVERGENCE_SELECTOR)||Boolean(node.querySelector?.(CONVERGENCE_SELECTOR));
  }

  function mutationNeedsConverge(record){
    const target=record?.target instanceof Element?record.target:null;
    if(target?.closest?.('#course-wizard-681'))return true;
    return [...(record?.addedNodes||[])].some(nodeNeedsConverge);
  }

  converge();
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',converge,{once:true});
  const observer=new MutationObserver(records=>{
    if(records.some(mutationNeedsConverge))converge();
  });
  observer.observe(document.body||document.documentElement,{childList:true,subtree:true});
})();
