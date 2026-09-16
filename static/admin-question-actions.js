/* Phase 3U · Question mutation/runtime actions.
 * UI rendering/selection lives in admin-question-editor-ui.js; this module
 * owns question CRUD, bulk mutations, import, and question-list refresh.
 */
(function(){
  'use strict';

  const actionBusy=new Set();
  let bulkBusy=false;

  function editor(qId){ return document.getElementById(`qedit-${qId}`); }
  function field(qId,name){ return editor(qId)?.querySelector(`[data-field="${name}"]`); }

  window.adminBuildQuestionPayload = function(qId){
    const box=editor(qId);
    if(!box) throw new Error('找不到題目編輯區');
    const type=field(qId,'questionType')?.value||'choice';
    const question=(field(qId,'question')?.value||'').trim();
    if(!question) throw new Error('題目內容不可空白');
    const difficulty=field(qId,'difficulty')?.value||'standard';
    const tag=(field(qId,'tag')?.value||'').trim();
    const explanation=(field(qId,'explanation')?.value||'').trim();
    const active=!!field(qId,'active')?.checked;
    const answerConfig={};
    let options=[];
    let correct=0;

    if(['choice','multi','image','video'].includes(type)){
      options=[0,1,2,3,4,5].map(i=>(field(qId,`opt${i}`)?.value||'').trim()).filter(Boolean);
      if(options.length<2) throw new Error('選擇題至少需要 2 個選項');
      if(type==='multi'){
        const indices=[0,1,2,3,4,5].filter(i=>field(qId,`multi${i}`)?.checked && i<options.length);
        if(!indices.length) throw new Error('複選題至少要設定一個正確答案');
        answerConfig.correctIndices=indices;
        correct=indices[0];
      }else{
        correct=Math.max(0,Math.min(options.length-1,Number(field(qId,'correct')?.value||0)));
      }
    }else if(type==='true_false'){
      options=['是','否'];
      correct=Number(field(qId,'trueFalseCorrect')?.value||0)===1?1:0;
    }else if(type==='fill'){
      const accepted=(field(qId,'fillAnswers')?.value||'').split('|').map(x=>x.trim()).filter(Boolean);
      if(!accepted.length) throw new Error('填空題至少需要一個可接受答案');
      answerConfig.acceptedAnswers=accepted;
      answerConfig.caseSensitive=false;
    }

    if(type==='video'||box.dataset.hasMedia==='1'){
      const mediaUrl=(field(qId,'mediaUrl')?.value||'').trim();
      if(type==='video'&&!mediaUrl) throw new Error('影片題需要媒體網址');
      if(mediaUrl){
        answerConfig.mediaUrl=mediaUrl;
        answerConfig.pauseAt=Math.max(0,Number(field(qId,'pauseAt')?.value||0));
      }
    }

    return {question,questionType:type,difficulty,options,correct,answerConfig,tag,explanation,active};
  };

  window.setQuestionRowBusy = function(qId,busy,label='處理中…'){
    const row=document.getElementById(`qrow-${qId}`);
    if(!row) return;
    row.classList.toggle('opacity-60',!!busy);
    row.querySelectorAll('button,input,select,textarea').forEach(el=>{ if(el.id!==`qsave-${qId}`) el.disabled=!!busy; });
    const save=document.getElementById(`qsave-${qId}`);
    if(save){ save.disabled=!!busy; save.textContent=busy?`⏳ ${label}`:'💾 儲存此題'; }
  };

  window.setQuestionBulkBusy = function(catId,busy,label='批次處理中…'){
    bulkBusy=!!busy;
    const host=document.getElementById(`qpanel-${catId}`);
    if(!host) return;
    host.querySelectorAll('[data-question-bulk-action], .question-bulk-action').forEach(el=>el.disabled=!!busy);
    const status=document.getElementById(`qbulk-status-${catId}`);
    if(status) status.textContent=busy?label:'';
  };

  window.updateQuestionCacheAndPaint = function(catId,patches=[],options={}){
    let rows=Array.isArray(adminQuizQuestionCache[catId])?[...adminQuizQuestionCache[catId]]:[];
    const remove=new Set(options.removeIds||[]);
    if(remove.size) rows=rows.filter(q=>!remove.has(q.id));
    for(const patch of patches||[]){
      const i=rows.findIndex(q=>q.id===patch.id);
      if(i>=0) rows[i]={...rows[i],...patch};
      else if(patch&&patch.id) rows.push(patch);
    }
    adminQuizQuestionCache[catId]=rows;
    delete allQuizData[catId];
    window.renderFilteredQuestionList(catId);
    const count=document.getElementById(`qcount-${catId}`);
    if(count) count.textContent=rows.filter(q=>q.active!==false).length;
  };

  window.loadQuizQuestionsIntoPanel = async function(catId){
    const list=document.getElementById(`qlist-${catId}`);
    if(list) list.innerHTML='<p class="text-xs text-slate-400 py-3">讀取題庫中…</p>';
    const key=await getAdminKey();
    if(!key) return;
    try{
      const r=await fetch(`/api/quiz-questions/admin?category=${encodeURIComponent(catId)}`,{headers:{'X-Admin-Key':key}});
      const d=await r.json().catch(()=>[]);
      if(!r.ok) throw new Error(d.error||'題庫讀取失敗');
      adminQuizQuestionCache[catId]=Array.isArray(d)?d:[];
      window.renderFilteredQuestionList(catId);
      const count=document.getElementById(`qcount-${catId}`);
      if(count) count.textContent=adminQuizQuestionCache[catId].filter(q=>q.active!==false).length;
    }catch(e){
      if(list) list.innerHTML=`<p class="text-xs text-rose-600 py-3">❌ ${escapeHtml(e.message)}</p>`;
    }
  };

  window.adminSaveOneInlineQuestion = async function(qId,catId){
    if(actionBusy.has(qId)) return;
    let payload;
    try{ payload=window.adminBuildQuestionPayload(qId); }
    catch(e){ alert(e.message); return; }
    const key=await getAdminKey();
    if(!key) return;
    actionBusy.add(qId); window.setQuestionRowBusy(qId,true,'儲存中…');
    try{
      const r=await fetch(`/api/quiz-questions/${encodeURIComponent(qId)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
      const d=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(d.error||'修改失敗');
      window.updateQuestionCacheAndPaint(catId,[{id:qId,...payload,...(d.question||{})}]);
    }catch(e){ alert(e.message); }
    finally{ actionBusy.delete(qId); window.setQuestionRowBusy(qId,false); }
  };

  window.adminToggleQuizQuestion = async function(qId,catId,active){
    if(actionBusy.has(qId)) return;
    const key=await getAdminKey(); if(!key) return;
    actionBusy.add(qId); window.setQuestionRowBusy(qId,true,active?'啟用中…':'停用中…');
    try{
      const r=await fetch(`/api/quiz-questions/${encodeURIComponent(qId)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});
      const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||'更新失敗');
      window.updateQuestionCacheAndPaint(catId,[{id:qId,active}]);
    }catch(e){ alert(e.message); }
    finally{ actionBusy.delete(qId); window.setQuestionRowBusy(qId,false); }
  };

  window.adminDeleteQuizQuestion = async function(qId,catId){
    if(!confirm('確定刪除此題目？此操作無法復原。')) return;
    if(actionBusy.has(qId)) return;
    const key=await getAdminKey(); if(!key) return;
    actionBusy.add(qId); window.setQuestionRowBusy(qId,true,'刪除中…');
    try{
      const r=await fetch(`/api/quiz-questions/${encodeURIComponent(qId)}`,{method:'DELETE',headers:{'X-Admin-Key':key}});
      const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||'刪除失敗');
      window.updateQuestionCacheAndPaint(catId,[],{removeIds:[qId]});
    }catch(e){ alert(e.message); }
    finally{ actionBusy.delete(qId); window.setQuestionRowBusy(qId,false); }
  };

  window.adminBulkSetQuestionActive = async function(catId,active){
    const ids=window.adminSelectedQuestionIds(catId);
    if(!ids.length){alert('請先勾選題目');return;}
    if(bulkBusy) return;
    const key=await getAdminKey(); if(!key) return;
    window.setQuestionBulkBusy(catId,true,active?'批次啟用中…':'批次停用中…');
    try{
      const patches=[];
      for(const id of ids){
        const r=await fetch(`/api/quiz-questions/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({active})});
        const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||'批次更新失敗');
        patches.push({id,active});
      }
      window.updateQuestionCacheAndPaint(catId,patches);
    }catch(e){ alert(e.message); }
    finally{ window.setQuestionBulkBusy(catId,false); }
  };

  window.adminBulkTagQuestions = async function(catId){
    const ids=window.adminSelectedQuestionIds(catId);
    if(!ids.length){alert('請先勾選題目');return;}
    const tag=prompt('輸入要套用到已選題目的分類標籤：');
    if(tag===null) return;
    if(bulkBusy) return;
    const key=await getAdminKey(); if(!key) return;
    window.setQuestionBulkBusy(catId,true,'批次更新分類中…');
    try{
      const patches=[];
      for(const id of ids){
        const r=await fetch(`/api/quiz-questions/${encodeURIComponent(id)}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({tag:tag.trim()})});
        const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||'批次分類失敗');
        patches.push({id,tag:tag.trim()});
      }
      window.updateQuestionCacheAndPaint(catId,patches);
    }catch(e){ alert(e.message); }
    finally{ window.setQuestionBulkBusy(catId,false); }
  };

  window.adminBulkDeleteQuestions = async function(catId){
    const ids=window.adminSelectedQuestionIds(catId);
    if(!ids.length){alert('請先勾選題目');return;}
    if(!confirm(`確定刪除已選的 ${ids.length} 題？此操作無法復原。`)) return;
    if(bulkBusy) return;
    const key=await getAdminKey(); if(!key) return;
    window.setQuestionBulkBusy(catId,true,`刪除 ${ids.length} 題中…`);
    try{
      for(const id of ids){
        const r=await fetch(`/api/quiz-questions/${encodeURIComponent(id)}`,{method:'DELETE',headers:{'X-Admin-Key':key}});
        const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.error||'批次刪除失敗');
      }
      window.updateQuestionCacheAndPaint(catId,[],{removeIds:ids});
    }catch(e){ alert(e.message); }
    finally{ window.setQuestionBulkBusy(catId,false); }
  };

  window.adminImportQuizUrl = async function(catId){
    const key=await getAdminKey(); if(!key) return;
    const el=document.getElementById(`qimport-${catId}`),url=el?.value.trim();
    if(!url){alert('請貼上 JSON 或 CSV 題庫公開連結');return;}
    const r=await fetch('/api/quiz-questions/import-url',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify({quizCategoryId:catId,url})});
    const d=await r.json().catch(()=>({})); if(!r.ok){alert(d.error||'匯入失敗');return;}
    alert(`成功匯入 ${d.imported} 題${d.errors?.length?`；另有 ${d.errors.length} 筆略過`:''}`);
    if(el) el.value='';
    delete allQuizData[catId];
    await window.loadQuizQuestionsIntoPanel(catId);
  };

  window.adminAddQuizQuestion = async function(catId){
    const key=await getAdminKey(); if(!key) return;
    const question=document.getElementById(`qform-${catId}-question`)?.value.trim()||'';
    const rawType=document.getElementById(`qform-${catId}-type`)?.value||'choice';
    const isVideo=rawType.startsWith('video_');
    const questionType=isVideo?rawType.slice(6):rawType;
    const difficulty=document.getElementById(`qform-${catId}-difficulty`)?.value||'standard';
    if(!question){alert('請輸入題目內容');return;}
    let imageUrl='';
    const imageFile=document.getElementById(`qform-${catId}-image`)?.files?.[0];
    if(imageFile){
      const fd=new FormData(); fd.append('file',imageFile);
      const ir=await fetch('/api/quiz-question-images',{method:'POST',headers:{'X-Admin-Key':key},body:fd});
      const idata=await ir.json().catch(()=>({})); if(!ir.ok){alert(idata.error||'圖片上傳失敗');return;}
      imageUrl=idata.url||'';
    }
    const options=[0,1,2,3].map(i=>document.getElementById(`qform-${catId}-opt${i}`)?.value.trim()||'');
    const answerConfig={};
    if(questionType==='multi') answerConfig.correctIndices=[0,1,2,3].filter(i=>document.getElementById(`qform-${catId}-multi${i}`)?.checked);
    if(questionType==='fill') answerConfig.acceptedAnswers=(document.getElementById(`qform-${catId}-fill-answers`)?.value||'').split('|').map(x=>x.trim()).filter(Boolean);
    if(isVideo){
      answerConfig.mediaUrl=document.getElementById(`qform-${catId}-media-url`)?.value.trim()||'';
      answerConfig.pauseAt=Number(document.getElementById(`qform-${catId}-pause-at`)?.value||0);
      if(!answerConfig.mediaUrl){alert('影片題請填入影片教材播放網址');return;}
    }
    const needsOptions=['choice','multi','image','true_false'].includes(questionType);
    const payload={quizCategoryId:catId,question,questionType,difficulty,imageUrl,options:questionType==='true_false'?['是','否']:(needsOptions?options:[]),correct:questionType==='true_false'?Number(document.getElementById(`qform-${catId}-truefalse-correct`)?.value||0):Number(document.getElementById(`qform-${catId}-correct`)?.value||0),answerConfig,tag:document.getElementById(`qform-${catId}-tag`)?.value.trim()||'',explanation:document.getElementById(`qform-${catId}-explain`)?.value.trim()||''};
    const r=await fetch('/api/quiz-questions',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Key':key},body:JSON.stringify(payload)});
    const d=await r.json().catch(()=>({})); if(!r.ok){alert(d.error||'新增失敗');return;}
    ['question','opt0','opt1','opt2','opt3','tag','explain','fill-answers','media-url','pause-at'].forEach(f=>{const el=document.getElementById(`qform-${catId}-${f}`);if(el)el.value='';});
    [0,1,2,3].forEach(i=>{const el=document.getElementById(`qform-${catId}-multi${i}`);if(el)el.checked=false;});
    const img=document.getElementById(`qform-${catId}-image`);if(img)img.value='';
    delete allQuizData[catId];
    await window.loadQuizQuestionsIntoPanel(catId);
  };
})();
