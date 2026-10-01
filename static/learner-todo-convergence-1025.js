/* P1 Product Convergence · one learner 我的待辦 source on portal surfaces.
 * Read-only projection: /api/training-command-center remains authoritative.
 */
(function(){
  'use strict';

  const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function taskHref(item){
    if(item?.target==='pgy-workflow') return '/system?area=pgy&group=grpNew&module=assessment&from=home';
    const moduleName=item?.target==='exam'?'exam':'materials';
    const query=new URLSearchParams({
      area:item?.area||'internal',
      group:item?.group||'grpBio',
      module:moduleName,
      from:'home'
    });
    if(moduleName==='exam'&&item?.resourceId)query.set('examId',String(item.resourceId));
    if(item?.courseId)query.set('courseId',String(item.courseId));
    if(['material','retraining'].includes(item?.kind)&&item?.resourceId)query.set('materialId',String(item.resourceId));
    return `/system?${query.toString()}`;
  }

  function badgeLabel(item){
    if(item?.overdue)return '逾期';
    if(item?.kind==='retraining')return '重訓';
    if(item?.kind==='exam')return item?.status==='remediation'?'補強再測':'考核';
    if(item?.kind==='material')return '教材';
    if(item?.kind==='course')return '必修';
    if(item?.domain==='pgy')return 'PGY';
    return item?.statusLabel||'待辦';
  }

  function render(command){
    const list=document.getElementById('v571-pending-exams');
    const count=document.getElementById('v681-home-todo-count');
    if(!list&&!count)return;
    const items=(Array.isArray(command?.items)?command.items:[]).filter(item=>item?.persona==='learner');
    if(count)count.textContent=String(items.length);
    if(!list)return;
    list.dataset.learnerTodoSource='training-command-center';
    list.innerHTML=items.length?items.slice(0,8).map(item=>{
      const due=item?.dueAt?`${item?.overdue?'已逾期':'期限'} ${String(item.dueAt).slice(0,10)}`:'';
      const detail=[due,item?.detail||''].filter(Boolean).join(' · ');
      return `<a class="v56-assessment-row phase3-home-task-row" href="${taskHref(item)}"><span class="v56-assessment-badge ${item?.kind==='course'||item?.kind==='material'?'material':''}">${escapeHtml(badgeLabel(item))}</span><span><strong>${escapeHtml(item?.title||'待處理項目')}</strong><span>${escapeHtml(detail||item?.statusLabel||'前往處理')}</span></span><b aria-hidden="true">›</b></a>`;
    }).join(''):'<div class="v56-empty">目前沒有待辦，今天可以依自己的節奏繼續學習。</div>';
  }

  async function load(){
    try{
      const authResponse=await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store'});
      const auth=await authResponse.json().catch(()=>({}));
      if(!authResponse.ok||!auth?.authenticated)return;
      const response=await fetch('/api/training-command-center',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data?.error||'無法讀取我的待辦');
      render(data);
    }catch(_){
      // Keep the existing portal fallback if the canonical projection is temporarily unavailable.
    }
  }

  function init(){
    load();
    // portal-v56 loads its progress dashboard independently; re-apply once after
    // that async paint so the visible task list/count always ends on the canonical source.
    window.setTimeout(load,800);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
