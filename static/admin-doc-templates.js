/* Phase 3N: canonical document-template administration runtime. */
(() => {
  'use strict';

  let pendingUploadGroup = null;

  async function renderTemplates() {
    const box = document.getElementById('admin-doc-templates-list');
    if (!box) return;
    box.innerHTML = '<p class="text-xs text-slate-400">讀取範本設定中…</p>';
    try {
      const response = await fetch('/api/doc-templates');
      const list = await response.json();
      box.innerHTML = list.map(group => `
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border border-amber-200 rounded-xl p-2.5 bg-white">
          <div class="min-w-0">
            <span class="font-bold text-sm text-slate-800">${escapeHtml(group.label)}</span>
            ${group.exists
              ? `<span class="text-xs text-emerald-700 ml-2">✅ 已設定：${escapeHtml(group.filename)}（${escapeHtml(group.uploadedAt)}）</span><span class="text-[10px] text-slate-400 ml-2">${group.storageBackend === 'mega' ? '🟣 MEGA' : (group.storageBackend === 'oci' ? '🔴 Oracle' : (group.storageBackend === 'gdrive' ? '🟢 Google Drive' : (group.storageBackend === 'r2' ? '☁️ R2' : '💾 本機')))}</span>`
              : '<span class="text-xs text-slate-400 ml-2">尚未上傳範本</span>'}
          </div>
          <div class="flex gap-2 shrink-0">
            <button data-csp-click="adminTriggerDocTemplateUpload('${group.group}')" class="text-xs bg-amber-600 hover:bg-amber-500 text-white px-3 py-1.5 rounded-lg">⬆️ ${group.exists ? '重新上傳' : '上傳範本'}</button>
            ${group.exists ? `<a href="/api/doc-templates/${group.group}/download" target="_blank" class="text-xs bg-white border border-amber-300 hover:bg-amber-50 text-amber-800 px-3 py-1.5 rounded-lg">⬇️ 下載目前範本</a><button data-csp-click="adminDeleteDocTemplate('${group.group}')" class="text-[11px] bg-white border border-slate-200 hover:border-rose-200 text-slate-500 hover:text-rose-700 px-2.5 py-1.5 rounded-lg">更多：刪除</button>` : ''}
          </div>
        </div>`).join('');
    } catch (error) {
      box.innerHTML = `<p class="text-xs text-rose-500">❌ ${escapeHtml(error.message)}</p>`;
    }
  }

  function triggerUpload(groupKey) {
    pendingUploadGroup = groupKey;
    document.getElementById('admin-doc-template-upload-input')?.click();
  }

  async function uploadTemplate(event) {
    const input = event.target;
    const file = input.files[0];
    input.value = '';
    const groupKey = pendingUploadGroup;
    pendingUploadGroup = null;
    if (!file || !groupKey) return;
    const key = await getAdminKey();
    if (!key) return;
    const data = new FormData();
    data.append('file', file);
    try {
      const response = await fetch(`/api/doc-templates/${groupKey}`, {method:'POST', headers:{'X-Admin-Key':key}, body:data});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || '上傳失敗');
      alert(`✅ Word 範本格式檢查通過並已上傳（${Math.round((result.validation?.sizeBytes || 0) / 1024)} KB）`);
      await renderTemplates();
    } catch (error) {
      alert(`❌ ${error.message}`);
    }
  }

  async function deleteTemplate(groupKey) {
    if (!confirm('確定刪除此組別的 Word 匯出範本？')) return;
    const key = await getAdminKey();
    if (!key) return;
    const response = await fetch(`/api/doc-templates/${groupKey}`, {method:'DELETE', headers:{'X-Admin-Key':key}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) { alert(result.error || '刪除失敗'); return; }
    await renderTemplates();
  }

  document.getElementById('admin-doc-template-upload-input')?.addEventListener('change', uploadTemplate);

  // Keep the existing HTML onclick contract; authorization remains getAdminKey.
  window.renderAdminDocTemplates = renderTemplates;
  window.adminTriggerDocTemplateUpload = triggerUpload;
  window.adminDeleteDocTemplate = deleteTemplate;
})();
