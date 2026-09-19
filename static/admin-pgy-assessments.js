/* Phase 3O: canonical PGY assessment administration runtime.
 * This module owns the admin-side onclick entry points. */
(() => {
  'use strict';

  let pendingTemplateType = '';

  function templateTypes() {
    return typeof PGY_ASSESSMENT_ACTIVE_TYPES === 'undefined' ? [] : PGY_ASSESSMENT_ACTIVE_TYPES;
  }

  function assessmentConfig(type) {
    return typeof PGY_ASSESSMENT_CONFIG === 'undefined' ? {} : (PGY_ASSESSMENT_CONFIG[type] || {});
  }

  async function renderTemplates() {
    const box = document.getElementById('admin-pgy-template-list');
    if (!box) return;
    box.innerHTML = '<p class="text-xs text-slate-400">讀取範本中…</p>';
    try {
      const response = await fetch('/api/pgy-assessment-templates');
      const list = await response.json();
      box.innerHTML = templateTypes().map(type => {
        const template = list.find(item => item.templateType === type);
        const title = assessmentConfig(type).title || type;
        return `<div class="border border-indigo-100 rounded-xl p-3 bg-white"><div class="font-black text-sm text-slate-800">${escapeHtml(title)}</div><div class="text-[11px] text-slate-500 mt-1">${template ? '✅ ' + escapeHtml(template.filename) : '尚未上傳 Word/PDF 範本'} · 僅接受有效 DOCX/PDF，大小上限由後端檢查</div><div class="flex flex-wrap gap-2 mt-3"><button data-csp-click="adminTriggerPgyTemplateUpload('${type}')" class="text-xs bg-indigo-700 text-white px-3 py-1.5 rounded-lg">⬆️ ${template ? '重新上傳' : '上傳範本'}</button>${template ? `<a href="/api/pgy-assessment-templates/${type}/download" target="_blank" class="text-xs border border-indigo-200 px-3 py-1.5 rounded-lg">⬇️ 開啟／下載</a><button data-csp-click="adminDeletePgyTemplate('${type}')" class="text-[11px] border border-slate-200 text-slate-500 hover:text-rose-700 px-2 py-1.5 rounded-lg">更多：刪除</button>` : ''}</div></div>`;
      }).join('');
    } catch (error) {
      box.innerHTML = `<p class="text-xs text-rose-500">${escapeHtml(error.message)}</p>`;
    }
  }

  function triggerTemplateUpload(type) {
    pendingTemplateType = type;
    document.getElementById('admin-pgy-template-upload-input')?.click();
  }

  async function uploadTemplate(event) {
    const input = event.target;
    const file = input.files[0];
    input.value = '';
    const type = pendingTemplateType;
    pendingTemplateType = '';
    if (!file || !type) return;
    const key = await getAdminKey();
    if (!key) return;
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`/api/pgy-assessment-templates/${type}`, {method:'POST', headers:{'X-Admin-Key':key}, body:formData});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) { alert('❌ ' + (result.error || '上傳失敗')); return; }
    alert(`✅ 範本檢查通過並已上傳（${result.validation?.kind?.toUpperCase?.() || '檔案'}，${Math.round((result.validation?.sizeBytes || 0) / 1024)} KB）`);
    await renderTemplates();
  }

  async function deleteTemplate(type) {
    if (!confirm('確定刪除此 PGY 評量範本？')) return;
    const key = await getAdminKey();
    if (!key) return;
    const response = await fetch(`/api/pgy-assessment-templates/${type}`, {method:'DELETE', headers:{'X-Admin-Key':key}});
    if (!response.ok) { alert('刪除失敗'); return; }
    await renderTemplates();
  }

  async function importTslmEpa() {
    const key = await getAdminKey();
    if (!key) return;
    const response = await fetch('/api/pgy-assessment-templates/import-tslm-epa', {method:'POST', headers:{'X-Admin-Key':key}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) { alert(result.error || '匯入失敗'); return; }
    alert('已將台灣醫事檢驗學會 EPA 公版參考匯入院內範本庫');
    await renderTemplates();
  }

  async function renderAssessments() {
    const box = document.getElementById('admin-pgy-records');
    if (!box) return;
    const key = await getAdminKey();
    if (!key) return;
    box.innerHTML = '<p class="text-xs text-slate-400">讀取評量紀錄中…</p>';
    const response = await fetch('/api/pgy-assessments', {headers:{'X-Admin-Key':key}});
    const list = await response.json().catch(() => []);
    box.innerHTML = (list || []).length ? list.slice(0, 100).map(item => {
      const group = GROUPS[item.group] || GROUPS.grpBio;
      const title = assessmentConfig(item.assessmentType).title || item.title;
      return `<div class="border border-slate-200 rounded-xl p-3 flex flex-col lg:flex-row lg:items-center justify-between gap-2"><div><div class="font-bold text-sm text-slate-800">${escapeHtml(item.name)}｜${escapeHtml(title)}</div><div class="text-[11px] text-slate-500 mt-1">${escapeHtml(item.assessmentDate)}・${escapeHtml(group.name)}・${escapeHtml(item.empId)}・評估者 ${escapeHtml(item.evaluatorName)}</div></div><span class="text-xs font-bold px-3 py-1 rounded-full bg-indigo-50 text-indigo-700">${Number(item.overallScore || 0).toFixed(1)} / 5</span></div>`;
    }).join('') : '<p class="text-xs text-slate-400">尚無 PGY 評量紀錄</p>';
  }

  document.getElementById('admin-pgy-template-upload-input')?.addEventListener('change', uploadTemplate);

  window.renderAdminPgyTemplates = renderTemplates;
  window.adminTriggerPgyTemplateUpload = triggerTemplateUpload;
  window.adminDeletePgyTemplate = deleteTemplate;
  window.adminImportTslmEpa = importTslmEpa;
  window.renderAdminPgyAssessments = renderAssessments;
})();
