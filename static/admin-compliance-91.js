/* 0091 · Read-only Training Compliance Matrix */
(() => {
  'use strict';

  let rows = [];
  const courseCatalog = new Map();
  const statusMeta = {
    complete: ['✅ 完成','text-emerald-700 bg-emerald-50 border-emerald-200'],
    overdue: ['🔴 逾期','text-rose-700 bg-rose-50 border-rose-200'],
    retraining: ['🟣 需重訓','text-violet-700 bg-violet-50 border-violet-200'],
    remediation: ['🟠 補強','text-amber-700 bg-amber-50 border-amber-200'],
    pending_review: ['🟡 待批改','text-amber-700 bg-amber-50 border-amber-200'],
    awaiting_exam: ['🔵 待考核','text-sky-700 bg-sky-50 border-sky-200'],
    in_progress: ['進行中','text-slate-600 bg-slate-50 border-slate-200'],
  };

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  const el = id => document.getElementById(id);
  const dateText = value => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value).slice(0,10) : date.toLocaleDateString('zh-TW');
  };
  const groupCatalog = () => window.AppCore?.groups || window.GROUPS || {};

  function populateGroups() {
    const select = el('admin-compliance-group');
    if (!select || select.dataset.ready === '1') return;
    const previous = select.value;
    select.innerHTML = '<option value="">全部組別</option>' + Object.entries(groupCatalog()).map(([key,item]) => `<option value="${esc(key)}">${esc(item.name || item.label || key)}</option>`).join('');
    select.value = previous;
    select.dataset.ready = '1';
  }

  function populateCourses() {
    const select = el('admin-compliance-course');
    if (!select) return;
    const previous = select.value;
    for (const item of rows) if (item.courseId) courseCatalog.set(item.courseId, item.courseTitle || item.courseId);
    select.innerHTML = '<option value="">全部課程</option>' + [...courseCatalog.entries()].sort((a,b) => String(a[1]).localeCompare(String(b[1]), 'zh-TW')).map(([id,title]) => `<option value="${esc(id)}">${esc(title)}</option>`).join('');
    if (courseCatalog.has(previous)) select.value = previous;
  }

  function examLabel(item) {
    if (!item.examRequired) return '不要求';
    if (item.examPassed) return '✅ 通過';
    if (item.examStatus === 'pending_review') return '⏳ 待批改';
    if (item.examStatus === 'remediation') return '🟠 補強';
    return '尚未通過';
  }

  function certificateLabel(item) {
    if (item.certificateStatus === 'current') return `✅ 有${item.certificateCount > 1 ? `（${item.certificateCount}）` : ''}`;
    if (item.certificateStatus === 'historical') return `歷史證明${item.certificateCount > 1 ? `（${item.certificateCount}）` : ''}`;
    return '—';
  }

  function renderSummary(summary = {}) {
    const mapping = {total:'total',complete:'complete',overdue:'overdue',retraining:'retraining',remediation:'remediation',awaitingExam:'awaiting',inProgress:'progress'};
    Object.entries(mapping).forEach(([key,id]) => { const node=el(`compliance-count-${id}`); if(node) node.textContent=String(summary[key] ?? 0); });
  }

  function renderRows() {
    const body = el('admin-compliance-body');
    const status = el('admin-compliance-status-text');
    if (!body) return;
    const q = (el('admin-compliance-search')?.value || '').trim().toLowerCase();
    const visible = q ? rows.filter(item => [item.name,item.empId,item.username,item.courseTitle].some(value => String(value || '').toLowerCase().includes(q))) : rows;
    if (status) status.textContent = `顯示 ${visible.length} 筆指派合規狀態；資料來自既有完成紀錄，不在本頁修改。`;
    body.innerHTML = visible.length ? visible.map(item => {
      const meta = statusMeta[item.status] || statusMeta.in_progress;
      return `<tr class="align-top"><td class="p-3"><div class="font-bold text-slate-900">${esc(item.name || item.username)}</div><div class="mt-0.5 text-[10px] text-slate-400">${esc(item.empId || item.username)} · ${esc((groupCatalog()[item.group] || {}).name || item.group || '')}</div></td><td class="p-3"><div class="font-bold text-slate-800">${esc(item.courseTitle)}</div><div class="mt-0.5 text-[10px] text-slate-400">${item.required ? '必修' : '選修／建議'}</div></td><td class="p-3 whitespace-nowrap">${esc(dateText(item.dueAt))}</td><td class="p-3 whitespace-nowrap">${Number(item.materialsCompleted || 0)} / ${Number(item.materialsTotal || 0)}</td><td class="p-3 whitespace-nowrap">${esc(examLabel(item))}</td><td class="p-3 whitespace-nowrap">${item.retrainingRequired ? '<span class="font-bold text-violet-700">需要</span>' : '—'}</td><td class="p-3 whitespace-nowrap">${esc(certificateLabel(item))}</td><td class="p-3"><span class="inline-flex rounded-full border px-2.5 py-1 text-[10px] font-bold ${meta[1]}">${meta[0]}</span></td></tr>`;
    }).join('') : '<tr><td colspan="8" class="p-6 text-center text-slate-400">目前沒有符合條件的訓練指派。</td></tr>';
  }

  function queryParams() {
    const params = new URLSearchParams();
    const values = {area:el('admin-compliance-area')?.value, group:el('admin-compliance-group')?.value, courseId:el('admin-compliance-course')?.value, status:el('admin-compliance-status')?.value};
    Object.entries(values).forEach(([key,value]) => { if(value) params.set(key,value); });
    return params;
  }

  async function renderTrainingCompliance(force=false) {
    populateGroups();
    const status = el('admin-compliance-status-text');
    if (status) status.textContent = '正在讀取訓練合規資料…';
    try {
      const res = await fetch('/api/training-compliance?' + queryParams().toString(), {credentials:'same-origin', cache:force ? 'reload' : 'no-store'});
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || '無法讀取訓練合規資料');
      rows = Array.isArray(data.rows) ? data.rows : [];
      renderSummary(data.summary || {});
      populateCourses();
      renderRows();
    } catch (error) {
      rows = [];
      renderSummary({});
      renderRows();
      if (status) status.textContent = `❌ ${error.message || '無法讀取訓練合規資料'}`;
    }
  }

  function bindUI() {
    const refresh = el('admin-compliance-refresh');
    if (refresh && refresh.dataset.bound !== '1') { refresh.dataset.bound='1'; refresh.addEventListener('click', () => renderTrainingCompliance(true)); }
    ['admin-compliance-area','admin-compliance-group','admin-compliance-course','admin-compliance-status'].forEach(id => {
      const node=el(id); if(node && node.dataset.bound !== '1'){node.dataset.bound='1';node.addEventListener('change',()=>renderTrainingCompliance(true));}
    });
    const search = el('admin-compliance-search');
    if (search && search.dataset.bound !== '1') { search.dataset.bound='1'; search.addEventListener('input', renderRows); }
  }

  window.renderTrainingCompliance = renderTrainingCompliance;
  window.AdminWorkspaceShell?.registerWorkspace('compliance', async ({switchSection}) => {
    await switchSection('compliance', true);
    bindUI();
    await renderTrainingCompliance(true);
  });
  window.TeacherRBAC681Ready?.then(() => {
    const user = window.TeacherRBAC681?.user || {};
    if (window.TeacherRBAC681?.scopedTeacher) {
      const area=el('admin-compliance-area');
      if(area){area.value=user.preferredArea || 'internal';area.disabled=true;}
    }
    bindUI();
  });
})();
