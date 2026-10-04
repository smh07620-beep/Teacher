/* Phase F2-1 · learner reader progress convergence. */
(function(){
  'use strict';
  const cache=new Map();
  const materialById=id=>(window.cachedSlidesList||[]).find(item=>String(item.id)===String(id));
  const autoTracked=material=>Boolean(window.SmartLearning67&&window.SmartLearning67.isAutoTracked&&window.SmartLearning67.isAutoTracked(material));
  function parseId(button){
    const raw=String(button&&button.getAttribute('data-csp-click')||'');
    const match=raw.match(/'([^']+)'/);
    return match?match[1]:'';
  }
  function labelFor(material,state){
    if(state&&state.retrainingRequired)return '需要重新閱讀';
    if(state&&state.completed)return '已完成';
    const pct=Math.max(0,Math.min(100,Number(state&&state.progress||0)));
    if(pct>0)return '繼續閱讀 · '+Math.round(pct)+'%';
    return ['video','audio'].includes(material&&material.viewerMode)?'開始播放':'開始閱讀';
  }
  function statusFor(material,state){
    if(state&&state.retrainingRequired)return '⚠️ 教材已更新，請完成目前要求版本';
    if(state&&state.completed)return '✓ 已完成';
    const pct=Math.max(0,Math.min(100,Number(state&&state.progress||0)));
    if(pct>0)return '已完成 '+Math.round(pct)+'%';
    return autoTracked(material)?'系統會自動記錄閱讀進度':'完成後請人工確認';
  }
  function paint(){
    document.querySelectorAll('[data-csp-click^="openMaterial("]').forEach(button=>{
      const id=parseId(button),material=materialById(id),state=cache.get(id);
      if(!material)return;
      const label=labelFor(material,state);
      if(button.textContent&&(/閱讀|播放|%|完成/.test(button.textContent))){
        button.textContent=(['video','audio'].includes(material.viewerMode)?'▶ ':'📖 ')+label;
      }
      button.dataset.learningProgress=String(Math.round(Number(state&&state.progress||0)));
    });
    document.querySelectorAll('[data-csp-click^="markMaterialComplete("]').forEach(button=>{
      const id=parseId(button),material=materialById(id),state=cache.get(id);
      if(!material||!autoTracked(material))return;
      button.hidden=true;
      button.setAttribute('aria-hidden','true');
      let status=button.parentElement&&button.parentElement.querySelector('[data-auto-learning-status]');
      if(!status){
        status=document.createElement('div');
        status.dataset.autoLearningStatus='1';
        status.className='mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-600';
        button.insertAdjacentElement('afterend',status);
      }
      status.textContent=statusFor(material,state);
    });
    const current=window.slideViewerState&&window.slideViewerState.materialId;
    const readerComplete=document.getElementById('reader-complete');
    if(readerComplete&&autoTracked(materialById(current))){
      readerComplete.hidden=true;
      readerComplete.setAttribute('aria-hidden','true');
    }
  }
  async function hydrate(){
    try{
      const response=await fetch('/api/learning-progress',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)return;
      (data.items||[]).forEach(item=>cache.set(String(item.materialId||''),item));
      paint();
    }catch(_){}
  }
  const originalComplete=window.markMaterialComplete;
  if(typeof originalComplete==='function'){
    window.markMaterialComplete=async function(materialId){
      const material=materialById(materialId);
      if(autoTracked(material)){
        if(typeof window.openMaterial==='function')await window.openMaterial(materialId);
        paint();
        return false;
      }
      return originalComplete.apply(this,arguments);
    };
  }
  window.addEventListener('smartLearning67:progress',event=>{
    const item=event.detail||{};
    if(item.materialId)cache.set(String(item.materialId),item);
    if(item.completed&&item.materialId&&window.myCompletedMaterials){
      window.myCompletedMaterials[item.materialId]=item.lastViewedAt||true;
    }
    paint();
  });
  const originalCourseOverview=window.renderCourseOverview;
  if(typeof originalCourseOverview==='function'){
    window.renderCourseOverview=function(){
      const result=originalCourseOverview.apply(this,arguments);
      queueMicrotask(paint);
      return result;
    };
  }
  const originalSlides=window.renderSlidesGrid;
  if(typeof originalSlides==='function'){
    window.renderSlidesGrid=async function(){
      const result=await originalSlides.apply(this,arguments);
      await hydrate();
      return result;
    };
  }
  window.LearnerReadingProgressF2=Object.freeze({hydrate:hydrate,paint:paint,state:id=>cache.get(String(id||''))||null});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',hydrate,{once:true});
  else hydrate();
})();
