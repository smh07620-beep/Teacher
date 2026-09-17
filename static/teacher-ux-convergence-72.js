/* Teacher 7.2 convergence layer.
 * One creation entry, one management surface, one guided question flow.
 * Presentation/orchestration only: final question mutation stays with
 * adminAddQuizQuestion() and existing server-side RBAC.
 */
(function(){
  'use strict';

  const esc=value=>(window.escapeHtml?window.escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const studio=()=>document.getElementById('teacher-content-studio-71');
  const body=()=>document.getElementById('teacher-content-studio-body-71');
  const state={question:null};
  let reconcileScheduled=false;

  function stepper(step){
    const labels=['選擇考卷','編輯題目','預覽確認'];
    return `<div class="grid grid-cols-3 gap-2 mb-5">${labels.map((label,i)=>{const n=i+1,done=n<step,active=n===step;return `<div class="rounded-xl border px-3 py-2 text-center ${active?'border-teal-300 bg-teal-50 text-teal-900':done?'border-emerald-200 bg-emerald-50 text-emerald-800':'border-slate-200 bg-white text-slate-400'}"><div class="text-[10px] font-black">${done?'✓':n}</div><div class="mt-0.5 text-xs font-bold">${label}</div></div>`;}).join('')}</div>`;
  }

  function scope(){
    return {
      area:document.getElementById('admin-quiz-area')?.value||window.currentTrainingArea||'internal',
      group:document.getElementById('admin-quiz-group')?.value||window.currentGroupKey||'grpBio'
    };
  }

  function setTextIfChanged(node,value){
    if(node&&node.textContent!==value) node.textContent=value;
  }

  function hideOnce(node){
    if(!node)return;
    if(!node.classList.contains('hidden')) node.classList.add('hidden');
    if(node.getAttribute('aria-hidden')!=='true') node.setAttribute('aria-hidden','true');
    if(node.tabIndex!==-1) node.tabIndex=-1;
  }

  function showOnce(node){
    if(!node)return;
    if(node.classList.contains('hidden')) node.classList.remove('hidden');
    if(node.hasAttribute('aria-hidden')) node.removeAttribute('aria-hidden');
  }

  function simplifyAssessmentSurface(){
    const root=document.getElementById('assessment-681');
    if(!root)return;
    setTextIfChanged(root.querySelector('h4'),'📝 考卷與已建立題目');
    setTextIfChanged(root.querySelector('h4 + p'),'這裡只管理既有考卷與題目；新增、AI 出題、圖片題與影片題請從「＋ 建立教學內容」開始。');

    const tabs=document.getElementById('assessment-681-tabs');
    [...(tabs?.querySelectorAll('button')||[])].forEach(button=>{
      const onclick=button.getAttribute('onclick')||'';
      if(onclick.includes("'exams'")){
        setTextIfChanged(button,'考卷管理');
        showOnce(button);
        return;
      }
      if(onclick.includes("'bank'")){
        setTextIfChanged(button,'已建立題目');
        showOnce(button);
        return;
      }
      hideOnce(button);
    });

    const assessmentBody=document.getElementById('assessment-681-body');
    if(!assessmentBody)return;
    [...assessmentBody.querySelectorAll('button')].forEach(button=>{
      const onclick=button.getAttribute('onclick')||'';
      if(onclick.includes("assessment681Tab('ai')")||onclick.includes("assessment681Tab('blueprint')")){
        hideOnce(button.closest('.rounded-lg')||button);
      }
      if(onclick.includes("assessment681OpenQuestion('')")) hideOnce(button);
    });
    [...assessmentBody.querySelectorAll('p')].forEach(p=>{
      if(p.textContent.includes('點選題列會打開完整 editor')){
        setTextIfChanged(p,'點選既有題目即可查看、編輯或刪除；新增題目請使用「＋ 建立教學內容」。');
      }
    });
  }

  function compactLegacyCourseWizard(){
    const heading=[...document.querySelectorAll('h4')].find(node=>node.textContent.includes('快速建立整套課程'));
    if(!heading)return;
    const card=heading.closest('.rounded-2xl')||heading.parentElement?.parentElement;
    if(!card||card.dataset.teacher72Compact==='1'||card.closest('[data-teacher72-course-wizard]'))return;
    card.dataset.teacher72Compact='1';
    const details=document.createElement('details');
    details.dataset.teacher72CourseWizard='1';
    details.className='rounded-2xl border border-slate-200 bg-white shadow-sm';
    const summary=document.createElement('summary');
    summary.className='cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3';
    summary.innerHTML='<span><span class="font-black text-slate-900">進階：一次建立整套課程</span><span class="ml-2 text-xs text-slate-500">需要課程＋多份教材＋考卷時才使用</span></span><span class="text-xs font-bold text-teal-700">展開</span>';
    card.parentNode?.insertBefore(details,card);
    details.appendChild(summary);
    details.appendChild(card);
    card.classList.remove('rounded-2xl','shadow-sm');
    card.classList.add('border-0','shadow-none');
  }

  function getStartSelection(){
    const catId=document.getElementById('composer-question-exam-72')?.value||'';
    const preset=document.querySelector('[data-composer-question-next]')?.dataset.preset||'choice';
    const imageKind=document.querySelector('input[name="composer-image-kind"]:checked')?.value||'';
    return {catId,preset,imageKind,...scope()};
  }

  function renderQuestionEdit(){
    const host=body();if(!host||!state.question)return;
    const {preset,imageKind}=state.question;
    const title=preset==='image'?'圖片判讀題':preset==='video'?'影片互動題':'一般考題';
    host.innerHTML=`${stepper(2)}<div class="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-5"><div class="flex items-center justify-between gap-3"><div><h4 class="text-lg font-black text-slate-950">${esc(title)}</h4><p class="mt-1 text-xs text-slate-500">只填教師出題真正需要的內容；下一步會先顯示學生預覽。</p></div>${imageKind?`<span class="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-bold text-rose-700">${esc(imageKind)}</span>`:''}</div><div class="mt-5 space-y-4"><label class="block text-sm font-bold text-slate-700">題幹<textarea id="teacher72-question" rows="3" class="mt-1 w-full rounded-xl border border-slate-300 p-3 text-sm" placeholder="輸入題目內容"></textarea></label>${preset==='image'?'<label class="block text-sm font-bold text-slate-700">題目圖片<input id="teacher72-image" type="file" accept="image/*" class="mt-1 block w-full rounded-xl border border-slate-300 bg-white p-2 text-sm"></label>':''}${preset==='video'?'<div class="grid gap-3 sm:grid-cols-[1fr_150px]"><label class="text-sm font-bold text-slate-700">影片網址<input id="teacher72-video-url" type="url" class="mt-1 w-full rounded-xl border border-slate-300 p-2.5 text-sm" placeholder="https://..."></label><label class="text-sm font-bold text-slate-700">提示秒數<input id="teacher72-pause" type="number" min="0" step="1" value="0" class="mt-1 w-full rounded-xl border border-slate-300 p-2.5 text-sm"></label></div>':''}<div><div class="mb-2 text-sm font-bold text-slate-700">選項</div><div class="grid gap-2 sm:grid-cols-2">${[0,1,2,3].map(i=>`<label class="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2"><span class="w-5 text-center text-xs font-black text-slate-500">${String.fromCharCode(65+i)}</span><input id="teacher72-opt${i}" class="min-w-0 flex-1 bg-transparent text-sm outline-none" placeholder="選項 ${String.fromCharCode(65+i)}"></label>`).join('')}</div></div><label class="block text-sm font-bold text-slate-700">正確答案<select id="teacher72-correct" class="mt-1 w-full rounded-xl border border-slate-300 p-2.5 text-sm">${[0,1,2,3].map(i=>`<option value="${i}">${String.fromCharCode(65+i)}</option>`).join('')}</select></label><label class="block text-sm font-bold text-slate-700">解析（選填）<textarea id="teacher72-explain" rows="2" class="mt-1 w-full rounded-xl border border-slate-300 p-3 text-sm" placeholder="作答後顯示的解析"></textarea></label></div><div class="mt-5 flex justify-between gap-2"><button type="button" data-teacher72-question-cancel class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">取消</button><button type="button" data-teacher72-question-preview class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white">下一步：預覽確認</button></div></div>`;
    document.getElementById('teacher72-question')?.focus();
  }

  function readQuestionDraft(){
    return {
      question:document.getElementById('teacher72-question')?.value.trim()||'',
      options:[0,1,2,3].map(i=>document.getElementById(`teacher72-opt${i}`)?.value.trim()||''),
      correct:Number(document.getElementById('teacher72-correct')?.value||0),
      explanation:document.getElementById('teacher72-explain')?.value.trim()||'',
      videoUrl:document.getElementById('teacher72-video-url')?.value.trim()||'',
      pauseAt:Number(document.getElementById('teacher72-pause')?.value||0),
      imageFile:document.getElementById('teacher72-image')?.files?.[0]||null
    };
  }

  function validateDraft(draft){
    const issues=[];
    if(!draft.question)issues.push('請輸入題幹');
    if(draft.options.filter(Boolean).length<2)issues.push('至少填寫 2 個選項');
    if(state.question?.preset==='image'&&!draft.imageFile)issues.push('請上傳題目圖片');
    if(state.question?.preset==='video'&&!draft.videoUrl)issues.push('請填入影片網址');
    return issues;
  }

  function renderQuestionPreview(){
    const draft=readQuestionDraft(),issues=validateDraft(draft);
    if(issues.length){window.TeacherContentComposer72?.showOutcome?.('warning','資料尚未完成',issues.join('\n'));return;}
    state.question.draft=draft;
    const host=body();if(!host)return;
    const imagePreview=draft.imageFile?`<img src="${URL.createObjectURL(draft.imageFile)}" class="mb-4 max-h-72 w-full rounded-xl border border-slate-200 object-contain" alt="題目圖片預覽">`:'';
    const videoPreview=state.question.preset==='video'?`<div class="mb-4 rounded-xl bg-slate-900 p-3 text-xs text-white">🎬 ${esc(draft.videoUrl)}${draft.pauseAt?`｜${draft.pauseAt} 秒提示`:''}</div>`:'';
    host.innerHTML=`${stepper(3)}<div class="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-5"><div class="flex items-start justify-between gap-3"><div><h4 class="text-lg font-black text-slate-950">學生看到的樣子</h4><p class="mt-1 text-xs text-slate-500">確認內容後才會真正建立題目。</p></div><span class="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">資料完整</span></div><div class="mt-5 rounded-2xl border border-indigo-100 bg-indigo-50/30 p-4">${imagePreview}${videoPreview}<div class="font-black text-slate-900">${esc(draft.question)}</div><div class="mt-3 space-y-2">${draft.options.filter(Boolean).map((opt,i)=>`<div class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">${String.fromCharCode(65+i)}. ${esc(opt)}</div>`).join('')}</div></div><div class="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">教師檢查：正確答案 ${String.fromCharCode(65+draft.correct)}${draft.explanation?`｜解析：${esc(draft.explanation)}`:''}</div><div class="mt-5 flex justify-between gap-2"><button type="button" data-teacher72-question-edit class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">← 返回修改</button><button type="button" data-teacher72-question-submit class="rounded-xl bg-teal-700 px-4 py-2 text-sm font-black text-white">確認並建立題目</button></div></div>`;
  }

  function setSelect(select,wanted){
    if(!select)return;
    const options=[...select.options];
    let option=options.find(o=>o.value===wanted);
    if(!option&&wanted==='video') option=options.find(o=>String(o.value).startsWith('video_'))||options.find(o=>/影片|影音/.test(o.textContent||''));
    if(option){select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));}
  }

  async function prepareCanonicalForm(){
    const q=state.question,d=q?.draft;if(!q||!d)throw new Error('題目資料遺失，請重新開始。');
    await window.openAdminWorkspace?.('assessment');
    const area=document.getElementById('admin-quiz-area'),group=document.getElementById('admin-quiz-group');
    if(area)area.value=q.area;if(group)group.value=q.group;
    await window.renderAdminQuizCategories?.(true);
    const panel=document.getElementById(`qpanel-${q.catId}`);
    if(panel?.classList.contains('hidden'))await window.toggleQuizQuestionsPanel?.(q.catId);
    const get=id=>document.getElementById(`qform-${q.catId}-${id}`);
    setSelect(get('type'),q.preset==='image'?'image':q.preset==='video'?'video':'choice');
    window.updateManualQuestionType?.(q.catId);
    if(get('question'))get('question').value=d.question;
    d.options.forEach((value,i)=>{if(get(`opt${i}`))get(`opt${i}`).value=value;});
    if(get('correct'))get('correct').value=String(d.correct);
    if(get('explain'))get('explain').value=d.explanation;
    if(q.imageKind&&get('tag')&&!get('tag').value)get('tag').value=q.imageKind;
    if(q.preset==='video'){if(get('media-url'))get('media-url').value=d.videoUrl;if(get('pause-at'))get('pause-at').value=String(d.pauseAt||0);}
    if(q.preset==='image'&&d.imageFile&&get('image')){
      const transfer=new DataTransfer();transfer.items.add(d.imageFile);get('image').files=transfer.files;
    }
  }

  async function submitQuestion(){
    const button=document.querySelector('[data-teacher72-question-submit]');
    if(button){button.disabled=true;button.textContent='⏳ 建立中…';}
    try{
      await prepareCanonicalForm();
      const canonicalQuestion=document.getElementById(`qform-${state.question.catId}-question`);
      const before=canonicalQuestion?.value.trim()||'';
      await window.adminAddQuizQuestion?.(state.question.catId);
      const succeeded=!!before&&!(canonicalQuestion?.value.trim());
      if(!succeeded)throw new Error('題目尚未建立，請檢查欄位或權限後再試。');
      window.TeacherContentComposer72?.showOutcome?.('success','題目已建立','題目已加入考卷。你可以繼續出下一題，或回到已建立題目清單管理。',[
        {label:'回到已建立題目',run:async()=>{window.teacherContentStudioClose?.();await window.openAdminWorkspace?.('assessment');window.assessment681Tab?.('bank');scheduleReconcile();}},
        {label:'繼續出下一題',primary:true,run:()=>{state.question.draft=null;window.teacherContentStudioOpen?.();renderQuestionEdit();}}
      ]);
    }catch(error){
      window.TeacherContentComposer72?.showOutcome?.('error','題目建立失敗',error.message||'請稍後再試。');
    }finally{
      if(button){button.disabled=false;button.textContent='確認並建立題目';}
    }
  }

  function interceptQuestionNext(event){
    const button=event.target.closest('[data-composer-question-next]');
    if(!button||!studio()?.contains(button))return;
    event.preventDefault();event.stopImmediatePropagation();
    const selection=getStartSelection();
    if(!selection.catId)return;
    state.question=selection;
    renderQuestionEdit();
  }

  function handleStudioClicks(event){
    if(!studio()?.contains(event.target))return;
    if(event.target.closest('[data-teacher72-question-cancel]')){
      event.preventDefault();
      window.TeacherContentComposer72?.renderQuestionStart?.(state.question?.preset||'choice');
      return;
    }
    if(event.target.closest('[data-teacher72-question-preview]')){event.preventDefault();renderQuestionPreview();return;}
    if(event.target.closest('[data-teacher72-question-edit]')){event.preventDefault();renderQuestionEdit();return;}
    if(event.target.closest('[data-teacher72-question-submit]')){event.preventDefault();submitQuestion();}
  }

  function reconcile(){
    reconcileScheduled=false;
    simplifyAssessmentSurface();
    compactLegacyCourseWizard();
  }

  function scheduleReconcile(){
    if(reconcileScheduled)return;
    reconcileScheduled=true;
    requestAnimationFrame(reconcile);
  }

  function mutationTargetNeedsReconcile(target){
    if(!target||target.nodeType!==1)return false;
    if(target.id==='assessment-681'||target.id==='assessment-681-tabs'||target.id==='assessment-681-body')return true;
    if(target.closest?.('#assessment-681'))return true;
    if(target.matches?.('[data-course-wizard-root], [data-admin-course-wizard]'))return true;
    return false;
  }

  function mutationNeedsReconcile(mutation){
    if(mutationTargetNeedsReconcile(mutation.target))return true;
    return [...mutation.addedNodes].some(node=>{
      if(node.nodeType!==1)return false;
      if(node.id==='assessment-681'||node.id==='assessment-681-tabs'||node.id==='assessment-681-body')return true;
      if(node.matches?.('[data-course-wizard-root], [data-admin-course-wizard]'))return true;
      if(node.querySelector?.('#assessment-681, #assessment-681-tabs, #assessment-681-body'))return true;
      if((node.matches?.('h4')||node.querySelector?.('h4'))&&node.textContent?.includes('快速建立整套課程'))return true;
      return false;
    });
  }

  function install(){
    reconcile();
    document.addEventListener('click',interceptQuestionNext,true);
    document.addEventListener('click',handleStudioClicks,true);
    const observer=new MutationObserver(mutations=>{
      if(mutations.some(mutationNeedsReconcile))scheduleReconcile();
    });
    observer.observe(document.body,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();

  window.TeacherUxConvergence72=Object.freeze({simplifyAssessmentSurface,compactLegacyCourseWizard,renderQuestionEdit,renderQuestionPreview,scheduleReconcile});
})();
