/* Teacher 7.3: one-shot navigation convergence.
 * Presentation only. No MutationObserver, no authorization logic, no data mutation.
 */
(function(){
  'use strict';

  function text(el,value){ if(el && el.textContent!==value) el.textContent=value; }

  function normalizePublicPortal(){
    const path=location.pathname;
    if(path==='/' || path==='/internal' || path==='/pgy'){
      document.querySelectorAll('.v575-manage-direct').forEach(entry=>entry.remove());
    }

    if(path==='/pgy'){
      const nav=document.querySelector('.v56-header .v56-nav');
      if(nav){
        nav.replaceChildren();
        const items=[
          ['首頁','/'],
          ['PGY 學習','/pgy'],
          ['輪訓組別','#rotations']
        ];
        items.forEach(([label,href],index)=>{
          const link=document.createElement('a');
          link.href=href;
          link.textContent=label;
          if(index===1) link.classList.add('active');
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
