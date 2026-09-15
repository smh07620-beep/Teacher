/* Teacher 6.7 M1/M5 unified reader progress; never exposes exam review data. */
(function(){'use strict';
  const state={material:null,lastSave:0};
  const api=(url,opts)=>fetch(url,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opts?.headers||{})},...opts});
  async function load(id){try{return await (await api(`/api/learning-progress/${encodeURIComponent(id)}`)).json()}catch(_){return {position:{},progress:0,completed:false}}}
  async function save(position,progress,completed=false){if(!state.material)return;try{await api(`/api/learning-progress/${encodeURIComponent(state.material.id)}`,{method:'PUT',body:JSON.stringify({position,progress,completed})});}catch(_){/* offline readers remain usable */}}
  function page(){return Number(window.slideViewerState?.index||0)+1}
  function total(){return Math.max(1,Number(window.slideViewerState?.pageCount||window.slideViewerState?.images?.length||1))}
  function syncPage(){const p=page(),t=total();save({page:p},Math.round(p/t*100),p>=t);}
  function externalFrame(){let frame=document.getElementById('external-media-frame');if(!frame){frame=document.createElement('iframe');frame.id='external-media-frame';frame.className='hidden w-full aspect-video rounded-lg bg-black';frame.title='YouTube 教材';frame.allow='accelerometer; autoplay; encrypted-media; picture-in-picture';frame.referrerPolicy='strict-origin-when-cross-origin';document.getElementById('media-video')?.insertAdjacentElement('afterend',frame);}return frame;}
  function bindYouTube(frame,material){
    if(frame.dataset.youtubeBound==='1')return;frame.dataset.youtubeBound='1';const watched=new Set();let last=0;
    frame.addEventListener('load',()=>frame.contentWindow?.postMessage(JSON.stringify({event:'listening',id:1}), 'https://www.youtube-nocookie.com'));
    window.addEventListener('message',event=>{if(event.source!==frame.contentWindow||!/^https:\/\/(www\.)?youtube(-nocookie)?\.com$/.test(event.origin))return;let data;try{data=typeof event.data==='string'?JSON.parse(event.data):event.data;}catch(_){return;}const info=data?.info||{},seconds=Number(info.currentTime||0),duration=Number(info.duration||0);if(!duration||Date.now()-last<15000)return;last=Date.now();watched.add(Math.floor(seconds/10));state.material=material;save({seconds},Math.min(100,seconds/duration*100),false,{duration,lastPositionSeconds:seconds,watchedBuckets:[...watched],completionThreshold:.9});});
  }
  async function openExternal(material,media,saved){
    const modal=document.getElementById('media-viewer-modal'),video=document.getElementById('media-video'),audio=document.getElementById('media-audio'),image=document.getElementById('media-image'),audioWrap=document.getElementById('media-audio-wrap'),frame=externalFrame();if(!modal||!video)return;
    [video,image,audioWrap,frame].forEach(x=>x?.classList.add('hidden'));video.pause();audio?.pause();video.removeAttribute('src');frame.removeAttribute('src');document.getElementById('media-viewer-title').textContent=material.title||'外部影音教材';
    if(media.provider==='youtube'){
      // Only a validated YouTube id is ever interpolated; arbitrary iframes are not supported.
      frame.src=`https://www.youtube-nocookie.com/embed/${encodeURIComponent(media.videoId)}?rel=0&enablejsapi=1&origin=${encodeURIComponent(location.origin)}&start=${Math.max(0,Math.floor(saved.lastPositionSeconds||0))}`;frame.classList.remove('hidden');bindYouTube(frame,material);
    }else{video.src=media.canonicalUrl;video.classList.remove('hidden');video.addEventListener('loadedmetadata',()=>{if(saved.lastPositionSeconds>0)video.currentTime=Math.min(saved.lastPositionSeconds,Math.max(0,(video.duration||0)-.25));},{once:true});window.smartLearning67BindMedia(video,material,.9);}
    modal.classList.remove('hidden');modal.classList.add('flex');document.body.style.overflow='hidden';
  }
  const originalOpen=window.openMaterial;
  window.openMaterial=async function(id){const material=(window.cachedSlidesList||[]).find(x=>x.id===id);if(!material)return originalOpen?.apply(this,arguments);state.material=material;const saved=await load(id);let external=null;try{external=(await api(`/api/materials/${encodeURIComponent(id)}/external-media`)).externalMedia;}catch(_){}if(external)return openExternal(material,external,saved);await originalOpen.apply(this,arguments);if(['slides','preview_pdf'].includes(material.viewerMode)&&saved.position?.page>0&&typeof window.goToSlidePage==='function')window.goToSlidePage(Math.min(saved.position.page-1,total()-1));const media=document.getElementById(material.viewerMode==='audio'?'media-audio':'media-video');if(['video','audio'].includes(material.viewerMode)&&media)window.smartLearning67BindMedia(media,material,.9);};
  const originalGoto=window.goToSlidePage;
  window.goToSlidePage=function(){const result=originalGoto?.apply(this,arguments);if(state.material)setTimeout(syncPage,0);return result;};
  const originalClose=window.closeSlideViewer;
  window.closeSlideViewer=function(){if(state.material)syncPage();return originalClose?.apply(this,arguments);};
  window.smartLearning67Complete=()=>{if(state.material)save({page:page()},100,true);};
  window.smartLearning67BindMedia=function(media,material,threshold=.9){
    if(!media||!material||media.dataset.smartLearningBound==='1')return;media.dataset.smartLearningBound='1';state.material=material;let last=0;const watched=new Set();
    const sync=()=>{const duration=Number(media.duration||0),seconds=Math.max(0,Number(media.currentTime||0));if(duration>0)watched.add(Math.floor(seconds/10));const progress=duration?Math.min(100,seconds/duration*100):0;save({seconds},progress,false,{duration,lastPositionSeconds:seconds,watchedBuckets:[...watched],completionThreshold:threshold});};
    media.addEventListener('timeupdate',()=>{if(Date.now()-last>15000){last=Date.now();sync();}});
    ['pause','ended'].forEach(event=>media.addEventListener(event,sync));
  };
  const legacySave=save;
  // Keep document progress calls compatible while media sends its authoritative coverage data.
  save=async function(position,progress,completed=false,media={}){if(!state.material)return;try{await api(`/api/learning-progress/${encodeURIComponent(state.material.id)}`,{method:'PUT',body:JSON.stringify({position,progress,completed,...media})});}catch(_){/* offline readers remain usable */}};
  window.teacher681SeekReviewSource=async function(source){if(!source?.materialId)return;await window.openMaterial(source.materialId);if(source.timeStart!==undefined){setTimeout(()=>{const video=document.getElementById('media-video');if(video)video.currentTime=Number(source.timeStart)||0;},350);}if(source.page!==undefined)setTimeout(()=>window.goToSlidePage?.(Math.max(0,Number(source.page||1)-1)),350);};
})();
