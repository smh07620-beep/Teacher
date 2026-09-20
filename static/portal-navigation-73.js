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
        location.assign(location.pathname==='/pgy'?'/pgy#rotations':'/internal');
      }
    },true);
  }

  function normalizePublicPortal(){
    const path=location.pathname;
    if(path==='/' || path==='/internal' || path==='/pgy'){
        normalizeSearch();
    }

    if(path==='/pgy'){
      const nav=document.querySelector('.v56-header .v56-nav');
      if(nav){
        nav.replaceChildren();
        const items=[
          ['首頁','/'],
          ['院內課程','/internal'],
          ['PGY','/pgy']
        ];
        items.forEach(([label,href],index)=>{
          const link=document.createElement('a');
          link.href=href;
          link.textContent=label;
          if(index===2){link.classList.add('active');link.setAttribute('aria-current','page');}
          nav.appendChild(link);
        });
      }
    }
  }

  function normalizeSystem(){
    if(location.pathname!=='/system' && location.pathname!=='/system.html') return;
    const params=new URLSearchParams(location.search);
    const area=params.get('area')==='pgy'?'pgy':'internal';
    const areaHref=area==='pgy'?'/pgy':'/internal';
    const areaLabel=area==='pgy'?'PGY 學習':'院內課程';

    const nav=document.querySelector('.v575-system-nav');
    if(nav && !nav.querySelector('[data-portal73-area-link]')){
      const link=document.createElement('a');
      link.dataset.portal73AreaLink='1';
      link.href=areaHref;
      link.textContent=areaLabel;
      const manage=nav.querySelector('.v575-manage-direct');
      if(manage) nav.insertBefore(link,manage); else nav.appendChild(link);
    }

    const rootCrumb=document.querySelector('nav[aria-label="教學導覽"] a[href="/"]');
    text(rootCrumb,'首頁');
    const areaLink=document.getElementById('learning-area-link');
    if(areaLink){ areaLink.href=areaHref; text(areaLink,areaLabel); }

    const back=[...document.querySelectorAll('button')].find(button=>button.getAttribute('onclick')?.includes('goBackLearning'));
    if(back) text(back,`← 回${areaLabel}`);
  }

  function install(){
    normalizePublicPortal();
    normalizeSystem();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
