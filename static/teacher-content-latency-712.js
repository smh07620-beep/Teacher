/* RC 7.12 · Teacher Content Studio latency/stability guard.
 *
 * Goals:
 * - warm and de-duplicate the public exam-list request so opening the Studio does
 *   not start a second Render -> Supabase round trip;
 * - de-duplicate the canonical admin exam-list request as well (the slow
 *   /api/quiz-categories/admin request seen in production);
 * - use one AbortController per request instead of a Promise.race that leaves
 *   the real request running after the UI already declared a timeout;
 * - route the six exam actions without waiting for the legacy force-refresh
 *   path in prepareAssessment77(); the canonical admin renderer may hydrate in
 *   the background while the requested tool waits only for its own panel DOM.
 */
(function(){
  'use strict';

  const apiClient=window.AppApiClient;
  const PUBLIC_PATH='/api/quiz-categories';
  const ADMIN_PATH='/api/quiz-categories/admin';
  const CATEGORY_PATHS=new Set([PUBLIC_PATH,ADMIN_PATH]);
  const CACHE_TTL_MS=60000;
  const FETCH_TIMEOUT_MS=15000;
  const memoryCache=new Map();
  const inflight=new Map();

  const esc=value=>(window.escapeHtml?window.escapeHtml(String(value??'')):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));

  function currentScope(){
    return {
      area:document.getElementById('admin-quiz-area')?.value||document.getElementById('admin-material-area')?.value||window.currentTrainingArea||'internal',
      group:document.getElementById('admin-quiz-group')?.value||document.getElementById('admin-material-group')?.value||window.currentGroupKey||'grpBio'
    };
  }

  function isCategoryList(meta){
    return !!meta&&meta.method==='GET'&&meta.url.origin===window.location.origin&&CATEGORY_PATHS.has(meta.url.pathname);
  }

  function invalidatesExamList(meta){
    if(!meta||meta.method==='GET'||meta.url.origin!==window.location.origin)return false;
    return meta.url.pathname.startsWith('/api/quiz-categories')||meta.url.pathname.startsWith('/api/quiz-questions');
  }

  function cacheKey(url){
    const params=[...url.searchParams.entries()].sort(([a,av],[b,bv])=>a===b?String(av).localeCompare(String(bv)):a.localeCompare(b));
    return `${url.pathname}?${params.map(([k,v])=>`${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')}`;
  }

  function storageKey(key){return `teacher712:${key}`;}

  function clearCachedLists(){
    memoryCache.clear();
    inflight.clear();
    try{
      for(let index=sessionStorage.length-1;index>=0;index--){
        const key=sessionStorage.key(index);
        if(key?.startsWith('teacher712:'))sessionStorage.removeItem(key);
      }
    }catch(_error){}
  }

  function readCached(key){
    const inMemory=memoryCache.get(key);
    if(inMemory&&Date.now()-inMemory.at<CACHE_TTL_MS)return inMemory;
    try{
      const raw=sessionStorage.getItem(storageKey(key));
      if(!raw)return null;
      const parsed=JSON.parse(raw);
      if(!parsed||Date.now()-Number(parsed.at||0)>=CACHE_TTL_MS){sessionStorage.removeItem(storageKey(key));return null;}
      memoryCache.set(key,parsed);
      return parsed;
    }catch(_error){return null;}
  }

  function writeCached(key,entry){
    const cached={...entry,at:Date.now()};
    memoryCache.set(key,cached);
    try{sessionStorage.setItem(storageKey(key),JSON.stringify(cached));}catch(_error){}
    return cached;
  }

  function responseFrom(entry){
    return new Response(entry.body,{status:entry.status,statusText:entry.statusText,headers:entry.headers});
  }

  async function networkEntry(context,next,init={}){
    // Never reuse an AbortController: once aborted it remains aborted forever.
    const controller=new AbortController();
    const input=context.input;
    const externalSignal=init?.signal||(typeof Request!=='undefined'&&input instanceof Request?input.signal:null);
    const abortFromCaller=()=>controller.abort(externalSignal?.reason);
    if(externalSignal){
      if(externalSignal.aborted)abortFromCaller();
      else externalSignal.addEventListener('abort',abortFromCaller,{once:true});
    }
    const timer=setTimeout(()=>controller.abort(new DOMException('Exam list timeout','AbortError')),FETCH_TIMEOUT_MS);
    try{
      const response=await next({init:{...init,signal:controller.signal}});
      const body=await response.text();
      return {
        status:response.status,
        statusText:response.statusText,
        headers:[...response.headers.entries()],
        body
      };
    }catch(error){
      if(error?.name==='AbortError')throw new Error('考卷清單讀取超過 15 秒，已停止本次請求；主畫面仍可使用，可直接重新嘗試。');
      throw error;
    }finally{
      clearTimeout(timer);
      externalSignal?.removeEventListener?.('abort',abortFromCaller);
    }
  }

  function fetchCategoryList(context,next,meta){
    const input=context.input;
    const init=context.init||{};
    const key=cacheKey(meta.url);
    const cached=readCached(key);
    if(cached){
      // Stale-while-revalidate: show the usable list now, refresh it once in
      // the background. Repeated callers share the same in-flight request.
      if(!inflight.has(key)){
        const refresh=networkEntry(context,next,init)
          .then(entry=>{if(entry.status>=200&&entry.status<300)writeCached(key,entry);return entry;})
          .catch(()=>null)
          .finally(()=>inflight.delete(key));
        inflight.set(key,refresh);
      }
      return Promise.resolve(responseFrom(cached));
    }
    if(inflight.has(key))return inflight.get(key).then(entry=>{
      if(!entry)throw new Error('考卷清單背景同步失敗，請重新嘗試。');
      return responseFrom(entry);
    });
    const request=networkEntry(context,next,init)
      .then(entry=>{
        if(entry.status>=200&&entry.status<300)writeCached(key,entry);
        return entry;
      })
      .finally(()=>inflight.delete(key));
    inflight.set(key,request);
    return request.then(responseFrom);
  }

  function latencyMiddleware(context,next){
    const meta=context.url?{url:context.url,method:context.method}:null;
    if(invalidatesExamList(meta)){
      clearCachedLists();
      return next().then(response=>{
        if(response.ok)clearCachedLists();
        return response;
      });
    }
    if(isCategoryList(meta))return fetchCategoryList(context,next,meta);
    return next();
  }

  apiClient?.use('teacher-content-latency-712',latencyMiddleware,100);

  function showSkeleton(title='正在準備考卷功能…',detail='畫面先保持可用，資料在背景同步。'){
    const host=document.getElementById('teacher-content-studio-body-71');
    if(!host)return;
    host.innerHTML=`<div class="mx-auto max-w-4xl"><div class="rounded-2xl border border-indigo-100 bg-white p-5"><div class="font-black text-slate-900">${esc(title)}</div><div class="mt-1 text-xs text-slate-500">${esc(detail)}</div><div class="mt-5 space-y-3"><div class="h-16 animate-pulse rounded-xl bg-slate-100"></div><div class="h-16 animate-pulse rounded-xl bg-slate-100"></div><div class="h-16 animate-pulse rounded-xl bg-slate-100"></div></div></div></div>`;
  }

  function showActionError(catId,error){
    const host=document.getElementById('teacher-content-studio-body-71');
    if(!host)return;
    host.innerHTML=`<div class="mx-auto max-w-4xl rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700"><div class="font-black">❌ 功能暫時無法開啟</div><div class="mt-1">${esc(error?.message||String(error||'未知錯誤'))}</div><div class="mt-4"><button type="button" data-exam-open="${esc(catId)}" class="rounded-lg border border-rose-200 bg-white px-3 py-2 font-bold">返回考卷</button></div></div>`;
  }

  async function waitForPanel(catId,timeoutMs=15000){
    const started=Date.now();
    while(Date.now()-started<timeoutMs){
      const panel=document.getElementById(`qpanel-${catId}`);
      if(panel)return panel;
      await new Promise(resolve=>setTimeout(resolve,80));
    }
    return null;
  }

  function setQuestionType(select,wanted){
    if(!select)return false;
    const options=[...select.options];
    let option=options.find(item=>item.value===wanted);
    if(!option&&wanted==='video')option=options.find(item=>String(item.value).startsWith('video_'))||options.find(item=>/影片|影音/.test(item.textContent||''));
    if(!option&&wanted==='image')option=options.find(item=>item.value==='image')||options.find(item=>/圖片/.test(item.textContent||''));
    if(!option&&wanted==='choice')option=options.find(item=>item.value==='choice')||options[0];
    if(!option)return false;
    select.value=option.value;
    select.dispatchEvent(new Event('change',{bubbles:true}));
    return true;
  }

  async function prepareQuestionPanel(catId,label){
    const selected=currentScope();
    showSkeleton(label,'正在切換到這份考卷；不再等待整份考卷清單強制重新整理。');
    const opened=typeof window.openAdminWorkspace==='function'?await window.openAdminWorkspace('assessment'):true;
    if(opened===false)throw new Error('考卷管理工作區無法開啟。');
    const area=document.getElementById('admin-quiz-area');
    const group=document.getElementById('admin-quiz-group');
    if(area)area.value=selected.area;
    if(group)group.value=selected.group;

    let panel=document.getElementById(`qpanel-${catId}`);
    if(!panel&&typeof window.renderAdminQuizCategories==='function'){
      // openAdminWorkspace already started canonical hydration. Do not start a
      // second forced request and then await it; simply join/cache the normal
      // renderer and wait for this exam's DOM.
      void Promise.resolve(window.renderAdminQuizCategories(false)).catch(()=>{});
      panel=await waitForPanel(catId,FETCH_TIMEOUT_MS);
    }
    if(!panel)throw new Error('考卷工作區在 15 秒內仍未準備完成，請重新嘗試。');
    return panel;
  }

  async function openManualQuestion(action,catId){
    try{
      const labels={question:'正在開啟一般考題…',image:'正在開啟圖片判讀題…',video:'正在開啟影片互動題…'};
      const panel=await prepareQuestionPanel(catId,labels[action]||'正在開啟題目編輯器…');
      window.teacherContentStudioClose?.();
      if(panel.classList.contains('hidden'))await Promise.resolve(window.toggleQuizQuestionsPanel?.(catId));
      const typeSelect=document.getElementById(`qform-${catId}-type`);
      setQuestionType(typeSelect,action==='image'?'image':(action==='video'?'video':'choice'));
      window.updateManualQuestionType?.(catId);
      const question=document.getElementById(`qform-${catId}-question`);
      question?.scrollIntoView({behavior:'smooth',block:'center'});
      setTimeout(()=>question?.focus(),180);
    }catch(error){showActionError(catId,error);}
  }

  async function openSettings(catId){
    try{
      const selected=currentScope();
      showSkeleton('正在開啟考卷設定…','設定頁先切換；考卷清單同步留在背景。');
      const opened=typeof window.openAdminWorkspace==='function'?await window.openAdminWorkspace('assessment'):true;
      if(opened===false)throw new Error('考卷管理工作區無法開啟。');
      const area=document.getElementById('admin-quiz-area');
      const group=document.getElementById('admin-quiz-group');
      if(area)area.value=selected.area;
      if(group)group.value=selected.group;
      window.teacherContentStudioClose?.();
      await Promise.resolve(window.adminEditQuizCategory?.(catId));
    }catch(error){showActionError(catId,error);}
  }

  window.TeacherContentStudio71?.registerExamActions?.(
    ['question','image','video'],
    (action,catId)=>openManualQuestion(action,catId)
  );
  window.TeacherContentStudio71?.registerExamActions?.(
    ['settings'],
    (_action,catId)=>openSettings(catId)
  );

  function warmCurrentScope(){
    const {area,group}=currentScope();
    if(!group)return;
    // Warm only the public list. Warming the admin list too would cause a
    // second DB round trip; admin list requests are instead de-duplicated on use.
    const url=`${PUBLIC_PATH}?area=${encodeURIComponent(area)}&group=${encodeURIComponent(group)}`;
    void window.fetch(url,{credentials:'same-origin'}).then(response=>response.text()).catch(()=>{});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(warmCurrentScope,350),{once:true});
  else setTimeout(warmCurrentScope,350);

  window.TeacherContentLatency712={warm:warmCurrentScope,clear:clearCachedLists};
})();
