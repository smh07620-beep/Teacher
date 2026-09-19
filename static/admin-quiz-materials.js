/* Phase 3S · Canonical quiz-to-material linking runtime. */
(function(){
  'use strict';

  const state = Object.create(null);

  window.openQuizMaterialLinker = async function(catId){
    document.getElementById(`qpanel-${catId}`)?.classList.remove('hidden');
    const panel=document.getElementById(`qmaterial-link-${catId}`);
    if(!panel) return;
    panel.classList.remove('hidden');
    const list=document.getElementById(`qmaterial-list-${catId}`);
    const status=document.getElementById(`qmaterial-status-${catId}`);
    if(list) list.innerHTML='<p class="text-xs text-slate-400">讀取教材中…</p>';
    if(status) status.textContent='';
    const key=await getAdminKey();
    if(!key) return;
    try{
      const r=await fetch(`/api/quiz-categories/${catId}/materials`,{headers:{'X-Admin-Key':key}});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'讀取教材失敗');
      state[catId]=Array.isArray(d.items)?d.items:[];
      window.renderQuizMaterialLinker(catId);
    }catch(e){
      if(list) list.innerHTML=`<p class="text-xs text-rose-600">❌ ${escapeHtml(e.message)}</p>`;
    }
  };

  window.closeQuizMaterialLinker = function(catId){
    document.getElementById(`qmaterial-link-${catId}`)?.classList.add('hidden');
  };

  window.renderQuizMaterialLinker = function(catId){
    const list=document.getElementById(`qmaterial-list-${catId}`);
    if(!list) return;
    const q=(document.getElementById(`qmaterial-search-${catId}`)?.value||'').trim().toLowerCase();
    const items=(state[catId]||[]).filter(m=>!q||`${m.title||''} ${m.filename||''}`.toLowerCase().includes(q));
    list.innerHTML=items.length?items.map(m=>`<label class="flex items-center gap-2 rounded-lg border ${m.linked?'border-cyan-300 bg-white':'border-slate-200 bg-white/70'} px-3 py-2 text-xs"><input class="qmaterial-check-${catId}" data-mid="${escapeHtml(m.id)}" type="checkbox" ${m.linked?'checked':''}><span class="min-w-0 flex-1"><span class="font-bold text-slate-800 block truncate">${escapeHtml(m.title||m.filename)}</span><span class="text-[10px] text-slate-400">${escapeHtml(m.materialType||'standard')}${m.category&&!m.linked?' · 目前綁定其他考卷':''}</span></span></label>`).join(''):'<p class="text-xs text-slate-400 py-3">找不到符合的教材。</p>';
  };

  window.filterQuizMaterialLinker = function(catId){
    window.renderQuizMaterialLinker(catId);
  };

  window.saveQuizMaterialLinks = async function(catId){
    const ids=[...document.querySelectorAll(`.qmaterial-check-${catId}:checked`)].map(x=>x.dataset.mid).filter(Boolean);
    const status=document.getElementById(`qmaterial-status-${catId}`);
    if(status) status.textContent=`⏳ 正在儲存 ${ids.length} 份教材關聯…`;
    const key=await getAdminKey();
    if(!key) return;
    try{
      const r=await fetch(`/api/quiz-categories/${catId}/materials`,{
        method:'PUT',
        headers:{'Content-Type':'application/json','X-Admin-Key':key},
        body:JSON.stringify({materialIds:ids})
      });
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'儲存關聯失敗');
      invalidateAdminMaterialsCache();
      await window.openQuizMaterialLinker(catId);
      if(status) status.textContent=`✅ 已關聯 ${d.linked||0} 份教材`;
      if(typeof window.loadAiMaterialOptions==='function') window.loadAiMaterialOptions(catId,true);
    }catch(e){
      if(status) status.textContent=`❌ ${e.message}`;
    }
  };
})();
