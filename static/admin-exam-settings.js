/* Phase 3M: canonical exam settings, preview, review, and publication runtime. */
(() => {
  'use strict';

  let editingMeta = null;
  const types = ['choice','multi','true_false','fill','essay','image','video'];
  const status = () => document.getElementById('exam-settings-status');
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

  async function openSettings(catId) {
    const key = await getAdminKey(); if (!key) return;
    const group = document.getElementById('admin-quiz-group')?.value || currentGroupKey;
    const area = document.getElementById('admin-quiz-area')?.value || currentTrainingArea;
    if (status()) status().textContent = '讀取考卷設定中…';
    await switchAdminSection('exam-settings', true); paintAdminWorkspaceNav('exams');
    try {
      const [categoryResponse, courseResponse] = await Promise.all([
        fetch(`/api/quiz-categories/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`, {headers:{'X-Admin-Key':key}}),
        fetch(`/api/courses/admin?group=${encodeURIComponent(group)}&area=${encodeURIComponent(area)}`, {headers:{'X-Admin-Key':key}})
      ]);
      const categories = await categoryResponse.json().catch(() => []), courses = await courseResponse.json().catch(() => []);
      const category = (categories || []).find(item => item.id === catId); if (!category) throw new Error('找不到此考卷');
      editingMeta = {...category, group, area};
      document.getElementById('exam-settings-id').value = catId;
      document.getElementById('exam-settings-heading').textContent = `📋 ${category.title || '考卷'}｜設定`;
      document.getElementById('exam-settings-title').value = category.title || '';
      document.getElementById('exam-settings-desc').value = category.desc || '';
      document.getElementById('exam-settings-audience').value = category.audience || '';
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
    const current = meta.active ? 'publish' : (meta.reviewStatus === 'approved' ? 'review' : 'settings');
    const order = {select:1, method:2, settings:3, review:4, publish:5};
    document.querySelectorAll('#exam-workflow-steps [data-stage]').forEach(element => { element.classList.toggle('is-done', order[element.dataset.stage] < (order[current] || 3)); element.classList.toggle('is-current', element.dataset.stage === current); });
    const workflowStatus = document.getElementById('exam-workflow-status');
    if (workflowStatus) workflowStatus.textContent = meta.active ? `🚀 已發布${meta.publishedAt ? '・' + meta.publishedAt : ''}${meta.publicationHash ? '・快照 ' + meta.publicationHash.slice(0,10) : ''}` : (meta.reviewStatus === 'approved' ? `✅ 已由 ${meta.reviewerName || '審核者'} 審核，待發布` : '📝 草稿／設定中，完成預覽後請審核');
    const publish = document.getElementById('exam-publish-btn'); if (publish) publish.disabled = meta.reviewStatus !== 'approved' || !!meta.active;
  }

  async function saveSettings() {
    const key = await getAdminKey(), catId = document.getElementById('exam-settings-id').value; if (!key || !catId) return;
    const button = document.getElementById('exam-settings-save-btn'), title = document.getElementById('exam-settings-title').value.trim();
    if (!title) { status().textContent = '❌ 請輸入考卷名稱'; return; }
    const limited = document.getElementById('exam-draw-limited').checked, quotaMode = document.getElementById('exam-draw-quota').checked;
    const quotas = Object.fromEntries(types.map(type => [type, Math.max(0, parseInt(document.getElementById(`exam-quota-${type}`)?.value || '0', 10) || 0)]));
    if (quotaMode && Object.values(quotas).reduce((a,b) => a + b, 0) <= 0) { status().textContent = '❌ 題型配額至少要設定 1 題'; return; }
    const payload = {title, desc:document.getElementById('exam-settings-desc').value.trim(), audience:document.getElementById('exam-settings-audience').value.trim(), courseId:document.getElementById('exam-settings-course').value || '', drawCount:limited ? Math.max(1, parseInt(document.getElementById('exam-settings-draw-count').value || '1', 10) || 1) : 0, drawRules:quotaMode ? {mode:'type_quota', quotas} : {}, passingScore:Math.max(1, Math.min(100, parseInt(document.getElementById('exam-settings-passing-score').value || '80', 10) || 80)), blindMode:document.getElementById('exam-settings-blind').checked};
    try { button.disabled = true; status().textContent = '⏳ 儲存設定中…'; const response = await fetch(`/api/quiz-categories/${catId}`, {method:'PATCH', headers:{'Content-Type':'application/json','X-Admin-Key':key}, body:JSON.stringify(payload)}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '修改失敗'); editingMeta = {...(editingMeta || {}), ...payload, reviewStatus:data.reviewStatus || 'draft', reviewerName:data.reviewerName || '', reviewedAt:data.reviewedAt || '', publishedAt:data.publishedAt || '', active:!!data.active}; invalidate(catId, editingMeta.group); clearExamDraft(catId); status().textContent = editingMeta.reviewStatus === 'draft' ? '✅ 設定已儲存；因內容已變更，考卷回到「待審核」狀態。' : '✅ 設定已儲存。'; updateWorkflow(editingMeta); } catch (error) { status().textContent = '❌ ' + error.message; } finally { button.disabled = false; }
  }

  async function preview() {
    const catId = document.getElementById('exam-settings-id')?.value; if (!catId) return;
    const panel = document.getElementById('exam-preview-panel'), list = document.getElementById('exam-preview-list'), meta = document.getElementById('exam-preview-meta'); panel?.classList.remove('hidden'); if (list) list.innerHTML = '<p class="text-xs text-slate-400">建立預覽中…</p>';
    try { const key = await getAdminKey(), response = await fetch(`/api/quiz-questions/admin?category=${encodeURIComponent(catId)}`, {headers:{'X-Admin-Key':key}}), all = await response.json(); if (!response.ok) throw new Error(all.error || '讀取題庫失敗'); let questions = all.filter(question => question.active !== false), quotaMode = document.getElementById('exam-draw-quota')?.checked, limited = document.getElementById('exam-draw-limited')?.checked;
      if (quotaMode) { const quotas = Object.fromEntries(types.map(type => [type, Math.max(0, Number(document.getElementById(`exam-quota-${type}`)?.value || 0))])), selected = [], ids = new Set(); for (const type of types) { questions.filter(question => (question.questionType || 'choice') === type).sort(() => Math.random() - .5).slice(0, quotas[type]).forEach(question => { selected.push(question); ids.add(question.id); }); } const target = Object.values(quotas).reduce((a,b) => a + b, 0); selected.push(...questions.filter(question => !ids.has(question.id)).sort(() => Math.random() - .5).slice(0, Math.max(0, target - selected.length))); questions = selected.sort(() => Math.random() - .5); } else { questions.sort(() => Math.random() - .5); if (limited) questions = questions.slice(0, Math.min(Math.max(1, Number(document.getElementById('exam-settings-draw-count')?.value || 1)), questions.length)); }
      if (meta) meta.innerHTML = `考卷：<b>${escapeHtml(document.getElementById('exam-settings-title')?.value || '')}</b>　｜　本次預覽 <b>${questions.length}</b> 題　｜　及格 <b>${Number(document.getElementById('exam-settings-passing-score')?.value || 80)}</b> 分`;
      if (list) list.innerHTML = questions.length ? questions.map((question, index) => `<div class="rounded-xl border border-slate-200 bg-white p-4"><div class="flex gap-2 flex-wrap mb-2"><span class="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700">${questionTypeLabel(question.questionType)}</span><span class="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">${difficultyLabel(question.difficulty)}</span></div><div class="font-bold text-sm text-slate-900">${index+1}. ${escapeHtml(question.question || '')}</div>${(question.options || []).length ? `<div class="mt-2 grid sm:grid-cols-2 gap-2 text-xs">${question.options.map((option, optionIndex) => `<div class="rounded-lg border border-slate-200 px-3 py-2">${String.fromCharCode(65+optionIndex)}. ${escapeHtml(option)}</div>`).join('')}</div>` : ''}${question.questionType === 'essay' ? '<textarea disabled rows="3" class="mt-2 w-full border rounded-lg bg-slate-50 p-2 text-xs" placeholder="考生問答輸入區"></textarea>' : ''}</div>`).join('') : '<p class="text-xs text-amber-700">目前沒有可預覽的啟用題目。</p>';
    } catch (error) { if (list) list.innerHTML = `<p class="text-xs text-rose-600">❌ ${escapeHtml(error.message)}</p>`; }
  }

  async function review() { const catId = document.getElementById('exam-settings-id').value; if (!catId) return; await preview(); const key = await getAdminKey(); if (!key) return; try { status().textContent = '⏳ 正在檢查題目完整性並送出審核…'; const response = await fetch(`/api/quiz-categories/${catId}/review`, {method:'POST', headers:{'Content-Type':'application/json','X-Admin-Key':key}, body:'{}'}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.issues?.length ? `${data.error}：${data.issues.join('、')}` : (data.error || '審核失敗')); const reviewerName=data.reviewerName || '目前登入者'; const reviewer=document.getElementById('exam-reviewer-name'); if(reviewer) reviewer.value=reviewerName; editingMeta = {...(editingMeta || {}), reviewStatus:'approved', reviewerName, reviewedAt:data.reviewedAt, active:false}; status().textContent = `✅ 審核完成：${reviewerName}；現在可發布考卷。`; updateWorkflow(editingMeta); adminQuizCategoriesCache.clear(); } catch (error) { status().textContent = '❌ ' + error.message; } }
  async function publish() { const catId = document.getElementById('exam-settings-id').value; if (!catId) return; const key = await getAdminKey(); if (!key) return; try { status().textContent = '⏳ 正在建立不可漂移發布快照並發布…'; const response = await fetch(`/api/quiz-categories/${catId}/publish`, {method:'POST', headers:{'X-Admin-Key':key}}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '發布失敗'); editingMeta = {...(editingMeta || {}), active:true, publishedAt:data.publishedAt, reviewStatus:'approved', publicationId:data.publicationId || '', publicationHash:data.publicationHash || '', publishedBy:data.publishedBy || ''}; status().textContent = `🚀 考卷已發布${data.publishedBy ? '（發布者：' + data.publishedBy + '）' : ''}；已保存 ${Number(data.snapshotQuestionCount || 0)} 題發布快照${data.publicationHash ? '（' + data.publicationHash.slice(0,10) + '…）' : ''}。`; updateWorkflow(editingMeta); adminQuizCategoriesCache.clear(); Object.keys(dynamicCategoriesCache).forEach(key => delete dynamicCategoriesCache[key]); } catch (error) { status().textContent = '❌ ' + error.message; } }
  async function toggleBlindMode(catId, enabled) { const key = await getAdminKey(); if (!key) return; const button = document.getElementById(`blind-toggle-${catId}`); if (button) { button.disabled = true; button.textContent = '⏳ 更新盲測…'; } try { const response = await fetch(`/api/quiz-categories/${catId}`, {method:'PATCH', headers:{'Content-Type':'application/json','X-Admin-Key':key}, body:JSON.stringify({blindMode:!!enabled})}), data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || '盲測設定失敗'); const area = document.getElementById('admin-quiz-area')?.value || currentTrainingArea, group = document.getElementById('admin-quiz-group')?.value || currentGroupKey; adminQuizCategoriesCache.delete(adminScopeKey(area, group)); await renderAdminQuizCategories(true); } catch (error) { alert(error.message); if (button) { button.disabled = false; button.textContent = '🕶️ 盲測設定'; } } }

  window.adminEditQuizCategory = catId => openSettings(catId);
  window.openExamSettings = openSettings;
  window.saveExamSettings = saveSettings;
  window.syncExamDrawModeUI = syncDrawMode;
  window.updateExamQuotaTotal = updateQuotaTotal;
  window.updateExamWorkflowUI = updateWorkflow;
  window.previewCurrentExam = preview;
  window.reviewCurrentExam = review;
  window.publishCurrentExam = publish;
  window.adminToggleBlindMode = toggleBlindMode;

  // Final convergence: canonical owner migrated from system-admin.js.
  function difficultyLabel(d){return ({basic:'基礎',standard:'一般',advanced:'進階'})[d||'standard']||'一般';}

  window.difficultyLabel=difficultyLabel;
})();
