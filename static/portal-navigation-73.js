/* Teacher 7.3: one-shot navigation convergence.
 * Presentation only. No MutationObserver, no authorization logic, no data mutation.
 */
(function(){
  'use strict';

  const GROUP_ROUTES={
    '生化':'grpBio','鏡檢':'grpMicro','血清':'grpSero','血庫':'grpBB','細菌':'grpBact','血液':'grpHema'
  };

  function text(el,value){ if(el && el.textContent!==value) el.textContent=value; }

  function normalizeSearch(){
    const search=document.querySelector('[data-v56-search]');
    if(!search) return;
    search.addEventListener('keydown',event=>{
      if(event.key!=='Enter') return;
      const query=String(search.value||'').trim();
      if(!query) return;
      const hit=Object.entries(GROUP_ROUTES).find(([label])=>query.includes(label)||label.includes(query));
      if(hit){
        event.preventDefault();
        event.stopImmediatePropagation();
        const area=location.pathname==='/pgy'?'pgy':'internal';
        location.assign(`/system?area=${area}&group=${encodeURIComponent(hit[1])}&module=materials&from=search`);
        return;
      }
      if(query.includes('考核')||query.includes('測驗')){
        event.preventDefault();
        event.stopImmediatePropagation();
        if(location.pathname==='/') location.assign('/#pending-exams');
        else location.assign(location.pathname==='/pgy'?'/system?area=pgy&group=grpPgyDocs&module=assessment&from=search':'/#pending-exams');
        return;
      }
      if(query.includes('教材')||query.includes('課程')){
        event.preventDefault();
        event.stopImmediatePropagation();
        location.assign(location.pathname==='/pgy'?'/pgy':'/internal');
      }
    },true);
  }

  function normalizePublicPortal(){
    const path=location.pathname;
    if(path==='/' || path==='/internal' || path==='/pgy'){
        normalizeSearch();
    }

    /* Public headers are authored per page to match the supplied reference:
       home only shows Home; area pages show Home + the current area. */
  }

  function normalizeSystem(){
    if(location.pathname!=='/system' && location.pathname!=='/system.html') return;
    const params=new URLSearchParams(location.search);
    const area=params.get('area')==='pgy'?'pgy':'internal';
    const areaHref=area==='pgy'?'/pgy':'/internal';
    const areaLabel=area==='pgy'?'PGY 學習':'院內課程';

    // The breadcrumb already links back to the training area, so the primary
    // nav no longer carries a second copy of that link.
    const rootCrumb=document.querySelector('nav[aria-label="教學導覽"] a[href="/"]');
    text(rootCrumb,'首頁');
    const areaLink=document.getElementById('learning-area-link');
    if(areaLink){ areaLink.href=areaHref; text(areaLink,areaLabel); }
  }

  /* 繼續上次: newest unfinished material -> learning center, which opens it on the saved page. */
  async function resumeCard(){
    if(location.pathname!=='/') return;
    const anchor=document.getElementById('today-learning');
    if(!anchor || document.getElementById('home-resume')) return;
    try{
      const res=await fetch('/api/learning-progress',{credentials:'same-origin',cache:'no-store'});
      if(!res.ok) return; // not signed in: no card
      const data=await res.json().catch(()=>({}));
      const item=(data.items||[])
        .filter(row=>!row.completed && row.lastViewedAt && row.materialTitle && row.area && row.group)
        .sort((a,b)=>String(b.lastViewedAt).localeCompare(String(a.lastViewedAt)))[0];
      if(!item) return;
      const page=Number(item.position?.page||0), total=Number(item.position?.totalPages||0);
      const where=page&&total?`上次讀到第 ${page} / ${total} 頁`:`已完成 ${Math.round(Number(item.progress||0))}%`;
      const href=`/system?area=${encodeURIComponent(item.area)}&group=${encodeURIComponent(item.group)}&module=materials&from=home&resume=${encodeURIComponent(item.materialId)}&page=${page>0?page:''}`;
      const box=document.createElement('section');
      box.id='home-resume';
      box.className='card';
      box.setAttribute('aria-label','繼續上次');
      const info=document.createElement('div');
      const label=document.createElement('p');label.textContent='繼續上次';label.style.fontSize='var(--fs-sm)';
      const title=document.createElement('h2');title.textContent=item.materialTitle;title.style.fontSize='var(--fs-lg)';
      const sub=document.createElement('p');sub.textContent=where;sub.style.fontSize='var(--fs-sm)';
      info.append(label,title,sub);
      const link=document.createElement('a');
      link.className='btn btn-primary';link.href=href;link.textContent='繼續閱讀 →';
      box.append(info,link);
      anchor.insertAdjacentElement('afterend',box);
    }catch(_){/* convenience only */}
  }

  function install(){
    normalizePublicPortal();
    normalizeSystem();
    void resumeCard();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
