/* Teacher 10/14: official SOP Word template management inside paper-record workflow. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const canManage = typeof R.hasPermission === 'function' && R.hasPermission('template.manage');
  const user = R.user || {};
  let rows = [];

  function preferredGroup() {
    return String(user.preferredGroup || user.preferred_group || '').trim();
  }

  function status(message, tone = 'normal') {
    const node = document.getElementById('teacher-paper-template-status-1014');
    if (!node) return;
    node.textContent = message;
    node.className = tone === 'error'
      ? 'text-xs font-bold text-rose-700'
      : tone === 'success'
        ? 'text-xs font-bold text-emerald-700'
        : 'text-xs text-slate-600';
  }

  function selectedRow() {
    const group = document.getElementById('teacher-paper-template-group-1014')?.value || preferredGroup();
    return rows.find(row => String(row.group) === String(group)) || null;
  }

  function paint() {
    const select = document.getElementById('teacher-paper-template-group-1014');
    const upload = document.getElementById('teacher-paper-template-upload-1014');
    const download = document.getElementById('teacher-paper-template-download-1014');
    if (!select || !upload || !download) return;
    const preferred = preferredGroup();
    const shown = canManage ? rows : rows.filter(row => String(row.group) === preferred);
    const choices = shown.length ? shown : rows.slice(0, 1);
    const previous = select.value;
    select.replaceChildren(...choices.map(row => {
      const option = document.createElement('option');
      option.value = row.group || '';
      option.textContent = row.label || row.group || '';
      return option;
    }));
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
    else if ([...select.options].some(option => option.value === preferred)) select.value = preferred;
    select.disabled = choices.length <= 1;
    upload.classList.toggle('hidden', !canManage);
    upload.disabled = !canManage;

    const row = selectedRow();
    if (row?.exists) {
      download.href = `/api/doc-templates/${encodeURIComponent(row.group)}/download`;
      download.classList.remove('hidden');
      status(`目前範本：${row.filename || '正式 Word 範本'}${row.uploadedAt ? `｜更新 ${row.uploadedAt}` : ''}。下方「匯出 Word」會自動套用此組範本。`, 'success');
    } else {
      download.removeAttribute('href');
      download.classList.add('hidden');
      status(canManage
        ? '此組尚未匯入正式 SOP Word 範本；請先匯入 .docx。'
        : '此組尚未設定正式 SOP Word 範本；請由系統管理者匯入。', canManage ? 'normal' : 'error');
    }
  }

  async function load() {
    if (!document.getElementById('teacher-paper-template-manager-1014')) return;
    status('讀取正式 SOP Word 範本設定中…');
    try {
      const response = await fetch('/api/doc-templates', {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => []);
      if (!response.ok) throw new Error(data.error || '無法讀取 Word 範本設定');
      rows = Array.isArray(data) ? data : [];
      paint();
    } catch (error) {
      rows = [];
      status(`範本設定讀取失敗：${error.message}`, 'error');
    }
  }

  async function upload(event) {
    const input = event.target;
    const file = input?.files?.[0];
    if (input) input.value = '';
    if (!file || !canManage) return;
    const row = selectedRow();
    if (!row?.group) return status('請先選擇組別。', 'error');
    if (!String(file.name || '').toLowerCase().endsWith('.docx')) return status('正式紙本範本僅接受 .docx 檔案。', 'error');
    const form = new FormData();
    form.append('file', file);
    status(`正在檢查並匯入「${file.name}」…`);
    try {
      const response = await fetch(`/api/doc-templates/${encodeURIComponent(row.group)}`, {
        method:'POST', credentials:'same-origin', body:form
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Word 範本匯入失敗');
      status('✅ 正式 SOP Word 範本已更新；之後此組匯出會自動套用。', 'success');
      await load();
    } catch (error) {
      status(`範本匯入失敗：${error.message}`, 'error');
    }
  }

  function install() {
    const paper = document.getElementById('teacher-paper-documents');
    if (!paper || document.getElementById('teacher-paper-template-manager-1014')) return !!paper;
    const section = document.createElement('section');
    section.id = 'teacher-paper-template-manager-1014';
    section.className = 'rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4 space-y-3';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div><h5 class="text-sm font-black text-indigo-950">📎 正式 SOP Word 範本</h5><p class="mt-1 text-xs leading-5 text-indigo-800">匯入科內核准的 .docx 表單範本；下方正式考核紀錄按「匯出 Word」時會依組別自動套用。更換範本不會改動既有電子考核紀錄。</p></div>
        <div class="flex flex-wrap items-center gap-2">
          <select id="teacher-paper-template-group-1014" class="rounded-xl border border-indigo-200 bg-white px-3 py-2 text-xs font-bold text-slate-700" aria-label="正式 Word 範本組別"></select>
          <button id="teacher-paper-template-upload-1014" type="button" class="rounded-xl bg-indigo-700 px-4 py-2 text-xs font-black text-white disabled:opacity-40">⬆️ 匯入／更換 SOP Word 範本</button>
          <a id="teacher-paper-template-download-1014" class="hidden rounded-xl border border-indigo-200 bg-white px-4 py-2 text-xs font-black text-indigo-700" target="_blank" rel="noopener">⬇️ 下載目前範本</a>
          <input id="teacher-paper-template-file-1014" class="hidden" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
        </div>
      </div>
      <p id="teacher-paper-template-status-1014" class="text-xs text-slate-600">讀取正式 SOP Word 範本設定中…</p>`;
    const steps = paper.querySelector('.grid.sm\\:grid-cols-2.xl\\:grid-cols-4');
    if (steps) paper.insertBefore(section, steps);
    else paper.appendChild(section);
    section.querySelector('#teacher-paper-template-group-1014')?.addEventListener('change', paint);
    section.querySelector('#teacher-paper-template-upload-1014')?.addEventListener('click', () => document.getElementById('teacher-paper-template-file-1014')?.click());
    section.querySelector('#teacher-paper-template-file-1014')?.addEventListener('change', upload);
    void load();
    return true;
  }

  if (!install()) {
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.TeacherPaperTemplateManager1014 = Object.freeze({ load, paint });
})();
