/* 0092 · People × training competency matrix. */
(() => {
  'use strict';
  let matrixRows = [];
  let matrixMode = false;
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const groups = () => window.AppCore?.groups || window.GROUPS || {};
  const statusMeta = {
    complete:['✅ 完成','border-emerald-200 bg-emerald-50 text-emerald-700'],
    overdue:['🔴 逾期','border-rose-200 bg-rose-50 text-rose-700'],
    retraining:['🟣 重訓','border-violet-200 bg-violet-50 text-violet-700'],
    remediation:['🟠 補強','border-amber-200 bg-amber-50 text-amber-700'],
    pending_review:['🟡 待批改','border-amber-200 bg-amber-50 text-amber-700'],
    awaiting_exam:['🔵 待考核','border-sky-200 bg-sky-50 text-sky-700'],
    in_progress:['進行中','border-slate-200 bg-slate-50 text-slate-600'],
  };

  function queryParams(){
    const p=new URLSearchParams();
    for(const [k,v] of Object.entries({area:el('admin-compliance-area')?.value,group:el('admin-compliance-group')?.value,courseId:el('admin-compliance-course')?.value})) if(v) p.set(k,v);
    return p;
  }
  function pivot(rows){
    const abilities=new Map(), people=new Map();
    for(const item of rows){
      const courseId=String(item.courseId||''), username=String(item.username||'').toLowerCase();
      if(!courseId||!username) continue;
      if(!abilities.has(courseId)) abilities.set(courseId,{id:courseId,title:item.courseTitle||courseId,group:item.group||''});
      if(!people.has(username)) people.set(username,{username,name:item.name||username,empId:item.empId||'',group:item.group||'',cells:{}});
      people.get(username).cells[courseId]=item;
    }
    return {abilities:[...abilities.values()].sort((a,b)=>String(a.title).localeCompare(String(b.title),'zh-TW')),people:[...people.values()].sort((a,b)=>`${a.group}|${a.name}|${a.empId}`.localeCompare(`${b.group}|${b.name}|${b.empId}`,'zh-TW'))};
  }
  function cellHtml(item){
    if(!item) return '<span class="text-slate-300">—</span>';
    const meta=statusMeta[item.status]||statusMeta.in_progress;
    const evidence=[`教材 ${Number(item.materialsCompleted||0)}/${Number(item.materialsTotal||0)}`,item.examRequired?(item.examPassed?'考核已通過':'考核未完成'):'無指定考核',item.retrainingRequired?'需重新訓練':'',item.certificateStatus==='current'?'有目前有效完訓證明':''].filter(Boolean).join('；');
    return `<span title="${esc(evidence)}" class="inline-flex min-w-[78px] justify-center rounded-full border px-2 py-1 text-[10px] font-bold ${meta[1]}">${meta[0]}</span>`;
  }
  function renderMatrix(){
    const host=el('admin-competency-matrix-table'), summary=el('admin-competency-matrix-summary');
    if(!host) return;
    const data=pivot(matrixRows), q=(el('admin-compliance-search')?.value||'').trim().toLowerCase();
    const people=q?data.people.filter(person=>[person.name,person.empId,person.username,...Object.values(person.cells).map(item=>item.courseTitle)].some(v=>String(v||'').toLowerCase().includes(q))):data.people;
    const assigned=people.reduce((n,p)=>n+Object.keys(p.cells).length,0), complete=people.reduce((n,p)=>n+Object.values(p.cells).filter(item=>item.status==='complete').length,0);
    if(summary) summary.textContent=`顯示 ${people.length} 位人員 × ${data.abilities.length} 個訓練能力項目；已完成 ${complete}/${assigned} 個已指派項目。`;
    if(!people.length||!data.abilities.length){host.innerHTML='<div class="p-6 text-center text-xs text-slate-400">目前沒有可形成能力矩陣的正式課程指派。</div>';return;}
    host.innerHTML=`<table class="min-w-max w-full text-left text-xs"><thead class="bg-slate-50 text-slate-700"><tr><th class="sticky left-0 z-10 min-w-[180px] border-b border-r border-slate-200 bg-slate-50 p-3">人員</th>${data.abilities.map(a=>`<th class="min-w-[130px] border-b border-slate-200 p-3 text-center"><div class="font-bold text-slate-800">${esc(a.title)}</div><div class="mt-0.5 text-[9px] font-normal text-slate-400">${esc((groups()[a.group]||{}).name||a.group||'')}</div></th>`).join('')}</tr></thead><tbody>${people.map(p=>`<tr><td class="sticky left-0 z-[1] border-b border-r border-slate-100 bg-white p-3"><div class="font-bold text-slate-900">${esc(p.name||p.username)}</div><div class="mt-0.5 text-[9px] text-slate-400">${esc(p.empId||p.username)} · ${esc((groups()[p.group]||{}).name||p.group||'')}</div></td>${data.abilities.map(a=>`<td class="border-b border-slate-100 bg-white p-2 text-center">${cellHtml(p.cells[a.id])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }
  async function loadMatrix(force=false){
    const summary=el('admin-competency-matrix-summary'); if(summary) summary.textContent='正在讀取人員 × 能力矩陣…';
    try{const res=await fetch('/api/training-compliance?'+queryParams().toString(),{credentials:'same-origin',cache:force?'reload':'no-store'}),data=await res.json().catch(()=>({}));if(!res.ok)throw new Error(data.error||'無法讀取能力矩陣');matrixRows=Array.isArray(data.rows)?data.rows:[];renderMatrix();}
    catch(error){matrixRows=[];if(summary)summary.textContent=`❌ ${error.message||'無法讀取能力矩陣'}`;const host=el('admin-competency-matrix-table');if(host)host.innerHTML='';}
  }
  function paintMode(){
    el('admin-compliance-list-view')?.classList.toggle('hidden',matrixMode);
    el('admin-competency-matrix-view')?.classList.toggle('hidden',!matrixMode);
    for(const [id,active] of [['admin-compliance-view-list',!matrixMode],['admin-compliance-view-matrix',matrixMode]]){const b=el(id);if(b){b.classList.toggle('bg-teal-700',active);b.classList.toggle('text-white',active);}}
  }
  function setMode(mode){matrixMode=mode==='matrix';paintMode();if(matrixMode)void loadMatrix(true);}
  function bind(){
    const list=el('admin-compliance-view-list'), matrix=el('admin-compliance-view-matrix');
    if(list&&list.dataset.bound92!=='1'){list.dataset.bound92='1';list.addEventListener('click',()=>setMode('list'));}
    if(matrix&&matrix.dataset.bound92!=='1'){matrix.dataset.bound92='1';matrix.addEventListener('click',()=>setMode('matrix'));}
    for(const id of ['admin-compliance-area','admin-compliance-group','admin-compliance-course']){const n=el(id);if(n&&n.dataset.bound92!=='1'){n.dataset.bound92='1';n.addEventListener('change',()=>{if(matrixMode)void loadMatrix(true);});}}
    const search=el('admin-compliance-search');if(search&&search.dataset.bound92!=='1'){search.dataset.bound92='1';search.addEventListener('input',()=>{if(matrixMode)renderMatrix();});}
    const refresh=el('admin-compliance-refresh');if(refresh&&refresh.dataset.bound92!=='1'){refresh.dataset.bound92='1';refresh.addEventListener('click',()=>{if(matrixMode)void loadMatrix(true);});}
    paintMode();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind,{once:true});else bind();
})();
