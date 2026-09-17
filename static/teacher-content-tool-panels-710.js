/* RC 7.10 · Dedicated Teacher Content Studio tool panels.
 * AI 出題與題目管理各自掛載到自己的 Studio 面板，不再展開整個 qpanel。
 * 此層只負責 presentation / orchestration；真正 CRUD 仍交由既有 canonical owners。
 */
(function(){
  'use strict';

  const STUDIO_ID='teacher-content-studio-71';
  const BODY_ID='teacher-content-studio-body-71';
  const originalExamAction=window.teacherContentStudioExamAction;
  const originalToggleQuizPanel=window.toggleQuizQuestionsPanel;
  const mountState={node:null,placeholder:null,catId:'',kind:''};

  const esc=value=>(window.escapeHtml?window.escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const body=()=>document.getElementById(BODY_ID);
  const studio=()=>document.getElementById(STUDIO_ID);
  const scope=()=>({
    area:document.getElementById('admin-quiz-area')?.value||document.getElementById('admin-material-area')?.value||window.currentTrainingArea||'internal',
    group:document.getElementById('admin-quiz-group')?.value||document.getElementById('admin-material-group')?.value||window.currentGroupKey||'grpBio'
  });

  function removeLegacyCloseControls(root=document){
    root?.querySelectorAll?.('[data-quiz-panel-close-710]').forEach(node=>node.remove());
  }

  function restoreMountedTool(){
    const node=mountState.node;
    if(!node)return;
    const placeholder=mountState.placeholder;
    const panel=document.getElementById(`qpanel-${mountState.catId}`);
    if(placeholder?.isConnected)placeholder.replaceWith(node);
    else if(panel)panel.appendChild(node);
    else node.remove();
    mountState.node=null;
    mountState.placeholder=null;
    mountState.catId='';
    mountState.kind='';
  }

  function showLoading(title,detail){
    const host=body();
    if(!host)return;
    host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="rounded-2xl border border-indigo-100 bg-indigo-50 p-5"><div class="text-sm font-black text-indigo-900">${esc(title)}</div><div class="mt-1 text-xs text-indigo-700">${esc(detail)}</div><div class="mt-4 h-1.5 overflow-hidden rounded-full bg-indigo-100"><div class="h-full w-1/2 animate-pulse rounded-full bg-indigo-500"></div></div></div></div>`;
  }

  function showError(catId,kind,error){
    const host=body();
    if(!host)return;
    const label=kind==='ai'?'AI 輔助出題':'題目管理';
    host.innerHTML=`<div class="mx-auto max-w-4xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700"><div class="font-black">❌ ${esc(label)}開啟失敗</div><div class="mt-1">${esc(error?.message||String(error||'未知錯誤'))}</div><div class="mt-4 flex flex-wrap gap-2"><button type="button" data-tool-retry class="rounded-lg bg-rose-700 px-3 py-2 font-bold text-white">↻ 重新嘗試</button><button type="button" data-tool-return class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回考卷</button></div></div>`;
    host.querySelector('[data-tool-retry]')?.addEventListener('click',()=>kind==='ai'?openAiTool(catId):openQuestionManager(catId));
    host.querySelector('[data-tool-return]')?.addEventListener('click',()=>returnToExam(catId));
  }

  async function prepareCanonicalPanel(catId){
    const selected=scope();
    showLoading('正在準備考卷工作區…','只載入這份考卷需要的功能，不展開其他工具。');
    if(typeof window.openAdminWorkspace==='function')await window.openAdminWorkspace('assessment');
    const area=document.getElementById('admin-quiz-area');
    const group=document.getElementById('admin-quiz-group');
    if(area)area.value=selected.area;
    if(group)group.value=selected.group;

    let panel=document.getElementById(`qpanel-${catId}`);
    if(!panel&&typeof window.renderAdminQuizCategories==='function'){
      await window.renderAdminQuizCategories(true);
      panel=document.getElementById(`qpanel-${catId}`);
    }
    if(!panel)throw new Error('找不到指定考卷，請返回考卷管理重新選擇。');

    removeLegacyCloseControls(panel);
    panel.classList.add('hidden');
    return panel;
  }

  function mountDedicatedNode(catId,kind,node,title,desc){
    restoreMountedTool();
    const host=body();
    if(!host||!node)throw new Error('功能面板尚未準備完成。');

    const placeholder=document.createElement('div');
    placeholder.hidden=true;
    placeholder.dataset.teacher710ToolPlaceholder=`${kind}:${catId}`;
    node.before(placeholder);
    mountState.node=node;
    mountState.placeholder=placeholder;
    mountState.catId=String(catId);
    mountState.kind=kind;

    host.innerHTML=`<div class="mx-auto max-w-5xl"><div class="mb-4 flex items-start justify-between gap-3 flex-wrap"><div><button type="button" data-tool-return class="text-sm font-bold text-slate-500">← 返回考卷</button><h4 class="mt-2 text-xl font-black text-slate-950">${esc(title)}</h4><p class="mt-1 text-xs text-slate-500">${esc(desc)}</p></div><span data-tool-sync class="rounded-full bg-indigo-50 px-2.5 py-1 text-[11px] font-bold text-indigo-700">背景同步中…</span></div><div data-tool-host></div><div class="sticky bottom-0 z-20 mt-4 flex justify-end border-t border-slate-200 bg-slate-50/95 py-3 backdrop-blur"><button type="button" data-tool-done class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-black text-white">完成，返回考卷</button></div></div>`;
    host.querySelector('[data-tool-host]')?.appendChild(node);
    node.classList.remove('hidden');
    host.querySelector('[data-tool-return]')?.addEventListener('click',()=>returnToExam(catId));
    host.querySelector('[data-tool-done]')?.addEventListener('click',()=>returnToExam(catId));
    return host.querySelector('[data-tool-sync]');
  }

  async function returnToExam(catId){
    restoreMountedTool();
    if(typeof window.openTeacherContentExam==='function'){
      await window.openTeacherContentExam(catId);
      return;
    }
    if(typeof originalExamAction==='function')await originalExamAction('exam',catId);
  }

  async function openQuestionManager(catId){
    if(!catId)return;
    restoreMountedTool();
    try{
      const panel=await prepareCanonicalPanel(catId);
      const list=document.getElementById(`qlist-${catId}`);
      const section=list?.closest('section');
      if(!section)throw new Error('題目管理面板尚未載入。');
      const sync=mountDedicatedNode(catId,'questions',section,'🧠 題目管理','只顯示目前考卷的題庫、搜尋、編輯與批次管理。完成後直接返回考卷。');
      panel.classList.add('hidden');
      Promise.resolve(typeof window.loadQuizQuestionsIntoPanel==='function'?window.loadQuizQuestionsIntoPanel(catId):null)
        .then(()=>{if(sync?.isConnected){sync.className='rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-700';sync.textContent='✓ 題庫已同步';}})
        .catch(error=>{if(sync?.isConnected){sync.className='rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-bold text-amber-700';sync.textContent=`⚠️ ${error?.message||'同步失敗'}`;}});
    }catch(error){
      restoreMountedTool();
      showError(catId,'questions',error);
    }
  }

  async function openAiTool(catId){
    if(!catId)return;
    restoreMountedTool();
    try{
      const panel=await prepareCanonicalPanel(catId);
      const section=panel.querySelector(`[data-ai-question-studio="${CSS.escape(String(catId))}"]`)||panel.querySelector('[data-ai-question-studio]');
      if(!section)throw new Error('AI 出題工作室尚未載入。');
      const sync=mountDedicatedNode(catId,'ai',section,'✨ AI 輔助出題','只顯示 AI 出題工作室；不再展開整份考卷工具。產生、預覽、審核完成後可直接返回考卷。');
      panel.classList.add('hidden');

      Promise.allSettled([
        Promise.resolve().then(()=>typeof window.loadAiMaterialOptions==='function'?window.loadAiMaterialOptions(catId):null),
        Promise.resolve().then(()=>typeof window.refreshAiQuestionStatus==='function'?window.refreshAiQuestionStatus(catId):null)
      ]).then(results=>{
        if(!sync?.isConnected)return;
        const failed=results.some(result=>result.status==='rejected');
        sync.className=`rounded-full px-2.5 py-1 text-[11px] font-bold ${failed?'bg-amber-50 text-amber-700':'bg-emerald-50 text-emerald-700'}`;
        sync.textContent=failed?'⚠️ 部分狀態稍後補齊':'✓ AI 工作區已就緒';
      });
    }catch(error){
      restoreMountedTool();
      showError(catId,'ai',error);
    }
  }

  // The previous RC injected a qpanel-level "收合考卷工具" control. The
  // Studio now owns dedicated child panels, so keep the canonical toggle but
  // remove that obsolete control whenever a legacy path still opens qpanel.
  if(typeof originalToggleQuizPanel==='function'){
    window.toggleQuizQuestionsPanel=function(catId){
      const result=originalToggleQuizPanel(catId);
      return Promise.resolve(result).finally(()=>{
        removeLegacyCloseControls(document.getElementById(`qpanel-${catId}`));
      });
    };
  }
  removeLegacyCloseControls();

  window.teacherContentStudioExamAction=function(action,catId){
    if(action==='ai')return openAiTool(catId);
    if(action==='questions')return openQuestionManager(catId);
    restoreMountedTool();
    return typeof originalExamAction==='function'?originalExamAction(action,catId):undefined;
  };

  window.TeacherContentToolPanels710={
    restore:restoreMountedTool,
    openAi:openAiTool,
    openQuestions:openQuestionManager
  };

  function observeStudio(){
    const root=studio();
    if(!root)return;
    const observer=new MutationObserver(()=>{
      if(root.classList.contains('hidden'))restoreMountedTool();
      removeLegacyCloseControls(root);
    });
    observer.observe(root,{attributes:true,attributeFilter:['class'],childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',observeStudio,{once:true});
  else observeStudio();
})();
