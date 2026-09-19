/* Phase 3R · Canonical admin results data/table runtime.
 * Loaded before admin-results-workspace.js so its wrapper captures this owner.
 */
(function(){
  'use strict';

  let page = 1;

  window.renderResultsAnalytics = function(records){
    const wrap=document.getElementById('admin-results-analytics');
    const cards=document.getElementById('admin-analytics-cards');
    const qbox=document.getElementById('admin-question-analytics');
    if(!wrap||!cards||!qbox) return;
    const rows=Array.isArray(records)?records:[];
    const completed=rows.filter(r=>r.reviewStatus!=='pending'&&Number.isFinite(Number(r.score)));
    const pending=rows.filter(r=>r.reviewStatus==='pending').length;
    const avg=completed.length?completed.reduce((s,r)=>s+Number(r.score||0),0)/completed.length:0;
    const passed=completed.filter(r=>(r.status||'')==='合格').length;
    const rate=completed.length?Math.round(passed/completed.length*100):0;
    cards.innerHTML=`<div class="rounded-xl bg-slate-50 border p-4"><span class="text-xs text-slate-500">總考核次數</span><b class="block text-2xl mt-1">${rows.length}</b></div><div class="rounded-xl bg-teal-50 border border-teal-100 p-4"><span class="text-xs text-teal-700">平均分</span><b class="block text-2xl mt-1 text-teal-950">${avg.toFixed(1)}</b></div><div class="rounded-xl bg-emerald-50 border border-emerald-100 p-4"><span class="text-xs text-emerald-700">通過率</span><b class="block text-2xl mt-1 text-emerald-950">${rate}%</b></div><div class="rounded-xl bg-amber-50 border border-amber-100 p-4"><span class="text-xs text-amber-700">待人工批改</span><b class="block text-2xl mt-1 text-amber-950">${pending}</b></div>`;
    const map=new Map();
    for(const r of rows){
      for(const a of r.answersDetail||[]){
        if(a.questionType==='essay'||a.isCorrect===null||a.isCorrect===undefined) continue;
        const k=a.questionText||`第${a.num||''}題`;
        const x=map.get(k)||{text:k,total:0,correct:0};
        x.total++;
        if(a.isCorrect===true) x.correct++;
        map.set(k,x);
      }
    }
    const list=[...map.values()].map(x=>({...x,rate:x.total?Math.round(x.correct/x.total*100):0})).sort((a,b)=>a.rate-b.rate||b.total-a.total).slice(0,12);
    qbox.innerHTML=list.length?list.map(x=>`<div class="rounded-xl border ${x.rate<60?'border-rose-200 bg-rose-50/40':'border-slate-200 bg-white'} p-3 flex items-center justify-between gap-3"><div class="min-w-0"><div class="text-xs font-bold text-slate-800 line-clamp-2">${escapeHtml(x.text)}</div><div class="text-[11px] text-slate-500 mt-1">作答 ${x.total} 次・答對 ${x.correct} 次</div></div><div class="shrink-0 text-sm font-black ${x.rate<60?'text-rose-700':'text-teal-700'}">${x.rate}%</div></div>`).join(''):'<p class="text-xs text-slate-400">目前沒有足夠的客觀題作答紀錄可分析。</p>';
  };

  window.fetchAdminRecords = async function(){
    const key=await getAdminKey();
    if(!key) return null;
    const res=await fetch('/api/records',{headers:{'X-Admin-Key':key}});
    if(res.status===401){
      alert('登入狀態已失效，請重新登入後再試。');
      return null;
    }
    const data=await res.json().catch(()=>[]);
    if(!res.ok) throw new Error(data.error||'無法取得成績');
    adminRecords=Array.isArray(data)?data:[];
    return adminRecords;
  };

  window.adminResultDetail = function(index){
    const row=adminRecords[index];
    if(!row) return;
    document.getElementById(`admin-result-detail-${index}`)?.classList.toggle('hidden');
  };

  function paintPagination(visibleRecords,pageSize,pages){
    const pager=document.getElementById('admin-results-pagination');
    if(!pager) return;
    pager.innerHTML=`<span>顯示 ${(page-1)*pageSize+1}–${Math.min(page*pageSize,visibleRecords.length)}／${visibleRecords.length} 筆</span><span class="flex gap-2"><button ${page===1?'disabled':''} data-admin-results-page="prev" class="border rounded px-2 py-1 disabled:opacity-40">上一頁</button><b class="px-1 py-1">${page} / ${pages}</b><button ${page===pages?'disabled':''} data-admin-results-page="next" class="border rounded px-2 py-1 disabled:opacity-40">下一頁</button></span>`;
    pager.querySelector('[data-admin-results-page="prev"]')?.addEventListener('click',()=>{page=Math.max(1,page-1);window.renderAdminTable();});
    pager.querySelector('[data-admin-results-page="next"]')?.addEventListener('click',()=>{page=Math.min(pages,page+1);window.renderAdminTable();});
  }

  window.renderAdminTable = async function(){
    window.updateResultsWorkspacePresentation?.();
    const tbody=document.getElementById('admin-table-body');
    if(!tbody) return;
    tbody.innerHTML='<tr><td colspan="8" class="p-6 text-center text-slate-400">讀取伺服器成績中…</td></tr>';
    try{
      const records=await window.fetchAdminRecords();
      if(!records) return;
      if(records.length===0){
        tbody.innerHTML='<tr><td colspan="8" class="p-6 text-center text-slate-400">目前尚無任何考核紀錄</td></tr>';
        document.getElementById('admin-results-pagination')?.replaceChildren();
        return;
      }
      window.renderResultsAnalytics(records);
      let visibleRecords=[...records];
      const query=(document.getElementById('admin-results-search')?.value||'').trim().toLowerCase();
      const filter=document.getElementById('admin-results-filter')?.value||'all';
      visibleRecords=visibleRecords.filter(r=>{
        const text=`${r.name||''} ${r.empId||''} ${r.quizTitle||''} ${r.groupLabel||''}`.toLowerCase();
        if(query&&!text.includes(query)) return false;
        if(filter==='pending') return r.reviewStatus==='pending';
        if(filter==='pass') return r.status==='合格';
        if(filter==='fail') return r.reviewStatus!=='pending'&&r.status!=='合格';
        return true;
      });
      if(!visibleRecords.length){
        tbody.innerHTML='<tr><td colspan="8" class="p-6 text-center text-slate-400">目前尚無任何考核紀錄</td></tr>';
        document.getElementById('admin-results-pagination')?.replaceChildren();
        return;
      }
      const pageSize=Math.max(20,Number(document.getElementById('admin-results-page-size')?.value||20));
      const pages=Math.max(1,Math.ceil(visibleRecords.length/pageSize));
      page=Math.min(Math.max(1,page),pages);
      const pageRows=visibleRecords.slice((page-1)*pageSize,page*pageSize);
      tbody.innerHTML=pageRows.map(r=>{
        const index=records.indexOf(r);
        const detail=r.answersDetail||[];
        return `<tr class="hover:bg-slate-50 transition-colors"><td class="p-3"><button data-csp-click="adminResultDetail(${index})" class="text-xs font-bold text-indigo-700">明細</button></td><td class="p-3 font-mono text-slate-500">${r.timestamp||''}</td><td class="p-3"><span class="px-2 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700">${escapeHtml(r.groupLabel||'1 生化組')}</span></td><td class="p-3 font-bold text-slate-800">${escapeHtml(r.name||'')}</td><td class="p-3 font-mono">${escapeHtml(r.empId||'')}</td><td class="p-3">${escapeHtml(r.quizTitle||'')}</td><td class="p-3 text-center font-bold ${r.reviewStatus==='pending'?'text-amber-600':(Number(r.score)>=Number(r.passingScore||80)?'text-green-600':'text-red-600')}">${r.reviewStatus==='pending'?'待批改':(Number(r.score)||0)}</td><td class="p-3 text-center"><span class="px-2 py-0.5 rounded-full text-xs font-bold ${r.reviewStatus==='pending'?'bg-amber-100 text-amber-800':(r.status==='合格'?'bg-green-100 text-green-800':'bg-red-100 text-red-800')}">${escapeHtml(r.status||'')}</span></td><td class="p-3 text-center space-y-1">${detail.some(a=>a.questionType==='essay')?`<button data-csp-click="openEssayReview(${index})" class="bg-rose-600 hover:bg-rose-500 text-white text-xs px-2.5 py-1 rounded shadow-sm">✍️ ${r.reviewStatus==='pending'?'批改問答題':'重新批改'}</button>`:''}<button data-csp-click="exportRecordToWord(${index})" class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs px-2.5 py-1 rounded transition-colors shadow-sm">📄 匯出 Word</button></td></tr><tr id="admin-result-detail-${index}" class="hidden bg-slate-50"><td colspan="9" class="p-3"><div class="text-xs text-slate-600"><b>作答明細（預設收合）</b><div class="mt-2 space-y-1">${detail.length?detail.map((a,i)=>`<div>${i+1}. ${escapeHtml(a.questionText||'')}　<span class="text-slate-500">${escapeHtml(String(a.userAnswer??'未作答'))}</span></div>`).join(''):'無逐題明細'}</div></div></td></tr>`;
      }).join('');
      paintPagination(visibleRecords,pageSize,pages);
    }catch(error){
      tbody.innerHTML=`<tr><td colspan="8" class="p-6 text-center text-rose-500">❌ ${escapeHtml(error.message)}</td></tr>`;
    }
  };

  window.clearAllRecords = async function(){
    if(!confirm('確定要清空伺服器後台所有歷史考核成績紀錄嗎？此操作無法復原。')) return;
    const key=await getAdminKey();
    if(!key) return;
    try{
      const res=await fetch('/api/records',{method:'DELETE',headers:{'X-Admin-Key':key}});
      const data=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(data.error||'清空失敗');
      adminRecords=[];
      page=1;
      await window.renderAdminTable();
    }catch(error){
      alert(`清空失敗：${error.message}`);
    }
  };
})();
