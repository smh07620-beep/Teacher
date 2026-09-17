from pathlib import Path

path=Path('static/admin-question-bank.js')
s=path.read_text(encoding='utf-8')
s=s.replace("  'use strict';\n","  'use strict';\n\n  const quizListView78={all:[],query:'',status:'all',visible:20};\n",1)
old='''    root.querySelectorAll('button[onclick*="adminDeleteQuizCategory"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除考卷') btn.textContent='🗑️ 刪除考卷';
      btn.className='text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg font-bold';
      const details=btn.closest('details');
      const actions=details?.parentElement;
      if(details&&actions){
        actions.insertBefore(btn,details);
        details.remove();
      }
    });'''
new='''    root.querySelectorAll('button[onclick*="adminDeleteQuizCategory"]').forEach(btn=>{
      if(btn.textContent.trim()!=='🗑️ 刪除考卷') btn.textContent='🗑️ 刪除考卷';
      btn.className='w-full text-left text-xs bg-white hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg font-bold';
    });'''
assert s.count(old)==1
s=s.replace(old,new,1)
start=s.index('  window.paintAdminQuizCategories = function(cats){')
end=s.index('\n  window.optimisticInsertQuizCategory',start)
replacement='''  function filteredQuizCategories78(){
    const q=quizListView78.query.trim().toLowerCase();
    return quizListView78.all.filter(c=>{
      const status=quizListView78.status;
      const statusOk=status==='all'||(status==='active'&&c.active)||(status==='approved'&&!c.active&&c.reviewStatus==='approved')||(status==='draft'&&!c.active&&c.reviewStatus!=='approved');
      const text=`${c.title||''} ${c.desc||''}`.toLowerCase();
      return statusOk&&(!q||text.includes(q));
    });
  }

  function renderQuizList78(){
    const box=document.getElementById('admin-quiz-categories-list');if(!box)return;
    const filtered=filteredQuizCategories78(),shown=filtered.slice(0,quizListView78.visible);
    box.innerHTML=`<div data-quiz-list-tools-78 class="sticky top-0 z-10 rounded-xl border border-slate-200 bg-white/95 p-3 backdrop-blur"><div class="grid gap-2 sm:grid-cols-[1fr_150px_auto]"><input value="${escapeHtml(quizListView78.query)}" oninput="teacher78FilterQuizCategories(this.value)" placeholder="🔎 搜尋考卷名稱…" class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"><select onchange="teacher78SetQuizStatus(this.value)" class="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm"><option value="all" ${quizListView78.status==='all'?'selected':''}>全部狀態</option><option value="active" ${quizListView78.status==='active'?'selected':''}>已發布</option><option value="approved" ${quizListView78.status==='approved'?'selected':''}>已審核</option><option value="draft" ${quizListView78.status==='draft'?'selected':''}>草稿</option></select><span class="self-center text-xs text-slate-400">${filtered.length} 份考卷</span></div></div><div data-quiz-list-items-78 class="space-y-2">${shown.length?shown.map(quizCategoryCardHTML).join(''):'<div class="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center text-sm text-slate-500">沒有符合條件的考卷。</div>'}</div>${shown.length<filtered.length?`<button type="button" onclick="teacher78LoadMoreQuizCategories()" class="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-50">顯示更多（尚有 ${filtered.length-shown.length} 份）</button>`:''}`;
    window.exposeQuestionDeleteActions(box);
    updateQuizWorkspacePresentation();
  }
  window.teacher78FilterQuizCategories=value=>{quizListView78.query=String(value||'');quizListView78.visible=20;renderQuizList78();};
  window.teacher78SetQuizStatus=value=>{quizListView78.status=String(value||'all');quizListView78.visible=20;renderQuizList78();};
  window.teacher78LoadMoreQuizCategories=()=>{quizListView78.visible+=20;renderQuizList78();};
  window.paintAdminQuizCategories=function(cats){quizListView78.all=Array.isArray(cats)?cats:[];quizListView78.visible=20;renderQuizList78();};
'''
s=s[:start]+replacement+s[end:]
old='''                  <div class="flex gap-2 shrink-0 flex-wrap">
                      <button data-admin-role="questions-action" onclick="toggleQuizQuestionsPanel('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-2 rounded-lg font-bold">🧠 題庫／AI（<span id="qcount-${c.id}">${Number.isFinite(Number(c.questionCount)) ? Number(c.questionCount) : 0}</span>）</button>
                      <button data-admin-role="exam-action" onclick="adminEditQuizCategory('${c.id}')" class="text-xs bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">✏️ 考卷設定</button>
                      <button id="blind-toggle-${c.id}" onclick="adminToggleBlindMode('${c.id}',${c.blindMode?'false':'true'})" class="text-xs ${c.blindMode?'bg-slate-900 text-white border-slate-900':'bg-white text-slate-700 border-slate-300'} border hover:bg-slate-100 px-3 py-2 rounded-lg font-bold">🕶️ 盲測：${c.blindMode?'開啟':'關閉'}</button>
                      <button onclick="openQuizMaterialLinker('${c.id}')" class="text-xs bg-white border border-cyan-200 hover:bg-cyan-50 text-cyan-700 px-3 py-2 rounded-lg font-bold">🔗 關聯教材</button>
                      <details class="relative"><summary class="list-none cursor-pointer text-xs bg-white border border-slate-200 text-slate-500 px-3 py-2 rounded-lg">更多</summary><div class="absolute right-0 mt-1 z-30 w-40 bg-white border border-slate-200 shadow-xl rounded-xl p-2"><button onclick="adminDeleteQuizCategory('${c.id}')" class="w-full text-xs bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg">🗑️ 刪除考卷</button></div></details>
                  </div>'''
new='''                  <div class="flex gap-2 shrink-0 items-center">
                      <button data-admin-role="questions-action" onclick="window.openTeacherContentExam?.('${c.id}') || toggleQuizQuestionsPanel('${c.id}')" class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-4 py-2 rounded-lg font-black">開啟考卷</button>
                      <details data-quiz-overflow-78 class="relative"><summary class="list-none cursor-pointer text-xs bg-white border border-slate-200 text-slate-600 px-3 py-2 rounded-lg font-bold">⋯</summary><div class="absolute right-0 mt-1 z-30 w-48 bg-white border border-slate-200 shadow-xl rounded-xl p-2"><button data-admin-role="exam-action" onclick="adminEditQuizCategory('${c.id}')" class="w-full text-left text-xs hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">⚙️ 考卷設定</button><button id="blind-toggle-${c.id}" onclick="adminToggleBlindMode('${c.id}',${c.blindMode?'false':'true'})" class="w-full text-left text-xs hover:bg-slate-50 text-slate-700 px-3 py-2 rounded-lg">🕶️ ${c.blindMode?'關閉':'開啟'}盲測</button><button onclick="openQuizMaterialLinker('${c.id}')" class="w-full text-left text-xs hover:bg-cyan-50 text-cyan-700 px-3 py-2 rounded-lg">🔗 調整關聯教材</button><button onclick="adminDeleteQuizCategory('${c.id}')" class="w-full text-left text-xs hover:bg-rose-50 text-rose-700 px-3 py-2 rounded-lg">🗑️ 刪除考卷</button></div></details>
                  </div>'''
assert s.count(old)==1
s=s.replace(old,new,1)
path.write_text(s,encoding='utf-8')
