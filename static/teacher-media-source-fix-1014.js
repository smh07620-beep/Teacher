/* Teacher media source picker reliability fix.
 * AI media authoring may use uploaded draft or published materials that the
 * current teacher can manage. Built-in legacy slide packs stay excluded because
 * they do not retain an AI-readable original source.
 */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  const preferredGroup = String(R.user?.preferredGroup || '').trim();
  const scopedTeacher = Boolean(R.scopedTeacher && preferredGroup);
  const groupCatalog = typeof GROUPS !== 'undefined' ? GROUPS : (window.GROUPS || {});
  let compatibleMaterials = [];
  let builtinCount = 0;
  let selectObserver = null;
  let repainting = false;

  const groupLabel = key => groupCatalog[key]?.label || groupCatalog[key]?.name || key || '未設定組別';
  const areaLabel = area => area === 'pgy' ? 'PGY' : (area === 'internal' ? '院內' : (area || ''));

  function setStatus(message, tone = 'normal') {
    const node = document.getElementById('teacher-script-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function scopedRows(rows) {
    const all = Array.isArray(rows) ? rows : [];
    builtinCount = all.filter(item => item?.isBuiltin).length;
    const uploaded = all.filter(item => item && !item.isBuiltin && item.id);
    const allowed = scopedTeacher
      ? uploaded.filter(item => String(item.group || '') === preferredGroup)
      : uploaded;
    return allowed.sort((a, b) => {
      const ga = String(a.group || '');
      const gb = String(b.group || '');
      if (ga !== gb) return ga.localeCompare(gb, 'zh-Hant');
      return String(a.title || a.filename || a.id).localeCompare(String(b.title || b.filename || b.id), 'zh-Hant');
    });
  }

  function paintFromCache(preserve = true) {
    const select = document.getElementById('teacher-script-material-1014');
    if (!select) return false;
    const previous = preserve ? select.value : '';
    repainting = true;
    select.replaceChildren();

    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = compatibleMaterials.length ? '選擇教材…' : '目前沒有可用的上傳教材';
    select.appendChild(placeholder);

    compatibleMaterials.forEach(item => {
      const option = document.createElement('option');
      option.value = String(item.id || '');
      const draft = item.active === false ? '［草稿］' : '';
      const group = groupLabel(String(item.group || ''));
      const area = areaLabel(String(item.area || ''));
      const title = item.title || item.filename || item.id;
      option.textContent = `${draft}${group}${area ? `・${area}` : ''}｜${title}`;
      select.appendChild(option);
    });

    if (previous && [...select.options].some(option => option.value === previous)) select.value = previous;
    const generate = document.getElementById('teacher-script-generate-1014');
    if (generate && !compatibleMaterials.length) generate.disabled = true;
    if (generate && compatibleMaterials.length && !generate.dataset.mediaBusy) generate.disabled = false;
    repainting = false;
    return true;
  }

  async function refreshMaterials() {
    const select = document.getElementById('teacher-script-material-1014');
    if (!select) return false;
    const previous = select.value;
    try {
      setStatus('正在讀取可製作媒體的教材…');
      const response = await fetch('/api/slides/admin', {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error(data.error || '無法讀取教材清單');
      compatibleMaterials = scopedRows(data);
      paintFromCache(false);
      if (previous && [...select.options].some(option => option.value === previous)) select.value = previous;

      if (!compatibleMaterials.length) {
        const legacy = builtinCount
          ? `目前另有 ${builtinCount} 份內建舊教材，但它們沒有保留原始文字來源，因此不能直接送 AI。`
          : '';
        setStatus(`目前沒有可供 AI 媒體製作的上傳教材。請先到「教材與課程」上傳 PDF、Word 或 PPT。${legacy}`, 'error');
      } else {
        const drafts = compatibleMaterials.filter(item => item.active === false).length;
        setStatus(`✅ 已載入 ${compatibleMaterials.length} 份教材${drafts ? `（含 ${drafts} 份草稿）` : ''}；可先製作講稿，正式發布仍走原教材審核流程。`, 'success');
      }
      return true;
    } catch (error) {
      compatibleMaterials = [];
      paintFromCache(false);
      setStatus(`教材清單讀取失敗：${error.message}`, 'error');
      return false;
    }
  }

  function installControls() {
    const select = document.getElementById('teacher-script-material-1014');
    if (!select) return false;
    if (select.dataset.mediaSourceFix === '1') return true;
    select.dataset.mediaSourceFix = '1';

    const help = document.createElement('div');
    help.className = 'mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500';
    const note = document.createElement('span');
    note.textContent = '可使用已上傳的 PDF／Word／PPT 教材；草稿也可先做講稿。內建舊教材因沒有原始文字來源不列入。';
    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.id = 'teacher-script-refresh-materials-1014';
    refresh.className = 'rounded-lg border border-slate-200 bg-white px-2 py-1 font-bold text-slate-600 hover:bg-slate-50';
    refresh.textContent = '↻ 重新整理教材';
    refresh.addEventListener('click', () => void refreshMaterials());
    help.append(note, refresh);
    select.insertAdjacentElement('afterend', help);

    selectObserver = new MutationObserver(() => {
      if (repainting || !compatibleMaterials.length) return;
      const expected = compatibleMaterials.length + 1;
      if (select.options.length !== expected) paintFromCache(true);
    });
    selectObserver.observe(select, {childList:true});

    // The original studio also loads this list. Refresh after it finishes so
    // draft materials are not accidentally removed by the older active-only filter.
    setTimeout(() => void refreshMaterials(), 50);
    setTimeout(() => {
      if (document.getElementById('teacher-script-material-1014')) void refreshMaterials();
    }, 1200);
    return true;
  }

  if (!installControls()) {
    const observer = new MutationObserver(() => {
      if (installControls()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.TeacherMediaSourceFix1014 = Object.freeze({ refreshMaterials });
})();
