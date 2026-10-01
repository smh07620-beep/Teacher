/* Teacher media controls 10/23 reliability pass.
 * The visible shared source picker must work independently of the hidden legacy
 * script picker.  Existing server RBAC/scope remains authoritative.
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
    hint.textContent = message;
    hint.classList.toggle('text-rose-700', Boolean(error));
    hint.classList.toggle('text-cyan-900', !error);
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
      if (status && !usable.length) status.textContent = '這份教材尚無已核准 PowerPoint。可先使用上方「多資料 AI PowerPoint」建立並核准。';
    } catch (error) {
      select.replaceChildren(new Option('PowerPoint 版本讀取失敗', ''));
      select.disabled = true;
      const status = $('teacher-ai-video-status-1015');
      if (status) status.textContent = `PowerPoint 讀取失敗：${error.message}`;
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
      setSharedHint(materials.length ? '請先選擇來源教材／來源內容。' : '目前沒有可用教材；請先上傳教材或建立 AI PowerPoint 來源。', !materials.length);
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
      paintSelect(shared, materials, '目前沒有可用教材；請先上傳或建立來源');
      syncSelectedSource();
      return true;
    } catch (error) {
      if (generation !== refreshGeneration) return false;
      materials = [];
      shared.replaceChildren(new Option('教材清單讀取失敗', ''));
      shared.disabled = true;
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
    if (label?.firstChild?.nodeType === Node.TEXT_NODE) label.firstChild.textContent = '字幕語言';
    return true;
  }

  function improvePowerPointEntry() {
    const entry = $('teacher-media-powerpoint-entry-1018');
    if (!entry) return;
    const text = entry.querySelector('p');
    if (text) text.textContent = '可一次加入多份 PDF、Word、PPT、圖片或文字，先由 AI Worker 統整／RAG 產生大綱，教師核准後再真正建立 .pptx。';
    const button = $('teacher-media-open-powerpoint-1018');
    if (button) button.textContent = '🖥️ 多資料 AI PowerPoint';
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

  async function enhance() {
    const shared = $('teacher-media-source-1018');
    if (!shared) return false;
    if (shared.dataset.mediaControls1023 !== '1') {
      shared.dataset.mediaControls1023 = '1';
      shared.addEventListener('change', syncSelectedSource);
    }
    replaceSubtitleLanguageInput();
    improvePowerPointEntry();
    improveVideoHelp();
    await refreshSources();
    return true;
  }

  window.AdminWorkspaceShell?.addAfterWorkspace?.(() => setTimeout(() => void enhance(), 0));
  document.addEventListener('click', event => {
    if (event.target.closest?.('#teacher-course-media-entry-1014 button,#teacher-nav-media-1014,#teacher-media-open-powerpoint-1018')) {
      setTimeout(() => void enhance(), 80);
    }
  });

  observer = new MutationObserver(() => {
    if ($('teacher-media-source-1018')) {
      replaceSubtitleLanguageInput();
      improvePowerPointEntry();
      improveVideoHelp();
      if ($('teacher-media-source-1018').dataset.mediaControls1023 !== '1') void enhance();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

  [0, 400, 1200, 3000, 7000, 12000].forEach(delay => setTimeout(() => void enhance(), delay));
  window.TeacherAIMediaControls1023 = Object.freeze({ refreshSources });
})();