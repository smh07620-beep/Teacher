/* Teacher AI material assistant: source upload/material -> AI draft -> teacher review -> explicit publication. */
// Compatibility vocabulary retained for existing teacher guidance: 📚 發布成教材.
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  const TYPE_LABELS = Object.freeze({
    handout: '教學講義',
    summary: '重點摘要',
    slides: '投影片大綱',
    script: '教學講稿',
    quiz: '測驗題草稿',
    objectives: '課程學習目標',
  });

  let materials = [];
  let activeJobId = '';
  let activeDraft = null;
  let pollToken = 0;
  // These are private authoring inputs, not learner-visible material.  They
  // become a formal teaching material only through the explicit publish flow.
  let authoringSourceIds = [];

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  function currentScope() {
    const params = new URLSearchParams(window.location.search);
    return {
      area: params.get('area') || window.currentTrainingArea || String(R.user?.preferredArea || '').trim() || 'internal',
      group: params.get('group') || window.currentGroupKey || String(R.user?.preferredGroup || '').trim() || 'grpBio',
    };
  }

  function status(message, tone = 'normal') {
    const node = document.getElementById('teacher-ai-material-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-sm font-bold text-rose-700'
      : tone === 'success'
        ? 'text-sm font-bold text-emerald-700'
        : 'text-sm text-slate-600';
  }

  function setBusy(busy) {
    ['teacher-ai-material-generate-1014','teacher-ai-material-upload-1014','teacher-ai-material-save-1014',
     'teacher-ai-material-paste-add-1014','teacher-ai-material-approve-1014','teacher-ai-material-publish-1014'].forEach(id => {
      const button = document.getElementById(id);
      if (button) button.disabled = busy;
    });
  }

  function selectedReferenceIds() {
    const select = document.getElementById('teacher-ai-material-source-1014');
    return [...(select?.selectedOptions || [])].map(option => option.value).filter(Boolean);
  }

  function primarySourceId() {
    return authoringSourceIds[0] || selectedReferenceIds()[0] || '';
  }

  function allAuthoringSourceIds() {
    return [...new Set([...authoringSourceIds, ...selectedReferenceIds()])];
  }

  function renderAuthoringSources() {
    const host = document.getElementById('teacher-ai-material-uploaded-sources-1014');
    if (!host) return;
    const rows = authoringSourceIds.map(id => materials.find(item => item.id === id)).filter(Boolean);
    host.innerHTML = rows.length
      ? rows.map((item, index) => `<span class="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2.5 py-1 text-xs font-bold text-violet-800">${index === 0 ? '主要' : '原始'}｜${escapeHtml(item.title || item.filename || item.id)}<button type="button" data-remove-authoring-source="${escapeHtml(item.id)}" class="ml-1 rounded px-1 text-violet-700 hover:bg-violet-200" aria-label="移除 ${escapeHtml(item.title || item.filename || '原始資料')}">×</button></span>`).join('')
      : '<span class="text-xs text-slate-500">尚未加入新來源資料。</span>';
  }

  function announceDraft(draft = activeDraft) {
    window.dispatchEvent(new CustomEvent('teacher-ai-material-draft-selected', {detail: {draft: draft || null}}));
  }

  function announcePublication(materialId) {
    window.dispatchEvent(new CustomEvent('teacher-ai-material-published', {detail: {materialId: String(materialId || '')}}));
  }

  function materialLabel(item) {
    const scope = item.groupLabel || item.group || '';
    const state = item.active === false ? '｜草稿來源' : '';
    return `${scope ? `${scope}｜` : ''}${item.title || item.filename || item.id}${state}`;
  }

  function materialStamp(item) {
    const value = item?.updatedAt || item?.dateAdded || item?.createdAt || '';
    const stamp = Date.parse(String(value || ''));
    return Number.isFinite(stamp) ? stamp : 0;
  }

  function dedupeMaterialRows(rows) {
    const byId = new Map();
    (Array.isArray(rows) ? rows : []).forEach(item => {
      if (!item || item.isBuiltin) return;
      const id = String(item.id || '').trim();
      const idKey = id || `anon:${materialLabel(item)}`;
      const previous = byId.get(idKey);
      if (!previous || materialStamp(item) >= materialStamp(previous)) byId.set(idKey, item);
    });
    const byLogicalSource = new Map();
    [...byId.values()].forEach(item => {
      const name = String(item.filename || item.title || item.id || '').trim().toLocaleLowerCase('zh-Hant');
      const key = [
        String(item.area || '').trim(),
        String(item.group || '').trim(),
        String(item.courseId || '').trim(),
        item.active === false ? 'draft' : 'active',
        name,
      ].join('::');
      const previous = byLogicalSource.get(key);
      if (!previous || materialStamp(item) >= materialStamp(previous)) byLogicalSource.set(key, item);
    });
    return [...byLogicalSource.values()];
  }

  async function fetchMaterials() {
    const response = await fetch('/api/slides/admin', {credentials:'same-origin', cache:'no-store'});
    const data = await response.json().catch(() => []);
    if (!response.ok) throw new Error(data.error || '無法讀取教材清單');
    materials = dedupeMaterialRows(data);
    return materials;
  }

  async function paintMaterialOptions(preferredId = '') {
    const select = document.getElementById('teacher-ai-material-source-1014');
    if (!select) return;
    const previous = preferredId || select.value;
    select.innerHTML = '<option value="">選擇既有教材…</option>';
    try {
      await fetchMaterials();
      const {area, group} = currentScope();
      // Multi-source generation is deliberately same-scope on the server.
      // Do the same in the picker so teachers cannot accidentally combine
      // another group/area and only discover the mismatch as a red API error.
      const ordered = materials
        .filter(item => (!group || !item.group || String(item.group) === String(group))
          && (!area || !item.area || String(item.area) === String(area)))
        .sort((a, b) => materialLabel(a).localeCompare(materialLabel(b), 'zh-Hant'));
      ordered.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id || '';
        option.textContent = materialLabel(item);
        select.appendChild(option);
      });
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
    } catch (error) {
      status(`教材清單讀取失敗：${error.message}`, 'error');
    }
  }

  async function pollMaterialJob(jobId, token, label) {
    for (let attempt = 0; attempt < 180 && token === pollToken; attempt += 1) {
      const response = await fetch(`/api/material-jobs/${encodeURIComponent(jobId)}`, {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取教材背景工作');
      const state = String(data.status || 'queued');
      status(`${label}｜${data.stage || state}${data.detail ? `｜${data.detail}` : ''}`);
      if (state === 'completed') return data;
      if (['failed','cancelled'].includes(state)) throw new Error(data.error || data.detail || `${label}失敗`);
      await sleep(2200);
    }
    throw new Error(`${label}等待逾時，工作仍可能在背景繼續。`);
  }

  async function uploadAuthoringFiles(files) {
    const normalizedFiles = [...(files || [])];
    if (!normalizedFiles.length) return status('請先選擇 PDF、Word、PPTX、圖片或文字資料。', 'error');
    if (!window.MaterialUploadClient?.enqueue) return status('教材安全上傳元件尚未載入。', 'error');
    const {area, group} = currentScope();
    setBusy(true);
    const token = ++pollToken;
    try {
      const uploaded = [];
      for (let index = 0; index < normalizedFiles.length; index += 1) {
        const file = normalizedFiles[index];
        const title = file.name.replace(/\.[^.]+$/, '') || file.name;
        const fd = new FormData();
        fd.append('file', file); fd.append('title', title);
        fd.append('desc', 'AI PowerPoint authoring source；教師確認前不提供學員使用。');
        fd.append('group', group); fd.append('area', area); fd.append('courseId', ''); fd.append('category', ''); fd.append('materialType', 'standard');
        status(`正在上傳原始資料 ${index + 1}/${normalizedFiles.length}｜${file.name}`);
        const queued = await window.MaterialUploadClient.enqueue(fd, {
          fileName: file.name,
          fallbackToSameOriginQueue: false,
          onProgress: event => status(`安全上傳 ${index + 1}/${normalizedFiles.length}・${event.percent}%｜${file.name}`),
        });
        const jobId = queued.jobId || '', materialId = queued.materialId || '';
        if (!jobId || !materialId) throw new Error('伺服器沒有回傳教材工作 ID');
        await pollMaterialJob(jobId, token, '原始資料處理中');
        const patch = await fetch(`/api/slides/${encodeURIComponent(materialId)}`, {method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({active:false, title})});
        const patchBody = await patch.json().catch(() => ({}));
        if (!patch.ok) throw new Error(patchBody.error || '無法將原始資料保持為草稿狀態');
        uploaded.push(materialId);
      }
      authoringSourceIds = [...new Set([...authoringSourceIds, ...uploaded])];
      await paintMaterialOptions();
      renderAuthoringSources();
      status(`✅ 已加入 ${uploaded.length} 份原始資料並保持為作者草稿；可先統整/RAG 再建立投影片大綱。`, 'success');
      return true;
    } catch (error) {
      status(`來源資料處理失敗：${error.message}`, 'error');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function uploadSource() {
    const input = document.getElementById('teacher-ai-material-file-1014');
    const completed = await uploadAuthoringFiles(input?.files || []);
    if (completed && input) input.value = '';
  }

  async function addPastedSource() {
    const titleInput = document.getElementById('teacher-ai-material-paste-title-1014');
    const textInput = document.getElementById('teacher-ai-material-paste-1014');
    const body = String(textInput?.value || '').trim();
    if (body.length < 20) return status('請貼入至少 20 個字的 SOP、教學內容或補充資料。', 'error');
    const title = String(titleInput?.value || '貼入文字資料').trim() || '貼入文字資料';
    const file = new File([body], safeTextFilename(title), {type:'text/plain;charset=utf-8', lastModified:Date.now()});
    const completed = await uploadAuthoringFiles([file]);
    if (completed) {
      if (titleInput) titleInput.value = '';
      if (textInput) textInput.value = '';
    }
  }

  function renderSource(result) {
    const host = document.getElementById('teacher-ai-material-source-info-1014');
    if (!host) return;
    const chunks = Array.isArray(result?.sourceChunks) ? result.sourceChunks : [];
    const fallback = result?.fallbackUsed ? '｜已使用免費備援' : '';
    host.innerHTML = `
      <div><b>來源教材：</b>${escapeHtml(result?.sourceTitle || '')}</div>
      <div><b>產出：</b>${escapeHtml(result?.outputLabel || TYPE_LABELS[result?.outputType] || '')}</div>
      <div><b>AI：</b>${escapeHtml(result?.provider || '')} / ${escapeHtml(result?.model || '')}${escapeHtml(fallback)}</div>
      <details class="mt-2"><summary class="cursor-pointer font-bold">？查看來源段落</summary><div class="mt-1">${chunks.length ? chunks.map(chunk => escapeHtml(chunk.chunkId || chunk.section || '')).join('、') : '—'}</div></details>
      <div class="mt-2 font-bold text-amber-800">⚠️ AI 只產生草稿；必須由教師確認後才能核准或發布。</div>`;
    host.classList.remove('hidden');
  }

  function showEditor(result) {
    const editor = document.getElementById('teacher-ai-material-editor-1014');
    const title = document.getElementById('teacher-ai-material-title-1014');
    const body = document.getElementById('teacher-ai-material-body-1014');
    if (title) title.value = result?.title || 'AI 教材草稿';
    if (body) body.value = result?.body || '';
    editor?.classList.remove('hidden');
    activeDraft = null;
    renderSource(result || {});
    syncEditorButtons();
  }

  function syncEditorButtons() {
    const approve = document.getElementById('teacher-ai-material-approve-1014');
    const publish = document.getElementById('teacher-ai-material-publish-1014');
    if (approve) approve.disabled = !activeDraft || activeDraft.status === 'approved';
    if (publish) publish.disabled = !activeDraft || activeDraft.status !== 'approved' || Boolean(activeDraft.publicationMaterialId);
  }

  async function pollAiJob(jobId, token) {
    while (token === pollToken && activeJobId === jobId) {
      const response = await fetch(`/api/ai-material-drafts/jobs/${encodeURIComponent(jobId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取 AI 教材進度');
      const progress = data.progress || {};
      status(`${progress.stage || 'AI 教材處理中'}｜${Math.round(Number(progress.percent || 0))}%${progress.detail ? `｜${progress.detail}` : ''}`);
      if (data.status === 'completed') {
        showEditor(data.result || {});
        status('✅ AI 草稿完成。請先編修與儲存，再由教師核准。', 'success');
        return;
      }
      if (data.status === 'failed') throw new Error(data.error || 'AI 教材產生失敗');
      await sleep(1800);
    }
  }

  async function generateDraft() {
    const materialId = primarySourceId();
    if (!materialId) return status('請先上傳來源資料或選擇既有教材。', 'error');
    const outputType = document.getElementById('teacher-ai-material-type-1014')?.value || 'summary';
    const payload = {
      materialId,
      referenceMaterialIds: allAuthoringSourceIds().filter(id => id !== materialId),
      outputType,
      targetMinutes: Number(document.getElementById('teacher-ai-material-minutes-1014')?.value || 5),
      tone: document.getElementById('teacher-ai-material-tone-1014')?.value || 'clinical',
      focus: document.getElementById('teacher-ai-material-focus-1014')?.value || '',
    };
    setBusy(true);
    activeDraft = null;
    activeJobId = '';
    document.getElementById('teacher-ai-material-editor-1014')?.classList.add('hidden');
    try {
      status(`正在建立「${TYPE_LABELS[outputType] || 'AI 教材'}」工作…`);
      const response = await fetch('/api/ai-material-drafts/generate', {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法建立 AI 教材工作');
      activeJobId = data.jobId || '';
      if (!activeJobId) throw new Error('伺服器沒有回傳 AI 教材工作 ID');
      const token = ++pollToken;
      await pollAiJob(activeJobId, token);
    } catch (error) {
      status(`AI 教材產生失敗：${error.message}`, 'error');
    } finally {
      setBusy(false);
      syncEditorButtons();
    }
  }

  async function saveDraft() {
    if (!activeJobId && !activeDraft) return status('目前沒有可儲存的 AI 教材草稿。', 'error');
    const title = String(document.getElementById('teacher-ai-material-title-1014')?.value || '').trim();
    const body = String(document.getElementById('teacher-ai-material-body-1014')?.value || '').trim();
    if (body.length < 60) return status('草稿內容太短，請確認後再儲存。', 'error');
    setBusy(true);
    try {
      let response;
      if (activeDraft) {
        response = await fetch(`/api/ai-material-drafts/${encodeURIComponent(activeDraft.id)}`, {
          method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({title, body, status:'draft'}),
        });
      } else {
        response = await fetch('/api/ai-material-drafts', {
          method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({jobId:activeJobId, title, body}),
        });
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'AI 教材草稿儲存失敗');
      activeDraft = data.draft || null;
      status('✅ 草稿已儲存。確認內容正確後再按「教師核准」。', 'success');
      await loadDrafts();
    } catch (error) {
      status(`儲存失敗：${error.message}`, 'error');
    } finally {
      setBusy(false);
      syncEditorButtons();
    }
  }

  async function approveDraft() {
    if (!activeDraft) return status('請先儲存草稿。', 'error');
    if (!confirm('確認已檢查這份 AI 草稿的內容、數值、步驟與來源，可以核准嗎？')) return;
    const title = String(document.getElementById('teacher-ai-material-title-1014')?.value || '').trim();
    const body = String(document.getElementById('teacher-ai-material-body-1014')?.value || '').trim();
    setBusy(true);
    try {
      const response = await fetch(`/api/ai-material-drafts/${encodeURIComponent(activeDraft.id)}`, {
        method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({title, body, status:'approved'}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '教師核准失敗');
      activeDraft = data.draft || activeDraft;
      announceDraft();
      status(activeDraft.draftType === 'script'
        ? '✅ 已核准。此教學講稿現在也可作為 AI 語音來源。'
        : '✅ 已由教師核准；需要時可發布成正式文字教材。', 'success');
      await loadDrafts();
    } catch (error) {
      status(`核准失敗：${error.message}`, 'error');
    } finally {
      setBusy(false);
      syncEditorButtons();
    }
  }

  function safeTextFilename(title) {
    const safe = String(title || 'AI教材').replace(/[\\/:*?"<>|\r\n]+/g, '_').trim().slice(0, 80) || 'AI教材';
    return `${safe}.txt`;
  }

  async function publishDraft() {
    if (!activeDraft || activeDraft.status !== 'approved') return status('必須先由教師核准草稿才能發布。', 'error');
    if (activeDraft.publicationMaterialId) return status('此草稿已經連結正式教材。', 'success');
    if (!window.MaterialUploadClient?.enqueue) return status('教材安全上傳元件尚未載入。', 'error');
    if (!confirm('將目前核准內容建立為正式文字教材。發布後學員可依原有課程／教材權限看到它，確定繼續？')) return;
    const title = String(document.getElementById('teacher-ai-material-title-1014')?.value || activeDraft.title || '').trim();
    const body = String(document.getElementById('teacher-ai-material-body-1014')?.value || activeDraft.body || '').trim();
    const source = materials.find(item => item.id === activeDraft.materialId) || {};
    const file = new File([body], safeTextFilename(title), {type:'text/plain;charset=utf-8', lastModified:Date.now()});
    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', title);
    fd.append('desc', `教師核准 AI ${TYPE_LABELS[activeDraft.draftType] || '教材'}；來源：${source.title || source.filename || activeDraft.materialId}`);
    fd.append('group', activeDraft.group || source.group || currentScope().group);
    fd.append('area', activeDraft.area || source.area || currentScope().area);
    fd.append('courseId', source.courseId || '');
    fd.append('category', '');
    fd.append('materialType', 'standard');
    setBusy(true);
    const token = ++pollToken;
    try {
      status('正在發布教師核准內容…');
      const queued = await window.MaterialUploadClient.enqueue(fd, {
        fileName: file.name,
        onProgress: event => status(`發布教材 ${event.percent}%｜${file.name}`),
      });
      if (!queued.jobId || !queued.materialId) throw new Error('伺服器沒有回傳正式教材工作 ID');
      await pollMaterialJob(queued.jobId, token, '正式教材處理中');
      const link = await fetch(`/api/ai-material-drafts/${encodeURIComponent(activeDraft.id)}`, {
        method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({title, body, status:'approved', publicationMaterialId:queued.materialId}),
      });
      const linkData = await link.json().catch(() => ({}));
      if (!link.ok) throw new Error(linkData.error || '正式教材已完成，但無法連結 AI 草稿紀錄');
      activeDraft = linkData.draft || activeDraft;
      announcePublication(queued.materialId);
      await paintMaterialOptions();
      await loadDrafts();
      status('✅ 已建立正式教材並保留 AI 來源／教師核准紀錄。', 'success');
    } catch (error) {
      status(`發布失敗：${error.message}`, 'error');
    } finally {
      setBusy(false);
      syncEditorButtons();
    }
  }

  async function loadDrafts() {
    const materialId = primarySourceId();
    const host = document.getElementById('teacher-ai-material-saved-1014');
    if (!host) return;
    if (!materialId) {
      host.innerHTML = '<p class="text-sm text-slate-500">選擇來源教材後會顯示已儲存 AI 草稿。</p>';
      return;
    }
    try {
      const response = await fetch(`/api/ai-material-drafts?materialId=${encodeURIComponent(materialId)}`, {credentials:'same-origin', cache:'no-store'});
      const list = await response.json().catch(() => []);
      if (!response.ok) throw new Error(list.error || '無法讀取 AI 草稿');
      host.innerHTML = Array.isArray(list) && list.length
        ? list.map(draft => `<button type="button" data-ai-draft-id="${escapeHtml(draft.id)}" class="w-full text-left rounded-xl border ${draft.status==='approved'?'border-emerald-200 bg-emerald-50/60':'border-slate-200 bg-white'} p-3"><div class="flex flex-wrap items-center justify-between gap-2"><b class="text-sm text-slate-900">${escapeHtml(draft.title)}</b><span class="text-xs font-bold ${draft.status==='approved'?'text-emerald-700':'text-amber-700'}">${escapeHtml(TYPE_LABELS[draft.draftType] || draft.draftType || '草稿')}｜${draft.status==='approved'?'已核准':'草稿'}${draft.publicationMaterialId?'｜已發布':''}</span></div><p class="mt-1 text-sm text-slate-500">更新：${escapeHtml(draft.updatedAt || '')}</p></button>`).join('')
        : '<p class="text-sm text-slate-500">這份來源教材目前沒有已儲存 AI 草稿。</p>';
      host.querySelectorAll('[data-ai-draft-id]').forEach(button => button.addEventListener('click', () => {
        const draft = list.find(item => item.id === button.dataset.aiDraftId);
        if (!draft) return;
        activeDraft = draft;
        activeJobId = draft.sourceJobId || '';
        document.getElementById('teacher-ai-material-title-1014').value = draft.title || '';
        document.getElementById('teacher-ai-material-body-1014').value = draft.body || '';
        document.getElementById('teacher-ai-material-editor-1014')?.classList.remove('hidden');
        renderSource({sourceTitle:(materials.find(item=>item.id===materialId)||{}).title || '', outputType:draft.draftType, outputLabel:TYPE_LABELS[draft.draftType] || '', sourceChunks:draft.sourceChunks || [], provider:draft.provider, model:draft.model, fallbackUsed:draft.fallbackUsed});
        syncEditorButtons();
        announceDraft();
        status(draft.publicationMaterialId ? '此草稿已核准並發布成正式教材。' : (draft.status === 'approved' ? '此草稿已核准，可發布成正式教材。' : '已載入草稿，可繼續編修。'));
      }));
    } catch (error) {
      host.innerHTML = `<p class="text-sm font-bold text-rose-700">${escapeHtml(error.message)}</p>`;
    }
  }

  function install(targetBox = null) {
    const existing = document.getElementById('teacher-ai-material-1014');
    if (existing) return existing;
    const box = targetBox
      || document.getElementById('teacher-media-panel-presentation-1018')
      || document.getElementById('teacher-media-production-1014')
      || document.getElementById('admin-course-material-hub');
    if (!box) return false;
    const section = document.createElement('section');
    section.id = 'teacher-ai-material-1014';
    section.className = 'mb-5 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm space-y-5';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-violet-700">AI SOURCE AUTHORING</p><h4 class="text-xl font-black text-slate-950">✨ AI 來源內容工作台</h4><p class="mt-1 text-sm text-slate-600">可直接上傳文件、圖片或貼入文字，作為講稿、配音、PowerPoint 或教學影片的共同來源；既有教材只是可選來源，不強制綁定。</p></div><details class="text-sm text-slate-600"><summary class="cursor-pointer font-bold text-violet-700">使用說明</summary><p class="mt-2 max-w-xl leading-6">PDF、Word、PPTX、SOP、Excel、圖片與貼入文字都可作為私人 authoring source。預設保持草稿，不會自動對學員發布；之後可選擇製作 PowerPoint／影片，或由教師明確發布成正式教材。</p></details></div>
      <div class="rounded-2xl border border-violet-200 bg-violet-50/40 p-4 space-y-4"><div class="flex flex-col lg:flex-row lg:items-end gap-3"><label class="flex-1 text-sm font-bold text-slate-700">Step 1｜加入來源資料（可多選或拖曳）<input id="teacher-ai-material-file-1014" type="file" multiple class="mt-1 block w-full text-sm" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odp,.odt,.ods,.txt,.csv,.png,.jpg,.jpeg,.webp"></label><button id="teacher-ai-material-upload-1014" type="button" class="rounded-xl bg-violet-700 px-4 py-2.5 text-sm font-black text-white">⬆️ 加入原始資料</button></div><div class="rounded-xl border border-violet-100 bg-white/80 p-3"><div class="grid gap-3 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)_auto] lg:items-end"><label class="text-sm font-bold text-slate-700">文字標題（貼入文字時使用）<input id="teacher-ai-material-paste-title-1014" maxlength="120" class="learning-input mt-1" placeholder="例如：生化檢驗 SOP"></label><label class="text-sm font-bold text-slate-700">直接貼入文字<textarea id="teacher-ai-material-paste-1014" rows="5" maxlength="60000" class="mt-1 w-full rounded-xl border border-slate-300 bg-white p-3 text-sm leading-6" placeholder="貼上 SOP、課程重點、會議紀錄或其他要製作成 PowerPoint 的內容"></textarea></label><button id="teacher-ai-material-paste-add-1014" type="button" class="rounded-xl border border-violet-200 bg-white px-4 py-2.5 text-sm font-black text-violet-700">＋ 加入貼入文字</button></div></div><p class="text-xs text-slate-600">這些資料是共用 AI 製作來源：可接講稿／配音／PowerPoint／影片；預設保持私人草稿，只有教師明確發布時才成為正式教材。</p><div id="teacher-ai-material-uploaded-sources-1014" class="flex flex-wrap gap-2"></div></div>
      <div class="grid md:grid-cols-2 xl:grid-cols-4 gap-3"><label class="text-sm font-bold text-slate-700 xl:col-span-2">補充既有教材（可多選；上方共用來源會自動帶入）<select id="teacher-ai-material-source-1014" multiple size="4" class="learning-input mt-1"><option value="">讀取教材中…</option></select></label><label class="text-sm font-bold text-slate-700">產出類型<select id="teacher-ai-material-type-1014" class="learning-input mt-1"><option value="slides" selected>投影片大綱</option><option value="handout">教學講義</option><option value="summary">重點摘要</option><option value="script">教學講稿</option><option value="quiz">測驗題草稿</option><option value="objectives">課程學習目標</option></select></label><label class="text-sm font-bold text-slate-700">文字風格<select id="teacher-ai-material-tone-1014" class="learning-input mt-1"><option value="clinical">專業臨床教學</option><option value="friendly">自然口語</option><option value="brief">精簡重點</option></select></label></div>
      <div class="grid md:grid-cols-[1fr_auto] gap-3"><div class="grid sm:grid-cols-[1fr_160px] gap-3"><input id="teacher-ai-material-focus-1014" class="learning-input" maxlength="500" placeholder="Step 2｜設定：特別聚焦的重點（選填）"><select id="teacher-ai-material-minutes-1014" class="learning-input" title="教學講稿目標長度；其他產出類型會作為篇幅參考"><option value="3">精簡</option><option value="5" selected>標準</option><option value="10">較完整</option><option value="15">深入</option></select></div><button id="teacher-ai-material-generate-1014" type="button" class="rounded-xl bg-violet-700 px-5 py-2.5 text-sm font-black text-white disabled:opacity-40">Step 3｜產生 AI 草稿</button></div>
      <div id="teacher-ai-material-status-1014" class="text-sm text-slate-600">選好來源後，設定產出類型與重點，再產生 AI 草稿。</div>
      <div id="teacher-ai-material-source-info-1014" class="hidden rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-slate-700"></div>
      <div id="teacher-ai-material-editor-1014" class="hidden space-y-3"><h5 class="text-base font-black text-slate-900">Step 3｜投影片大綱</h5><label class="block text-sm font-bold text-slate-700">標題<input id="teacher-ai-material-title-1014" class="learning-input mt-1" maxlength="255"></label><label class="block text-sm font-bold text-slate-700">內容<textarea id="teacher-ai-material-body-1014" rows="18" maxlength="40000" class="mt-1 w-full rounded-xl border border-slate-300 bg-white p-3 text-base leading-7" placeholder="AI 草稿會出現在這裡；請由教師逐段確認與修改。"></textarea></label><div class="flex flex-wrap gap-2"><button id="teacher-ai-material-save-1014" type="button" class="rounded-xl border border-violet-200 bg-white px-4 py-2 text-sm font-black text-violet-700">💾 儲存草稿</button><button id="teacher-ai-material-approve-1014" type="button" disabled class="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-black text-white disabled:opacity-40">✅ 教師核准</button><button id="teacher-ai-material-publish-1014" type="button" disabled class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-black text-white disabled:opacity-40">📚 選擇發布成正式教材</button></div><p class="text-sm text-slate-500">測驗題草稿若要進正式題庫，仍請到「評量與出題」完成審核與建立。</p></div>
      <div class="border-t border-slate-100 pt-4"><h5 class="text-base font-black text-slate-900">已儲存 AI 草稿</h5><div id="teacher-ai-material-saved-1014" class="mt-2 grid gap-2"><p class="text-sm text-slate-500">選擇來源教材後會顯示已儲存草稿。</p></div></div>
      <div id="teacher-ai-material-presentation-stage-1014" class="border-t border-slate-100 pt-5"></div>`;
    const dashboard = box.querySelector('.admin-course-dashboard');
    box.insertBefore(section, dashboard || box.firstChild);
    document.getElementById('teacher-ai-material-upload-1014')?.addEventListener('click', uploadSource);
    document.getElementById('teacher-ai-material-paste-add-1014')?.addEventListener('click', addPastedSource);
    document.getElementById('teacher-ai-material-generate-1014')?.addEventListener('click', generateDraft);
    document.getElementById('teacher-ai-material-save-1014')?.addEventListener('click', saveDraft);
    document.getElementById('teacher-ai-material-approve-1014')?.addEventListener('click', approveDraft);
    document.getElementById('teacher-ai-material-publish-1014')?.addEventListener('click', publishDraft);
    document.getElementById('teacher-ai-material-uploaded-sources-1014')?.addEventListener('click', event => {
      const button = event.target.closest?.('[data-remove-authoring-source]');
      if (!button) return;
      authoringSourceIds = authoringSourceIds.filter(id => id !== button.dataset.removeAuthoringSource);
      renderAuthoringSources();
    });
    const uploadInput = document.getElementById('teacher-ai-material-file-1014');
    uploadInput?.closest('label')?.addEventListener('dragover', event => event.preventDefault());
    uploadInput?.closest('label')?.addEventListener('drop', event => {
      event.preventDefault();
      if (!event.dataTransfer?.files?.length) return;
      const transfer = new DataTransfer();
      [...event.dataTransfer.files].forEach(file => transfer.items.add(file));
      uploadInput.files = transfer.files;
      status(`已選擇 ${transfer.files.length} 份原始資料，按「加入原始資料」開始安全上傳。`);
    });
    document.getElementById('teacher-ai-material-source-1014')?.addEventListener('change', () => {
      activeDraft = null;
      activeJobId = '';
      pollToken += 1;
      document.getElementById('teacher-ai-material-editor-1014')?.classList.add('hidden');
      void loadDrafts();
    });
    // The old standalone script studio remains loaded for compatibility, but
    // the teacher-facing entry is now consolidated into this assistant.
    document.getElementById('teacher-media-script-1014')?.classList.add('hidden');
    void paintMaterialOptions();
    renderAuthoringSources();
    return section;
  }

  function ensureMounted(targetBox = null) {
    const existing = document.getElementById('teacher-ai-material-1014');
    if (existing) {
      if (targetBox && existing.parentElement !== targetBox) targetBox.appendChild(existing);
      existing.classList.remove('hidden');
      existing.removeAttribute('aria-hidden');
      return existing;
    }
    return install(targetBox);
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.addEventListener('teacher-ai-material-request-publication', () => void publishDraft());
  window.TeacherAIMaterial1014 = Object.freeze({paintMaterialOptions, loadDrafts, publishCurrentDraft: publishDraft, ensureMounted});
})();
