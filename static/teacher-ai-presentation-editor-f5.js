/* Phase F5-2 · immutable teacher slide editor for AI PowerPoint revisions. */
(async function(){
  'use strict';
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
    return dialog;
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
        slides:(Array.isArray(item.slides)?item.slides:[]).map(slide=>({...slide,blocks:Array.isArray(slide.blocks)?slide.blocks:[]}))
      };
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
