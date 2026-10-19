(()=>{
  'use strict';

  const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));
  let activeRootId='atlas-manager';

  const root=()=>document.getElementById(activeRootId)||document.getElementById('atlas-manager');

  const CATEGORY_LABELS={microscope:'顯微鏡照片',blood_cell:'血球圖片',urine_sediment:'尿液沉渣圖片',colony:'菌落圖片'};
  const label=(text,hint,control,wide)=>`<label class="block text-xs font-bold text-slate-700${wide?' sm:col-span-2':''}">${text}${hint?`<span class="ml-1 font-normal text-slate-500">${hint}</span>`:''}<span class="mt-1 block font-normal">${control}</span></label>`;
  const fields=(prefix='',value={})=>{
    const category=String(value.category||'microscope');
    const difficulty=String(value.difficulty||'general');
    const input='class="w-full border rounded-lg p-2 text-sm"';
    return `
      <input type="hidden" name="${prefix}group" value="${esc(value.group||'')}">
      <div class="grid gap-2 sm:grid-cols-2">
        ${label('圖片名稱','（留空會直接用檔名）',`<input name="${prefix}title" value="${esc(value.title||'')}" ${input}>`)}
        ${label('圖片類型','',`<select name="${prefix}category" ${input}>${Object.entries(CATEGORY_LABELS).map(([key,text])=>`<option value="${key}" ${category===key?'selected':''}>${text}</option>`).join('')}</select>`)}
        ${label('難易度','',`<select name="${prefix}difficulty" ${input}>
          <option value="general" ${difficulty==='general'?'selected':''}>一般</option>
          <option value="basic" ${difficulty==='basic'?'selected':''}>入門</option>
          <option value="advanced" ${difficulty==='advanced'?'selected':''}>進階</option>
        </select>`)}
        ${label('排列順序','（數字小的排前面，不確定就保持 0）',`<input name="${prefix}sortOrder" value="${esc(value.sortOrder||0)}" type="number" ${input}>`)}
        ${label('關鍵字','（用逗號分開，之後方便搜尋，例如：尿液, 上皮細胞）',`<input name="${prefix}tags" value="${esc((value.tags||[]).join(', '))}" ${input}>`,true)}
      </div>
      ${label('圖片說明','（例如：這是什麼細胞、在哪裡看到）',`<textarea name="${prefix}description" rows="2" ${input}>${esc(value.description||'')}</textarea>`)}
      ${label('辨別重點','（容易和哪些細胞搞混？怎麼分辨？）',`<textarea name="${prefix}differentialPoints" rows="2" ${input}>${esc(value.differentialPoints||'')}</textarea>`)}
      ${label('教學提醒','（教學時想特別提醒學員的地方）',`<textarea name="${prefix}teachingNotes" rows="2" ${input}>${esc(value.teachingNotes||'')}</textarea>`)}`;
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
        <b>Word 圖片轉圖譜｜第 1 步（共 5 步）：選擇 Word 檔</b>
        <p class="text-xs text-slate-600">系統會把這份 Word 裡的圖片一張一張取出來，另外放進「圖譜」。原本的 Word 教材不會被改動或刪除。</p>
        <p class="text-xs text-amber-800">請先確認圖片裡沒有病人的姓名、病歷號、條碼、生日等個人資料（去識別化）。</p>
        <select id="atlas-docx-source" class="w-full border rounded-lg p-2 text-sm"><option>正在載入 Word 教材…</option></select>
        <button id="atlas-docx-next" type="button" class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">下一步：找出 Word 裡的圖片</button>
      </section>`;
    try{
      const response=await fetch('/api/slides/admin',{credentials:'same-origin',cache:'no-store'});
      const data=await response.json().catch(()=>[]);
      if(!response.ok)throw new Error(data.error||'無法讀取教材清單');
      const list=Array.isArray(data)?data:(data.slides||data.materials||[]);
      const docx=list.filter(item=>/\.docx$/i.test(item.filename||item.storageFilename||''));
      const select=box.querySelector('#atlas-docx-source');
      select.innerHTML=docx.map(item=>`<option value="${esc(item.id)}">${esc(item.title||item.filename||item.id)}</option>`).join('')
        ||'<option value="">沒有可以使用的 Word（.docx）教材</option>';
      if(preferred&&docx.some(item=>String(item.id)===preferred))select.value=preferred;
      box.querySelector('#atlas-docx-next')?.addEventListener('click',preview);
      if(preferred&&select.value===preferred)await preview();
      return true;
    }catch(error){
      box.innerHTML=`<p class="text-sm text-rose-600">無法讀取 Word 教材：${esc(error.message||'未知錯誤')}</p>`;
      return false;
    }
  };

  async function preview(){
    const box=root();
    const id=box?.querySelector('#atlas-docx-source')?.value||'';
    if(!box||!id)return;
    // 讀 Word 要解壓縮與分析，主機忙時可能要等一陣子：先明確顯示「處理中」，避免看起來沒反應。
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-2" role="status">
        <b>正在找出這份 Word 裡的圖片…</b>
        <p class="text-xs text-slate-600">請稍候，通常幾秒到半分鐘；請不要重複按按鈕或離開頁面。</p>
      </section>`;
    let response,data;
    try{
      response=await fetch('/api/atlas/import-docx/'+encodeURIComponent(id)+'/preview',{
        method:'POST',
        credentials:'same-origin'
      });
      data=await response.json().catch(()=>({}));
    }catch(error){
      response={ok:false};data={error:'連線中斷或逾時，請稍後再試一次。'};
    }
    if(!response.ok){
      alert(data.error||'無法讀取這份 Word 檔，請確認檔案沒有損壞。');
      await window.openAtlasDocxWizard(activeRootId);
      return;
    }
    const images=Array.isArray(data.preview?.images)?data.preview.images:[];
    const warnings=(data.preview?.warnings||[]).map(warning=>`<p class="text-xs text-amber-800">⚠ ${esc(warning)}</p>`).join('');
    if(!images.length){
      box.innerHTML=`
        <section class="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 space-y-3">
          <b>這份 Word 裡找不到可以取出的圖片</b>
          ${warnings}
          <p class="text-xs text-slate-600">原本的 Word 教材不受影響。如果圖片設成「文繞圖」（會浮在文字上方）、是做成圖表的，或不是 JPG／PNG 格式，請先在 Word 裡點選圖片 → 圖片格式 → 文繞圖 → 選「與文字排列在一起」，存檔後再試一次。</p>
          <button id="atlas-docx-reselect" type="button" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold">重新選擇 Word</button>
        </section>`;
      box.querySelector('#atlas-docx-reselect')?.addEventListener('click',()=>window.openAtlasDocxWizard(activeRootId));
      return;
    }
    const defaults={group:data.defaultGroup||'',category:'microscope',difficulty:'general',sortOrder:0};
    box.innerHTML=`
      <section class="mt-4 rounded-2xl border border-teal-200 bg-white p-4 space-y-3">
        <b>第 2 步（共 5 步）：先填這批圖片共同的資料</b>
        <p class="text-xs text-slate-500">已在 Word 裡找到 ${images.length} 張圖片。這裡填的資料會先套用到每一張圖，下一步還可以逐張修改。放進圖譜後都是「草稿」，學員暫時看不到，等你確認後才會公開。</p>
        ${warnings}
        <form id="atlas-docx-common" class="space-y-2">
          ${fields('',defaults)}
          <button class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">下一步：挑選要用的圖片</button>
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
        <b>第 3 步（共 5 步）：挑選要放進圖譜的圖片</b>
        <p class="text-xs text-slate-500">Word 教材會照原樣保留；只有打勾的圖片會另外放進圖譜。系統會依圖片旁邊的文字，先幫你填好名稱和類型，你可以自己修改。</p>
        <div class="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-600"><span>這份 Word 之前如果匯入過好幾次，可以先清掉重複的草稿。</span><button id="atlas-docx-dedupe" type="button" class="rounded-lg border border-slate-300 bg-white px-2 py-1 font-bold text-slate-700">🧹 移除這份 Word 的重複草稿</button><span id="atlas-docx-dedupe-msg" role="status" class="font-bold"></span></div>
        <form id="atlas-docx-items" class="space-y-3">
          ${images.map(item=>`
            <fieldset class="border rounded-lg p-3">
              <label class="font-bold text-sm">
                <input type="checkbox" name="pick" value="${Number(item.index)}" data-relationship="${esc(item.relationshipId||'')}" checked>
                第 ${Number(item.index)} 張圖片
              </label>
              ${item.thumbnail?`<img src="${esc(item.thumbnail)}" alt="圖片 ${Number(item.index)} 預覽" loading="lazy" class="mt-2 max-h-52 rounded-lg border border-slate-200 bg-slate-50 object-contain">`:'<p class="mt-1 text-xs text-slate-400">（此圖未提供預覽）</p>'}
              <p class="mt-1 text-xs text-slate-500">${item.section?'圖片附近的文字：'+esc(item.section):'（這張圖附近沒有文字）'}</p>
              <details class="mt-2">
                <summary class="cursor-pointer text-xs text-teal-700">修改這張圖的名稱與說明</summary>
                <p class="mt-2 text-xs font-bold text-teal-700">已先把圖片旁邊的文字填進名稱和說明，可以直接修改。</p>
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
    box.querySelector('#atlas-docx-dedupe')?.addEventListener('click',async event=>{
      const msg=box.querySelector('#atlas-docx-dedupe-msg');
      if(!confirm('會刪除這份 Word 重複匯入、尚未發布的圖譜草稿，每組只保留最早的一張。已發布的圖譜不會被動到。要繼續嗎？'))return;
      event.currentTarget.disabled=true;
      try{
        const res=await fetch('/api/atlas/dedupe',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({materialId})});
        const data=await res.json().catch(()=>({}));
        if(!res.ok)throw new Error(data.error||'清理失敗');
        msg.textContent='已移除 '+(data.removed||0)+' 張重複草稿。';
      }catch(error){msg.textContent='清理失敗：'+(error.message||'未知錯誤');}
      event.currentTarget.disabled=false;
    });
    box.querySelector('#atlas-docx-items')?.addEventListener('submit',event=>{
      event.preventDefault();
      const form=event.currentTarget;
      const items=[...form.querySelectorAll('[name=pick]:checked')].map(input=>({
        index:Number(input.value),
        relationshipId:String(input.dataset.relationship||''),
        ...read(form,'item-'+input.value+'-'),
      }));
      if(!items.length){
        alert('請至少打勾一張圖片');
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
        <b>第 4 步（共 5 步）：確認</b>
        <p class="text-sm">即將把 ${items.length} 張圖片放進圖譜（草稿）。原本的 Word 不會被刪除或改寫；公開給學員之前，你還可以逐張修改。</p>
        <ul class="text-xs list-disc pl-5">${items.map(item=>`<li>${esc(item.title||('第 '+item.index+' 張圖片'))} · ${esc(CATEGORY_LABELS[item.category]||'顯微鏡照片')}</li>`).join('')}</ul>
        <button id="atlas-docx-confirm" type="button" class="rounded-lg bg-teal-700 text-white px-3 py-2 font-bold">確認，放進圖譜</button>
      </section>`;
    const confirmButton=box.querySelector('#atlas-docx-confirm');
    const message=document.createElement('p');
    message.id='atlas-docx-confirm-message';
    message.setAttribute('role','status');
    message.className='text-sm font-bold text-slate-600';
    confirmButton?.after(message);
    const say=(text,bad)=>{message.textContent=text;message.className='text-sm font-bold '+(bad?'text-rose-700':'text-slate-600');};
    confirmButton?.addEventListener('click',async()=>{
      if(confirmButton.disabled)return;
      confirmButton.disabled=true;
      confirmButton.textContent='放進圖譜中，請稍候…';
      say('正在處理，圖片多的時候需要十幾秒，請不要關閉或重新整理頁面。');
      try{
        const response=await fetch('/api/atlas/import-docx/'+encodeURIComponent(materialId)+'/confirm',{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          credentials:'same-origin',
          body:JSON.stringify({metadata,items})
        });
        const data=await response.json().catch(()=>({}));
        if(!response.ok){
          const reason=data.error||('伺服器回應異常（代碼 '+response.status+'）');
          throw new Error(reason);
        }
        const created=Array.isArray(data.created)?data.created:[];
        if(!created.length)throw new Error('沒有任何圖片被放進圖譜。');
        framingStep(created);
      }catch(error){
        confirmButton.disabled=false;
        confirmButton.textContent='確認，放進圖譜';
        say('沒有成功：'+(error&&error.message?error.message:'連線中斷')+'。可以再按一次「確認，放進圖譜」；仍然不行，請把這行字截圖給管理員。',true);
      }
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
        <b>第 5 步（共 5 步）：已放進圖譜 ${ids.length} 張，要順便框出細胞的位置嗎？（可以略過）</b>
        <p class="text-xs text-slate-500">框出來之後，學員點圖就能放大看到你寫的介紹，也能拿來出「點選圖片題」。可以現在做，也可以之後到「圖譜」頁再編輯。公開之前，學員都看不到這些圖。</p>
        <ul class="space-y-2">${items.map(item=>`
          <li class="flex flex-wrap items-center gap-2 rounded-lg border p-2" data-atlas-frame-item="${esc(item.id)}">
            <img src="${esc(item.thumbnailUrl||item.imageUrl)}" alt="" class="h-14 w-14 rounded object-cover">
            <span class="min-w-0 flex-1 truncate text-sm font-bold">${esc(item.title)}</span>
            <span class="text-xs text-slate-500" data-frame-status></span>
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
      <div class="flex gap-2"><button type="submit" class="rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-bold text-white">儲存</button>
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
      if(!response.ok){alert(data.error||'儲存失敗，請稍後再試。');return;}
      const count=marks&&marks.marks?marks.marks.length:0;
      item.annotationJson=marks||{};
      const status=row?.querySelector('[data-frame-status]');
      if(status)status.textContent=count?`✓ 已標記 ${count} 個`:'未標記';
      host.innerHTML='';
    });
  }
})();
