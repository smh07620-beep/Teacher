/* Phase 3F · Canonical admin material list/search-index runtime. */
(function(){
  'use strict';

  const MATERIAL_INDEX_AUTOCHECK_LIMIT = 8;
  const MATERIAL_INDEX_CONCURRENCY = 2;
  const MATERIAL_INDEX_TIMEOUT_MS = 3500;
  let materialIndexHydrationGeneration = 0;

  window.invalidateAdminMaterialsCache = function(){
    adminMaterialsCache = { data: null, at: 0 };
  };

  window.fetchAdminMaterials = async function(force=false){
    const now = Date.now();
    if (!force && Array.isArray(adminMaterialsCache.data) && (now - adminMaterialsCache.at) < ADMIN_CACHE_MS) {
      return adminMaterialsCache.data;
    }
    const res = await fetch('/api/slides/admin', {credentials:'same-origin'});
    if (res.status === 401) {
      window.invalidateAdminMaterialsCache();
      alert('登入狀態已失效，請重新登入後再試。');
      return null;
    }
    const data = await res.json().catch(() => []);
    if (!res.ok) throw new Error(data.error || '無法取得教材清單');
    const list = Array.isArray(data) ? data : [];
    adminMaterialsCache = { data: list, at: Date.now() };
    return list;
  };

  function versionChip(m){
    if(m.isBuiltin) return '';
    const current=Math.max(1,Number(m.currentVersion||1));
    const required=Math.max(1,Number(m.requiredCompletionVersion||1));
    const retraining=required>1&&required===current;
    return `<span class="text-[11px] px-2 py-0.5 rounded-full ${retraining?'bg-rose-100 text-rose-700':'bg-violet-100 text-violet-700'}">${retraining?'需重訓 · ':''}V${current}</span>`;
  }

  function paintAdminMaterials(materials, box){
    if (!box) return;
    box.innerHTML = materials.map(m => `
      <div class="border border-slate-200 rounded-xl p-3 ${m.isBuiltin ? 'bg-slate-50' : 'bg-white'}">
        <div class="flex flex-col lg:flex-row gap-3 lg:items-center justify-between">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-sm text-slate-800 break-all">${escapeHtml(m.title || m.filename)}</span>
              <span class="text-[11px] px-2 py-0.5 rounded-full bg-teal-100 text-teal-700">${escapeHtml((GROUPS[m.group] || GROUPS.grpBio).label)}</span>
              <span class="text-[11px] px-2 py-0.5 rounded-full ${m.isBuiltin ? 'bg-slate-200 text-slate-600' : 'bg-indigo-100 text-indigo-700'}">${m.isBuiltin ? '內建' : '上傳'}</span>
              ${versionChip(m)}
              ${!m.isBuiltin ? `<span class="text-[11px] px-2 py-0.5 rounded-full ${m.storageBackend==='mega'?'bg-fuchsia-100 text-fuchsia-800':(m.storageBackend==='oci'?'bg-red-100 text-red-800':(m.storageBackend==='gdrive'?'bg-emerald-100 text-emerald-800':(m.storageBackend==='r2'?'bg-cyan-100 text-cyan-800':'bg-orange-100 text-orange-800')))}">${m.storageBackend==='mega'?'🟣 MEGA':(m.storageBackend==='oci'?'🔴 Oracle':(m.storageBackend==='gdrive'?'🟢 Google Drive':(m.storageBackend==='r2'?'☁️ R2':'💾 本機')))}</span>` : ''}
              ${!m.isBuiltin && !m.active ? '<span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">已停用</span>' : ''}${!m.isBuiltin&&m.materialType==='atlas'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-teal-50 text-teal-700">🔬 Atlas</span>':''}${!m.isBuiltin&&m.materialType==='infographic'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">📊 資訊圖表</span>':m.materialType==='sop'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-700">📑 SOP</span>':m.materialType==='troubleshooting'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">🧰 Troubleshooting</span>':m.materialType==='case'?'<span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-700">🩸 案例分析</span>':''}
            </div>
            <div class="text-xs text-slate-500 mt-1">${escapeHtml(m.categoryLabel || '未分類')} · ${m.pageCount || 0} 頁 · ${escapeHtml(m.dateAdded || '')}</div><div id="material-index-${m.id}" class="text-[11px] text-slate-400 mt-1">全文搜尋：背景檢查中…</div>
            ${!m.isBuiltin && m.storageMeta ? `<div class="text-[11px] text-slate-400 mt-1">☁ ${m.storageMeta.previewMode==='single_pdf'?'單一預覽檔':'閱讀版'} ${escapeHtml((m.slideFormat||m.storageMeta.slideFormat||'png').toUpperCase())}${m.storageMeta.slideBytes?` · ${window.formatFileBytes(m.storageMeta.slideBytes)}`:''}${m.storageMeta.sourceBytes?` ｜ 原始檔 ${window.formatFileBytes(m.storageMeta.sourceBytes)}`:''}${m.storageMeta.cloudObjectCount?` ｜ 雲端檔案 ${m.storageMeta.cloudObjectCount} 個`:''}</div>` : ''}
          </div>
          ${m.isBuiltin ? '<span class="text-xs text-slate-400">內建教材不可修改</span>' : `
            <div class="flex flex-wrap gap-2 shrink-0">
              <button data-csp-click="editAdminMaterial('${m.id}')" class="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg">✏️ 編輯</button>
              <button data-csp-click="openMaterialVersionDialog('${m.id}')" class="text-xs border border-violet-200 text-violet-800 px-3 py-1.5 rounded-lg">🧾 版本 / 重訓</button>
              <button data-csp-click="rebuildMaterialIndex('${m.id}')" class="text-xs border border-teal-200 text-teal-800 px-3 py-1.5 rounded-lg">🔄 重建索引</button>
              <button data-csp-click="toggleAdminMaterial('${m.id}', ${m.active ? 'false' : 'true'})" class="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg">${m.active ? '⏸️ 停用' : '▶️ 啟用'}</button>
              <details class="relative"><summary class="list-none cursor-pointer text-[11px] bg-white border border-slate-200 text-slate-500 px-2.5 py-1.5 rounded-lg">更多</summary><div class="absolute right-0 z-20 mt-1 w-40 rounded-xl border border-rose-200 bg-white shadow-lg p-2"><button data-csp-click="deleteAdminMaterial('${m.id}')" class="w-full text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-1.5 rounded-lg">🗑️ 永久刪除</button></div></details>
            </div>`}
        </div>
      </div>`).join('') || '<p class="text-xs text-slate-400">目前沒有教材。</p>';
  }

  function ensureVersionDialog(){
    let dialog=document.getElementById('material-version-dialog');
    if(dialog) return dialog;
    dialog=document.createElement('dialog');
    dialog.id='material-version-dialog';
    dialog.className='rounded-2xl p-0 w-[min(92vw,720px)] backdrop:bg-slate-950/50';
    dialog.innerHTML=`<form method="dialog" class="bg-white rounded-2xl overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-200 flex items-start justify-between gap-3"><div><p class="text-[10px] font-black tracking-[.15em] text-violet-700">MATERIAL VERSION</p><h3 id="material-version-title" class="font-black text-slate-950 text-lg mt-1">教材版本與重訓</h3></div><button value="cancel" class="text-slate-500">✕</button></div>
      <div class="p-5 space-y-4">
        <div id="material-version-current" class="rounded-xl border border-violet-100 bg-violet-50 p-3 text-sm text-violet-900"></div>
        <div><label class="text-xs font-bold text-slate-600">版本變更原因<textarea id="material-version-reason" rows="3" maxlength="1000" class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm" placeholder="例如：SOP 新增檢體拒收條件與應變流程"></textarea></label></div>
        <label class="flex items-start gap-2 rounded-xl border border-rose-100 bg-rose-50 p-3 text-sm text-rose-900"><input id="material-version-retraining" type="checkbox" class="mt-1"><span><b>此版本要求重新訓練</b><span class="block text-xs mt-1">勾選後，舊版本完成紀錄保留供稽核，但不再視為完成目前版本。</span></span></label>
        <div class="flex justify-end"><button type="button" id="material-version-publish" class="bg-violet-700 hover:bg-violet-600 text-white font-bold text-sm px-4 py-2 rounded-xl">發布新版本</button></div>
        <div><div class="text-xs font-black text-slate-700 mb-2">版本歷史</div><div id="material-version-history" class="space-y-2 text-xs text-slate-600">讀取中…</div></div>
      </div>
    </form>`;
    document.body.appendChild(dialog);
    dialog.querySelector('#material-version-publish').addEventListener('click',()=>void publishMaterialVersion());
    return dialog;
  }

  let materialVersionContext=null;
  window.openMaterialVersionDialog=async function(id){
    const dialog=ensureVersionDialog();
    const material=(adminMaterialsCache.data||[]).find(x=>String(x.id)===String(id));
    materialVersionContext={id:String(id),material};
    dialog.querySelector('#material-version-reason').value='';
    dialog.querySelector('#material-version-retraining').checked=false;
    dialog.querySelector('#material-version-title').textContent=`教材版本與重訓 · ${material?.title||id}`;
    dialog.querySelector('#material-version-current').textContent=`目前 V${Number(material?.currentVersion||1)} · 有效完成門檻 V${Number(material?.requiredCompletionVersion||1)}`;
    dialog.querySelector('#material-version-history').textContent='讀取中…';
    dialog.showModal();
    try{
      const r=await fetch(`/api/slides/${encodeURIComponent(id)}/versions`,{credentials:'same-origin'});
      const rows=await r.json().catch(()=>[]);
      if(!r.ok) throw new Error(rows.error||'讀取版本歷史失敗');
      dialog.querySelector('#material-version-history').innerHTML=(Array.isArray(rows)?rows:[]).map(v=>`<div class="rounded-xl border border-slate-200 p-3"><div class="font-bold text-slate-800">V${Number(v.version||1)}${v.requiresRetraining?' · <span class="text-rose-700">要求重訓</span>':''}</div><div class="mt-1">${escapeHtml(v.changeReason||'未填寫變更原因')}</div><div class="mt-1 text-slate-400">${escapeHtml(v.createdAt||'')} · ${escapeHtml(v.createdBy||'')}</div></div>`).join('')||'<div class="text-slate-400">尚無版本歷史。</div>';
    }catch(err){dialog.querySelector('#material-version-history').textContent=err.message;}
  };

  async function publishMaterialVersion(){
    if(!materialVersionContext) return;
    const dialog=ensureVersionDialog();
    const reason=dialog.querySelector('#material-version-reason').value.trim();
    const requiresRetraining=dialog.querySelector('#material-version-retraining').checked;
    if(!reason){dialog.querySelector('#material-version-reason').focus();return;}
    const button=dialog.querySelector('#material-version-publish');
    button.disabled=true;button.textContent='發布中…';
    try{
      const r=await fetch(`/api/slides/${encodeURIComponent(materialVersionContext.id)}/versions`,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({changeReason:reason,requiresRetraining})});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'發布版本失敗');
      window.invalidateAdminMaterialsCache();
      await window.renderAdminMaterials(true);
      await window.openMaterialVersionDialog(materialVersionContext.id);
    }catch(err){alert(err.message);}
    finally{button.disabled=false;button.textContent='發布新版本';}
  }

  window.renderAdminMaterials = async function(force=false){
    const box = document.getElementById('admin-materials-list');
    if (!box) return;
    const cached = Array.isArray(adminMaterialsCache.data) ? adminMaterialsCache.data : null;
    if (cached) paintAdminMaterials(cached, box);
    else box.innerHTML = '<p class="text-xs text-slate-400">讀取教材中…</p>';
    try {
      const materials = await window.fetchAdminMaterials(force);
      if (!materials) return;
      paintAdminMaterials(materials, box);
      const generation = ++materialIndexHydrationGeneration;
      setTimeout(() => {
        if (generation !== materialIndexHydrationGeneration) return;
        void window.hydrateMaterialIndexStatus(materials, generation);
      }, 0);
    } catch (err) {
      if (!cached) box.innerHTML = `<p class="text-xs text-rose-500">❌ ${escapeHtml(err.message)}</p>`;
      else box.insertAdjacentHTML('afterbegin', `<p class="mb-2 text-xs text-amber-600">⚠️ 教材背景更新失敗：${escapeHtml(err.message)}；目前顯示最近一次資料。</p>`);
    }
  };

  window.hydrateMaterialIndexStatus = async function(materials, generation=materialIndexHydrationGeneration){
    const targets = (Array.isArray(materials) ? materials : []).filter(x=>!x.isBuiltin);
    const queue = targets.slice(0, MATERIAL_INDEX_AUTOCHECK_LIMIT);
    targets.slice(MATERIAL_INDEX_AUTOCHECK_LIMIT).forEach(m => {
      const el=document.getElementById(`material-index-${m.id}`);
      if(el) el.textContent='全文搜尋：需要時再檢查';
    });
    let cursor = 0;
    async function worker(){
      while(cursor < queue.length && generation === materialIndexHydrationGeneration){
        const m = queue[cursor++];
        const el=document.getElementById(`material-index-${m.id}`);
        if(!el) continue;
        const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timer = controller ? setTimeout(()=>controller.abort(), MATERIAL_INDEX_TIMEOUT_MS) : null;
        try{
          const r=await fetch(`/api/material-search/${encodeURIComponent(m.id)}/status`, {
            credentials:'same-origin',
            cache:'no-store',
            ...(controller ? {signal:controller.signal} : {})
          });
          const d=await r.json().catch(()=>({}));
          if(!r.ok) throw new Error(d.error||`HTTP ${r.status}`);
          const label={indexed:'已建立',not_indexed:'未建立',failed:'建立失敗',unsupported:'不支援',no_text:'無可搜尋文字'}[d.status]||d.status||'未建立';
          if(generation === materialIndexHydrationGeneration && el.isConnected) el.textContent=`全文搜尋：${label} · ${Number(d.page_count||0)} 頁${d.last_indexed_at?` · ${d.last_indexed_at}`:''}`;
        }catch(_){
          if(generation === materialIndexHydrationGeneration && el.isConnected) el.textContent='全文搜尋：稍後再檢查';
        }finally{
          if(timer) clearTimeout(timer);
        }
      }
    }
    await Promise.all(Array.from({length:Math.min(MATERIAL_INDEX_CONCURRENCY, queue.length)}, ()=>worker()));
  };

  window.rebuildMaterialIndex = async function(id){
    if(!confirm('重新建立教材全文搜尋索引？')) return;
    const r=await fetch(`/api/material-search/${encodeURIComponent(id)}/index`,{method:'POST'});
    const d=await r.json();
    if(!r.ok) return alert(d.error||'重建失敗');
    await window.renderAdminMaterials(true);
  };

  window.formatFileBytes = function(value){
    const n=Number(value||0);
    if(!Number.isFinite(n)||n<=0) return '0 B';
    if(n<1024) return `${Math.round(n)} B`;
    if(n<1024*1024) return `${(n/1024).toFixed(1)} KB`;
    if(n<1024*1024*1024) return `${(n/1024/1024).toFixed(1)} MB`;
    return `${(n/1024/1024/1024).toFixed(2)} GB`;
  };
})();
