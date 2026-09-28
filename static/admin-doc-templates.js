/* Phase 3N: canonical document-template administration runtime. */
(() => {
  'use strict';

  let pendingUploadGroup = null;

  function ensurePaperRetentionGuide() {
    const panel = document.getElementById('admin-section-word');
    const workspace = panel?.querySelector('.admin-primary-workspace');
    if (!workspace) return;

    const eyebrow = workspace.querySelector('.admin-page-eyebrow');
    const heading = workspace.querySelector('h4');
    const description = heading?.parentElement?.querySelector('p.text-xs');
    const chip = workspace.querySelector('.admin-workspace-chip');
    if (eyebrow) eyebrow.textContent = 'DOCUMENT GOVERNANCE';
    if (heading) heading.textContent = '正式紙本文件範本';
    if (description) description.textContent = '此處只維護各組正式 .docx 範本與版本來源；老師日常輸出請從教師工作台「紙本文件與匯出」進行。';
    if (chip) chip.textContent = '範本維護 · 版本治理';

    if (document.getElementById('paper-retention-template-guide')) return;
    const details = document.createElement('details');
    details.id = 'paper-retention-template-guide';
    details.className = 'text-xs text-sky-900 bg-sky-50 border border-sky-100 rounded-xl p-3';
    details.innerHTML = `
      <summary class="cursor-pointer font-bold">查看紙本留存建議佔位字</summary>
      <div class="mt-2 space-y-2 leading-5">
        <p><b>文件追溯：</b> {documentTitle} 文件名稱、{documentReference} 紀錄識別碼、{documentVersion} 文件／考卷版本、{groupLabel} 組別、{quizTitle} 考核主題。</p>
        <p><b>時間與輸出：</b> {assessmentDate} 原始考核時間、{exportedAt} 輸出時間、{exportedBy} 輸出人、{paperStatus} 紙本狀態。</p>
        <p><b>簽核與歸檔：</b> {examineeSignature} 受評者簽名、{evaluatorSignature} 評核者簽名、{reviewSignature} 複核簽名、{signatureDate} 簽核日期、{archiveNumber} 歸檔編號、{archiveNote} 留存說明。</p>
        <p class="text-slate-500">這些欄位是新增的可選佔位字；既有 Word 範本沒有放入也不會影響原本匯出。</p>
      </div>`;
    workspace.appendChild(details);
  }

  async function renderTemplates() {
    ensurePaperRetentionGuide();
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
    const data = new FormData();
    data.append('file', file);
    try {
      const response = await fetch(`/api/doc-templates/${groupKey}`, {method:'POST',  body:data});
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
    const response = await fetch(`/api/doc-templates/${groupKey}`, {method:'DELETE', });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) { alert(result.error || '刪除失敗'); return; }
    await renderTemplates();
  }

  document.getElementById('admin-doc-template-upload-input')?.addEventListener('change', uploadTemplate);
  ensurePaperRetentionGuide();

  // Keep the existing HTML action contract; server-side session RBAC authorizes requests.
  window.renderAdminDocTemplates = renderTemplates;
  window.adminTriggerDocTemplateUpload = triggerUpload;
  window.adminDeleteDocTemplate = deleteTemplate;
})();
