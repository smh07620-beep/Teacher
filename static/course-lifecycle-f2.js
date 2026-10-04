/* Phase F2-2 · explicit course publication lifecycle. */
(function(){
  'use strict';
  async function json(url,options={}){
    const response=await fetch(url,{
      credentials:'same-origin',
      cache:'no-store',
      headers:{'Content-Type':'application/json',...(options.headers||{})},
      ...options
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      const error=new Error(data.error||'課程狀態操作失敗');
      error.data=data;
      throw error;
    }
    return data;
  }
  function blockerText(readiness){
    return (readiness?.blockers||[])
      .map(item=>'• '+String(item.message||item.code||'尚未完成'))
      .join('\n');
  }
  async function refresh(){
    if(typeof window.renderAdminCourseMaterialHub!=='function')return;
    await window.renderAdminCourseMaterialHub(true);
    const box=document.getElementById('admin-course-material-hub');
    await box?._adminCourseMaterialRefresh;
  }
  async function action(courseId,kind){
    try{
      if(kind==='check'){
        const readiness=await json('/api/courses/'+encodeURIComponent(courseId)+'/readiness');
        if(!readiness.ready){
          alert('目前還不能發布：\n'+blockerText(readiness));
          return;
        }
        await json('/api/courses/'+encodeURIComponent(courseId)+'/lifecycle',{
          method:'POST',
          body:JSON.stringify({action:'mark_ready'})
        });
        await refresh();
        return;
      }
      const message={
        publish:'確定正式發布這門課程？發布後已指派範圍的學員即可看到。',
        end:'確定結束這門課程？學員端將不再提供新的課程入口。',
        archive:'確定封存這門課程？',
        reopen:'確定重新開啟為草稿？重新發布前學員不會看到。'
      }[kind];
      if(message&&!confirm(message))return;
      await json('/api/courses/'+encodeURIComponent(courseId)+'/lifecycle',{
        method:'POST',
        body:JSON.stringify({action:kind})
      });
      await refresh();
    }catch(error){
      const readiness=error?.data?.readiness;
      alert((error.message||'操作失敗')+(readiness&&!readiness.ready?'\n'+blockerText(readiness):''));
    }
  }
  function makeButton(label,courseId,kind,className){
    const button=document.createElement('button');
    button.type='button';
    button.className=className||'text-[10px] rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1.5 font-bold text-violet-800';
    button.textContent=label;
    button.addEventListener('click',event=>{
      event.preventDefault();
      event.stopPropagation();
      void action(courseId,kind);
    });
    return button;
  }
  function decorate(root=document){
    root.querySelectorAll?.('[data-course-lifecycle-actions]').forEach(host=>{
      const card=host.closest('[data-course-id]');
      const courseId=String(card?.dataset.courseId||host.dataset.courseLifecycleActions||'');
      const status=String(card?.dataset.courseLifecycle||'draft');
      host.replaceChildren();
      if(status==='draft'){
        host.appendChild(makeButton('發布檢查',courseId,'check'));
      }else if(status==='ready'){
        host.appendChild(makeButton('正式發布',courseId,'publish','text-[10px] rounded-lg bg-emerald-700 px-2.5 py-1.5 font-bold text-white'));
        host.appendChild(makeButton('回到草稿',courseId,'reopen'));
      }else if(status==='published'){
        host.appendChild(makeButton('結束課程',courseId,'end'));
      }else if(status==='ended'){
        host.appendChild(makeButton('封存',courseId,'archive'));
        host.appendChild(makeButton('重新編輯',courseId,'reopen'));
      }else if(status==='archived'){
        host.appendChild(makeButton('重新開啟草稿',courseId,'reopen'));
      }
    });
  }
  document.addEventListener('teacher-course-surface-rendered-1014',event=>decorate(event.target));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>decorate(),{once:true});
  else decorate();
  window.CourseLifecycleF2=Object.freeze({decorate,action});
})();
