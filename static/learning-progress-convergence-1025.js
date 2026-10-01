/* Product convergence: one canonical learner progress projection.
 * Presentation only. Server-side dashboard/completion/PGY rules remain authoritative.
 */
(function(){
  'use strict';

  let inflight=null;

  async function load(force=false){
    if(inflight&&!force)return inflight;
    inflight=fetch('/api/training-command-center/progress',{credentials:'same-origin',cache:'no-store'})
      .then(async response=>{
        const data=await response.json().catch(()=>({}));
        if(!response.ok)throw new Error(data.error||'學習進度讀取失敗');
        paint(data);
        return data;
      })
      .finally(()=>{inflight=null;});
    return inflight;
  }

  function setText(id,value){
    const el=document.getElementById(id);
    if(el)el.textContent=String(value);
  }

  function paintHome(data){
    const online=data?.online||{};
    const pct=Math.max(0,Math.min(100,Number(online.percent||0)));
    setText('v561-progress-percent',pct);
    const bar=document.getElementById('v561-progress-bar');
    if(bar)bar.style.width=`${pct}%`;
  }

  function paintSystem(data){
    const online=data?.online||{};
    const onlinePct=Math.max(0,Math.min(100,Number(online.percent||0)));
    const pgy=data?.pgy;
    const summary=document.getElementById('training-progress-summary-71');
    if(summary){
      summary.textContent=data?.pgyLearner&&pgy
        ? `線上學習 ${onlinePct}% · PGY 指派 ${Number(pgy.percent||0).toFixed(0)}%`
        : `學習進度 ${onlinePct}%`;
    }

    document.querySelectorAll('#learning-analytics-stats-71 > div').forEach(card=>{
      const label=card.firstElementChild?.textContent?.trim();
      const value=card.children?.[1];
      if(!value)return;
      if(label==='整體學習進度')value.textContent=`${onlinePct}%`;
      if(label==='教材完成')value.textContent=`${Number(online.materialsCompleted||0)}/${Number(online.materialsTotal||0)}`;
      if(label==='進行中課程')value.textContent=String(Number(online.activeCourses||0));
      if(label==='PGY 指派完成'&&pgy)value.textContent=`${Number(pgy.percent||0).toFixed(1)}%`;
    });

    if(data?.pgyLearner&&pgy){
      document.querySelectorAll('#pgy-matrix-stats-71 > div').forEach(card=>{
        const label=card.firstElementChild?.textContent?.trim();
        const value=card.children?.[1];
        if(label==='指派完成率'&&value)value.innerHTML=`${Number(pgy.percent||0).toFixed(1)}<span class="text-[9px] text-slate-400 ml-1">%</span>`;
        if(label==='逾期指派'&&value)value.textContent=String(Number(pgy.assignmentsOverdue||0));
      });
    }
  }

  function paint(data){
    paintHome(data);
    paintSystem(data);
    document.documentElement.dataset.progressSource='training-command-center';
  }

  function init(){load(false).catch(()=>{});}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();

  window.TeacherLearningProgress1025=Object.freeze({load,paint});
})();
