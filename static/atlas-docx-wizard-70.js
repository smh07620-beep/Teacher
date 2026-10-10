(()=>{
  'use strict';

  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));
  let activeRootId='atlas-manager';

  const root=()=>document.getElementById(activeRootId)||document.getElementById('atlas-manager');

  const fields=(prefix='',value={})=>{
    const category=String(value.category||'microscope');
    const difficulty=String(value.difficulty||'general');
    return `
      <div class="grid gap-2 sm:grid-cols-2">
        <input name="${prefix}title" value="${esc(value.title||'')}" placeholder="名稱（留空以圖片檔名）" class="border rounded-lg p-2 text-sm">
        <select name="${prefix}category" class="border rounded-lg p-2 text-sm">
          <option value="microscope" ${category==='microscope'?'selected':''}>顯微鏡圖譜</option>
          <option value="blood_cell" ${category==='blood_cell'?'selected':''}>血球圖譜</option>
          <option value="urine_sediment" ${category==='urine_sediment'?'selected':''}>尿液沉渣圖譜</option>
          <option value="colony" ${category==='colony'?'selected':''}>菌落圖譜</option>
        </select>
        <input name="${prefix}group" value="${esc(value.group||'')}" placeholder="組別" class="border rounded-lg p-2 text-sm">
        <select name="${prefix}difficulty" class="border rounded-lg p-2 text-sm">
          <option value="general" ${difficulty==='general'?'selected':''}>一般</option>
          <option value="basic" ${difficulty==='basic'?'selected':''}>基礎</option>
          <option value="advanced" ${difficulty==='advanced'?'selected':''}>進階</option>
        </select>
        <input name="${prefix}sortOrder" value="${esc(value.sortOrder||0)}" type="number" placeholder="排序" class="border rounded-lg p-2 text-sm">
        <input name="${prefix}tags" value="${esc((value.tags||[]).join(', '))}" placeholder="標籤（逗號分隔）" class="border rounded-lg p-2 text-sm">
      </div>
      <textarea name="${prefix}description" placeholder="描述" class="w-full border rounded-lg p-2 text-sm">${esc(value.description||'')}</textarea>
      <textarea name="${prefix}differentialPoints" placeholder="鑑別重點" class="w-full border rounded-lg p-2 text-sm">${esc(value.differentialPoints||'')}</textarea>
      <textarea name="${prefix}teachingNotes" placeholder="教學提示" class="w-full border rounded-lg p-2 text-sm">${esc(value.teachingNotes||'')}</textarea>`;
  };

  const read=(form,prefix='')=>{
    const q=name=>form.elements[prefix+name]?.value||'';
    return {
      title:q('title').trim(),
      category:q('category'),
      group:q('group').trim(),
      difficulty:q('difficulty'),
      sortOrder:Number(q('sortOrder')||0),
      tags:q('tags').split(',').map(value=>value.trim()).filter(Boolean),
      description:q('description').trim(),
      differentialPoints:q('differentialPoints').trim(),
      teachingNotes:q('teachingNotes').trim(),
    };
  };

  window.openAtlasDocxWizard=async(targetRootId='atlas-manager',preferredMaterialId='')=>{
    activeRootId=String(targetRootId||'atlas-manager');
    const preferred=String(preferredMaterialId||'').trim();
    const box=root();
    if(!box)return false;
    box.classList.remove('hidden');
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>DOCX → Atlas · 1/4 選擇 Word 來源</b>
        <p class="text-xs text-slate-600">系統會把 Word 裡可驗證的內嵌 JPG／PNG／WEBP 單獨抽出成 Atlas 草稿；原 Word 教材仍會保留，不會被拆掉或覆蓋。</p>
        <p class="text-xs text-amber-800">請先確認教材與圖片已去識別化；姓名、病歷號、條碼、生日等資訊不可匯入。</p>
        <select id="atlas-docx-source" class="w-full border rounded-lg p-2 text-sm"><option>載入 DOCX 教材中…</option></select>
        <button id="atlas-docx-next" type="button" class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">下一步：掃描 Word 圖片</button>
      </section>`;
    try{
      const response=await fetch('/api/slides/admin',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>[]);
      if(!response.ok)throw new Error(data.error||'無法讀取教材清單');
      const list=Array.isArray(data)?data:(data.slides||data.materials||[]);
      const docx=list.filter(item=>/\.docx$/i.test(item.filename||item.storageFilename||''));
      const select=box.querySelector('#atlas-docx-source');
      select.innerHTML=docx.map(item=>`<option value="${esc(item.id)}">${esc(item.title||item.filename||item.id)}</option>`).join('')
        ||'<option value="">沒有可匯入的 DOCX 教材</option>';
      if(preferred&&docx.some(item=>String(item.id)===preferred))select.value=preferred;
      box.querySelector('#atlas-docx-next')?.addEventListener('click',preview);
      if(preferred&&select.value===preferred)await preview();
      return true;
    }catch(error){
      box.innerHTML=`<p class="text-sm text-rose-600">無法載入 DOCX 教材：${esc(error.message||'未知錯誤')}</p>`;
      return false;
    }
  };

  async function preview(){
    const box=root();
    const id=box?.querySelector('#atlas-docx-source')?.value||'';
    if(!box||!id)return;
    const response=await fetch('/api/atlas/import-docx/'+encodeURIComponent(id)+'/preview',{
      method:'POST',
      credentials:'same-origin'
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok){
      alert(data.error||'無法解析 DOCX');
      return;
    }
    const images=Array.isArray(data.preview?.images)?data.preview.images:[];
    const warnings=(data.preview?.warnings||[]).map(warning=>`<p class="text-xs text-amber-800">⚠ ${esc(warning)}</p>`).join('');
    if(!images.length){
      box.innerHTML=`
        <section class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 space-y-3">
          <b>DOCX → Atlas｜沒有可安全抽出的圖片</b>
          ${warnings}
          <p class="text-xs text-slate-600">原 Word 教材不受影響。若圖片是浮動物件、SmartArt、圖表或 OLE，請先在 Word 另存為一般 inline JPG／PNG／WEBP 後再試。</p>
          <button id="atlas-docx-reselect" type="button" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold">重新選擇 Word</button>
        </section>`;
      box.querySelector('#atlas-docx-reselect')?.addEventListener('click',()=>window.openAtlasDocxWizard(activeRootId));
      return;
    }
    const defaults={group:data.defaultGroup||'',category:'microscope',difficulty:'general',sortOrder:0};
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>DOCX → Atlas · 2/4 共用 metadata</b>
        <p class="text-xs text-slate-500">已找到 ${images.length} 張可驗證的內嵌圖片。共用欄位會套用至所有勾選圖片；下一步可以逐張覆寫。所有項目先建立為草稿。</p>
        ${warnings}
        <form id="atlas-docx-common" class="space-y-2">
          ${fields('',defaults)}
          <button class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">下一步：選取與覆寫</button>
        </form>
      </section>`;
    box.querySelector('#atlas-docx-common')?.addEventListener('submit',event=>{
      event.preventDefault();
      choose(data.materialId,images,read(event.currentTarget));
    });
  }

  function choose(materialId,images,common){
    const box=root();
    if(!box)return;
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>DOCX → Atlas · 3/4 選取要獨立建立的圖片</b>
        <p class="text-xs text-slate-500">Word 本身仍保留為教材；只有勾選的圖片會另外建立 Atlas 草稿。系統依圖片附近文字先給分類建議，教師仍可逐張修改。</p>
        <form id="atlas-docx-items" class="space-y-3">
          ${images.map(item=>`
            <fieldset class="border rounded-lg p-3">
              <label class="font-bold text-sm">
                <input type="checkbox" name="pick" value="${Number(item.index)}" data-relationship="${esc(item.relationshipId||'')}" checked>
                圖片 ${Number(item.index)}${item.fileName?' · '+esc(item.fileName):''}
              </label>
              <p class="mt-1 text-xs text-slate-500">${esc(item.section||'無周圍文字')}</p>
              <details class="mt-2">
                <summary class="cursor-pointer text-xs text-teal-700">覆寫此圖片 metadata</summary>
                <p class="mt-2 text-[11px] font-bold text-teal-700">已把圖片同段文字帶入名稱，前後附近文字帶入描述；可直接修改。</p>
                <div class="mt-2 space-y-2">${fields('item-'+Number(item.index)+'-',{
                  ...common,
                  category:item.suggestedCategory||common.category,
                  title:item.suggestedTitle||item.caption||common.title||'',
                  description:item.suggestedDescription||item.section||common.description||''
                })}</div>
              </details>
            </fieldset>`).join('')}
          <button class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">下一步：確認</button>
        </form>
      </section>`;
    box.querySelector('#atlas-docx-items')?.addEventListener('submit',event=>{
      event.preventDefault();
      const form=event.currentTarget;
      const items=[...form.querySelectorAll('[name=pick]:checked')].map(input=>({
        index:Number(input.value),
        relationshipId:String(input.dataset.relationship||''),
        ...read(form,'item-'+input.value+'-'),
      }));
      if(!items.length){
        alert('請至少選擇一張圖片');
        return;
      }
      confirmStep(materialId,common,items);
    });
  }

  function confirmStep(materialId,metadata,items){
    const box=root();
    if(!box)return;
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>DOCX → Atlas · 4/4 確認建立草稿</b>
        <p class="text-sm">將從 Word 另外建立 ${items.length} 筆 Atlas 草稿；原 Word 不會被刪除或改寫。發布前仍可逐筆編輯與覆核。</p>
        <ul class="text-xs list-disc pl-5">${items.map(item=>`<li>${esc(item.title||('圖片 '+item.index))} · ${esc(item.category)} · ${esc(item.group)}</li>`).join('')}</ul>
        <button id="atlas-docx-confirm" type="button" class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">確認建立 Atlas 草稿</button>
      </section>`;
    box.querySelector('#atlas-docx-confirm')?.addEventListener('click',async()=>{
      const response=await fetch('/api/atlas/import-docx/'+encodeURIComponent(materialId)+'/confirm',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({metadata,items})
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok){
        alert(data.error||'建立失敗');
        return;
      }
      framingStep(Array.isArray(data.created)?data.created:[]);
    });
  }

  // 5/5: right after the import, the teacher can frame cells on each new draft
  // (optional).  The drafts stay unpublished; learners see nothing until the
  // teacher publishes them in the Atlas area.
  async function framingStep(ids){
    const box=root();
    if(!box)return;
    const items=[];
    for(const id of ids){
      try{
        const response=await fetch('/api/atlas/'+encodeURIComponent(id),{credentials:'same-origin'});
        const data=await response.json().catch(()=>({}));
        if(response.ok&&data.item)items.push(data.item);
      }catch(_error){}
    }
    const finish=()=>{box.classList.add('hidden');window.renderFormalAtlas?.();};
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>DOCX → Atlas · 5/5 已建立 ${ids.length} 筆草稿，要順便框選細胞嗎？（選填）</b>
        <p class="text-xs text-slate-500">框選後，學員點圖就能放大看到你寫的介紹，也能拿來出「點選圖片題」。可以現在做，也可以之後到「圖譜」頁編輯。草稿發布前學員都看不到。</p>
        <ul class="space-y-2">${items.map(item=>`
          <li class="flex flex-wrap items-center gap-2 rounded-lg border p-2" data-atlas-frame-item="${esc(item.id)}">
            <img src="${esc(item.thumbnailUrl||item.imageUrl)}" alt="" class="h-14 w-14 rounded object-cover">
            <span class="min-w-0 flex-1 truncate text-sm font-bold">${esc(item.title)}</span>
            <span class="text-[11px] text-slate-500" data-frame-status></span>
            <button type="button" data-frame-open class="rounded-lg border border-teal-300 bg-teal-50 px-3 py-1.5 text-xs font-bold text-teal-800">框選細胞</button>
          </li>`).join('')}</ul>
        <div id="atlas-docx-frame-editor"></div>
        <button id="atlas-docx-frame-done" type="button" class="rounded-lg bg-teal-700 px-3 py-2 font-bold text-white">完成</button>
      </section>`;
    box.querySelector('#atlas-docx-frame-done')?.addEventListener('click',finish);
    box.querySelectorAll('[data-frame-open]').forEach(button=>{
      button.addEventListener('click',()=>{
        const row=button.closest('[data-atlas-frame-item]');
        const item=items.find(candidate=>candidate.id===row?.dataset.atlasFrameItem);
        if(item)openFrameEditor(box,item,row);
      });
    });
  }

  function openFrameEditor(box,item,row){
    const host=box.querySelector('#atlas-docx-frame-editor');
    if(!host||!window.AtlasAnnotations?.attachEditor)return;
    host.innerHTML=`<form class="space-y-2 rounded-xl border border-indigo-200 p-3"><b class="text-sm">${esc(item.title)}</b>
      <div class="flex gap-2"><button type="submit" class="rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-bold text-white">儲存標記</button>
      <button type="button" data-frame-cancel class="rounded-lg border px-3 py-1.5 text-xs font-bold">取消</button></div></form>`;
    const form=host.querySelector('form');
    window.AtlasAnnotations.attachEditor(form,item);
    form.querySelector('[data-frame-cancel]')?.addEventListener('click',()=>{host.innerHTML='';});
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      const marks=window.AtlasAnnotations.collect(form);
      if(marks===null)return;
      const response=await fetch('/api/atlas/'+encodeURIComponent(item.id),{
        method:'PATCH',
        headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({annotationJson:marks||{}})
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok){alert(data.error||'儲存標記失敗');return;}
      const count=marks&&marks.marks?marks.marks.length:0;
      item.annotationJson=marks||{};
      const status=row?.querySelector('[data-frame-status]');
      if(status)status.textContent=count?`✓ 已標記 ${count} 個`:'未標記';
      host.innerHTML='';
    });
  }
})();
