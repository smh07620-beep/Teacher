/* Teacher authoring source-picker + media workspace recovery.
 * Keeps server RBAC/scope authoritative while removing internal IDs from teacher UX.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher', 'group_leader', 'education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  const $ = id => document.getElementById(id);
  let materials = null;
  let materialsPromise = null;
  let installing = false;

  function currentScope() {
    const query = new URLSearchParams(window.location.search);
    return {
      group: String(query.get('group') || window.currentGroupKey || '').trim(),
      area: String(query.get('area') || window.currentTrainingArea || '').trim(),
    };
  }

  async function json(path) {
    const response = await fetch(path, {credentials:'same-origin', cache:'no-store'});
    const data = await response.json().catch(() => ([]));
    if (!response.ok) throw new Error(data?.error || '資料讀取失敗');
    return data;
  }

  async function loadMaterials(force = false) {
    if (!force && Array.isArray(materials)) return materials;
    if (!force && materialsPromise) return materialsPromise;
    materialsPromise = (async () => {
      const data = await json('/api/slides/admin');
      const current = currentScope();
      materials = (Array.isArray(data) ? data : [])
        .filter(item => item && item.id && !item.isBuiltin)
        .filter(item => !current.group || String(item.group || '') === current.group)
        .filter(item => !current.area || String(item.area || '') === current.area)
        .sort((a, b) => String(a.title || a.filename || a.id).localeCompare(String(b.title || b.filename || b.id), 'zh-Hant'));
      return materials;
    })();
    try {
      return await materialsPromise;
    } finally {
      materialsPromise = null;
    }
  }

  function areaLabel(area) {
    return area === 'pgy' ? 'PGY' : (area === 'internal' ? '院內' : String(area || ''));
  }

  function materialLabel(item) {
    const draft = item.active === false ? '［草稿］' : '';
    const group = String(item.groupLabel || item.group || '').trim();
    const area = areaLabel(String(item.area || '').trim());
    const title = item.title || item.filename || item.id;
    const scopeText = [group, area].filter(Boolean).join('・');
    return `${draft}${scopeText ? `${scopeText}｜` : ''}${title}`;
  }

  // PowerPoint now owns its controls inside the AI PowerPoint 製作室.  Keep
  // this callable no-op only for cached pages that still call the old hook;
  // it deliberately does not rewrite controls or install a second observer.
  async function installPresentationPickers() {
    return Boolean($('teacher-ai-presentation-1016'));
  }

  function isCaptionMaterial(item) {
    const type = String(item?.materialType || '').toLowerCase();
    const mime = String(item?.mimeType || item?.sourceMimeType || '').toLowerCase();
    const filename = String(item?.filename || item?.title || '').toLowerCase();
    const backend = String(item?.storageBackend || '').toLowerCase();
    return type === 'video'
      || mime.startsWith('video/')
      || mime.startsWith('audio/')
      || /\.(mp4|webm|mov|m4v|avi|mkv|mp3|wav|m4a|aac|ogg|oga|flac)$/i.test(filename)
      || backend === 'external';
  }

  function syncSubtitleSource(materialId, label) {
    // Subtitle selection is deliberately independent from the script picker.
    // The previous bridge rewrote a shared select and dispatched its change
    // event, which made subtitle state disappear whenever the script panel
    // rerendered.  Keep the selected material with the subtitle workspace.
    void label;
    const picker = $('teacher-subtitle-material-1017');
    if (picker && picker.value !== materialId) picker.value = materialId || '';
    window.TeacherMediaSubtitle1014?.selectMaterial?.(materialId || '');
    return Boolean(materialId);
  }

  async function installSubtitlePicker() {
    const section = $('teacher-media-subtitle-1014');
    if (!section || $('teacher-subtitle-material-1017')) return Boolean(section);
    const language = $('teacher-subtitle-language-1014');
    const grid = language?.closest('div');
    if (!grid) return false;

    const label = document.createElement('label');
    label.className = 'block text-xs font-bold text-slate-600';
    label.textContent = '來源影音教材';
    const select = document.createElement('select');
    select.id = 'teacher-subtitle-material-1017';
    select.className = 'learning-input mt-1';
    const loading = document.createElement('option');
    loading.value = '';
    loading.textContent = '讀取影音教材中…';
    select.appendChild(loading);
    label.appendChild(select);
    grid.insertAdjacentElement('beforebegin', label);

    try {
      const rows = (await loadMaterials()).filter(isCaptionMaterial);
      select.replaceChildren();
      const option0 = document.createElement('option');
      option0.value = '';
      option0.textContent = rows.length ? '選擇影音教材…' : '目前沒有可產生字幕的影音教材';
      select.appendChild(option0);
      rows.forEach(item => {
        const option = document.createElement('option');
        option.value = String(item.id || '');
        option.textContent = materialLabel(item);
        select.appendChild(option);
      });
      select.disabled = !rows.length;
      const activeValue = window.TeacherMediaSubtitle1014?.selectedMaterialId?.() || '';
      if (activeValue && rows.some(item => String(item.id) === activeValue)) select.value = activeValue;
    } catch (_) {
      select.innerHTML = '<option value="">影音教材讀取失敗</option>';
      select.disabled = true;
    }

    select.addEventListener('change', () => {
      const option = select.selectedOptions?.[0];
      syncSubtitleSource(select.value, option?.textContent || '');
      const status = $('teacher-subtitle-status-1014');
      if (status && select.value) status.textContent = '已選擇影音教材，正在讀取既有字幕版本…';
    });
    return true;
  }

  function fallbackRevealMediaWorkspace() {
    const content = $('admin-section-content');
    const media = $('teacher-media-production-1014');
    if (!content || !media) return false;
    [...content.children].forEach(child => {
      if (child === media || child.classList.contains('hidden')) return;
      child.dataset.teacher1014HiddenByMedia = '1';
      child.classList.add('hidden');
    });
    media.classList.remove('hidden');
    const title = $('admin-workspace-title');
    const summary = $('admin-workspace-summary');
    const icon = $('admin-workspace-icon');
    if (icon) icon.textContent = '🎙️';
    if (title) title.textContent = '教材媒體製作 Workspace';
    if (summary) summary.textContent = '從既有教材建立講稿、語音、字幕與教學影片；正式發布仍使用原教材權限與範圍。';
    const url = new URL(window.location.href);
    url.searchParams.set('admin', '1');
    url.searchParams.set('persona', 'teacher');
    url.searchParams.set('workspace', 'course-materials');
    url.searchParams.set('teacherMode', 'media');
    window.history?.replaceState?.(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
    return true;
  }

  async function safeOpenMediaWorkspace() {
    try {
      const openMedia = window.TeacherWorkspace1014?.openMedia;
      if (typeof openMedia === 'function') await openMedia();
    } catch (_) {
      // Fall through to the local presentation-only recovery. Server RBAC remains unchanged.
    }
    if ($('teacher-media-production-1014')?.classList.contains('hidden')) fallbackRevealMediaWorkspace();
    await installPresentationPickers();
    await installSubtitlePicker();
  }

  function installMediaEntryRecovery() {
    if (document.documentElement.dataset.teacherMediaRecovery1017 === '1') return;
    document.documentElement.dataset.teacherMediaRecovery1017 = '1';
    document.addEventListener('click', event => {
      const button = event.target.closest?.('#teacher-course-media-entry-1014 button');
      if (!button) return;
      // The canonical entry owns its own click listener.  Only recover when
      // that owner was not installed; stopping propagation here used to block
      // the working handler and made this entry look frozen.
      if (typeof window.TeacherWorkspace1014?.openMedia === 'function') return;
      event.preventDefault();
      event.stopImmediatePropagation();
      void safeOpenMediaWorkspace();
    }, true);
  }

  async function installAll() {
    if (installing) return;
    installing = true;
    try {
      installMediaEntryRecovery();
      await installPresentationPickers();
      await installSubtitlePicker();
      const params = new URLSearchParams(window.location.search);
      if (params.get('teacherMode') === 'media' && $('teacher-media-production-1014')?.classList.contains('hidden')) {
        await safeOpenMediaWorkspace();
      }
    } finally {
      installing = false;
    }
  }

  void installAll();
  const observer = new MutationObserver(() => queueMicrotask(() => void installAll()));
  observer.observe(document.body, {childList:true, subtree:true});
  [300, 900, 1800].forEach(delay => setTimeout(() => void installAll(), delay));

  window.TeacherAuthoringSourceFix1017 = Object.freeze({
    loadMaterials,
    installPresentationPickers,
    installSubtitlePicker,
    safeOpenMediaWorkspace,
  });
})();
