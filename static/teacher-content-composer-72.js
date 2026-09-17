/* Teacher 7.2: guided composer layered over the task-first content studio.
 * It owns no persistence. Final mutations are delegated to canonical question,
 * material and external-media owners after an explicit teacher confirmation.
 */
(function(){
  'use strict';

  const studioId='teacher-content-studio-71';
  const bodyId='teacher-content-studio-body-71';
  const esc=value=>(window.escapeHtml?window.escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const state={question:null,material:null,external:null};

  const studio=()=>document.getElementById(studioId);
  const body=()=>document.getElementById(bodyId);
  const scope=()=>({
    area:document.getElementById('admin-quiz-area')?.value||document.getElementById('admin-material-area')?.value||window.currentTrainingArea||'internal',
    group:document.getElementById('admin-quiz-group')?.value||document.getElementById('admin-material-group')?.value||window.currentGroupKey||'grpBio',
  });

  function stepper(step,labels=['選擇內容','編輯內容','預覽確認']){
    return `<div class="grid grid-cols-3 gap-2 mb-5">${labels.map((label,i)=>{const n=i+1,done=n<step,active=n===step;return `<div class="rounded-xl border px-3 py-2 text-center ${active?'border-teal-300 bg-teal-50 text-teal-900':done?'border-emerald-200 bg-emerald-50 text-emerald-800':'border-slate-200 bg-white text-slate-400'}"><div class="text-[10px] font-black">${done?'✓':n}</div><div class="text-xs font-bold mt-0.5">${esc(label)}</div></div>`;}).join('')}</div>`;
  }

  function setSelect(select,wanted){
    if(!select)return false;
    const options=[...select.options];
    let option=options.find(o=>o.value===wanted);
    if(!option&&wanted==='video')option=options.find(o=>String(o.value).startsWith('video_'))||options.find(o=>/影片|影音/.test(o.textContent||''));
    if(!option&&wanted==='image')option=options.find(o=>o.value==='image')||options.find(o=>/圖片/.test(o.textContent||''));
    if(!option&&wanted==='standard')option=options.find(o=>['standard','file','document'].includes(o.value))||options.find(o=>/一般|教材|文件/.test(o.textContent||''));
    if(!option&&wanted==='video-material')option=options.find(o=>['video','media'].includes(o.value))||options.find(o=>/影音|影片/.test(o.textContent||''));
    if(!option)return false;
    select.value=option.value;
    select.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  }

  async function loadCategories(){
    const {area,group}=scope();
    const response=await fetch(`/api/quiz-categories?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`,{credentials:'same-origin'});
    const data=await response.json().catch(()=>[]);
    if(!response.ok)throw new Error(data.error||'無法讀取考卷清單');
    return Array.isArray(data)?data:[];
  }

  function imageKindOptions(){
    return `<div class="mt-4"><div class="text-sm font-bold text-slate-700">圖片類型</div><div class="mt-2 grid grid-cols-3 gap-2"><label class="cursor-pointer rounded-xl border border-slate-200 bg-white p-3 text-center text-xs font-bold"><input class="mr-1" type="radio" name="composer-image-kind" value="顯微鏡" checked>🔬 顯微鏡</label><label class="cursor-pointer rounded-xl border border-slate-200 bg-white p-3 text-center text-xs font-bold"><input class="mr-1" type="radio" name="composer-image-kind" value="血球">🩸 血球</label><label class="cursor-pointer rounded-xl border border-slate-200 bg-white p-3 text-center text-xs font-bold"><input class="mr-1" type="radio" name="composer-image-kind" value="">🖼️ 其他</label></div></div>`;
  }

  async function renderQuestionStart(preset){
    const host=body();if(!host)return;
    host.innerHTML=`${stepper(1)}<div class="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">正在讀取目前組別的考卷…</div>`;
    try{
      const categories=await loadCategories();
      if(!categories.length){host.innerHTML=`${stepper(1)}<div class="rounded-2xl border border-amber-200 bg-amber-50 p-5"><h4 class="font-black text-amber-950">目前還沒有考卷</h4><p class="mt-1 text-sm text-amber-800">請先建立考卷，再新增題目。</p><div class="mt-4 flex gap-2"><button data-studio-action="exam" class="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">建立考卷</button><button data-studio-back class="rounded-xl border bg-white px-4 py-2 text-sm font-bold">返回</button></div></div>`;return;}
      const title=preset==='image'?'圖片判讀題':preset==='video'?'影片互動題':'一般考題';
      host.innerHTML=`${stepper(1)}<div class="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black text-slate-900">${esc(title)}</h4><p class="mt-1 text-xs text-slate-500">第一步先選考卷；下一步只顯示這種題型需要的欄位。</p><label class="mt-4 block text-sm font-bold text-slate-700">加入哪一份考卷？<select id="composer-question-exam-72" class="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">${categories.map(c=>`<option value="${esc(c.id)}">${esc(c.title||c.id)}</option>`).join('')}</select></label>${preset==='image'?imageKindOptions():''}<div class="mt-5 flex justify-between gap-2"><button data-studio-back class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button data-composer-question-next data-preset="${esc(preset)}" class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white">下一步：編輯題目</button></div></div>`;
    }catch(error){host.innerHTML=`${stepper(1)}<div class="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">❌ ${esc(error.message)}</div>`;}
  }

  function questionPreviewData(catId){
    const v=id=>document.getElementById(`qform-${catId}-${id}`);
    const raw=v('type')?.value||'choice';
    const type=raw.startsWith('video_')?raw.slice(6):raw;
    const question=v('question')?.value.trim()||'尚未輸入題幹';
    const options=[0,1,2,3].map(i=>v(`opt${i}`)?.value.trim()||'').filter(Boolean);
    let answer='';
    if(['choice','image'].includes(type)||raw==='video_choice')answer=String.fromCharCode(65+Number(v('correct')?.value||0));
    else if(type==='multi')answer=[0,1,2,3].filter(i=>v(`multi${i}`)?.checked).map(i=>String.fromCharCode(65+i)).join('、')||'未設定';
    else if(type==='true_false')answer=Number(v('truefalse-correct')?.value||0)===0?'是':'否';
    else if(type==='fill')answer=v('fill-answers')?.value||'未設定';
    else answer='人工批改';
    return {raw,type,question,options,answer,mediaUrl:v('media-url')?.value.trim()||'',pauseAt:Number(v('pause-at')?.value||0),imageFile:v('image')?.files?.[0]||null};
  }

  function paintQuestionPreview(catId,preview){
    if(!preview)return;
    const data=questionPreviewData(catId);
    preview.querySelector('[data-preview-question]').textContent=data.question;
    const media=preview.querySelector('[data-preview-media]');
    media.innerHTML='';
    if(data.imageFile){const img=document.createElement('img');img.src=URL.createObjectURL(data.imageFile);img.alt='題目圖片預覽';img.className='mb-3 max-h-72 w-full rounded-xl border border-slate-200 bg-slate-50 object-contain';media.appendChild(img);}
    if(data.raw.startsWith('video_')){const box=document.createElement('div');box.className='mb-3 rounded-xl bg-slate-900 px-4 py-3 text-xs text-white/90';box.textContent=data.mediaUrl?`🎬 影片：${data.mediaUrl}${data.pauseAt?`｜${data.pauseAt} 秒提示`:''}`:'🎬 尚未填入影片網址';media.appendChild(box);}
    const answers=preview.querySelector('[data-preview-options]');answers.innerHTML='';
    if(['choice','multi','image'].includes(data.type)||['video_choice','video_multi'].includes(data.raw)){
      (data.options.length?data.options:['選項 A','選項 B']).forEach((text,i)=>{const row=document.createElement('div');row.className='rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm';row.textContent=`${String.fromCharCode(65+i)}. ${text}`;answers.appendChild(row);});
    }else if(data.type==='true_false')answers.innerHTML='<div class="grid grid-cols-2 gap-2"><div class="rounded-xl border bg-white p-2 text-center">是</div><div class="rounded-xl border bg-white p-2 text-center">否</div></div>';
    else if(data.type==='fill')answers.innerHTML='<div class="rounded-xl border border-dashed bg-white p-3 text-sm text-slate-400">學員輸入答案…</div>';
    else answers.innerHTML='<div class="rounded-xl border border-dashed bg-white p-3 text-sm text-slate-400">學員輸入作答內容…</div>';
    preview.querySelector('[data-preview-answer]').textContent=`教師檢查：正確答案／批改方式 → ${data.answer}`;
  }

  function decorateQuestionEditor(catId,preset,imageKind){
    const question=document.getElementById(`qform-${catId}-question`);if(!question)return;
    const details=question.closest('details');if(details)details.open=true;
    const host=question.closest('.rounded-xl')||question.parentElement;if(!host)return;
    if(imageKind){const tag=document.getElementById(`qform-${catId}-tag`);if(tag&&!tag.value)tag.value=imageKind;}
    const existing=host.querySelector('[data-composer-question-guide]');if(existing){paintQuestionPreview(catId,host.querySelector('[data-composer-question-preview]'));return;}
    const guide=document.createElement('div');guide.dataset.composerQuestionGuide='1';guide.className='rounded-2xl border border-teal-200 bg-teal-50/70 p-3';guide.innerHTML=`${stepper(2,['選擇考卷','編輯題目','學生預覽'])}<div class="flex flex-wrap items-center justify-between gap-2"><div><div class="text-sm font-black text-teal-950">教師出題導引</div><div class="text-xs text-teal-700 mt-0.5">必要欄位先完成；右下方會即時呈現學生看到的題目。</div></div><span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-teal-700">${preset==='image'?'圖片判讀題':preset==='video'?'影片互動題':'一般考題'}</span></div>`;
    host.prepend(guide);
    const preview=document.createElement('div');preview.dataset.composerQuestionPreview='1';preview.className='rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4';preview.innerHTML=`<div class="mb-3 flex items-center justify-between"><div><div class="text-sm font-black text-indigo-950">③ 學生預覽</div><div class="text-[11px] text-indigo-700">只模擬學員看到的內容，不會顯示答案。</div></div><span class="rounded-full bg-white px-2 py-1 text-[10px] font-bold text-indigo-700">即時更新</span></div><div data-preview-media></div><div data-preview-question class="font-black text-slate-900"></div><div data-preview-options class="mt-3 space-y-2"></div><div data-preview-answer class="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-[11px] font-bold text-amber-800"></div>`;
    const add=[...host.querySelectorAll('button')].find(b=>b.getAttribute('onclick')?.includes('adminAddQuizQuestion'));
    if(add){add.textContent='✅ 建立題目';add.classList.add('w-full','sm:w-auto');host.insertBefore(preview,add);}else host.appendChild(preview);
    const refresh=()=>paintQuestionPreview(catId,preview);
    host.addEventListener('input',refresh);host.addEventListener('change',refresh);refresh();
    question.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>question.focus(),250);
  }

  async function openQuestionEditor(preset){
    const catId=document.getElementById('composer-question-exam-72')?.value;if(!catId)return;
    const imageKind=document.querySelector('input[name="composer-image-kind"]:checked')?.value||'';
    state.question={preset,catId,imageKind,...scope()};
    window.teacherContentStudioClose?.();
    await window.openAdminWorkspace?.('assessment');
    const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');
    if(area)area.value=state.question.area;if(group)group.value=state.question.group;
    await window.renderAdminQuizCategories?.(true);
    const panel=document.getElementById(`qpanel-${catId}`);if(panel?.classList.contains('hidden'))await window.toggleQuizQuestionsPanel?.(catId);
    const type=document.getElementById(`qform-${catId}-type`);setSelect(type,preset==='image'?'image':preset==='video'?'video':'choice');window.updateManualQuestionType?.(catId);
    decorateQuestionEditor(catId,preset,imageKind);
  }

  function courseOptions(selected=''){
    const source=document.getElementById('admin-material-course');
    const options=source?[...source.options]:[];
    if(!options.length)return '<option value="">未指定課程</option>';
    return options.map(o=>`<option value="${esc(o.value)}" ${o.value===selected?'selected':''}>${esc(o.textContent)}</option>`).join('');
  }

  function formatSize(bytes){if(!Number.isFinite(bytes))return '';if(bytes<1024*1024)return `${Math.max(1,Math.round(bytes/1024))} KB`;return `${(bytes/1024/1024).toFixed(1)} MB`;}

  function renderMaterialEdit(kind){
    state.material={kind,files:[],...scope()};const host=body();if(!host)return;
    host.innerHTML=`${stepper(2)}<div class="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black">${kind==='video'?'🎥 上傳影音教材':'📄 上傳教材'}</h4><p class="mt-1 text-xs text-slate-500">先選檔案與必要資訊；下一步會先讓你確認，不會立刻上傳。</p><div class="mt-4 grid gap-3 sm:grid-cols-2"><label class="sm:col-span-2 text-sm font-bold">教材檔案<div class="mt-2 flex items-center gap-2"><button type="button" data-composer-material-pick class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-bold text-white">選擇檔案</button><span id="composer-material-files-72" class="text-xs text-slate-500">尚未選擇</span></div></label><label class="text-sm font-bold">教材名稱<input id="composer-material-title-72" class="mt-1 w-full rounded-xl border p-2.5 text-sm" placeholder="留白則沿用檔名"></label><label class="text-sm font-bold">所屬課程<select id="composer-material-course-72" class="mt-1 w-full rounded-xl border p-2.5 text-sm">${courseOptions()}</select></label><label class="sm:col-span-2 text-sm font-bold">簡短說明<textarea id="composer-material-desc-72" rows="2" class="mt-1 w-full rounded-xl border p-2.5 text-sm" placeholder="選填"></textarea></label></div><div class="mt-5 flex justify-between gap-2"><button data-studio-back class="rounded-xl border px-4 py-2 text-sm font-bold">取消</button><button data-composer-material-preview class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white">下一步：預覽確認</button></div></div>`;
  }

  function pickMaterialFiles(){
    const input=document.getElementById('admin-pptx-upload-input');if(!input)return alert('教材上傳元件尚未載入');
    input.value='';input.addEventListener('change',()=>{state.material.files=[...(input.files||[])].map(f=>({name:f.name,size:f.size,type:f.type}));const label=document.getElementById('composer-material-files-72');if(label)label.textContent=state.material.files.length?`${state.material.files.length} 份｜${state.material.files.map(f=>f.name).join('、')}`:'尚未選擇';},{once:true});input.click();
  }

  function renderMaterialPreview(){
    if(!state.material?.files?.length)return alert('請先選擇教材檔案');
    state.material.title=document.getElementById('composer-material-title-72')?.value.trim()||'';state.material.desc=document.getElementById('composer-material-desc-72')?.value.trim()||'';state.material.courseId=document.getElementById('composer-material-course-72')?.value||'';state.material.courseLabel=document.getElementById('composer-material-course-72')?.selectedOptions?.[0]?.textContent||'未指定課程';
    const total=state.material.files.reduce((n,f)=>n+f.size,0),host=body();
    host.innerHTML=`${stepper(3)}<div class="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black">確認教材</h4><div class="mt-4 rounded-2xl bg-slate-50 p-4"><div class="text-3xl">${state.material.kind==='video'?'🎥':'📄'}</div><div class="mt-2 font-black">${esc(state.material.title||state.material.files[0].name)}</div><div class="mt-1 text-xs text-slate-500">${state.material.files.length} 份檔案｜${formatSize(total)}｜${esc(state.material.courseLabel)}</div><ul class="mt-3 space-y-1 text-xs text-slate-600">${state.material.files.map(f=>`<li>• ${esc(f.name)} <span class="text-slate-400">${formatSize(f.size)}</span></li>`).join('')}</ul>${state.material.desc?`<p class="mt-3 text-sm text-slate-600">${esc(state.material.desc)}</p>`:''}</div><div class="mt-5 flex justify-between gap-2"><button data-composer-material-edit class="rounded-xl border px-4 py-2 text-sm font-bold">← 返回修改</button><button data-composer-material-submit class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white">確認並開始上傳</button></div></div>`;
  }

  async function submitMaterial(){
    const draft=state.material;if(!draft)return;
    window.teacherContentStudioClose?.();await window.openAdminWorkspace?.('course-materials');
    const area=document.getElementById('admin-material-area'),group=document.getElementById('admin-material-group');if(area)area.value=draft.area;if(group)group.value=draft.group;
    await Promise.resolve(window.refreshAdminMaterialCourses?.());
    const title=document.getElementById('admin-material-title'),desc=document.getElementById('admin-material-desc'),course=document.getElementById('admin-material-course'),type=document.getElementById('admin-material-type');if(title)title.value=draft.title;if(desc)desc.value=draft.desc;if(course&&[...course.options].some(o=>o.value===draft.courseId))course.value=draft.courseId;setSelect(type,draft.kind==='video'?'video-material':'standard');window.updateAdminMaterialTypeFields?.();
    const status=document.getElementById('admin-upload-status');status?.scrollIntoView({behavior:'smooth',block:'center'});await window.adminUploadMaterials?.();
  }

  function renderExternalEdit(){
    state.external={...scope()};const host=body();if(!host)return;
    host.innerHTML=`${stepper(2)}<div class="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black">🔗 外部影音／連結</h4><p class="mt-1 text-xs text-slate-500">貼入 YouTube、Shorts 或允許的 HTTPS 影音網址；先預覽資訊再建立。</p><div class="mt-4 grid gap-3 sm:grid-cols-2"><label class="text-sm font-bold">名稱<input id="composer-external-title-72" class="mt-1 w-full rounded-xl border p-2.5 text-sm" placeholder="例如：儀器操作示範"></label><label class="text-sm font-bold">所屬課程<select id="composer-external-course-72" class="mt-1 w-full rounded-xl border p-2.5 text-sm">${courseOptions()}</select></label><label class="sm:col-span-2 text-sm font-bold">網址<input id="composer-external-url-72" type="url" class="mt-1 w-full rounded-xl border p-2.5 text-sm" placeholder="https://youtube.com/watch?v=..."></label><label class="sm:col-span-2 text-sm font-bold">說明<textarea id="composer-external-desc-72" rows="2" class="mt-1 w-full rounded-xl border p-2.5 text-sm" placeholder="選填"></textarea></label></div><div class="mt-5 flex justify-between gap-2"><button data-studio-back class="rounded-xl border px-4 py-2 text-sm font-bold">取消</button><button data-composer-external-preview class="rounded-xl bg-sky-700 px-4 py-2 text-sm font-black text-white">下一步：預覽確認</button></div></div>`;
  }

  function externalProvider(url){try{const u=new URL(url);if(u.protocol!=='https:')return {ok:false,label:'僅接受 HTTPS'};const host=u.hostname.toLowerCase();if(host.includes('youtube.com')||host==='youtu.be')return {ok:true,label:u.pathname.includes('/shorts/')?'YouTube Shorts':'YouTube'};if(/\.(mp4|webm)$/i.test(u.pathname))return {ok:true,label:'HTTPS 影音檔'};return {ok:true,label:'外部 HTTPS 連結'};}catch(_){return {ok:false,label:'網址格式不正確'};}}

  function renderExternalPreview(){
    const title=document.getElementById('composer-external-title-72')?.value.trim()||'',url=document.getElementById('composer-external-url-72')?.value.trim()||'',desc=document.getElementById('composer-external-desc-72')?.value.trim()||'',course=document.getElementById('composer-external-course-72');const provider=externalProvider(url);if(!title)return alert('請輸入教材名稱');if(!provider.ok)return alert(provider.label);
    state.external={...state.external,title,url,desc,courseId:course?.value||'',courseLabel:course?.selectedOptions?.[0]?.textContent||'未指定課程',provider:provider.label};const host=body();
    host.innerHTML=`${stepper(3)}<div class="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-5"><h4 class="text-lg font-black">確認外部教材</h4><div class="mt-4 rounded-2xl border border-sky-200 bg-sky-50 p-4"><div class="text-xs font-black text-sky-700">${esc(state.external.provider)}</div><div class="mt-2 font-black text-slate-900">${esc(title)}</div><div class="mt-1 break-all text-xs text-slate-500">${esc(url)}</div><div class="mt-2 text-xs text-slate-600">課程：${esc(state.external.courseLabel)}</div>${desc?`<p class="mt-3 text-sm text-slate-600">${esc(desc)}</p>`:''}</div><p class="mt-3 text-[11px] text-slate-500">此處不直接嵌入第三方內容；建立時仍由既有後端驗證 provider 與網址。</p><div class="mt-5 flex justify-between gap-2"><button data-composer-external-edit class="rounded-xl border px-4 py-2 text-sm font-bold">← 返回修改</button><button data-composer-external-submit class="rounded-xl bg-sky-700 px-4 py-2 text-sm font-black text-white">確認並建立</button></div></div>`;
  }

  async function submitExternal(){
    const draft=state.external;if(!draft)return;
    window.teacherContentStudioClose?.();await window.openAdminWorkspace?.('course-materials');
    const area=document.getElementById('admin-material-area'),group=document.getElementById('admin-material-group');if(area)area.value=draft.area;if(group)group.value=draft.group;
    const opener=window.openExternalMaterialCreateDrawer||window.openExternalMaterialDrawer;await opener?.();
    const set=(id,value)=>{const el=document.getElementById(id);if(el)el.value=value||'';};set('external-material-title',draft.title);set('external-material-description',draft.desc);set('external-material-url',draft.url);set('external-material-area',draft.area);set('external-material-group',draft.group);set('external-material-course',draft.courseId);
    const create=window.createExternalMaterialFromDrawer||window.saveExternalMaterialLink;if(typeof create==='function')await create();
  }

  function handleStudioAction(action){
    if(action==='question')return renderQuestionStart('choice');
    if(action==='image-question')return renderQuestionStart('image');
    if(action==='video-question')return renderQuestionStart('video');
    if(action==='material')return renderMaterialEdit('standard');
    if(action==='video-material')return renderMaterialEdit('video');
    if(action==='external')return renderExternalEdit();
    return false;
  }

  document.addEventListener('click',event=>{
    const root=studio();if(!root||!root.contains(event.target))return;
    const action=event.target.closest('[data-studio-action]')?.dataset.studioAction;
    if(['question','image-question','video-question','material','video-material','external'].includes(action)){event.preventDefault();event.stopImmediatePropagation();handleStudioAction(action);return;}
    const qnext=event.target.closest('[data-composer-question-next]');if(qnext){event.preventDefault();event.stopImmediatePropagation();openQuestionEditor(qnext.dataset.preset||'choice');return;}
    if(event.target.closest('[data-composer-material-pick]')){event.preventDefault();event.stopImmediatePropagation();pickMaterialFiles();return;}
    if(event.target.closest('[data-composer-material-preview]')){event.preventDefault();event.stopImmediatePropagation();renderMaterialPreview();return;}
    if(event.target.closest('[data-composer-material-edit]')){event.preventDefault();event.stopImmediatePropagation();renderMaterialEdit(state.material?.kind||'standard');return;}
    if(event.target.closest('[data-composer-material-submit]')){event.preventDefault();event.stopImmediatePropagation();submitMaterial();return;}
    if(event.target.closest('[data-composer-external-preview]')){event.preventDefault();event.stopImmediatePropagation();renderExternalPreview();return;}
    if(event.target.closest('[data-composer-external-edit]')){event.preventDefault();event.stopImmediatePropagation();renderExternalEdit();return;}
    if(event.target.closest('[data-composer-external-submit]')){event.preventDefault();event.stopImmediatePropagation();submitExternal();}
  },true);

  window.TeacherContentComposer72={handleStudioAction,renderQuestionStart,decorateQuestionEditor};
})();
