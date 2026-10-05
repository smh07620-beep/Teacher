/* Teacher media controls 10/23 reliability pass.
 * The visible shared source picker works independently of legacy hidden pickers.
 * It also keeps AI PowerPoint authoring and ordinary material upload inside the
 * media workspace and keeps uploads on Browser -> R2. Server RBAC/scope remains authoritative.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const canManage = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role))
    && has('material.manage');
  if (!canManage) return;

  const $ = id => document.getElementById(id);
  let materials = [];
  let refreshGeneration = 0;
  let observer = null;
  let uploadRefreshTimer = null;
  let sourcesLoadedAt = 0;
  let presentationRefreshGeneration = 0;
  let presentationRefreshController = null;
  let presentationRefreshPromise = null;
  let presentationRefreshKey = '';
  let presentationCache = { group: '', loadedAt: 0, rows: [] };
  const powerpointOrigin = { parent: null, next: null, panel: null };

  function currentScope() {
    const params = new URLSearchParams(window.location.search);
    return {
      area: params.get('area') || window.currentTrainingArea || 'internal',
      group: params.get('group') || window.currentGroupKey || String(R.user?.preferredGroup || '') || 'grpBio',
    };
  }

  function sourceLabel(item) {
    const draft = item?.active === false ? '［草稿］' : '';
    const group = item?.groupLabel || item?.group || '';
    const title = item?.title || item?.filename || item?.id || '未命名教材';
    return `${draft}${group ? `${group}｜` : ''}${title}`;
  }

  function scopedMaterials(rows) {
    const { area, group } = currentScope();
    return (Array.isArray(rows) ? rows : [])
      .filter(item => item?.id && !item?.isBuiltin)
      .filter(item => !group || !item.group || String(item.group) === String(group))
      .filter(item => !area || !item.area || String(item.area) === String(area))
      .sort((a, b) => sourceLabel(a).localeCompare(sourceLabel(b), 'zh-Hant'));
  }

  function paintSelect(select, rows, emptyText) {
    if (!select) return;
    const previous = select.value;
    select.replaceChildren(new Option(rows.length ? '選擇來源教材／內容…' : emptyText, ''));
    rows.forEach(item => select.add(new Option(sourceLabel(item), String(item.id || ''))));
    if (previous && rows.some(item => String(item.id) === previous)) select.value = previous;
    select.disabled = !rows.length;
  }

  function setSharedHint(message, error = false) {
    const hint = $('teacher-media-next-step-1018');
    if (!hint) return;
    if (hint.textContent !== message) hint.textContent = message;
    hint.classList.toggle('text-rose-700', Boolean(error));
    hint.classList.toggle('text-cyan-900', !error);
  }

  function ensureSourceEmptyState() {
    const shared = $('teacher-media-source-1018');
    if (!shared) return null;
    let box = $('teacher-media-source-empty-1024');
    if (box) return box;

    box = document.createElement('div');
    box.id = 'teacher-media-source-empty-1024';
    box.className = 'hidden mt-3 rounded-xl border border-dashed border-cyan-200 bg-white/80 p-4 text-sm text-slate-700';
    box.innerHTML = `
      <b class="text-slate-900">目前沒有可選的已完成教材</b>
      <p class="mt-1 text-xs leading-5 text-slate-600">一般教材可直接在這一頁上傳；如果要用多份 PDF、Word、PPT、Excel、圖片或文字產生簡報，請使用下方唯一的「多資料 AI PowerPoint」。</p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button id="teacher-media-empty-upload-1024" type="button" class="rounded-lg bg-teal-700 px-3 py-2 text-xs font-black text-white">📚 上傳一般教材</button>
        <button id="teacher-media-source-refresh-1024" type="button" class="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-black text-cyan-800">↻ 重新整理教材</button>
      </div>`;
    const label = shared.closest('label');
    const anchor = label || shared;
    anchor.insertAdjacentElement('afterend', box);
    return box;
  }

  function showSourceAvailability(rows, errorMessage = '') {
    const shared = $('teacher-media-source-1018');
    if (!shared) return;
    const label = shared.closest('label');
    const empty = ensureSourceEmptyState();
    const hasRows = Array.isArray(rows) && rows.length > 0;
    if (label) label.classList.toggle('hidden', !hasRows);
    else shared.classList.toggle('hidden', !hasRows);
    empty?.classList.toggle('hidden', hasRows);
    if (!hasRows && empty) {
      const heading = empty.querySelector('b');
      const paragraph = empty.querySelector('p');
      if (errorMessage) {
        if (heading) heading.textContent = '教材清單讀取失敗';
        if (paragraph) paragraph.textContent = `${errorMessage}。可按「重新整理教材」再試一次，或直接在本頁上傳一般教材。`;
      } else {
        if (heading) heading.textContent = '目前沒有可選的已完成教材';
        if (paragraph) paragraph.textContent = '一般教材可直接在這一頁上傳；若要用多份原始資料產生簡報，請使用下方唯一的「多資料 AI PowerPoint」。';
      }
    }
  }

  function paintVideoPresentations(rows, preferredMaterialId = '') {
    const select = $('teacher-ai-video-presentation-1015');
    if (!select || select.tagName !== 'SELECT') return false;
    const previous = select.value;
    const usable = (Array.isArray(rows) ? rows : [])
      .filter(item => item?.artifactReady && ['approved', 'published'].includes(String(item.status || '')))
      .sort((a, b) => {
        const aPreferred = preferredMaterialId && String(a.materialId || '') === String(preferredMaterialId) ? 1 : 0;
        const bPreferred = preferredMaterialId && String(b.materialId || '') === String(preferredMaterialId) ? 1 : 0;
        return bPreferred - aPreferred
          || String(a.title || '').localeCompare(String(b.title || ''), 'zh-Hant')
          || Number(b.revisionNumber || 0) - Number(a.revisionNumber || 0);
      });
    select.replaceChildren(new Option(usable.length ? '選擇已核准 PowerPoint…' : '尚無已核准 PowerPoint', ''));
    usable.forEach(item => {
      const preferred = preferredMaterialId && String(item.materialId || '') === String(preferredMaterialId) ? '｜目前來源' : '';
      const label = `${item.title || '教學 PowerPoint'}｜版本 ${Number(item.revisionNumber || 1)}${item.status === 'published' ? '｜已發布' : '｜已核准'}${preferred}`;
      select.add(new Option(label, String(item.id || '')));
    });
    if (previous && usable.some(item => String(item.id) === previous)) select.value = previous;
    else if (usable.length === 1) select.value = String(usable[0].id || '');
    select.disabled = !usable.length;
    const status = $('teacher-ai-video-status-1015');
    if (status && !usable.length) status.textContent = '目前這個組別尚無已核准 PowerPoint；可直接丟 PDF／Word／PPT／Excel／圖片建立。';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  async function refreshVideoPresentations(materialId = '', options = {}) {
    const select = $('teacher-ai-video-presentation-1015');
    if (!select || select.tagName !== 'SELECT') return false;
    const force = Boolean(options?.force);
    const { group } = currentScope();
    const groupKey = String(group || '');
    const now = Date.now();

    if (!force && presentationCache.group === groupKey && presentationCache.rows.length
        && now - Number(presentationCache.loadedAt || 0) < 15000) {
      return paintVideoPresentations(presentationCache.rows, materialId);
    }

    const requestKey = groupKey || '__preferred_group__';
    if (!force && presentationRefreshPromise && presentationRefreshKey === requestKey) {
      return presentationRefreshPromise;
    }

    presentationRefreshController?.abort?.();
    const controller = new AbortController();
    presentationRefreshController = controller;
    presentationRefreshKey = requestKey;
    const generation = ++presentationRefreshGeneration;
    select.replaceChildren(new Option('讀取所有已核准 PowerPoint…', ''));
    select.disabled = true;

    const task = (async () => {
      let timeoutId = 0;
      let timedOut = false;
      try {
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, 12000);
        const query = groupKey ? `?group=${encodeURIComponent(groupKey)}` : '';
        const response = await fetch(`/api/ai-presentations${query}`, {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: controller.signal,
        });
        const body = await response.json().catch(() => []);
        if (!response.ok) throw new Error(body?.error || '無法讀取 PowerPoint 版本');
        if (generation !== presentationRefreshGeneration) return false;
        presentationCache = {
          group: groupKey,
          loadedAt: Date.now(),
          rows: Array.isArray(body) ? body : [],
        };
        return paintVideoPresentations(presentationCache.rows, materialId);
      } catch (error) {
        if (generation !== presentationRefreshGeneration) return false;
        if (error?.name === 'AbortError' && !timedOut) return false;
        select.replaceChildren(new Option(timedOut ? 'PowerPoint 讀取逾時｜請重試' : 'PowerPoint 版本讀取失敗', ''));
        select.disabled = true;
        const status = $('teacher-ai-video-status-1015');
        const message = timedOut ? 'PowerPoint 清單讀取逾時，請按重新整理或稍後再試。' : `PowerPoint 讀取失敗：${error.message}`;
        if (status && status.textContent !== message) status.textContent = message;
        return false;
      } finally {
        if (timeoutId) window.clearTimeout(timeoutId);
        if (generation === presentationRefreshGeneration) {
          presentationRefreshPromise = null;
          presentationRefreshController = null;
        }
      }
    })();
    presentationRefreshPromise = task;
    return task;
  }

  function syncSelectedSource() {
    const shared = $('teacher-media-source-1018');
    if (!shared) return;
    const materialId = shared.value || '';
    const legacy = $('teacher-script-material-1014');
    if (legacy) {
      if (![...legacy.options].some(option => option.value === materialId) && materialId) {
        const item = materials.find(row => String(row.id) === materialId);
        if (item) legacy.add(new Option(sourceLabel(item), materialId));
      }
      if (legacy.value !== materialId) {
        legacy.value = materialId;
        legacy.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    window.TeacherMediaSubtitle1014?.selectMaterial?.(materialId);
    void window.TeacherMediaAudio1014?.loadApprovedScripts?.();
    void refreshVideoPresentations(materialId);
    if (!materialId) {
      setSharedHint(materials.length
        ? '請先選擇來源教材／來源內容。'
        : '目前沒有已完成教材。可直接在本頁上傳一般教材，或用下方「多資料 AI PowerPoint」加入原始資料。');
      return;
    }
    const item = materials.find(row => String(row.id) === materialId);
    const isMedia = /video\/|audio\/|\.(mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|oga|flac)\b/i.test([
      item?.mimeType, item?.sourceMimeType, item?.filename, item?.title
    ].filter(Boolean).join(' ')) || String(item?.storageBackend || '').toLowerCase() === 'external';
    setSharedHint(isMedia
      ? '已選擇影音來源：可直接建立 AI 字幕；若已有核准講稿，也可產生 AI 配音。'
      : '已選擇教材來源：先建立／核准講稿即可產生 AI 配音；建立並核准 PowerPoint 後可製作教學影片。');
  }

  async function refreshSources() {
    const shared = $('teacher-media-source-1018');
    if (!shared) return false;
    const generation = ++refreshGeneration;
    shared.disabled = true;
    shared.replaceChildren(new Option('正在讀取可用教材…', ''));
    try {
      const response = await fetch('/api/slides/admin', { credentials: 'same-origin', cache: 'no-store' });
      const body = await response.json().catch(() => []);
      if (!response.ok) throw new Error(body?.error || '無法讀取教材清單');
      if (generation !== refreshGeneration) return false;
      materials = scopedMaterials(body);
      paintSelect($('teacher-script-material-1014'), materials, '目前沒有可用教材');
      paintSelect(shared, materials, '目前沒有可用教材；可直接在本頁上傳');
      showSourceAvailability(materials);
      sourcesLoadedAt = Date.now();
      syncSelectedSource();
      return true;
    } catch (error) {
      if (generation !== refreshGeneration) return false;
      materials = [];
      shared.replaceChildren(new Option('教材清單讀取失敗', ''));
      shared.disabled = true;
      showSourceAvailability([], error.message);
      setSharedHint(`教材清單讀取失敗：${error.message}`, true);
      return false;
    }
  }

  function replaceSubtitleLanguageInput() {
    const input = $('teacher-subtitle-language-1014');
    if (!input || input.tagName === 'SELECT') return false;
    const select = document.createElement('select');
    select.id = input.id;
    select.className = input.className;
    const options = [
      ['zh-TW', '繁體中文（zh-TW）'],
      ['zh-CN', '简体中文（zh-CN）'],
      ['en', 'English（en）'],
      ['ja', '日本語（ja）'],
      ['ko', '한국어（ko）'],
    ];
    options.forEach(([value, label]) => select.add(new Option(label, value)));
    select.value = options.some(([value]) => value === input.value) ? input.value : 'zh-TW';
    input.replaceWith(select);
    const label = select.closest('label');
    if (label?.firstChild?.nodeType === Node.TEXT_NODE && label.firstChild.textContent !== '字幕語言') {
      label.firstChild.textContent = '字幕語言';
    }
    return true;
  }

  function improvePowerPointEntry() {
    const entry = $('teacher-media-powerpoint-entry-1018');
    if (!entry) return;
    const desired = '不用先建立教材：可直接加入多份 PDF、Word、PPT、Excel、圖片或文字；也可選既有教材當參考。所有入口都會進入同一個 AI PowerPoint 工作台。';
    const text = entry.querySelector('p');
    if (text && text.textContent !== desired) text.textContent = desired;
    const button = $('teacher-media-open-powerpoint-1018');
    if (button && button.textContent !== '🖥️ 多資料 AI PowerPoint') button.textContent = '🖥️ 多資料 AI PowerPoint';
  }

  function improveVideoHelp() {
    const panel = $('teacher-ai-video-1015');
    if (!panel || $('teacher-ai-video-source-help-1023')) return;
    const note = document.createElement('p');
    note.id = 'teacher-ai-video-source-help-1023';
    note.className = 'rounded-xl border border-violet-100 bg-violet-50 p-3 text-xs leading-5 text-violet-900';
    note.textContent = '教學影片只需要「已核准 PowerPoint + 旁白」；來源教材不是必選。PowerPoint 也可以直接丟 PDF、Word、PPT、Excel、圖片或文字建立。';
    panel.insertBefore(note, panel.children[1] || null);
  }

  function ensurePowerPointWorkspace() {
    const studio = $('teacher-ai-media-studio-1018') || $('teacher-media-production-1014');
    if (!studio) return null;
    let host = $('teacher-media-powerpoint-workspace-1024');
    if (host) return host;
    host = document.createElement('section');
    host.id = 'teacher-media-powerpoint-workspace-1024';
    host.hidden = true;
    host.className = 'rounded-2xl border border-violet-200 bg-white p-4 sm:p-5 shadow-sm';
    host.innerHTML = `
      <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-[11px] font-black tracking-[0.16em] text-violet-700">AI POWERPOINT AUTHORING</p>
          <h4 class="mt-1 text-xl font-black text-slate-950">🖥️ 多資料 AI PowerPoint</h4>
          <p class="mt-1 text-sm text-slate-600">一次加入多份原始資料 → AI 統整／RAG → 教師修改與核准 → 建立正式 .pptx。</p>
        </div>
        <button id="teacher-media-powerpoint-close-1024" type="button" class="shrink-0 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-black text-slate-700">← 回媒體製作</button>
      </div>
      <div id="teacher-media-powerpoint-body-1024"></div>`;
    const entry = $('teacher-media-powerpoint-entry-1018');
    if (entry?.parentElement === studio) entry.insertAdjacentElement('afterend', host);
    else studio.prepend(host);
    return host;
  }

  async function openPowerPointWorkspace() {
    closeGeneralMaterialUpload();
    let panel = $('teacher-ai-material-1014');
    if (!panel && typeof window.renderAdminCourseMaterialHub === 'function') {
      try { await window.renderAdminCourseMaterialHub(true); } catch (_error) {}
      panel = $('teacher-ai-material-1014');
    }
    const host = ensurePowerPointWorkspace();
    const body = $('teacher-media-powerpoint-body-1024');
    const studio = $('teacher-ai-media-studio-1018') || $('teacher-media-production-1014');
    if (!host || !body || !studio || !panel) {
      setSharedHint('AI PowerPoint 工作台尚未載入完成，請稍候再試。', true);
      return false;
    }

    if (panel.parentElement !== body) {
      powerpointOrigin.parent = panel.parentElement;
      powerpointOrigin.next = panel.nextSibling;
      powerpointOrigin.panel = panel;
      body.appendChild(panel);
    }
    [...studio.children].forEach(child => {
      if (child === host || child.hidden) return;
      child.dataset.teacherPptHidden1024 = '1';
      child.hidden = true;
    });
    host.hidden = false;
    panel.classList.remove('hidden');
    panel.removeAttribute('aria-hidden');
    window.TeacherAIMaterial1014?.paintMaterialOptions?.();
    host.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
    setTimeout(() => $('teacher-ai-material-file-1014')?.focus?.(), 80);
    return true;
  }

  function closePowerPointWorkspace() {
    const host = $('teacher-media-powerpoint-workspace-1024');
    const studio = $('teacher-ai-media-studio-1018') || $('teacher-media-production-1014');
    const panel = powerpointOrigin.panel || $('teacher-ai-material-1014');
    const parent = powerpointOrigin.parent;
    if (panel && parent?.isConnected && panel.parentElement !== parent) {
      if (powerpointOrigin.next?.parentElement === parent) parent.insertBefore(panel, powerpointOrigin.next);
      else parent.appendChild(panel);
    }
    if (host) host.hidden = true;
    if (studio) {
      [...studio.children].forEach(child => {
        if (child.dataset.teacherPptHidden1024 === '1') {
          delete child.dataset.teacherPptHidden1024;
          child.hidden = false;
        }
      });
    }
    powerpointOrigin.parent = null;
    powerpointOrigin.next = null;
    powerpointOrigin.panel = null;
  }

  function ensureGeneralMaterialUploadWorkspace() {
    const shared = $('teacher-media-source-1018');
    const studio = $('teacher-ai-media-studio-1018') || $('teacher-media-production-1014');
    if (!shared || !studio) return null;
    let host = $('teacher-media-general-upload-1025');
    if (host) return host;
    host = document.createElement('section');
    host.id = 'teacher-media-general-upload-1025';
    host.hidden = true;
    host.className = 'mt-3 rounded-2xl border border-teal-200 bg-white p-4 sm:p-5 shadow-sm';
    host.innerHTML = `
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-[11px] font-black tracking-[0.14em] text-teal-700">MATERIAL UPLOAD</p>
          <h4 class="mt-1 text-lg font-black text-slate-950">📚 上傳一般教材</h4>
          <p class="mt-1 text-xs leading-5 text-slate-500">檔案直接由瀏覽器傳到 R2，再交給 Worker 處理；不會跳回「教材與課程」。Worker 完成後會自動加入上方來源選單。</p>
        </div>
        <button id="teacher-media-general-upload-close-1025" type="button" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-600">收起</button>
      </div>
      <div class="mt-4 grid gap-3 lg:grid-cols-2">
        <label class="block text-xs font-bold text-slate-700 lg:col-span-2">選擇教材檔案（可多選）
          <input id="teacher-media-general-files-1025" type="file" multiple accept=".ppt,.pptx,.pdf,.doc,.docx,.xls,.xlsx,.odp,.odt,.ods,.png,.jpg,.jpeg,.gif,.webp,.mp4,.webm,.mov,.m4v,.mp3,.wav,.m4a,.ogg,.txt,.csv" class="mt-2 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm">
        </label>
        <label class="block text-xs font-bold text-slate-700">教材名稱（選填）
          <input id="teacher-media-general-title-1025" maxlength="255" placeholder="單檔可自訂；多檔留白使用檔名" class="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm">
        </label>
        <label class="block text-xs font-bold text-slate-700">教材說明（選填）
          <input id="teacher-media-general-desc-1025" maxlength="1000" placeholder="例如：儀器操作與維護教材" class="mt-2 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm">
        </label>
      </div>
      <div class="mt-3 rounded-xl bg-teal-50 px-3 py-2 text-xs text-teal-900">上傳範圍：<b id="teacher-media-general-scope-1025"></b>｜安全路徑：Browser → R2 → Worker</div>
      <div id="teacher-media-general-status-1025" class="mt-3 text-xs leading-5 text-slate-600" aria-live="polite">選好檔案後按「開始上傳」。</div>
      <div class="mt-4 flex justify-end">
        <button id="teacher-media-general-upload-start-1025" type="button" class="rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-black text-white">開始上傳</button>
      </div>`;
    const empty = ensureSourceEmptyState();
    const anchor = empty || shared.closest('label') || shared;
    anchor.insertAdjacentElement('afterend', host);
    return host;
  }

  function closeGeneralMaterialUpload() {
    const host = $('teacher-media-general-upload-1025');
    if (host) host.hidden = true;
    if (uploadRefreshTimer) {
      clearTimeout(uploadRefreshTimer);
      uploadRefreshTimer = null;
    }
  }

  function scheduleMaterialRefresh(beforeIds, status) {
    if (uploadRefreshTimer) clearTimeout(uploadRefreshTimer);
    let attempts = 0;
    const poll = async () => {
      attempts += 1;
      await refreshSources();
      const added = materials.filter(item => !beforeIds.has(String(item.id || '')));
      if (added.length) {
        const shared = $('teacher-media-source-1018');
        if (shared) {
          shared.value = String(added[0].id || '');
          syncSelectedSource();
        }
        if (status) status.textContent = `✅ Worker 已完成 ${added.length} 份新教材；已更新來源選單並選取「${added[0].title || added[0].filename || '新教材'}」。`;
        uploadRefreshTimer = null;
        return;
      }
      if (attempts >= 24) {
        if (status) status.textContent = '⏳ 檔案已排入 Worker，但尚未完成處理。你可以繼續其他工作，完成後按「重新整理教材」即可看到。';
        uploadRefreshTimer = null;
        return;
      }
      uploadRefreshTimer = setTimeout(poll, 5000);
    };
    uploadRefreshTimer = setTimeout(poll, 3000);
  }

  async function uploadGeneralMaterials() {
    const input = $('teacher-media-general-files-1025');
    const files = Array.from(input?.files || []);
    const status = $('teacher-media-general-status-1025');
    const button = $('teacher-media-general-upload-start-1025');
    if (!files.length) {
      if (status) status.textContent = '請先選擇至少一份教材檔案。';
      return false;
    }
    if (!window.MaterialUploadClient?.enqueue) {
      if (status) status.textContent = '❌ 教材上傳元件尚未載入，請重新整理頁面後再試。';
      return false;
    }

    const beforeIds = new Set(materials.map(item => String(item.id || '')));
    const { area, group } = currentScope();
    const title = $('teacher-media-general-title-1025')?.value.trim() || '';
    const desc = $('teacher-media-general-desc-1025')?.value.trim() || '';
    if (button) button.disabled = true;
    let queued = 0;
    const failed = [];

    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const fd = new FormData();
      fd.append('file', file);
      fd.append('title', files.length === 1 ? title : '');
      fd.append('desc', desc);
      fd.append('category', '');
      fd.append('group', group);
      fd.append('area', area);
      fd.append('courseId', '');
      fd.append('materialType', 'standard');
      fd.append('progressId', `media-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 8)}`);
      try {
        if (status) status.textContent = `⬆️ ${index + 1}/${files.length} 正在安全上傳「${file.name}」…`;
        const data = await window.MaterialUploadClient.enqueue(fd, {
          fileName: file.name,
          fallbackToSameOriginQueue: false,
          onProgress: progress => {
            if (status) status.textContent = `⬆️ ${index + 1}/${files.length}「${file.name}」${Number(progress?.percent || 0).toFixed(0)}%｜Browser → R2`;
          }
        });
        if (!data?.accepted && !data?.jobId && data?.status !== 'queued') throw new Error(data?.error || '教材未成功排入 Worker');
        queued += 1;
      } catch (error) {
        failed.push(`${file.name}：${error.message}`);
      }
    }

    if (button) button.disabled = false;
    if (input) input.value = '';
    if ($('teacher-media-general-title-1025')) $('teacher-media-general-title-1025').value = '';
    if ($('teacher-media-general-desc-1025')) $('teacher-media-general-desc-1025').value = '';

    if (!queued) {
      if (status) status.textContent = `❌ 上傳失敗：${failed.join('；') || '未知錯誤'}`;
      return false;
    }
    if (status) {
      status.textContent = failed.length
        ? `⚠️ 已排入 Worker ${queued}/${files.length} 份；${failed.length} 份失敗：${failed.join('；')}`
        : `✅ ${queued} 份教材已安全傳到 R2 並排入 Worker，正在等待處理完成…`;
    }
    scheduleMaterialRefresh(beforeIds, status);
    return true;
  }

  function openGeneralMaterialUpload() {
    closePowerPointWorkspace();
    const host = ensureGeneralMaterialUploadWorkspace();
    if (!host) {
      setSharedHint('教材上傳區尚未載入完成，請稍候再試。', true);
      return false;
    }
    const { area, group } = currentScope();
    const scopeNode = $('teacher-media-general-scope-1025');
    if (scopeNode) scopeNode.textContent = `${area} · ${group}`;
    host.hidden = false;
    host.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    setTimeout(() => $('teacher-media-general-files-1025')?.focus?.(), 50);
    return true;
  }

  function installCourseWizardDirectUploadGuard() {
    const client = window.MaterialUploadClient;
    if (!client?.enqueue || client.enqueue.__teacherWizardDirectOnly1024) return;
    const original = client.enqueue;
    const wrapped = function(formData, options = {}) {
      const workflowId = typeof formData?.get === 'function' ? String(formData.get('bundleWorkflowId') || '') : '';
      if (!workflowId) return original.call(client, formData, options);
      const directOptions = { ...options, fallbackToSameOriginQueue: false };
      delete directOptions.onFallback;
      return original.call(client, formData, directOptions).catch(error => {
        if (/Web 檔案接收相容路徑已關閉/.test(String(error?.message || ''))) {
          throw new Error('Browser → R2 直傳未完成。請直接重試；若仍失敗，請檢查 R2 CORS 是否允許目前網站來源並公開 ETag。');
        }
        throw error;
      });
    };
    wrapped.__teacherWizardDirectOnly1024 = true;
    wrapped.__teacherWizardOriginal1024 = original;
    client.enqueue = wrapped;
  }

  async function enhance(options = {}) {
    const shared = $('teacher-media-source-1018');
    installCourseWizardDirectUploadGuard();
    if (!shared) return false;
    if (shared.dataset.mediaControls1023 !== '1') {
      shared.dataset.mediaControls1023 = '1';
      shared.addEventListener('change', syncSelectedSource);
    }
    ensureSourceEmptyState();
    replaceSubtitleLanguageInput();
    improvePowerPointEntry();
    improveVideoHelp();
    const force = Boolean(options?.force);
    if (force || !sourcesLoadedAt || Date.now() - sourcesLoadedAt > 30000) {
      await refreshSources();
    } else {
      syncSelectedSource();
    }
    return true;
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => setTimeout(() => void enhance(), 0));

  document.addEventListener('click', event => {
    const target = event.target?.closest?.(
      '#teacher-media-open-powerpoint-1018,#teacher-media-direct-powerpoint-1026,#teacher-media-powerpoint-close-1024,#teacher-media-empty-upload-1024,#teacher-media-source-refresh-1024,#teacher-media-general-upload-close-1025,#teacher-media-general-upload-start-1025'
    );
    if (target) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (target.id === 'teacher-media-powerpoint-close-1024') closePowerPointWorkspace();
      else if (target.id === 'teacher-media-empty-upload-1024') openGeneralMaterialUpload();
      else if (target.id === 'teacher-media-source-refresh-1024') void enhance({force:true});
      else if (target.id === 'teacher-media-general-upload-close-1025') closeGeneralMaterialUpload();
      else if (target.id === 'teacher-media-general-upload-start-1025') void uploadGeneralMaterials();
      else void openPowerPointWorkspace();
      return;
    }

    if (event.target?.closest?.('#teacher-nav-course-1014,#teacher-nav-assessment-1014,#teacher-nav-documents-1014,#teacher-media-pick-material-1014')) {
      closePowerPointWorkspace();
      closeGeneralMaterialUpload();
    }
  }, true);

  document.addEventListener('click', event => {
    if (event.target.closest?.('#teacher-course-media-entry-1014 button,#teacher-nav-media-1014')) {
      setTimeout(() => void enhance(), 80);
    }
  });

  observer = new MutationObserver(() => {
    installCourseWizardDirectUploadGuard();
    const shared = $('teacher-media-source-1018');
    if (!shared) return;
    ensureSourceEmptyState();
    replaceSubtitleLanguageInput();
    improvePowerPointEntry();
    improveVideoHelp();
    if (shared.dataset.mediaControls1023 !== '1') void enhance();
  });
  observer.observe(document.body, { childList: true, subtree: true });

  installCourseWizardDirectUploadGuard();
  [0, 400, 1200, 3000, 7000, 12000].forEach(delay => setTimeout(() => void enhance(), delay));
  window.addEventListener('teacher-ai-presentation-rendered-f5', () => {
    presentationCache.loadedAt = 0;
    void refreshVideoPresentations($('teacher-media-source-1018')?.value || '', {force:true});
  });

  window.TeacherAIMediaControls1023 = Object.freeze({
    refreshSources,
    refreshVideoPresentations,
    openPowerPointWorkspace,
    closePowerPointWorkspace,
    openGeneralMaterialUpload,
  });
})();