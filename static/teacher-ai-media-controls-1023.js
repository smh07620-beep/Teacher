/* Teacher media controls 10/23 reliability pass.
 * The visible shared source picker works independently of legacy hidden pickers.
 * It also keeps AI PowerPoint authoring inside the media workspace and keeps the
 * course wizard on the Browser -> R2 transport. Server RBAC/scope remains authoritative.
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
      <p class="mt-1 text-xs leading-5 text-slate-600">你仍可直接丟多份 PDF、Word、PPT、Excel、圖片或文字製作 AI PowerPoint；一般教材完成 Worker 處理後也會自動出現在這裡。</p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button id="teacher-media-empty-powerpoint-1024" type="button" class="rounded-lg bg-violet-700 px-3 py-2 text-xs font-black text-white">🖥️ 直接製作 AI PowerPoint</button>
        <button id="teacher-media-empty-upload-1024" type="button" class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700">📚 上傳一般教材</button>
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
        if (paragraph) paragraph.textContent = `${errorMessage}。可按「重新整理教材」再試一次，或直接開啟多資料 AI PowerPoint。`;
      } else {
        if (heading) heading.textContent = '目前沒有可選的已完成教材';
        if (paragraph) paragraph.textContent = '你仍可直接丟多份 PDF、Word、PPT、Excel、圖片或文字製作 AI PowerPoint；一般教材完成 Worker 處理後也會自動出現在這裡。';
      }
    }
  }

  async function refreshVideoPresentations(materialId) {
    const select = $('teacher-ai-video-presentation-1015');
    if (!select || select.tagName !== 'SELECT') return;
    const previous = select.value;
    select.replaceChildren(new Option(materialId ? '讀取可用 PowerPoint…' : '請先選擇來源教材', ''));
    select.disabled = !materialId;
    if (!materialId) return;
    try {
      const response = await fetch(`/api/ai-presentations?materialId=${encodeURIComponent(materialId)}`, {
        credentials: 'same-origin', cache: 'no-store'
      });
      const body = await response.json().catch(() => []);
      if (!response.ok) throw new Error(body?.error || '無法讀取 PowerPoint 版本');
      const usable = (Array.isArray(body) ? body : []).filter(item =>
        item?.artifactReady && ['approved', 'published'].includes(String(item.status || ''))
      );
      select.replaceChildren(new Option(usable.length ? '選擇已核准 PowerPoint…' : '尚無已核准 PowerPoint', ''));
      usable.forEach(item => {
        const label = `${item.title || '教學 PowerPoint'}｜版本 ${Number(item.revisionNumber || 1)}${item.status === 'published' ? '｜已發布' : '｜已核准'}`;
        select.add(new Option(label, String(item.id || '')));
      });
      if (previous && usable.some(item => String(item.id) === previous)) select.value = previous;
      else if (usable.length === 1) select.value = String(usable[0].id || '');
      select.disabled = !usable.length;
      const status = $('teacher-ai-video-status-1015');
      const noPpt = '這份教材尚無已核准 PowerPoint。可先使用上方「多資料 AI PowerPoint」建立並核准。';
      if (status && !usable.length && status.textContent !== noPpt) status.textContent = noPpt;
    } catch (error) {
      select.replaceChildren(new Option('PowerPoint 版本讀取失敗', ''));
      select.disabled = true;
      const status = $('teacher-ai-video-status-1015');
      const message = `PowerPoint 讀取失敗：${error.message}`;
      if (status && status.textContent !== message) status.textContent = message;
    }
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
      legacy.value = materialId;
      legacy.dispatchEvent(new Event('change', { bubbles: true }));
    }
    window.TeacherMediaSubtitle1014?.selectMaterial?.(materialId);
    void window.TeacherMediaAudio1014?.loadApprovedScripts?.();
    void refreshVideoPresentations(materialId);
    if (!materialId) {
      setSharedHint(materials.length
        ? '請先選擇來源教材／來源內容。'
        : '沒有既有教材也可以製作：直接使用「多資料 AI PowerPoint」加入原始資料。');
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
      paintSelect(shared, materials, '目前沒有可用教材；可直接製作 AI PowerPoint');
      showSourceAvailability(materials);
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
    const desired = '直接在這裡加入多份 PDF、Word、PPT、Excel、圖片或文字；AI Worker 會統整／RAG 產生大綱，教師核准後再建立 .pptx，不再跳回教材區。';
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
    note.textContent = '教學影片需要「來源教材 + 已核准 PowerPoint + 旁白」。若 PowerPoint 清單為空，先按上方「多資料 AI PowerPoint」建立並核准簡報。';
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

  async function openGeneralMaterialUpload() {
    closePowerPointWorkspace();
    await window.TeacherWorkspace1014?.openCourse?.();
    setTimeout(() => {
      const input = $('admin-pptx-upload-input');
      const target = input || $('admin-course-material-hub');
      target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
      input?.focus?.();
    }, 80);
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

  async function enhance() {
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
    await refreshSources();
    return true;
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => setTimeout(() => void enhance(), 0));

  document.addEventListener('click', event => {
    const target = event.target?.closest?.(
      '#teacher-media-open-powerpoint-1018,#teacher-media-empty-powerpoint-1024,#teacher-media-powerpoint-close-1024,#teacher-media-empty-upload-1024,#teacher-media-source-refresh-1024'
    );
    if (target) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (target.id === 'teacher-media-powerpoint-close-1024') closePowerPointWorkspace();
      else if (target.id === 'teacher-media-empty-upload-1024') void openGeneralMaterialUpload();
      else if (target.id === 'teacher-media-source-refresh-1024') void refreshSources();
      else void openPowerPointWorkspace();
      return;
    }

    if (event.target?.closest?.('#teacher-nav-course-1014,#teacher-nav-assessment-1014,#teacher-nav-documents-1014,#teacher-media-pick-material-1014')) {
      closePowerPointWorkspace();
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
  window.TeacherAIMediaControls1023 = Object.freeze({
    refreshSources,
    openPowerPointWorkspace,
    closePowerPointWorkspace,
  });
})();
