/* Phase 3M: canonical exam settings, preview, review, and publication runtime. */
(() => {
  'use strict';

  let editingMeta = null;
  const types = ['choice','multi','true_false','fill','essay','image','video'];
  // 訊息改成頁面上方固定的橫幅：成功（綠）、失敗（紅）、處理中（藍），不再只是按鈕旁的一行小字。
  const BANNER_TONES = {
    ok: 'border-emerald-300 bg-emerald-50 text-emerald-900',
    error: 'border-rose-300 bg-rose-50 text-rose-900',
    busy: 'border-indigo-200 bg-indigo-50 text-indigo-900',
  };
  const status = () => {
    const element = document.getElementById('exam-settings-status');
    if (!element) return null;
    return {
      get textContent() { return element.textContent; },
      set textContent(text) {
        const value = String(text || '');
        element.textContent = value;
        if (!value) { element.className = 'hidden'; return; }
        const tone = /^(❌|⚠️)/.test(value) ? 'error' : /^(✅|🚀)/.test(value) ? 'ok' : 'busy';
        element.className = `sticky top-2 z-30 rounded-xl border px-4 py-3 text-sm font-bold shadow-md ${BANNER_TONES[tone]}`;
      },
    };
  };
  const invalidate = (catId, group) => {
    Object.keys(dynamicCategoriesCache).filter(k => k.endsWith(':' + (group || currentGroupKey))).forEach(k => delete dynamicCategoriesCache[k]);
    delete allQuizData[catId];
    adminQuizCategoriesCache.clear();
  };

  function updateQuotaTotal() {
    const total = types.reduce((sum, type) => sum + Math.max(0, Number(document.getElementById(`exam-quota-${type}`)?.value || 0)), 0);
    const target = document.getElementById('exam-quota-total');
    if (target) target.textContent = `合計 ${total} 題`;
    return total;
  }
  function syncDrawMode() {
    const limited = document.getElementById('exam-draw-limited')?.checked;
    const quota = document.getElementById('exam-draw-quota')?.checked;
    document.getElementById('exam-draw-count-wrap')?.classList.toggle('hidden', !limited);
    document.getElementById('exam-draw-quota-wrap')?.classList.toggle('hidden', !quota);
    updateQuotaTotal();
  }
  document.addEventListener('input', event => { if (event.target?.id?.startsWith('exam-quota-')) updateQuotaTotal(); });

  async function openSettings(catId, {embedded = false} = {}) {
    if (!embedded) window.TeacherContentStudio71?.restoreExamSettings?.();
    const group = document.getElementById('admin-quiz-group')?.value || currentGroupKey;
    const area = document.getElementById('admin-quiz-area')?.value || currentTrainingArea;
    if (status()) status().textContent = '讀取考卷設定中…';
    if (!embedded) { await switchAdminSection('exam-settings', true); paintAdminWorkspaceNav('exams'); }
    try {
      const [categoryResponse, courseResponse, windowResponse] = await Promise.all([
        fetch(`/api/quiz-categories/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`, {}),
        fetch(`/api/courses/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`, {}),
        fetch(`/api/exam-windows/${encodeURIComponent(catId)}`, {})
      ]);
      const categories = await categoryResponse.json().catch(() => []), courses = await courseResponse.json().catch(() => []), windowData = await windowResponse.json().catch(() => ({}));
      const category = (categories || []).find(item => item.id === catId); if (!category) throw new Error('找不到此考卷');
      editingMeta = {...category, group, area};
      document.getElementById('exam-settings-id').value = catId;
      document.getElementById('exam-settings-heading').textContent = `📋 ${category.title || '考卷'}｜設定`;
      document.getElementById('exam-settings-title').value = category.title || '';
      document.getElementById('exam-settings-desc').value = category.desc || '';
      document.getElementById('exam-settings-audience').value = category.audience || (category.active ? '' : '所有符合課程資格人員');
      const examWindow=windowData.window||{};
      const localInput=value=>{if(!value)return ''; const date=new Date(value); if(Number.isNaN(date.getTime()))return ''; const pad=n=>String(n).padStart(2,'0'); return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;};
      document.getElementById('exam-settings-opens-at').value=localInput(examWindow.opens_at);
      document.getElementById('exam-settings-closes-at').value=localInput(examWindow.closes_at);
      editingMeta.examWindow=examWindow;
      void window.ExamAssigneePicker?.mount(document.getElementById('exam-who-host'), {categoryId: catId, area, group});
      document.getElementById('exam-settings-passing-score').value = Number(category.passingScore || 80);
      document.getElementById('exam-settings-blind').checked = !!category.blindMode;
      const courseSelect = document.getElementById('exam-settings-course');
      courseSelect.innerHTML = '<option value="">通用考卷（未指定課程）</option>' + (courses || []).map(course => `<option value="${escapeHtml(course.id)}">${escapeHtml(course.title)}</option>`).join('');
      courseSelect.value = category.courseId || '';
      const draw = Math.max(0, Number(category.drawCount || 0)), rules = category.drawRules || {}, quotaMode = rules.mode === 'type_quota';
      document.getElementById(quotaMode ? 'exam-draw-quota' : (draw > 0 ? 'exam-draw-limited' : 'exam-draw-all')).checked = true;
      document.getElementById('exam-settings-draw-count').value = draw > 0 ? draw : '';
      types.forEach(type => { const input = document.getElementById(`exam-quota-${type}`); if (input) input.value = Math.max(0, Number(rules.quotas?.[type] || 0)); });
      syncDrawMode();
      document.getElementById('exam-settings-question-summary').textContent = `目前題庫：${Number(category.questionCount || 0)} 題；${examDrawLabel(category)}`;
      const reviewer = document.getElementById('exam-reviewer-name');
      if (reviewer) { reviewer.value = category.reviewerName || ''; reviewer.readOnly = true; reviewer.placeholder = '由目前登入帳號自動帶入'; }
      updateWorkflow(category); if (status()) status().textContent = '';
    } catch (error) { if (status()) status().textContent = '❌ ' + error.message; }
  }

  function updateWorkflow(meta) {
    meta = meta || editingMeta || {};
    const now=Date.now(), opens=meta.examWindow?.opens_at ? new Date(meta.examWindow.opens_at).getTime() : 0, closes=meta.examWindow?.closes_at ? new Date(meta.examWindow.closes_at).getTime() : 0;
    const lifecycle=meta.active ? (opens&&now<opens?'scheduled':(closes&&now>closes?'closed':'open')) : '';
    const workflowStatus = document.getElementById('exam-workflow-status');
    if (workflowStatus) workflowStatus.textContent = meta.active ? (lifecycle==='scheduled' ? '🕒 已發布・尚未開始' : lifecycle==='closed' ? '⏰ 已截止・等待批改／完成' : '🟢 進行中') + (meta.publicationHash ? '・快照 ' + meta.publicationHash.slice(0,10) : '') : (meta.reviewStatus === 'approved' ? `✅ 已由 ${meta.reviewerName || '審核者'} 審核，待發布` : '📝 草稿／設定中，完成預覽後請審核');
    // 只留一顆主按鈕：草稿＝「發布考卷」，已發布＝「儲存變更」；審核在發布時自動完成。
    const publish = document.getElementById('exam-publish-btn');
    const saveDraft = document.getElementById('exam-settings-save-btn');
    const chip = document.getElementById('exam-state-chip');
    const published = !!meta.active;
    if (publish) { publish.textContent = published ? '💾 儲存變更' : '🚀 發布考卷'; publish.className = `ml-auto disabled:opacity-60 disabled:cursor-wait text-white font-black text-sm px-6 py-2.5 rounded-xl ${published ? 'bg-indigo-700 hover:bg-indigo-600' : 'bg-emerald-700 hover:bg-emerald-600'}`; publish.disabled = false; }
    if (saveDraft) saveDraft.classList.toggle('hidden', published);
    if (chip) { chip.textContent = published ? (lifecycle === 'closed' ? '⏰ 已截止' : lifecycle === 'scheduled' ? '🕒 已發布・未開始' : '🟢 已發布・進行中') : '📝 草稿'; chip.className = `text-xs font-black px-3 py-1.5 rounded-full ${published ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'}`; }
  }

  // datetime-local 是電腦本地時間；伺服器把沒有時區的字串當 UTC，所以送出前先轉成 UTC。
  function toUtcIso(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?'':d.toISOString();}
  // 「對象說明」不再要求老師另外填：留白時依「誰能使用」自動帶入。
  function audienceText() {
    const typed = (document.getElementById('exam-settings-audience')?.value || '').trim();
    if (typed) return typed;
    const custom = document.querySelector('#exam-who-host input[type=radio][value=custom]')?.checked;
    return custom ? '指定組別／人員' : '所有符合課程資格人員';
  }
  async function saveSettings() {
    const catId = document.getElementById('exam-settings-id').value; if (!catId) return;
    const button = document.getElementById('exam-settings-save-btn'), title = document.getElementById('exam-settings-title').value.trim();
    if (!title) { status().textContent = '❌ 請輸入考卷名稱'; return; }
    const limited = document.getElementById('exam-draw-limited').checked, quotaMode = document.getElementById('exam-draw-quota').checked;
    const quotas = Object.fromEntries(types.map(type => [type, Math.max(0, parseInt(document.getElementById(`exam-quota-${type}`)?.value || '0', 10) || 0)]));
    if (quotaMode && Object.values(quotas).reduce((a,b) => a + b, 0) <= 0) { status().textContent = '❌ 題型配額至少要設定 1 題'; return; }
    const wasActive = !!editingMeta?.active;
    const payload = {title, desc:document.getElementById('exam-settings-desc').value.trim(), audience:audienceText(), courseId:document.getElementById('exam-settings-course').value || '', drawCount:limited ? Math.max(1, parseInt(document.getElementById('exam-settings-draw-count').value || '1', 10) || 1) : 0, drawRules:quotaMode ? {mode:'type_quota', quotas} : {}, passingScore:Math.max(1, Math.min(100, parseInt(document.getElementById('exam-settings-passing-score').value || '80', 10) || 80)), blindMode:document.getElementById('exam-settings-blind').checked};
    try { button.disabled = true; status().textContent = '⏳ 儲存設定中…'; const opensAt=document.getElementById('exam-settings-opens-at')?.value||''; const closesAt=document.getElementById('exam-settings-closes-at')?.value||''; if(opensAt&&closesAt&&new Date(opensAt)>=new Date(closesAt))throw new Error('最後考核日期必須晚於開始日期'); const response = await fetch(`/api/quiz-categories/${catId}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '修改失敗'); const windowResponse=await fetch(`/api/exam-windows/${catId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({opensAt:toUtcIso(opensAt),closesAt:toUtcIso(closesAt),reminderEnabled:true})}); const windowData=await windowResponse.json().catch(() => ({})); if(!windowResponse.ok)throw new Error(windowData.error||'考核時間儲存失敗'); await window.ExamAssigneePicker?.saveFor?.(document.getElementById('exam-who-host'), catId); editingMeta = {...(editingMeta || {}), ...payload, examWindow:windowData.window||{}, reviewStatus:data.reviewStatus || 'draft', reviewerName:data.reviewerName || '', reviewedAt:data.reviewedAt || '', publishedAt:data.publishedAt || '', active:!!data.active}; invalidate(catId, editingMeta.group); clearExamDraft(catId); status().textContent = editingMeta.reviewStatus === 'draft' ? (wasActive ? '✅ 已儲存。因為內容有變更，這份考卷回到草稿；請再按「發布考卷」，學員才會看到新版。' : '✅ 草稿已儲存。準備好後按「發布考卷」。') : '✅ 已儲存。'; updateWorkflow(editingMeta); } catch (error) { status().textContent = '❌ ' + error.message; } finally { button.disabled = false; }
  }

  async function preview() {
    const catId = document.getElementById('exam-settings-id')?.value; if (!catId) return;
    const panel = document.getElementById('exam-preview-panel'), list = document.getElementById('exam-preview-list'), meta = document.getElementById('exam-preview-meta'); panel?.classList.remove('hidden'); if (list) list.innerHTML = '<p class="text-xs text-slate-400">建立預覽中…</p>';
    try { const response = await fetch(`/api/quiz-questions/admin?category=${encodeURIComponent(catId)}`, {}), all = await response.json(); if (!response.ok) throw new Error(all.error || '讀取題庫失敗'); let questions = all.filter(question => question.active !== false), quotaMode = document.getElementById('exam-draw-quota')?.checked, limited = document.getElementById('exam-draw-limited')?.checked;
      if (quotaMode) { const quotas = Object.fromEntries(types.map(type => [type, Math.max(0, Number(document.getElementById(`exam-quota-${type}`)?.value || 0))])), selected = [], ids = new Set(); for (const type of types) { questions.filter(question => (question.questionType || 'choice') === type).sort(() => Math.random() - .5).slice(0, quotas[type]).forEach(question => { selected.push(question); ids.add(question.id); }); } const target = Object.values(quotas).reduce((a,b) => a + b, 0); selected.push(...questions.filter(question => !ids.has(question.id)).sort(() => Math.random() - .5).slice(0, Math.max(0, target - selected.length))); questions = selected.sort(() => Math.random() - .5); } else { questions.sort(() => Math.random() - .5); if (limited) questions = questions.slice(0, Math.min(Math.max(1, Number(document.getElementById('exam-settings-draw-count')?.value || 1)), questions.length)); }
      if (meta) meta.innerHTML = `考卷：<b>${escapeHtml(document.getElementById('exam-settings-title')?.value || '')}</b>　｜　本次預覽 <b>${questions.length}</b> 題　｜　及格 <b>${Number(document.getElementById('exam-settings-passing-score')?.value || 80)}</b> 分`;
      if (list) list.innerHTML = questions.length ? questions.map((question, index) => `<div class="rounded-xl border border-slate-200 bg-white p-4"><div class="flex gap-2 flex-wrap mb-2"><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${questionTypeLabel(question.questionType)}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${difficultyLabel(question.difficulty)}</span></div><div class="font-bold text-sm text-slate-900">${index+1}. ${escapeHtml(question.question || '')}</div>${(question.options || []).length ? `<div class="mt-2 grid sm:grid-cols-2 gap-2 text-xs">${question.options.map((option, optionIndex) => `<div class="rounded-lg border border-slate-200 px-3 py-2">${String.fromCharCode(65+optionIndex)}. ${escapeHtml(option)}</div>`).join('')}</div>` : ''}${question.questionType === 'essay' ? '<textarea disabled rows="3" class="mt-2 w-full border rounded-lg bg-slate-50 p-2 text-xs" placeholder="考生問答輸入區"></textarea>' : ''}</div>`).join('') : '<p class="text-xs text-amber-700">目前沒有可預覽的啟用題目。</p>';
    } catch (error) { if (list) list.innerHTML = `<p class="text-xs text-rose-600">❌ ${escapeHtml(error.message)}</p>`; }
  }

  async function review() { const catId = document.getElementById('exam-settings-id').value; if (!catId) return; await preview(); try { status().textContent = '⏳ 正在檢查題目完整性並送出審核…'; const response = await fetch(`/api/quiz-categories/${catId}/review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.issues?.length ? `${data.error}：${data.issues.join('、')}` : (data.error || '審核失敗')); const reviewerName=data.reviewerName || '目前登入者'; const reviewer=document.getElementById('exam-reviewer-name'); if(reviewer) reviewer.value=reviewerName; editingMeta = {...(editingMeta || {}), reviewStatus:'approved', reviewerName, reviewedAt:data.reviewedAt, active:false}; status().textContent = `✅ 審核完成：${reviewerName}；現在可發布考卷。`; updateWorkflow(editingMeta); adminQuizCategoriesCache.clear(); } catch (error) { status().textContent = '❌ ' + error.message; } }
  function publicationIssues() {
    const issues=[];
    const title=document.getElementById('exam-settings-title')?.value.trim();
    const questionCount=Math.max(0,Number(editingMeta?.questionCount||0));
    if(!title)issues.push('考卷名稱未設定');
    if(questionCount<=0)issues.push('沒有可發布的題目');
    const opensAt=document.getElementById('exam-settings-opens-at')?.value||'';
    const closesAt=document.getElementById('exam-settings-closes-at')?.value||'';
    if(opensAt&&closesAt&&new Date(opensAt)>=new Date(closesAt))issues.push('最後考核日期必須晚於開始時間');
    if(closesAt&&new Date(closesAt)<=new Date())issues.push('最後考核日期必須晚於目前時間');
    const limited=document.getElementById('exam-draw-limited')?.checked;
    const drawCount=Math.max(0,Number(document.getElementById('exam-settings-draw-count')?.value||0));
    if(limited&&drawCount>questionCount)issues.push('抽題數超過目前題庫');
    const quotaMode=document.getElementById('exam-draw-quota')?.checked;
    if(quotaMode){
      const quotaTotal=updateQuotaTotal();
      if(quotaTotal<=0)issues.push('題型配額尚未設定');
      if(quotaTotal>questionCount)issues.push('題型配額總數超過目前題庫');
    }
    return issues;
  }

  async function publish() { const catId = document.getElementById('exam-settings-id').value; if (!catId) return; const issues=publicationIssues(); if(issues.length){status().textContent='❌ 發布前請先完成：'+issues.join('、'); return;} if(!confirm('確認發布這份考卷？發布後學員會看到目前設定的正式版本。'))return; try { status().textContent = '⏳ 儲存設定中…'; await saveSettings(); if(String(status().textContent||'').startsWith('❌'))return; status().textContent = '⏳ 檢查題目並審核中…'; const reviewResponse = await fetch(`/api/quiz-categories/${catId}/review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'}), reviewData = await reviewResponse.json().catch(() => ({})); if (!reviewResponse.ok) throw new Error(reviewData.issues?.length ? `${reviewData.error}：${reviewData.issues.join('、')}` : (reviewData.error || '審核失敗')); status().textContent = '⏳ 發布中…'; const response = await fetch(`/api/quiz-categories/${catId}/publish`, {method:'POST', }), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '發布失敗'); editingMeta = {...(editingMeta || {}), active:true, publishedAt:data.publishedAt, reviewStatus:'approved', publicationId:data.publicationId || '', publicationHash:data.publicationHash || '', publishedBy:data.publishedBy || ''}; status().textContent = `🚀 已發布！學員現在看得到這份考卷（共 ${Number(data.snapshotQuestionCount || 0)} 題）${data.publishedBy ? '，發布者：' + data.publishedBy : ''}。要修改請改完後按「儲存變更」。`; updateWorkflow(editingMeta); adminQuizCategoriesCache.clear(); Object.keys(dynamicCategoriesCache).forEach(key => delete dynamicCategoriesCache[key]); } catch (error) { status().textContent = '❌ ' + error.message; } }
  async function toggleBlindMode(catId, enabled) { const button = document.getElementById(`blind-toggle-${catId}`); if (button) { button.disabled = true; button.textContent = '⏳ 更新盲測…'; } try { const response = await fetch(`/api/quiz-categories/${catId}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({blindMode:!!enabled})}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '盲測設定失敗'); const area = document.getElementById('admin-quiz-area')?.value || currentTrainingArea, group = document.getElementById('admin-quiz-group')?.value || currentGroupKey; adminQuizCategoriesCache.delete(adminScopeKey(area, group)); await renderAdminQuizCategories(true); } catch (error) { alert(error.message); if (button) { button.disabled = false; button.textContent = '🕶️ 盲測設定'; } } }

  // 「誰能使用」挑選器：不限（預設）／指定組別與個人。設定頁與課程精靈共用；伺服器強制檢查。
  const ExamAssigneePicker = (() => {
    const models = new WeakMap();
    const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    const newModel = () => ({mode:'all', groups:[], users:[], options:null, filter:''});

    function paint(host) {
      const model = models.get(host); if (!model) return;
      const options = model.options || {groups:[], people:[]};
      const needle = model.filter.trim().toLowerCase();
      const people = (options.people || []).filter(person => !needle || `${person.name} ${person.username} ${person.empId} ${person.groupLabel}`.toLowerCase().includes(needle));
      host.innerHTML = `<div class="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
        <p class="text-xs font-black text-indigo-900">👥 誰能使用這份考卷</p>
        <div class="mt-2 flex flex-wrap gap-4 text-sm">
          <label class="inline-flex items-center gap-1.5"><input type="radio" name="who-mode-${esc(host.id)}" value="all" ${model.mode === 'all' ? 'checked' : ''}> 不限制（符合課程資格的人都能考）</label>
          <label class="inline-flex items-center gap-1.5"><input type="radio" name="who-mode-${esc(host.id)}" value="custom" ${model.mode === 'custom' ? 'checked' : ''}> 只限指定的組別／個人</label>
        </div>
        ${model.mode === 'custom' ? `<div class="mt-3 grid gap-3 md:grid-cols-2">
          <div><p class="text-[11px] font-bold text-slate-600">組別</p><div class="mt-1 space-y-1">${(options.groups || []).map(group => `<label class="flex items-center gap-1.5 text-xs"><input type="checkbox" data-who-group="${esc(group.key)}" ${model.groups.includes(group.key) ? 'checked' : ''}> ${esc(group.label)}</label>`).join('') || '<p class="text-xs text-slate-400">沒有可選的組別</p>'}</div></div>
          <div><p class="text-[11px] font-bold text-slate-600">個人（已選 ${model.users.length} 人）</p><input data-who-search value="${esc(model.filter)}" placeholder="搜尋姓名／帳號" class="mt-1 w-full rounded border px-2 py-1 text-xs"><div class="mt-1 max-h-40 overflow-auto rounded border bg-white p-1.5 space-y-1">${people.map(person => `<label class="flex items-center gap-1.5 text-xs"><input type="checkbox" data-who-user="${esc(person.username)}" ${model.users.includes(person.username.toLowerCase()) ? 'checked' : ''}> ${esc(person.name)}<span class="text-slate-400">${esc(person.groupLabel)}</span></label>`).join('') || '<p class="text-xs text-slate-400">找不到符合的人員</p>'}</div></div>
        </div><p class="mt-2 text-[11px] text-slate-500">只有被選到的人看得到、也能開始作答；管理者不受影響。已開始作答的人可以做完。</p>` : '<p class="mt-2 text-[11px] text-slate-500">沒有名單時維持原本規則，不會有人突然看不到。</p>'}
      </div>`;
    }

    function bind(host) {
      if (host.dataset.whoBound) return; host.dataset.whoBound = '1';
      host.addEventListener('change', event => {
        const model = models.get(host); if (!model) return; model.touched = true; const target = event.target;
        if (target.matches?.('input[type=radio]')) { model.mode = target.value === 'custom' ? 'custom' : 'all'; paint(host); return; }
        if (target.dataset?.whoGroup) { const key = target.dataset.whoGroup; model.groups = target.checked ? [...new Set([...model.groups, key])] : model.groups.filter(item => item !== key); paint(host); return; }
        if (target.dataset?.whoUser) { const key = target.dataset.whoUser.toLowerCase(); model.users = target.checked ? [...new Set([...model.users, key])] : model.users.filter(item => item !== key); paint(host); }
      });
      host.addEventListener('input', event => {
        const model = models.get(host);
        if (model && event.target.matches?.('[data-who-search]')) { model.filter = event.target.value; const caret = event.target.selectionStart; paint(host); const box = host.querySelector('[data-who-search]'); box?.focus(); box?.setSelectionRange?.(caret, caret); }
      });
    }

    async function load(host, area, group) {
      const model = models.get(host);
      try {
        const response = await fetch(`/api/learning-assignments/audience-options?area=${encodeURIComponent(area || '')}&group=${encodeURIComponent(group || '')}`);
        model.options = response.ok ? await response.json() : {groups:[], people:[]};
      } catch (_error) { model.options = {groups:[], people:[]}; }
      paint(host);
    }

    // model 可由呼叫端提供（精靈尚未建立考卷時先暫存選擇）。
    async function mount(host, {categoryId = '', area = '', group = '', model = null} = {}) {
      if (!host) return null;
      const current = model || newModel(); current.options = current.options || null;
      models.set(host, current); bind(host); paint(host);
      if (categoryId) {
        try {
          const data = await (await fetch(`/api/quiz-categories/${encodeURIComponent(categoryId)}/assignees`)).json();
          const rows = Array.isArray(data.assignees) ? data.assignees : [];
          current.groups = rows.filter(row => row.type === 'group').map(row => row.key);
          current.users = rows.filter(row => row.type === 'user').map(row => String(row.key).toLowerCase());
          current.mode = rows.length && !rows.some(row => row.type === 'all') ? 'custom' : 'all';
        } catch (_error) { /* 讀不到就維持不限制 */ }
      }
      await load(host, area, group);
      return current;
    }

    function listFor(model) {
      if (!model || model.mode !== 'custom') return [];
      const list = [...model.groups.map(key => ({type:'group', key})), ...model.users.map(key => ({type:'user', key}))];
      if (!list.length) throw new Error('已選「只限指定對象」，請至少選一個組別或一個人，或改回「不限制」。');
      return list;
    }

    async function saveModel(categoryId, model) {
      if (!categoryId || !model) return;
      const response = await fetch(`/api/quiz-categories/${encodeURIComponent(categoryId)}/assignees`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({assignees:listFor(model)})});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '考卷對象儲存失敗');
    }

    return {mount, newModel, saveModel, saveFor: (host, categoryId) => saveModel(categoryId, models.get(host))};
  })();
  window.ExamAssigneePicker = ExamAssigneePicker;

  window.adminEditQuizCategory = catId => openSettings(catId);
  window.openExamSettings = openSettings;
  window.saveExamSettings = saveSettings;
  window.syncExamDrawModeUI = syncDrawMode;
  window.updateExamQuotaTotal = updateQuotaTotal;
  window.updateExamWorkflowUI = updateWorkflow;
  window.previewCurrentExam = preview;
  window.reviewCurrentExam = review;
  // 主按鈕：草稿時發布，已發布時儲存變更；處理中顯示忙碌並避免連按。
  async function primaryAction() {
    const button = document.getElementById('exam-publish-btn');
    if (!button || button.disabled) return;
    const label = button.textContent;
    button.disabled = true; button.textContent = '⏳ 處理中…';
    try { await (editingMeta?.active ? saveSettings() : publish()); }
    finally { button.disabled = false; if (button.textContent === '⏳ 處理中…') button.textContent = label; updateWorkflow(editingMeta); }
  }
  window.examPrimaryAction = primaryAction;
  window.publishCurrentExam = publish;
  window.adminToggleBlindMode = toggleBlindMode;

  // Final convergence: canonical owner migrated from system-admin.js.
  function difficultyLabel(d){return ({basic:'基礎',standard:'一般',advanced:'進階'})[d||'standard']||'一般';}

  window.difficultyLabel=difficultyLabel;
})();
