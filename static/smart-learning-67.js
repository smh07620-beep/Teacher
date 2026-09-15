/* Teacher 6.7 M1/M5 unified reader progress; never exposes exam review data. */
(function(){'use strict';
  const state={material:null,lastSave:0};
  const api=(url,opts)=>fetch(url,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opts?.headers||{})},...opts});
  async function load(id){try{return await (await api(`/api/learning-progress/${encodeURIComponent(id)}`)).json()}catch(_){return {position:{},progress:0,completed:false}}}
  async function save(position,progress,completed=false){if(!state.material)return;try{await api(`/api/learning-progress/${encodeURIComponent(state.material.id)}`,{method:'PUT',body:JSON.stringify({position,progress,completed})});}catch(_){/* offline readers remain usable */}}
  function page(){return Number(window.slideViewerState?.index||0)+1}
  function total(){return Math.max(1,Number(window.slideViewerState?.pageCount||window.slideViewerState?.images?.length||1))}
  function syncPage(){const p=page(),t=total();save({page:p},Math.round(p/t*100),p>=t);}
  const originalOpen=window.openMaterial;
  window.openMaterial=async function(id){const material=(window.cachedSlidesList||[]).find(x=>x.id===id);if(!material)return originalOpen?.apply(this,arguments);state.material=material;const saved=await load(id);await originalOpen.apply(this,arguments);if(['slides','preview_pdf'].includes(material.viewerMode)&&saved.position?.page>0&&typeof window.goToSlidePage==='function')window.goToSlidePage(Math.min(saved.position.page-1,total()-1));};
  const originalGoto=window.goToSlidePage;
  window.goToSlidePage=function(){const result=originalGoto?.apply(this,arguments);if(state.material)setTimeout(syncPage,0);return result;};
  const originalClose=window.closeSlideViewer;
  window.closeSlideViewer=function(){if(state.material)syncPage();return originalClose?.apply(this,arguments);};
  window.smartLearning67Complete=()=>{if(state.material)save({page:page()},100,true);};
  window.smartLearning67BindMedia=function(media,material,threshold=80){
    if(!media||!material)return;state.material=material;let last=0;
    const sync=()=>{const duration=Number(media.duration||0),seconds=Math.max(0,Number(media.currentTime||0)),progress=duration?Math.min(100,seconds/duration*100):0;save({seconds},progress,progress>=threshold);};
    media.addEventListener('timeupdate',()=>{if(Date.now()-last>15000){last=Date.now();sync();}});
    ['pause','ended'].forEach(event=>media.addEventListener(event,sync));
  };
})();
