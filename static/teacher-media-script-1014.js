/* Teacher 10/14 media script studio: source material -> AI draft -> teacher approval. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  let activeJobId = '';
  let activeScriptId = '';
  let pollToken = 0;
  let materials = [];

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[char]));

  function status(message, tone = 'normal') {
    const node = document.getElementById('teacher-script-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function setBusy(busy) {
    const generate = document.getElementById('teacher-script-generate-1014');
    if (generate) generate.disabled = busy;
    const select = document.getElementById('teacher-script-material-1014');
    if (select) select.disabled = busy;
  }

  async function syncNarrationOptions() {
    const loader = window.TeacherMediaAudio1014?.loadApprovedScripts;
    if (typeof loader === 'function') await loader();
  }

  function updateMaterialCache(rows) {
    materials = (Array.isArray(rows) ? rows : []).filter(item => item && item.id && !item.isBuiltin);
    return materials;
  }

  async function fetchMaterials() {
    const response = await fetch('/api/slides/admin', {credentials:'same-origin', cache:'no-store'});
    const data = await response.json().catch(() => []);
    if (!response.ok) throw new Error(data.error || '無法讀取教材清單');
    return updateMaterialCache(data);
  }

  async function paintMaterialOptions() {
    const select = document.getElementById('teacher-script-material-1014');
    if (!select) return;
    const previous = select.value;
    select.innerHTML = '<option value="">選擇教材…</option>';
    try {
      await fetchMaterials();
      materials.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id || '';
        const group = item.groupLabel || item.group || '';
        option.textContent = `${group ? `${group}｜` : ''}${item.title || item.filename || item.id}`;
        select.appendChild(option);
      });
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
    } catch (error) {
      status(`教材清單讀取失敗：${error.message}`, 'error');
    }
  }

  function showSource(result) {
    const host = document.getElementById('teacher-script-source-1014');
    if (!host) return;
    const chunks = Array.isArray(result?.sourceChunks) ? result.sourceChunks : [];
    host.innerHTML = `
      <div><b>來源教材：</b>${escapeHtml(result?.sourceTitle || '')}</div>
      <div><b>AI：</b>${escapeHtml(result?.provider || '')} / ${escapeHtml(result?.model || '')}</div>
      <div><b>來源段落：</b>${chunks.length ? chunks.map(chunk => escapeHtml(chunk.chunkId || chunk.section || '')).join('、') : '—'}</div>
      <div class="mt-1 text-amber-800">⚠️ AI 僅產生草稿；請由授課教師逐段確認內容、數值與步驟後再核准。</div>`;
    host.classList.remove('hidden');
  }

  function showEditor(result) {
    const editor = document.getElementById('teacher-script-editor-1014');
    const title = document.getElementById('teacher-script-title-1014');
    const body = document.getElementById('teacher-script-body-1014');
    if (title) title.value = result?.title || '教學講稿';
    if (body) body.value = result?.body || '';
    editor?.classList.remove('hidden');
    document.getElementById('teacher-script-save-1014')?.removeAttribute('disabled');
    document.getElementById('teacher-script-approve-1014')?.setAttribute('disabled', 'disabled');
    activeScriptId = '';
    showSource(result || {});
  }

  async function pollJob(jobId, token) {
    while (token === pollToken && activeJobId === jobId) {
      const response = await fetch(`/api/media-scripts/jobs/${encodeURIComponent(jobId)}`, {
        credentials:'same-origin', cache:'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法讀取講稿工作進度');
      const progress = data.progress || {};
      status(`${progress.stage || 'AI 講稿處理中'}｜${Math.round(Number(progress.percent || 0))}%${progress.detail ? `｜${progress.detail}` : ''}`);
      if (data.status === 'completed') {
        setBusy(false);
        showEditor(data.result || {});
        status('✅ 講稿草稿已完成。請由老師編修、儲存後再核准。', 'success');
        return;
      }
      if (data.status === 'failed') {
        setBusy(false);
        throw new Error(data.error || '講稿產生失敗');
      }
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
  }

  async function generateScript() {
    const materialId = document.getElementById('teacher-script-material-1014')?.value || '';
    if (!materialId) {
      status('請先選擇一份教材。', 'error');
      return;
    }
    const payload = {
      materialId,
      targetMinutes: Number(document.getElementById('teacher-script-minutes-1014')?.value || 5),
      tone: document.getElementById('teacher-script-tone-1014')?.value || 'clinical',
      focus: document.getElementById('teacher-script-focus-1014')?.value || '',
    };
    setBusy(true);
    activeJobId = '';
    activeScriptId = '';
    document.getElementById('teacher-script-editor-1014')?.classList.add('hidden');
    status('正在建立講稿工作…');
    try {
      const response = await fetch('/api/media-scripts/generate', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '無法建立講稿工作');
      activeJobId = data.jobId || '';
      if (!activeJobId) throw new Error('伺服器沒有回傳講稿工作 ID');
      const token = ++pollToken;
      await pollJob(activeJobId, token);
    } catch (error) {
      setBusy(false);
      status(`講稿產生失敗：${error.message}`, 'error');
    }
  }

  async function saveNewDraft() {
    if (!activeJobId) {
      status('目前沒有可儲存的 AI 講稿工作。', 'error');
      return;
    }
    const title = String(document.getElementById('teacher-script-title-1014')?.value || '').trim();
    const body = String(document.getElementById('teacher-script-body-1014')?.value || '').trim();
    if (body.length < 80) {
      status('講稿內容太短，請確認後再儲存。', 'error');
      return;
    }
    const button = document.getElementById('teacher-script-save-1014');
    if (button) button.disabled = true;
    try {
      const response = await fetch('/api/media-scripts', {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({jobId:activeJobId, title, body}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '講稿儲存失敗');
      activeScriptId = data.script?.id || '';
      document.getElementById('teacher-script-approve-1014')?.removeAttribute('disabled');
      status('✅ 草稿已儲存。確認內容正確後，可按「教師核准講稿」。', 'success');
      await loadSavedScripts();
    } catch (error) {
      if (button) button.disabled = false;
      status(`儲存失敗：${error.message}`, 'error');
    }
  }

  async function updateSavedScript(statusValue) {
    if (!activeScriptId) {
      status('請先儲存講稿草稿。', 'error');
      return;
    }
    const title = String(document.getElementById('teacher-script-title-1014')?.value || '').trim();
    const body = String(document.getElementById('teacher-script-body-1014')?.value || '').trim();
    const response = await fetch(`/api/media-scripts/${encodeURIComponent(activeScriptId)}`, {
      method:'PATCH', credentials:'same-origin', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title, body, status:statusValue}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '講稿更新失敗');
    return data.script || {};
  }

  async function approveScript() {
    if (!confirm('確認這份講稿已由授課教師逐段檢查內容、數值與流程，可以作為後續語音／影片來源嗎？')) return;
    const button = document.getElementById('teacher-script-approve-1014');
    if (button) button.disabled = true;
    try {
      const script = await updateSavedScript('approved');
      status(`✅ 講稿已由 ${script.approvedBy || '目前教師'} 核准。已直接銜接下一步 AI 配音。`, 'success');
      await loadSavedScripts();
      await syncNarrationOptions();
      window.dispatchEvent(new CustomEvent('teacher-media-script-approved-1027', {
        detail: {
          materialId: document.getElementById('teacher-script-material-1014')?.value || '',
          scriptId: script.id || activeScriptId,
          title: script.title || ''
        }
      }));
    } catch (error) {
      if (button) button.disabled = false;
      status(`核准失敗：${error.message}`, 'error');
    }
  }

  async function saveEdits() {
    if (!activeScriptId) return saveNewDraft();
    const button = document.getElementById('teacher-script-save-1014');
    if (button) button.disabled = true;
    try {
      const script = await updateSavedScript('draft');
      status('✅ 講稿修改已儲存；因內容有變更，狀態回到草稿，請重新核准。', 'success');
      document.getElementById('teacher-script-approve-1014')?.removeAttribute('disabled');
      await loadSavedScripts();
      await syncNarrationOptions();
      return script;
    } catch (error) {
      status(`儲存失敗：${error.message}`, 'error');
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function loadSavedScripts() {
    const materialId = document.getElementById('teacher-script-material-1014')?.value || '';
    const host = document.getElementById('teacher-script-saved-1014');
    if (!host) return;
    if (!materialId) {
      host.innerHTML = '<p class="text-xs text-slate-400">選擇教材後會顯示已儲存講稿。</p>';
      return;
    }
    try {
      const response = await fetch(`/api/media-scripts?materialId=${encodeURIComponent(materialId)}`, {credentials:'same-origin', cache:'no-store'});
      const list = await response.json().catch(() => []);
      if (!response.ok) throw new Error(list.error || '無法讀取已儲存講稿');
      host.innerHTML = Array.isArray(list) && list.length
        ? list.map(script => `<button type="button" data-script-id="${escapeHtml(script.id)}" class="w-full text-left rounded-xl border ${script.status==='approved'?'border-emerald-200 bg-emerald-50/60':'border-slate-200 bg-white'} p-3"><div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-900">${escapeHtml(script.title)}</b><span class="text-[10px] font-bold ${script.status==='approved'?'text-emerald-700':'text-amber-700'}">${script.status==='approved'?'已核准':'草稿'}</span></div><p class="mt-1 text-[11px] text-slate-500">更新：${escapeHtml(script.updatedAt || '')}${script.approvedBy?`｜核准：${escapeHtml(script.approvedBy)}`:''}</p></button>`).join('')
        : '<p class="text-xs text-slate-400">這份教材尚未儲存任何講稿。</p>';
      host.querySelectorAll('[data-script-id]').forEach(button => button.addEventListener('click', () => {
        const script = list.find(item => item.id === button.dataset.scriptId);
        if (!script) return;
        activeScriptId = script.id;
        activeJobId = script.sourceJobId || '';
        document.getElementById('teacher-script-title-1014').value = script.title || '';
        document.getElementById('teacher-script-body-1014').value = script.body || '';
        document.getElementById('teacher-script-editor-1014')?.classList.remove('hidden');
        document.getElementById('teacher-script-save-1014')?.removeAttribute('disabled');
        const approve = document.getElementById('teacher-script-approve-1014');
        if (approve) approve.disabled = script.status === 'approved';
        showSource({sourceTitle:(materials.find(item=>item.id===materialId)||{}).title || '', sourceChunks:script.sourceChunks || []});
        status(script.status === 'approved' ? '此講稿目前已核准；如修改並儲存，會回到草稿狀態。' : '已載入既有草稿，可繼續編修。');
      }));
    } catch (error) {
      host.innerHTML = `<p class="text-xs text-rose-600">${escapeHtml(error.message)}</p>`;
    }
  }

  function install() {
    const media = document.getElementById('teacher-media-production-1014');
    if (!media || document.getElementById('teacher-media-script-1014')) return false;
    const section = document.createElement('section');
    section.id = 'teacher-media-script-1014';
    section.className = 'bg-white border border-indigo-200 rounded-2xl p-5 shadow-sm space-y-5';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3"><div><p class="admin-page-eyebrow text-indigo-700">STEP 1 · SCRIPT</p><h4 class="text-lg font-black text-slate-950">📝 先建立並核准講稿</h4><p class="mt-1 text-xs text-slate-500">來源可由上方教材／來源內容帶入；講稿核准後會直接銜接下方 AI 配音，不必切換到另一套流程。</p></div><span class="rounded-full bg-indigo-50 px-3 py-1.5 text-[11px] font-bold text-indigo-700">AI 草稿 → 教師核准</span></div>
      <div class="grid md:grid-cols-2 xl:grid-cols-4 gap-3"><label class="text-xs font-bold text-slate-600 xl:col-span-2">來源教材<select id="teacher-script-material-1014" class="learning-input mt-1"><option value="">讀取教材中…</option></select></label><label class="text-xs font-bold text-slate-600">目標長度<select id="teacher-script-minutes-1014" class="learning-input mt-1"><option value="3">約 3 分鐘</option><option value="5" selected>約 5 分鐘</option><option value="10">約 10 分鐘</option><option value="15">約 15 分鐘</option><option value="20">約 20 分鐘</option></select></label><label class="text-xs font-bold text-slate-600">講課語氣<select id="teacher-script-tone-1014" class="learning-input mt-1"><option value="clinical">專業臨床教學</option><option value="friendly">自然口語</option><option value="brief">精簡重點</option></select></label></div>
      <div class="flex flex-col sm:flex-row gap-2"><input id="teacher-script-focus-1014" class="learning-input flex-1" maxlength="500" placeholder="選填：特別聚焦，例如抗體鑑定判讀步驟、QC 異常處理"><button id="teacher-script-generate-1014" type="button" class="rounded-xl bg-indigo-700 px-5 py-2.5 text-xs font-black text-white disabled:opacity-40">✨ AI 產生講稿草稿</button></div>
      <div id="teacher-script-status-1014" class="text-xs text-slate-600">選擇教材後即可產生講稿。</div>
      <div id="teacher-script-source-1014" class="hidden rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] leading-5 text-slate-700"></div>
      <div id="teacher-script-editor-1014" class="hidden space-y-3"><label class="block text-xs font-bold text-slate-600">講稿標題<input id="teacher-script-title-1014" class="learning-input mt-1" maxlength="255"></label><label class="block text-xs font-bold text-slate-600">講稿內容<textarea id="teacher-script-body-1014" rows="18" maxlength="40000" class="mt-1 w-full rounded-xl border border-slate-300 bg-white p-3 text-sm leading-7" placeholder="AI 草稿會出現在這裡；請由老師逐段確認與修改。"></textarea></label><div class="flex flex-wrap items-center gap-2"><button id="teacher-script-save-1014" type="button" class="rounded-xl border border-indigo-200 bg-white px-4 py-2 text-xs font-black text-indigo-700">💾 儲存草稿</button><button id="teacher-script-approve-1014" type="button" disabled class="rounded-xl bg-emerald-700 px-4 py-2 text-xs font-black text-white disabled:opacity-40">✅ 教師核准講稿</button><span class="text-[11px] text-slate-500">核准後才可作為下一階段 AI 語音／影片的正式來源。</span></div></div>
      <div class="border-t border-slate-100 pt-4"><div class="flex items-center justify-between gap-2"><h5 class="text-sm font-black text-slate-900">已儲存講稿</h5><span class="text-[11px] text-slate-400">草稿／已核准</span></div><div id="teacher-script-saved-1014" class="mt-2 grid gap-2"><p class="text-xs text-slate-400">選擇教材後會顯示已儲存講稿。</p></div></div>`;
    media.prepend(section);
    document.getElementById('teacher-script-generate-1014')?.addEventListener('click', generateScript);
    document.getElementById('teacher-script-save-1014')?.addEventListener('click', saveEdits);
    document.getElementById('teacher-script-approve-1014')?.addEventListener('click', approveScript);
    document.getElementById('teacher-script-material-1014')?.addEventListener('change', () => {
      activeScriptId = '';
      activeJobId = '';
      pollToken += 1;
      void loadSavedScripts();
    });
    return true;
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.addEventListener('teacher-media-source-options-1014', event => {
    updateMaterialCache(event.detail?.materials);
  });

  window.TeacherMediaScript1014 = Object.freeze({ generateScript, loadSavedScripts });
})();
