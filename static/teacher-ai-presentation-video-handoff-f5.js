/* Phase F5-4 · direct approved PowerPoint -> AI video studio handoff. */
(async function(){
  'use strict';
  const R=await (window.TeacherRBAC681Ready||Promise.resolve(window.TeacherRBAC681||{}));
  const roles=R.roles instanceof Set?R.roles:new Set();
  if(!['clinical_teacher','group_leader','education_admin','system_admin'].some(role=>roles.has(role)))return;

  async function load(id){
    const response=await fetch('/api/ai-presentations/'+encodeURIComponent(id),{credentials:'same-origin',cache:'no-store'});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||'無法讀取 PowerPoint revision');
    return data;
  }

  function decorate(root=document){
    root.querySelectorAll?.('#teacher-ai-presentation-results-1016 [data-presentation-id]').forEach(card=>{
      if(card.querySelector('[data-presentation-video-f5]'))return;
      const row=card.querySelector('[data-action]')?.parentElement;
      if(!row)return;
      const button=document.createElement('button');
      button.type='button';
      button.dataset.presentationVideoF5='1';
      button.className='rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 font-bold text-indigo-800';
      button.textContent='🎬 製作教學影片';
      button.addEventListener('click',async event=>{
        event.preventDefault();
        const id=String(card.dataset.presentationId||'');
        if(!id)return;
        button.disabled=true;
        try{
          const item=await load(id);
          if(!['approved','published'].includes(String(item.status||'')))throw new Error('PowerPoint 必須先由授課教師核准。');
          if(!item.artifactReady)throw new Error('PowerPoint PPTX artifact 尚未完成。');
          window.dispatchEvent(new CustomEvent('teacher-ai-presentation-video-request',{
            detail:{presentationId:id,materialId:String(item.materialId||''),title:String(item.title||'')}
          }));
        }catch(error){
          alert(error.message||'無法進入教學影片製作');
        }finally{
          button.disabled=false;
        }
      });
      row.appendChild(button);
    });
  }

  const observer=new MutationObserver(records=>{
    if(records.some(record=>[...(record.addedNodes||[])].some(node=>node instanceof Element&&(node.matches?.('[data-presentation-id]')||node.querySelector?.('[data-presentation-id]')))))decorate();
  });
  observer.observe(document.body,{childList:true,subtree:true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>decorate(),{once:true});
  else decorate();
  window.TeacherAIVideoHandoffF5=Object.freeze({decorate});
})();
