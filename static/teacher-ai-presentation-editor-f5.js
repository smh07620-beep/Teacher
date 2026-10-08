/* Phase F5-2 · immutable teacher slide editor for AI PowerPoint revisions. */
(async function(){
  'use strict';
  /* 講稿 → 每頁講者備註：切點由伺服器依內容自動判斷（/api/ai-presentations/align-script），老師不需要自己找。 */
  const CHARS_PER_MINUTE=280;
  function notesDurationText(text){
    const chars=String(text||'').replace(/\s+/g,'').length;
    if(!chars)return '尚無備註：AI 影片會改念本頁的標題與重點。';
    const seconds=Math.max(1,Math.round(chars*60/CHARS_PER_MINUTE));
    return '約 '+chars+' 字，正常語速（每分鐘約 '+CHARS_PER_MINUTE+' 字）約念 '+(seconds>=60?Math.floor(seconds/60)+' 分 '+(seconds%60)+' 秒':seconds+' 秒')+'。';
  }
  window.TeacherScriptToNotesF5=Object.freeze({durationText:notesDurationText});

  const R=await (window.TeacherRBAC681Ready||Promise.resolve(window.TeacherRBAC681||{}));
  const roles=R.roles instanceof Set?R.roles:new Set();
  if(!['clinical_teacher','group_leader','education_admin','system_admin'].some(role=>roles.has(role)))return;

  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const layouts=['title','section','content','image','comparison','table','summary'];
  let current=null;
  let counter=0;

  async function api(path,options={}){
    const response=await fetch(path,{
      credentials:'same-origin',
      cache:'no-store',
      headers:{'Content-Type':'application/json',...(options.headers||{})},
      ...options
    });
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||'PowerPoint 編輯器無法完成操作');
    return data;
  }

  function ensureDialog(){
    let dialog=$('teacher-ai-presentation-editor-f5');
    if(dialog)return dialog;
    dialog=document.createElement('dialog');
    dialog.id='teacher-ai-presentation-editor-f5';
    dialog.className='w-[min(1100px,96vw)] max-h-[92vh] rounded-2xl border border-slate-200 p-0 shadow-2xl backdrop:bg-slate-900/50';
    dialog.innerHTML=`
      <form method="dialog" class="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-slate-200 bg-white p-4">
        <div><p class="text-[10px] font-black tracking-wide text-violet-700">F5 · IMMUTABLE SLIDE EDITOR</p><h3 class="text-lg font-black text-slate-950">教師投影片編輯器</h3><p class="mt-1 text-xs text-slate-500">儲存時會建立新 revision；舊版本與既有正式發布版本不會被覆蓋。</p></div>
        <button value="cancel" class="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-700">關閉</button>
      </form>
      <div class="p-4 space-y-4">
        <label class="block text-xs font-bold text-slate-700">簡報標題<input id="teacher-ppt-editor-title-f5" class="learning-input mt-1 w-full" maxlength="255"></label>
        <section class="rounded-xl border border-violet-200 bg-violet-50/50 p-3 space-y-2" aria-label="用講稿填入講者備註">
          <b class="text-sm text-slate-900">🎙️ 用講稿填入講者備註</b>
          <p class="text-[11px] text-slate-600">系統會自動找出講稿的切點，依內容對應到每一張投影片的「講者備註」，不需要手動標記。AI 影片會照備註逐頁念；有新講稿或改了投影片時可再按一次，微調後按下方儲存。</p>
          <div class="flex flex-col sm:flex-row sm:items-end gap-2">
            <label class="flex-1 text-[11px] font-bold text-slate-600">已核准講稿<select id="teacher-ppt-editor-script-f5" class="learning-input mt-1 w-full"><option value="">讀取講稿中…</option></select></label>
            <button id="teacher-ppt-editor-fill-f5" type="button" class="rounded-lg bg-violet-700 px-4 py-2 text-xs font-black text-white disabled:opacity-40" disabled>依內容自動分段</button>
          </div>
          <p id="teacher-ppt-editor-fill-status-f5" class="text-[11px] text-slate-500" aria-live="polite"></p>
        </section>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div><b class="text-sm text-slate-900">投影片</b><span id="teacher-ppt-editor-count-f5" class="ml-2 text-xs text-slate-400"></span></div>
          <button id="teacher-ppt-editor-add-f5" type="button" class="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-bold text-violet-800">＋ 新增投影片</button>
        </div>
        <div id="teacher-ppt-editor-slides-f5" class="space-y-3"></div>
        <div class="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/95 p-3 shadow-sm backdrop-blur">
          <p id="teacher-ppt-editor-status-f5" class="text-xs text-slate-500" aria-live="polite">修改後請建立新的 PowerPoint revision。</p>
          <button id="teacher-ppt-editor-save-f5" type="button" class="rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-black text-white">儲存為新 revision 並重新產檔</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    $('teacher-ppt-editor-add-f5').addEventListener('click',addSlide);
    $('teacher-ppt-editor-save-f5').addEventListener('click',save);
    $('teacher-ppt-editor-slides-f5').addEventListener('click',slideAction);
    $('teacher-ppt-editor-slides-f5').addEventListener('input',event=>{
      const area=event.target.closest?.('[data-field="speakerNotes"]');
      const label=area?.closest('[data-slide-editor-f5]')?.querySelector('[data-notes-duration]');
      if(label)label.textContent=notesDurationText(area.value);
    });
    $('teacher-ppt-editor-fill-f5').addEventListener('click',fillNotesFromScript);
    $('teacher-ppt-editor-script-f5').addEventListener('change',()=>{
      $('teacher-ppt-editor-fill-f5').disabled=!$('teacher-ppt-editor-script-f5').value;
    });
    return dialog;
  }

  let scripts=[];

  async function loadScripts(materialId){
    const select=$('teacher-ppt-editor-script-f5');
    const button=$('teacher-ppt-editor-fill-f5');
    const note=$('teacher-ppt-editor-fill-status-f5');
    scripts=[];
    if(note)note.textContent='';
    if(button)button.disabled=true;
    if(!select)return;
    if(!materialId){
      select.innerHTML='<option value="">這份投影片沒有關聯教材，無法列出講稿</option>';
      return;
    }
    try{
      const list=await api('/api/media-scripts?materialId='+encodeURIComponent(materialId));
      scripts=(Array.isArray(list)?list:[]).filter(item=>item&&item.status==='approved'&&String(item.body||'').trim());
      select.innerHTML=scripts.length
        ?'<option value="">請選擇講稿…</option>'+scripts.map(item=>`<option value="${esc(item.id)}">${esc(item.title||'教學講稿')}（核准於 ${esc(String(item.approvedAt||item.updatedAt||'').slice(0,10))}）</option>`).join('')
        :'<option value="">這份教材還沒有已核准的講稿（請先到「講稿與配音」核准）</option>';
      if(scripts.length){select.value=scripts[0].id;if(button)button.disabled=false;}
    }catch(error){
      select.innerHTML='<option value="">無法讀取講稿</option>';
      if(note)note.textContent='❌ '+(error.message||'無法讀取講稿');
    }
  }

  async function fillNotesFromScript(auto){
    const note=$('teacher-ppt-editor-fill-status-f5');
    const button=$('teacher-ppt-editor-fill-f5');
    const scriptId=$('teacher-ppt-editor-script-f5')?.value;
    if(!scriptId)return;
    collect();
    const targets=current.slides.filter(slide=>slide.enabled!==false);
    if(!targets.length)return;
    if(targets.some(slide=>String(slide.speakerNotes||'').trim())
      &&!confirm('部分投影片已經有講者備註，重新分段後會被講稿內容取代。要繼續嗎？（儲存前都可以關閉視窗放棄）'))return;
    button.disabled=true;
    if(note)note.textContent='正在依內容自動分段…';
    try{
      const outcome=await api('/api/ai-presentations/align-script',{
        method:'POST',
        body:JSON.stringify({scriptId,slides:targets.map(slide=>({id:slide.id,title:slide.title,bullets:slide.bullets,blocks:slide.blocks}))})
      });
      targets.forEach((slide,position)=>{slide.speakerNotes=String((outcome.segments||[])[position]||'');});
      render();
      const empty=(outcome.segments||[]).filter(text=>!text).length;
      if(note)note.textContent=(auto===true?'✅ 已自動預填：':'✅ ')+'已依內容把講稿自動分到 '+targets.length+' 張投影片的備註。'
        +(empty?` 其中 ${empty} 張沒有分到內容（AI 影片會改念該頁的標題與重點）。`:'')
        +(outcome.truncated?` ${outcome.truncated} 張超過 4000 字已截斷，請檢查。`:'')
        +' 可直接微調，確認後按下方儲存。';
    }catch(error){
      if(note)note.textContent='❌ '+(error.message||'自動分段失敗');
    }finally{
      button.disabled=!$('teacher-ppt-editor-script-f5')?.value;
    }
  }

  function slideCard(slide,index,total){
    const layout=layouts.includes(String(slide.layout||''))?String(slide.layout):'content';
    return `
      <article data-slide-editor-f5 data-slide-id="${esc(slide.id||'')}" class="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2"><b class="text-sm text-slate-900">第 ${index+1} 張</b><label class="text-[11px] font-bold text-slate-600"><input data-field="enabled" type="checkbox" ${slide.enabled!==false?'checked':''}> 啟用</label></div>
          <div class="flex gap-1">
            <button type="button" data-slide-action="up" class="rounded border border-slate-200 bg-white px-2 py-1 text-xs" ${index===0?'disabled':''}>↑</button>
            <button type="button" data-slide-action="down" class="rounded border border-slate-200 bg-white px-2 py-1 text-xs" ${index===total-1?'disabled':''}>↓</button>
            <button type="button" data-slide-action="delete" class="rounded border border-rose-200 bg-white px-2 py-1 text-xs text-rose-700">刪除</button>
          </div>
        </div>
        <div class="grid md:grid-cols-[180px_1fr] gap-3">
          <label class="text-[11px] font-bold text-slate-600">版型<select data-field="layout" class="learning-input mt-1 w-full">${layouts.map(item=>`<option value="${item}" ${item===layout?'selected':''}>${item}</option>`).join('')}</select></label>
          <label class="text-[11px] font-bold text-slate-600">標題<input data-field="title" class="learning-input mt-1 w-full" maxlength="180" value="${esc(slide.title||'')}"></label>
        </div>
        <label class="block text-[11px] font-bold text-slate-600">重點（每行一點）<textarea data-field="bullets" rows="5" class="learning-input mt-1 w-full">${esc((slide.bullets||[]).join('\n'))}</textarea></label>
        <label class="block text-[11px] font-bold text-slate-600">講者備註<textarea data-field="speakerNotes" rows="4" class="learning-input mt-1 w-full">${esc(slide.speakerNotes||'')}</textarea></label>
        <p data-notes-duration class="text-[10px] text-slate-400">${esc(notesDurationText(slide.speakerNotes||''))}</p>
        ${Array.isArray(slide.blocks)&&slide.blocks.length?'<p class="text-[10px] text-slate-400">此頁另有 '+slide.blocks.length+' 個圖表／圖片／表格區塊；本編輯器會原樣保留。</p>':''}
      </article>`;
  }

  function render(){
    const host=$('teacher-ppt-editor-slides-f5');
    if(!host||!current)return;
    host.innerHTML=current.slides.map((slide,index)=>slideCard(slide,index,current.slides.length)).join('');
    $('teacher-ppt-editor-count-f5').textContent=current.slides.length+' 張';
  }

  function collect(){
    if(!current)return;
    const original=new Map(current.slides.map(slide=>[String(slide.id||''),slide]));
    current.title=String($('teacher-ppt-editor-title-f5')?.value||'').trim();
    current.slides=[...document.querySelectorAll('#teacher-ppt-editor-slides-f5 [data-slide-editor-f5]')].map((node,index)=>{
      const id=String(node.dataset.slideId||'')||('f5-'+Date.now()+'-'+(++counter));
      const prior=original.get(id)||{};
      return {
        id,
        order:index+1,
        enabled:Boolean(node.querySelector('[data-field="enabled"]')?.checked),
        layout:String(node.querySelector('[data-field="layout"]')?.value||'content'),
        title:String(node.querySelector('[data-field="title"]')?.value||'').trim(),
        bullets:String(node.querySelector('[data-field="bullets"]')?.value||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean),
        speakerNotes:String(node.querySelector('[data-field="speakerNotes"]')?.value||'').trim(),
        blocks:Array.isArray(prior.blocks)?prior.blocks:[]
      };
    });
  }

  function addSlide(){
    collect();
    current.slides.push({
      id:'f5-'+Date.now()+'-'+(++counter),
      order:current.slides.length+1,
      enabled:true,
      layout:'content',
      title:'新投影片',
      bullets:[],
      speakerNotes:'',
      blocks:[]
    });
    render();
    document.querySelector('#teacher-ppt-editor-slides-f5 [data-slide-editor-f5]:last-child')?.scrollIntoView?.({behavior:'smooth',block:'center'});
  }

  function slideAction(event){
    const button=event.target.closest('[data-slide-action]');
    if(!button)return;
    const card=button.closest('[data-slide-editor-f5]');
    const cards=[...document.querySelectorAll('#teacher-ppt-editor-slides-f5 [data-slide-editor-f5]')];
    const index=cards.indexOf(card);
    if(index<0)return;
    collect();
    const action=button.dataset.slideAction;
    if(action==='delete'){
      if(current.slides.length<=1)return alert('至少要保留一張投影片。');
      current.slides.splice(index,1);
    }else if(action==='up'&&index>0){
      [current.slides[index-1],current.slides[index]]=[current.slides[index],current.slides[index-1]];
    }else if(action==='down'&&index<current.slides.length-1){
      [current.slides[index+1],current.slides[index]]=[current.slides[index],current.slides[index+1]];
    }
    render();
  }

  async function poll(jobId){
    const status=$('teacher-ppt-editor-status-f5');
    for(let attempt=0;attempt<180;attempt+=1){
      const job=await api('/api/ai-presentations/jobs/'+encodeURIComponent(jobId));
      if(status)status.textContent=(job.progressStage||job.status||'重新產檔')+'｜'+Math.round(Number(job.progressPercent||0))+'%'+(job.progressDetail?'｜'+job.progressDetail:'');
      if(job.status==='completed')return job;
      if(job.status==='failed')throw new Error(job.error||'新 revision 產檔失敗');
      await new Promise(resolve=>setTimeout(resolve,1800));
    }
    throw new Error('重新產檔仍在背景處理；可稍後按「讀取版本」查看。');
  }

  async function save(){
    collect();
    const status=$('teacher-ppt-editor-status-f5');
    const button=$('teacher-ppt-editor-save-f5');
    if(!current.title)return alert('請填寫簡報標題。');
    if(!current.slides.length||!current.slides.some(slide=>slide.enabled!==false))return alert('至少要保留一張啟用的投影片。');
    button.disabled=true;
    try{
      if(status)status.textContent='正在建立 immutable revision…';
      const data=await api('/api/ai-presentations/'+encodeURIComponent(current.id),{
        method:'PATCH',
        body:JSON.stringify({title:current.title,slides:current.slides})
      });
      const jobId=String(data.job?.id||'');
      if(!jobId)throw new Error('新 revision 已建立，但沒有收到 Worker 工作 ID。');
      current.id=String(data.presentation?.id||current.id);
      await poll(jobId);
      if(status)status.textContent='✅ 新 revision 已產生；舊版本仍完整保留。';
      $('teacher-ai-presentation-refresh-1016')?.click();
      setTimeout(()=>ensureDialog().close(),500);
    }catch(error){
      if(status)status.textContent='❌ '+(error.message||'儲存失敗');
    }finally{
      button.disabled=false;
    }
  }

  async function openEditor(id){
    const dialog=ensureDialog();
    const status=$('teacher-ppt-editor-status-f5');
    if(status)status.textContent='正在讀取投影片 revision…';
    try{
      const item=await api('/api/ai-presentations/'+encodeURIComponent(id));
      current={
        id:String(item.id||id),
        title:String(item.title||'AI 教學投影片'),
        slides:(Array.isArray(item.slides)?item.slides:[]).map(slide=>({...slide,blocks:Array.isArray(slide.blocks)?slide.blocks:[]})),
        materialId:String(item.materialId||'')
      };
      void loadScripts(current.materialId).then(()=>{
        // 備註全空而且有已核准講稿：自動預填（只是預覽，老師按儲存才會建立新版本）。
        const enabled=current.slides.filter(slide=>slide.enabled!==false);
        if(scripts.length&&enabled.length&&enabled.every(slide=>!String(slide.speakerNotes||'').trim()))void fillNotesFromScript(true);
      });
      $('teacher-ppt-editor-title-f5').value=current.title;
      render();
      if(status)status.textContent='修改後會建立新 revision 並由 AI Worker 重新產生 PPTX。';
      if(typeof dialog.showModal==='function'&&!dialog.open)dialog.showModal();
      else dialog.setAttribute('open','');
    }catch(error){
      alert(error.message||'無法開啟投影片編輯器');
    }
  }

  function decorate(root=document){
    root.querySelectorAll?.('#teacher-ai-presentation-results-1016 [data-presentation-id]').forEach(card=>{
      if(card.querySelector('[data-presentation-edit-f5]'))return;
      const row=card.querySelector('[data-action]')?.parentElement;
      if(!row)return;
      const button=document.createElement('button');
      button.type='button';
      button.dataset.presentationEditF5='1';
      button.className='rounded-lg border border-violet-200 bg-white px-3 py-1.5 font-bold text-violet-700';
      button.textContent='✏️ 編輯投影片';
      button.addEventListener('click',event=>{
        event.preventDefault();
        void openEditor(String(card.dataset.presentationId||''));
      });
      row.appendChild(button);
    });
  }

  window.addEventListener('teacher-ai-presentation-rendered-f5',()=>decorate());
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>decorate(),{once:true});
  else decorate();
  window.TeacherAIPresentationEditorF5=Object.freeze({open:openEditor,decorate});
})();
