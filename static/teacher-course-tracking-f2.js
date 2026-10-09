/* Phase F2-3 · course-centric teacher follow-up. */
(function(){
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function ensureDialog(){
    let dialog=document.getElementById('teacher-course-tracking-f2');
    if(dialog)return dialog;
    dialog=document.createElement('dialog');
    dialog.id='teacher-course-tracking-f2';
    dialog.className='rounded-2xl border border-slate-200 p-0 shadow-2xl backdrop:bg-slate-900/40 w-[min(980px,94vw)]';
    dialog.innerHTML='<div class="p-5"><div class="flex items-start justify-between gap-3"><div><h3 class="text-lg font-black text-slate-900" data-tracking-title>課程學習成果</h3><p class="text-xs text-slate-500 mt-1">只顯示既有指派、閱讀進度、考試紀錄與匿名回饋統計，不產生推測分數。</p></div><button type="button" data-tracking-close class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs">關閉</button></div><div class="mt-3 flex gap-1 border-b border-slate-200" role="tablist"><button type="button" role="tab" data-tracking-tab="progress" class="px-3 py-1.5 text-xs font-bold border-b-2 border-teal-600 text-teal-800">📊 學員進度</button><button type="button" role="tab" data-tracking-tab="feedback" class="px-3 py-1.5 text-xs font-bold border-b-2 border-transparent text-slate-500">💬 回饋彙總</button></div><div data-tracking-body class="mt-4"></div><div data-tracking-feedback class="mt-4 hidden"></div></div>';
    dialog.querySelectorAll('[data-tracking-tab]').forEach(tab=>tab.addEventListener('click',()=>showTab(dialog,tab.dataset.trackingTab)));
    dialog.querySelector('[data-tracking-close]')?.addEventListener('click',()=>dialog.close());
    document.body.appendChild(dialog);
    return dialog;
  }
  function showTab(dialog,name){
    dialog.querySelectorAll('[data-tracking-tab]').forEach(tab=>{
      const on=tab.dataset.trackingTab===name;
      tab.classList.toggle('border-teal-600',on);tab.classList.toggle('text-teal-800',on);
      tab.classList.toggle('border-transparent',!on);tab.classList.toggle('text-slate-500',!on);
    });
    dialog.querySelector('[data-tracking-body]').classList.toggle('hidden',name!=='progress');
    dialog.querySelector('[data-tracking-feedback]').classList.toggle('hidden',name!=='feedback');
  }
  async function loadFeedback(dialog,courseId){
    const out=dialog.querySelector('[data-tracking-feedback]');
    out.innerHTML='<div class="p-6 text-center text-sm text-slate-500">讀取回饋彙總中…</div>';
    try{
      const res=await fetch('/api/course-feedback/'+encodeURIComponent(courseId)+'/summary',{credentials:'same-origin',cache:'no-store'});
      const data=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(data.error||'無法讀取回饋彙總');
      const count=Number(data.responseCount||0),average=Number(data.averageRating||0),counts=data.ratingCounts||{};
      out.innerHTML='<div class="flex flex-wrap items-center gap-2 text-sm"><span class="rounded-lg bg-slate-100 px-3 py-1 font-bold">回覆 '+count+' 份</span><span class="rounded-lg bg-slate-100 px-3 py-1 font-bold">平均 '+(count?average.toFixed(1):'—')+' / 5</span></div><div class="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">'+[5,4,3,2,1].map(n=>'<span>'+n+' 分：'+Number(counts[String(n)]||0)+'</span>').join('')+'</div><p class="mt-3 text-[11px] text-slate-400">只顯示匿名統計，不列出個別學員與留言。</p>';
    }catch(error){
      out.innerHTML='<div class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">'+esc(error.message||'無法讀取回饋彙總')+'</div>';
    }
  }
  const statusLabel=status=>({notStarted:'未開始',inProgress:'進行中',completed:'已完成'})[status]||status;
  function render(data,courseId){
    const dialog=ensureDialog();
    const course=(data.courses||[]).find(row=>String(row.courseId)===String(courseId))||(data.courses||[])[0];
    const body=dialog.querySelector('[data-tracking-body]');
    if(!course){
      body.innerHTML='<div class="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">此課程目前沒有有效學習指派。</div>';
      return;
    }
    dialog.querySelector('[data-tracking-title]').textContent=(course.title||'課程')+'｜學習成果';
    const s=course.summary||{};
    const rows=(course.learners||[]).map(row=>{
      const needs=row.overdue||row.examNotPassed;
      return '<tr class="'+(needs?'bg-amber-50/60':'')+'"><td class="px-3 py-2"><div class="font-bold text-slate-800">'+esc(row.name||row.username)+'</div><div class="text-[10px] text-slate-400">'+esc(row.empId||'')+'</div></td><td class="px-3 py-2 text-xs">'+esc(statusLabel(row.status))+'</td><td class="px-3 py-2 text-xs">'+Number(row.materialProgress||0).toFixed(0)+'% ('+Number(row.materialsCompleted||0)+'/'+Number(row.materialsTotal||0)+')</td><td class="px-3 py-2 text-xs">'+(row.examRequired===false?'— 本課程沒有考試':row.examNotPassed?'⚠️ 未通過':row.examPassed?'✓ 已通過':row.examAttempts?'待完成':'尚未作答')+'</td><td class="px-3 py-2 text-xs">'+(row.overdue?'⚠️ 已逾期':esc(row.dueAt||'—'))+'</td></tr>';
    }).join('');
    body.innerHTML='<div class="grid grid-cols-2 md:grid-cols-6 gap-2">'+[
      ['指派',s.assigned],['未開始',s.notStarted],['進行中',s.inProgress],['完成',s.completed],['逾期',s.overdue],['考試未通過',s.examNotPassed]
    ].map(([label,value])=>'<div class="rounded-xl border border-slate-200 bg-white px-3 py-2"><div class="text-[10px] text-slate-500">'+label+'</div><div class="text-xl font-black text-slate-900">'+Number(value||0)+'</div></div>').join('')+'</div><div class="mt-4 overflow-x-auto rounded-xl border border-slate-200"><table class="min-w-full text-left"><thead class="bg-slate-50 text-[10px] text-slate-500"><tr><th class="px-3 py-2">學員</th><th class="px-3 py-2">狀態</th><th class="px-3 py-2">教材</th><th class="px-3 py-2">考試</th><th class="px-3 py-2">截止</th></tr></thead><tbody class="divide-y divide-slate-100">'+(rows||'<tr><td colspan="5" class="px-3 py-6 text-center text-sm text-slate-400">尚無學員指派</td></tr>')+'</tbody></table></div>';
  }
  async function open(courseId){
    const dialog=ensureDialog();
    const body=dialog.querySelector('[data-tracking-body]');
    body.innerHTML='<div class="p-6 text-center text-sm text-slate-500">正在讀取學習追蹤…</div>';
    showTab(dialog,'progress');
    void loadFeedback(dialog,courseId);
    if(typeof dialog.showModal==='function'&&!dialog.open)dialog.showModal();
    try{
      const response=await fetch('/api/training-command-center/course-tracking?courseId='+encodeURIComponent(courseId),{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.error||'無法讀取課程追蹤');
      render(data,courseId);
    }catch(error){
      body.innerHTML='<div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">'+esc(error.message||'讀取失敗')+'</div>';
    }
  }
  function decorate(root=document){
    root.querySelectorAll?.('[data-course-id]').forEach(card=>{
      const courseId=String(card.dataset.courseId||'');
      const status=String(card.dataset.courseLifecycle||'');
      const bar=card.querySelector('[data-course-card-actions]');
      if(!bar||!courseId||status!=='published'||bar.querySelector('[data-course-tracking-f2]'))return;
      const button=document.createElement('button');
      button.type='button';
      button.dataset.courseTrackingF2=courseId;
      button.className='text-[10px] rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 font-bold text-sky-800';
      button.textContent='📊 學習成果';
      button.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();void open(courseId);});
      bar.appendChild(button);
    });
  }
  document.addEventListener('teacher-course-surface-rendered-1014',event=>decorate(event.target));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>decorate(),{once:true});
  else decorate();
  window.TeacherCourseTrackingF2=Object.freeze({open,decorate});
})();
