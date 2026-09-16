/* Phase 3T · Question editor presentation/selection runtime.
 * Keeps API mutations in the existing runtime for this slice; this module
 * owns rendering, inline-editor UI, filtering, and selection contracts.
 */
(function(){
  'use strict';

  window.adminAnswerSummary = function(q){
    const type=q.questionType||'choice';
    if(type==='essay') return `人工批改 · 評分參考：${escapeHtml(q.explanation||'未設定')}`;
    if(type==='fill') return `可接受答案：${escapeHtml((q.answerConfig?.acceptedAnswers||[]).join(' / ')||'未設定')}`;
    if(type==='multi'){
      const letters=(q.answerConfig?.correctIndices||[]).map(i=>String.fromCharCode(65+Number(i))).join('、');
      return `正解：${escapeHtml(letters||'未設定')}`;
    }
    return `正解：${escapeHtml((q.options||[])[q.correct] ?? '未設定')}`;
  };

  window.adminQuestionEditFormHTML = function(q,catId){
    const type=q.questionType||'choice';
    const opts=[...(q.options||[])];
    while(opts.length<6) opts.push('');
    const cfg=q.answerConfig||{};
    const correctSet=new Set((cfg.correctIndices||[]).map(Number));
    const hasMedia=!!cfg.mediaUrl;
    const typeOptions=[['choice','單選題'],['multi','複選題'],['true_false','是非題'],['essay','問答題'],['fill','填空題'],['image','圖片判讀題'],['video','影片題']];
    const optionType=['choice','multi','image','video'].includes(type);
    return `<div id="qedit-${q.id}" data-qid="${q.id}" data-has-media="${hasMedia?'1':'0'}" class="hidden mt-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-3 space-y-2.5">
      <div class="flex items-center justify-between gap-2"><span class="text-xs font-black text-indigo-900">快速編輯題目</span><button onclick="adminToggleInlineQuestionEditor('${q.id}','${catId}',false)" class="text-[11px] text-slate-500 hover:text-slate-800">收合</button></div>
      <textarea data-field="question" rows="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white" placeholder="題目內容">${escapeHtml(q.question||'')}</textarea>
      <div class="grid sm:grid-cols-3 gap-2">
        <label><span class="text-[11px] font-bold text-slate-600">題目類型</span><select data-field="questionType" onchange="adminInlineQuestionTypeChanged('${q.id}')" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">${typeOptions.map(([v,t])=>`<option value="${v}" ${type===v?'selected':''}>${t}</option>`).join('')}</select></label>
        <label><span class="text-[11px] font-bold text-slate-600">難度</span><select data-field="difficulty" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="basic" ${q.difficulty==='basic'?'selected':''}>基礎</option><option value="standard" ${(q.difficulty||'standard')==='standard'?'selected':''}>一般</option><option value="advanced" ${q.difficulty==='advanced'?'selected':''}>進階</option></select></label>
        <label><span class="text-[11px] font-bold text-slate-600">題目分類</span><input data-field="tag" value="${escapeHtml(q.tag||'')}" placeholder="分類標籤" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></label>
      </div>
      <div data-role="optionFields" class="${optionType?'':'hidden'} grid sm:grid-cols-2 gap-2">${opts.map((v,i)=>`<input data-field="opt${i}" value="${escapeHtml(v)}" placeholder="選項 ${String.fromCharCode(65+i)}" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">`).join('')}</div>
      <div data-role="choiceCorrect" class="${['choice','image','video'].includes(type)?'':'hidden'} flex items-center gap-2"><label class="text-[11px] font-bold text-slate-600">正確答案</label><select data-field="correct" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white">${opts.map((_,i)=>`<option value="${i}" ${Number(q.correct||0)===i?'selected':''}>${String.fromCharCode(65+i)}</option>`).join('')}</select></div>
      <div data-role="multiConfig" class="${type==='multi'?'':'hidden'} flex gap-3 flex-wrap text-xs"><span class="font-bold text-slate-600">複選正確答案</span>${opts.map((_,i)=>`<label><input data-field="multi${i}" type="checkbox" ${correctSet.has(i)?'checked':''} class="mr-1">${String.fromCharCode(65+i)}</label>`).join('')}</div>
      <div data-role="trueFalseConfig" class="${type==='true_false'?'':'hidden'}"><label class="text-[11px] font-bold text-slate-600">正確答案</label><select data-field="trueFalseCorrect" class="ml-2 px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><option value="0" ${Number(q.correct||0)===0?'selected':''}>是</option><option value="1" ${Number(q.correct||0)===1?'selected':''}>否</option></select></div>
      <div data-role="fillConfig" class="${type==='fill'?'':'hidden'}"><label class="text-[11px] font-bold text-slate-600">可接受答案（以 | 分隔）</label><input data-field="fillAnswers" value="${escapeHtml((cfg.acceptedAnswers||[]).join(' | '))}" class="mt-1 w-full px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></div>
      <div data-role="mediaConfig" class="${(type==='video'||hasMedia)?'':'hidden'} grid sm:grid-cols-2 gap-2"><input data-field="mediaUrl" value="${escapeHtml(cfg.mediaUrl||'')}" placeholder="影片 / 媒體網址" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"><input data-field="pauseAt" type="number" min="0" step="1" value="${Number(cfg.pauseAt||0)}" placeholder="暫停秒數" class="px-2.5 py-2 border border-slate-300 rounded-lg text-xs bg-white"></div>
      <label class="inline-flex items-center gap-2 px-2.5 py-2 border border-slate-300 rounded-lg bg-white text-xs"><input data-field="active" type="checkbox" ${q.active===false?'':'checked'}> 啟用此題</label>
      <textarea data-field="explanation" rows="2" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white" placeholder="${type==='essay'?'評分重點 / 參考答案':'詳解 / 答案依據'}">${escapeHtml(q.explanation||'')}</textarea>
      <div class="flex gap-2"><button id="qsave-${q.id}" onclick="adminSaveOneInlineQuestion('${q.id}','${catId}')" class="text-[11px] bg-indigo-700 hover:bg-indigo-600 disabled:bg-slate-400 disabled:cursor-wait text-white px-3 py-1.5 rounded-lg font-bold">💾 儲存此題</button></div>
    </div>`;
  };

  window.adminInlineQuestionTypeChanged = function(qId){
    const box=document.getElementById(`qedit-${qId}`);
    if(!box) return;
    const type=box.querySelector('[data-field="questionType"]')?.value||'choice';
    const toggle=(role,show)=>box.querySelector(`[data-role="${role}"]`)?.classList.toggle('hidden',!show);
    toggle('optionFields',['choice','multi','image','video'].includes(type));
    toggle('choiceCorrect',['choice','image','video'].includes(type));
    toggle('multiConfig',type==='multi');
    toggle('trueFalseConfig',type==='true_false');
    toggle('fillConfig',type==='fill');
    toggle('mediaConfig',type==='video'||box.dataset.hasMedia==='1');
    const exp=box.querySelector('[data-field="explanation"]');
    if(exp) exp.placeholder=type==='essay'?'評分重點 / 參考答案':'詳解 / 答案依據';
  };

  window.adminQuestionRowHTML = function(q,i,catId){
    return `<div id="qrow-${q.id}" class="border ${q.active===false?'border-amber-200 bg-amber-50/50':'border-slate-200 bg-white'} rounded-xl p-3">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1 text-xs flex items-start gap-2.5">
          <input type="checkbox" class="qselect-${catId} mt-1 rounded" data-qid="${q.id}" onchange="adminUpdateQuestionSelection('${catId}')">
          <div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="font-bold text-slate-800">${i+1}. ${escapeHtml(q.question)}</span><span class="text-[10px] px-2 py-0.5 rounded-full ${q.active===false?'bg-amber-100 text-amber-800':'bg-emerald-50 text-emerald-700'}">${q.active===false?'停用':'啟用'}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${questionTypeLabel(q.questionType||'choice')}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${({basic:'基礎',standard:'一般',advanced:'進階'})[q.difficulty||'standard']||'一般'}</span></div><div class="text-slate-500 mt-1">${window.adminAnswerSummary(q)}${q.tag?' · 分類：'+escapeHtml(q.tag):''}</div></div>
        </div>
        <div class="flex gap-1.5 shrink-0 flex-wrap justify-end"><button onclick="adminToggleQuizQuestion('${q.id}','${catId}',${q.active===false?'true':'false'})" class="text-[11px] ${q.active===false?'bg-emerald-600 hover:bg-emerald-500':'bg-amber-500 hover:bg-amber-400'} text-white px-2.5 py-1.5 rounded-lg">${q.active===false?'▶ 啟用':'⏸ 停用'}</button><button onclick="adminToggleInlineQuestionEditor('${q.id}','${catId}',true)" class="text-[11px] bg-indigo-600 hover:bg-indigo-500 text-white px-2.5 py-1.5 rounded-lg">✏️ 快速編輯</button><button onclick="adminDeleteQuizQuestion('${q.id}','${catId}')" class="text-[11px] bg-rose-600 hover:bg-rose-500 text-white px-2.5 py-1.5 rounded-lg">🗑️</button></div>
      </div>${window.adminQuestionEditFormHTML(q,catId)}
    </div>`;
  };

  window.adminSelectedQuestionIds = function(catId){
    return [...document.querySelectorAll(`.qselect-${catId}:checked`)].map(x=>x.dataset.qid).filter(Boolean);
  };

  window.adminUpdateQuestionSelection = function(catId){
    const all=[...document.querySelectorAll(`.qselect-${catId}`)];
    const selected=all.filter(x=>x.checked);
    const badge=document.getElementById(`qselected-${catId}`);
    if(badge) badge.textContent=`已選 ${selected.length} 題`;
    const master=document.getElementById(`qselect-all-${catId}`);
    if(master){
      master.checked=all.length>0&&selected.length===all.length;
      master.indeterminate=selected.length>0&&selected.length<all.length;
    }
  };

  window.adminSelectAllQuestions = function(catId,checked){
    document.querySelectorAll(`.qselect-${catId}`).forEach(x=>x.checked=checked);
    window.adminUpdateQuestionSelection(catId);
  };

  window.adminToggleInlineQuestionEditor = function(qId,catId,open=true){
    const el=document.getElementById(`qedit-${qId}`);
    if(!el) return;
    el.classList.toggle('hidden',!open);
    if(open){
      const cb=document.querySelector(`.qselect-${catId}[data-qid="${qId}"]`);
      if(cb) cb.checked=true;
      window.adminUpdateQuestionSelection(catId);
    }
  };

  window.adminEditSelectedQuestions = function(catId,selectAll=false){
    if(selectAll) window.adminSelectAllQuestions(catId,true);
    const ids=window.adminSelectedQuestionIds(catId);
    if(!ids.length){alert('請先勾選要編輯的題目，或按「全選編輯」。');return;}
    if(ids.length>80&&!confirm(`即將一次展開 ${ids.length} 題，頁面可能較長，是否繼續？`)) return;
    ids.forEach(id=>window.adminToggleInlineQuestionEditor(id,catId,true));
    document.getElementById(`qedit-${ids[0]}`)?.scrollIntoView({behavior:'smooth',block:'center'});
  };

  window.renderFilteredQuestionList = function(catId){
    const box=document.getElementById(`qlist-${catId}`);
    if(!box) return;
    const all=adminQuizQuestionCache[catId]||[];
    const txt=(document.getElementById(`qfilter-text-${catId}`)?.value||'').trim().toLowerCase();
    const type=document.getElementById(`qfilter-type-${catId}`)?.value||'';
    const diff=document.getElementById(`qfilter-difficulty-${catId}`)?.value||'';
    const active=document.getElementById(`qfilter-active-${catId}`)?.value||'';
    const list=all.filter(q=>{
      if(type&&(q.questionType||'choice')!==type) return false;
      if(diff&&(q.difficulty||'standard')!==diff) return false;
      if(active==='active'&&q.active===false) return false;
      if(active==='inactive'&&q.active!==false) return false;
      if(txt&&!`${q.question||''} ${q.tag||''} ${q.explanation||''}`.toLowerCase().includes(txt)) return false;
      return true;
    });
    box.innerHTML=list.length?list.map((q,i)=>window.adminQuestionRowHTML(q,i,catId)).join(''):`<p class="text-xs text-slate-400 py-4 text-center">${all.length?'沒有符合篩選條件的題目。':'目前尚無題目，可使用 AI、手動新增或公開連結匯入。'}</p>`;
    window.adminUpdateQuestionSelection(catId);
  };
})();
