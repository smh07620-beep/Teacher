/* Teacher 6.2 · Phase 3 PGY assignment / signature workflow UI */
(function () {
  'use strict';

  const C = window.AppCore || {};
  const esc = C.escapeHtml || ((value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char])));
  const api = C.api || (async (path, options = {}) => {
    const response = await fetch(path, { credentials: 'same-origin', ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  });

  const ROLE_LABELS = {
    student: '學員',
    clinical_teacher: '臨床教師',
    group_leader: '組長',
    education_admin: '教學管理者',
    system_admin: '系統管理者',
    auditor: '稽核／唯讀'
  };
  const STATUS_LABELS = {
    assigned: '已指派',
    submitted: '待教師簽核',
    teacher_signed: '待組長複核',
    group_countersigned: '待最終確認',
    finalized: '已完成',
    cancelled: '已取消'
  };
  const STATUS_ORDER = ['assigned', 'submitted', 'teacher_signed', 'group_countersigned', 'finalized'];

  const state = {
    user: null,
    assignments: [],
    audit: [],
    filter: 'all',
    group: 'grpBio'
  };

  const byId = (id) => document.getElementById(id);
  const role = () => state.user?.role || '';
  const area = () => typeof currentTrainingArea !== 'undefined'
    ? currentTrainingArea
    : (new URLSearchParams(location.search).get('area') || 'internal');
  const currentGroup = () => typeof currentGroupKey !== 'undefined'
    ? currentGroupKey
    : (new URLSearchParams(location.search).get('group') || 'grpBio');

  function canUseAssignments() {
    return ['student', 'clinical_teacher', 'group_leader', 'education_admin'].includes(role());
  }

  function canAudit() {
    return ['group_leader', 'education_admin', 'system_admin', 'auditor'].includes(role());
  }

  function statusLabel(status) {
    return STATUS_LABELS[status] || status || '未知';
  }

  function formatDate(value) {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleString('zh-TW', { hour12: false });
    } catch (_) {
      return String(value);
    }
  }

  function evidenceToText(evidence) {
    if (!evidence) return '';
    if (Array.isArray(evidence)) return evidence.map(String).join('\n');
    if (Array.isArray(evidence.items)) return evidence.items.map(String).join('\n');
    if (typeof evidence === 'object') {
      return Object.entries(evidence).map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join('\n');
    }
    return String(evidence);
  }

  function textToEvidence(text) {
    const items = String(text || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    return items.length ? { items } : {};
  }

  function roleHint() {
    const hints = {
      student: '填寫反思與佐證後送出；送出後內容鎖定，若要修改需由教學管理者退回。',
      clinical_teacher: '只會看到指派給你的學員；學員送出後才能進行臨床教師簽核。',
      group_leader: '只會看到自己組別；臨床教師簽核後才能複核。',
      education_admin: '可建立指派、最終確認、退回或取消；不可代替臨床教師或組長簽名。',
      system_admin: '可查看稽核紀錄，但不可代替臨床教師簽核。',
      auditor: '唯讀查看稽核軌跡，不可修改或簽核。'
    };
    return hints[role()] || '';
  }

  function showStatus(message, isError = false) {
    const box = byId('pgywf-status');
    if (!box) return;
    box.className = isError ? 'pgywf-error mt-3' : 'pgywf-note mt-3';
    box.textContent = message;
  }

  function clearStatus() {
    const box = byId('pgywf-status');
    if (!box) return;
    box.className = 'mt-3';
    box.textContent = '';
  }

  function ensureMount() {
    const panel = byId('panel-assessment');
    if (!panel || byId('pgy-workflow-center')) return;

    const section = document.createElement('section');
    section.id = 'pgy-workflow-center';
    section.className = 'pgywf-shell';
    section.innerHTML = `
      <div class="pgywf-toolbar">
        <div>
          <p class="edu-kicker">PGY ASSIGNMENT WORKFLOW</p>
          <h3 class="font-black text-lg text-slate-900 mt-1">📌 PGY 指派與簽核待辦</h3>
          <p id="pgywf-role-hint" class="text-xs text-slate-500 mt-1"></p>
        </div>
        <div class="pgywf-actions">
          <button id="pgywf-refresh" class="pgywf-btn">↻ 更新</button>
          <button id="pgywf-audit-btn" class="pgywf-btn pgywf-hidden">🧾 稽核紀錄</button>
        </div>
      </div>
      <div id="pgywf-status" class="mt-3"></div>
      <div id="pgywf-admin-create" class="mt-4"></div>
      <div id="pgywf-filterbar" class="mt-4"></div>
      <div id="pgywf-list" class="pgywf-grid mt-3"><div class="pgywf-loading">讀取 PGY 指派中…</div></div>
      <div id="pgywf-audit" class="pgywf-hidden mt-4"></div>
    `;
    panel.insertBefore(section, panel.children[1] || null);
    byId('pgywf-refresh').addEventListener('click', () => loadAll(true));
    byId('pgywf-audit-btn').addEventListener('click', toggleAudit);
  }

  function renderFilters() {
    const box = byId('pgywf-filterbar');
    if (!box || !canUseAssignments()) {
      if (box) box.innerHTML = '';
      return;
    }
    const counts = {};
    state.assignments.forEach((item) => {
      counts[item.status] = (counts[item.status] || 0) + 1;
    });
    const options = ['all', 'assigned', 'submitted', 'teacher_signed', 'group_countersigned', 'finalized', 'cancelled'];
    box.innerHTML = `<div class="pgywf-stats">${options.map((status) => {
      const label = status === 'all' ? '全部' : statusLabel(status);
      const count = status === 'all' ? state.assignments.length : (counts[status] || 0);
      const active = state.filter === status ? 'ring-2 ring-indigo-200' : '';
      return `<button class="pgywf-stat ${active}" data-pgywf-filter="${status}">${esc(label)} ${count}</button>`;
    }).join('')}</div>`;
    box.querySelectorAll('[data-pgywf-filter]').forEach((button) => {
      button.addEventListener('click', () => {
        state.filter = button.dataset.pgywfFilter;
        renderFilters();
        renderAssignments();
      });
    });
  }

  function stepper(assignment) {
    const index = assignment.status === 'cancelled' ? -1 : STATUS_ORDER.indexOf(assignment.status);
    const labels = ['學員送出', '教師簽核', '組長複核', '最終確認'];
    return `<div class="pgywf-stepper">${labels.map((label, step) => {
      const cls = index > step ? 'done' : (index === step ? 'active' : '');
      return `<div class="pgywf-step ${cls}">${step + 1}. ${esc(label)}</div>`;
    }).join('')}</div>`;
  }

  function signatureLine(signature, label) {
    if (!signature || !Object.keys(signature).length) return '';
    const time = signature.signedAt || signature.confirmedAt || '';
    return `<div class="pgywf-meta mt-1">${esc(label)}：${esc(signature.name || signature.username || '')} · ${esc(formatDate(time))}${signature.comment ? ` · ${esc(signature.comment)}` : ''}</div>`;
  }

  function studentEditor(assignment) {
    if (role() !== 'student' || assignment.status !== 'assigned') return '';
    return `
      <details class="mt-3" data-pgywf-editor="${esc(assignment.id)}">
        <summary class="text-xs font-black text-indigo-700 cursor-pointer">✍️ 填寫學習反思與佐證</summary>
        <div class="pgywf-form mt-3">
          <label class="text-xs font-bold">學習反思
            <textarea class="pgywf-input mt-1" rows="5" data-field="reflection">${esc(assignment.reflection || '')}</textarea>
          </label>
          <label class="text-xs font-bold">佐證（每行一項，可貼教材、文件或紀錄連結）
            <textarea class="pgywf-input mt-1" rows="4" data-field="evidence">${esc(evidenceToText(assignment.evidence))}</textarea>
          </label>
          <div class="pgywf-actions">
            <button class="pgywf-btn" data-action="save-student" data-id="${esc(assignment.id)}">💾 儲存草稿</button>
            <button class="pgywf-btn primary" data-action="submit" data-id="${esc(assignment.id)}">📨 送出給臨床教師</button>
          </div>
        </div>
      </details>`;
  }

  function actionButtons(assignment) {
    const buttons = [];
    if (role() === 'clinical_teacher' && assignment.status === 'submitted') {
      buttons.push(`<button class="pgywf-btn success" data-action="teacher-sign" data-id="${esc(assignment.id)}">✅ 教師簽核</button>`);
    }
    if (role() === 'group_leader' && assignment.status === 'teacher_signed') {
      buttons.push(`<button class="pgywf-btn success" data-action="countersign" data-id="${esc(assignment.id)}">✅ 組長複核</button>`);
    }
    if (role() === 'education_admin' && assignment.status === 'group_countersigned') {
      buttons.push(`<button class="pgywf-btn success" data-action="finalize" data-id="${esc(assignment.id)}">🏁 最終確認</button>`);
    }
    if (role() === 'education_admin' && ['submitted', 'teacher_signed', 'group_countersigned', 'finalized'].includes(assignment.status)) {
      buttons.push(`<button class="pgywf-btn warn" data-action="reopen" data-id="${esc(assignment.id)}">↩ 退回重開</button>`);
    }
    if (role() === 'education_admin' && !['finalized', 'cancelled'].includes(assignment.status)) {
      buttons.push(`<button class="pgywf-btn danger" data-action="cancel" data-id="${esc(assignment.id)}">取消指派</button>`);
    }
    if (canAudit()) {
      buttons.push(`<button class="pgywf-btn" data-action="audit-one" data-id="${esc(assignment.id)}">稽核</button>`);
    }
    return buttons.join('');
  }

  function assignmentCard(assignment) {
    const evidence = evidenceToText(assignment.evidence);
    return `
      <article class="pgywf-card" data-status="${esc(assignment.status)}">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div class="pgywf-title">${esc(assignment.title || 'PGY 訓練指派')}</div>
            <div class="pgywf-meta mt-1">學員：${esc(assignment.learnerName || assignment.learnerUsername)}（${esc(assignment.learnerEmpId || '')}） · 臨床教師：${esc(assignment.teacherName || assignment.teacherUsername)} · ${assignment.dueAt ? `期限 ${esc(formatDate(assignment.dueAt))}` : '未設定期限'}</div>
          </div>
          <span class="pgywf-badge">${esc(statusLabel(assignment.status))}</span>
        </div>
        ${assignment.instructions ? `<div class="pgywf-note mt-3"><b>任務說明：</b>${esc(assignment.instructions)}</div>` : ''}
        ${(assignment.reflection || evidence) ? `<details class="mt-3"><summary class="text-xs font-bold text-indigo-700 cursor-pointer">查看學員反思與佐證</summary>${assignment.reflection ? `<div class="pgywf-evidence"><b>反思</b>\n${esc(assignment.reflection)}</div>` : ''}${evidence ? `<div class="pgywf-evidence"><b>佐證</b>\n${esc(evidence)}</div>` : ''}</details>` : ''}
        ${studentEditor(assignment)}
        ${stepper(assignment)}
        ${signatureLine(assignment.teacherSignature, '臨床教師')}
        ${signatureLine(assignment.groupSignature, '組長')}
        ${signatureLine(assignment.finalConfirmation, '最終確認')}
        <div class="pgywf-actions">${actionButtons(assignment)}</div>
      </article>`;
  }

  function renderAssignments() {
    const box = byId('pgywf-list');
    if (!box) return;
    if (!canUseAssignments()) {
      box.innerHTML = '<div class="pgywf-note">此角色不參與臨床簽核流程；可使用「稽核紀錄」查看操作軌跡。</div>';
      return;
    }
    const list = state.assignments.filter((item) => state.filter === 'all' || item.status === state.filter);
    box.innerHTML = list.length ? list.map(assignmentCard).join('') : '<div class="pgywf-empty">目前沒有符合條件的 PGY 指派。</div>';
    box.querySelectorAll('[data-action]').forEach((button) => {
      button.addEventListener('click', () => handleAction(button.dataset.action, button.dataset.id));
    });
  }

  async function loadCandidatesAndCourses() {
    if (role() !== 'education_admin') return;
    const groupKey = byId('pgywf-create-group')?.value || state.group;
    try {
      const [candidates, courses] = await Promise.all([
        api(`/api/pgy/assignment-candidates?group=${encodeURIComponent(groupKey)}`),
        api(`/api/courses?area=pgy&group=${encodeURIComponent(groupKey)}`)
      ]);
      const studentSelect = byId('pgywf-create-student');
      const teacherSelect = byId('pgywf-create-teacher');
      const courseSelect = byId('pgywf-create-course');
      if (studentSelect) studentSelect.innerHTML = '<option value="">選擇學員</option>' + (candidates.students || []).map((item) => `<option value="${esc(item.username)}">${esc(item.name)}（${esc(item.empId)}）</option>`).join('');
      if (teacherSelect) teacherSelect.innerHTML = '<option value="">選擇臨床教師</option>' + (candidates.teachers || []).map((item) => `<option value="${esc(item.username)}">${esc(item.name)}（${esc(item.empId)}）</option>`).join('');
      if (courseSelect) courseSelect.innerHTML = '<option value="">未指定課程</option>' + (Array.isArray(courses) ? courses : []).map((item) => `<option value="${esc(item.id)}">${esc(item.title)}</option>`).join('');
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  function renderCreateForm() {
    const box = byId('pgywf-admin-create');
    if (!box) return;
    if (role() !== 'education_admin') {
      box.innerHTML = '';
      return;
    }
    const groups = Object.entries(C.groups || {}).filter(([key]) => key !== 'grpPgyDocs');
    box.innerHTML = `
      <details class="pgywf-admin-box" id="pgywf-create-details">
        <summary class="cursor-pointer font-black text-indigo-950">➕ 建立 PGY 學員／臨床教師指派</summary>
        <div class="pgywf-form mt-3">
          <div class="pgywf-form-grid">
            <label class="text-xs font-bold">組別<select id="pgywf-create-group" class="pgywf-input mt-1">${groups.map(([key, value]) => `<option value="${esc(key)}" ${key === state.group ? 'selected' : ''}>${esc(value.name || value.label || key)}</option>`).join('')}</select></label>
            <label class="text-xs font-bold">課程<select id="pgywf-create-course" class="pgywf-input mt-1"><option value="">未指定課程</option></select></label>
            <label class="text-xs font-bold">學員<select id="pgywf-create-student" class="pgywf-input mt-1"><option value="">選擇學員</option></select></label>
            <label class="text-xs font-bold">臨床教師<select id="pgywf-create-teacher" class="pgywf-input mt-1"><option value="">選擇臨床教師</option></select></label>
            <label class="text-xs font-bold">期限<input id="pgywf-create-due" type="datetime-local" class="pgywf-input mt-1"></label>
            <label class="text-xs font-bold">指派標題<input id="pgywf-create-title" class="pgywf-input mt-1" placeholder="可留白，使用課程名稱"></label>
          </div>
          <label class="text-xs font-bold">任務說明<textarea id="pgywf-create-instructions" rows="3" class="pgywf-input mt-1" placeholder="需完成的教材、技能、案例或佐證"></textarea></label>
          <div><button id="pgywf-create-submit" class="pgywf-btn primary">建立指派</button></div>
        </div>
      </details>`;
    byId('pgywf-create-group').addEventListener('change', (event) => {
      state.group = event.target.value;
      loadCandidatesAndCourses();
    });
    byId('pgywf-create-submit').addEventListener('click', createAssignment);
    loadCandidatesAndCourses();
  }

  async function createAssignment() {
    const payload = {
      area: 'pgy',
      group: byId('pgywf-create-group')?.value || state.group,
      courseId: byId('pgywf-create-course')?.value || '',
      learnerUsername: byId('pgywf-create-student')?.value || '',
      teacherUsername: byId('pgywf-create-teacher')?.value || '',
      dueAt: byId('pgywf-create-due')?.value || '',
      title: byId('pgywf-create-title')?.value || '',
      instructions: byId('pgywf-create-instructions')?.value || ''
    };
    if (!payload.learnerUsername || !payload.teacherUsername) {
      showStatus('請選擇學員與臨床教師。', true);
      return;
    }
    try {
      await api('/api/pgy/assignments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      showStatus('✅ PGY 指派已建立。');
      state.group = payload.group;
      await loadAssignments();
      const details = byId('pgywf-create-details');
      if (details) details.open = false;
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  function getStudentEditor(assignmentId) {
    const editor = document.querySelector(`[data-pgywf-editor="${CSS.escape(assignmentId)}"]`);
    if (!editor) return null;
    return {
      reflection: editor.querySelector('[data-field="reflection"]')?.value || '',
      evidence: editor.querySelector('[data-field="evidence"]')?.value || ''
    };
  }

  async function saveStudentDraft(assignment, submitAfterSave) {
    const editor = getStudentEditor(assignment.id);
    if (!editor) return;
    try {
      await api(`/api/pgy/assignments/${encodeURIComponent(assignment.id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reflection: editor.reflection,
          evidence: textToEvidence(editor.evidence)
        })
      });
      if (submitAfterSave) {
        if (!editor.reflection.trim() && !editor.evidence.trim()) {
          throw new Error('送出前至少需填寫反思或佐證內容。');
        }
        if (!window.confirm('送出後學員內容會鎖定，確認送出給臨床教師？')) return;
        await api(`/api/pgy/assignments/${encodeURIComponent(assignment.id)}/submit`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
        showStatus('✅ 已送出給臨床教師。');
      } else {
        showStatus('✅ 草稿已儲存。');
      }
      await loadAssignments();
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  async function workflowAction(assignment, action) {
    const config = {
      'teacher-sign': { path: 'teacher-sign', prompt: '教師回饋（選填）', required: false, key: 'comment', label: '臨床教師簽核' },
      countersign: { path: 'countersign', prompt: '組長複核意見（選填）', required: false, key: 'comment', label: '組長複核' },
      finalize: { path: 'finalize', prompt: '最終確認意見（選填）', required: false, key: 'comment', label: '最終確認' },
      reopen: { path: 'reopen', prompt: '請填寫退回原因', required: true, key: 'reason', label: '退回重開' },
      cancel: { path: 'cancel', prompt: '請填寫取消原因', required: true, key: 'reason', label: '取消指派' }
    }[action];
    if (!config) return;

    const comment = window.prompt(config.prompt, '');
    if (comment === null) return;
    if (config.required && !comment.trim()) {
      showStatus('此操作必須填寫原因。', true);
      return;
    }
    if (!window.confirm(`確認執行「${config.label}」？`)) return;

    try {
      await api(`/api/pgy/assignments/${encodeURIComponent(assignment.id)}/${config.path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [config.key]: comment.trim() })
      });
      showStatus(`✅ ${config.label}完成。`);
      await loadAssignments();
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  function handleAction(action, assignmentId) {
    const assignment = state.assignments.find((item) => item.id === assignmentId);
    if (!assignment) return;
    if (action === 'save-student') return saveStudentDraft(assignment, false);
    if (action === 'submit') return saveStudentDraft(assignment, true);
    if (action === 'audit-one') return showAudit(assignment.id);
    return workflowAction(assignment, action);
  }

  async function loadAssignments() {
    if (!canUseAssignments()) {
      state.assignments = [];
      renderFilters();
      renderAssignments();
      return;
    }
    const params = new URLSearchParams();
    if (role() === 'education_admin' && state.group) params.set('group', state.group);
    const result = await api(`/api/pgy/assignments${params.toString() ? `?${params}` : ''}`);
    state.assignments = Array.isArray(result) ? result : [];
    renderFilters();
    renderAssignments();
  }

  async function loadAudit(assignmentId = '') {
    if (!canAudit()) return;
    const result = await api(`/api/pgy/audit${assignmentId ? `?assignmentId=${encodeURIComponent(assignmentId)}` : ''}`);
    state.audit = Array.isArray(result) ? result : [];
    renderAudit(assignmentId);
  }

  function renderAudit(assignmentId = '') {
    const box = byId('pgywf-audit');
    if (!box) return;
    box.classList.remove('pgywf-hidden');
    box.innerHTML = `
      <div class="pgywf-card">
        <div class="pgywf-toolbar">
          <div><div class="pgywf-title">🧾 ${assignmentId ? '此指派' : 'PGY'}稽核紀錄</div><div class="pgywf-meta mt-1">建立、修改、送出、簽核、複核、最終確認、退回與取消皆會留存。</div></div>
          <button id="pgywf-audit-close" class="pgywf-btn">收合</button>
        </div>
        <div class="mt-3">${state.audit.length ? state.audit.map((item) => `
          <div class="pgywf-audit-row">
            <div>${esc(formatDate(item.createdAt))}</div>
            <div><b>${esc(item.action)}</b><br>${esc(ROLE_LABELS[item.actorRole] || item.actorRole)}</div>
            <div>${esc(item.title || item.assignmentId)}<br><span class="text-slate-400">${esc(item.actorUsername)} · ${esc(item.fromStatus || '—')} → ${esc(item.toStatus || '—')}</span>${item.detail && Object.keys(item.detail).length ? `<div class="text-slate-500 mt-1">${esc(JSON.stringify(item.detail))}</div>` : ''}</div>
          </div>`).join('') : '<div class="pgywf-empty">目前沒有稽核紀錄。</div>'}</div>
      </div>`;
    byId('pgywf-audit-close').addEventListener('click', () => box.classList.add('pgywf-hidden'));
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  async function showAudit(assignmentId) {
    try {
      await loadAudit(assignmentId);
    } catch (error) {
      showStatus(error.message, true);
    }
  }

  async function toggleAudit() {
    const box = byId('pgywf-audit');
    if (!box) return;
    if (!box.classList.contains('pgywf-hidden')) {
      box.classList.add('pgywf-hidden');
      return;
    }
    await showAudit('');
  }

  async function loadAll(forceAuth = false) {
    if (area() !== 'pgy') return;
    clearStatus();
    state.group = currentGroup();
    try {
      if (!state.user || forceAuth) {
        state.user = C.getCurrentUser
          ? await C.getCurrentUser()
          : await api('/api/auth/me').then((result) => result.authenticated ? result.user : null);
      }
      const hint = byId('pgywf-role-hint');
      if (hint) hint.textContent = `目前身分：${ROLE_LABELS[role()] || role() || '未登入'}。${roleHint()}`;
      const auditButton = byId('pgywf-audit-btn');
      if (auditButton) auditButton.classList.toggle('pgywf-hidden', !canAudit());
      renderCreateForm();
      await loadAssignments();
      if (['system_admin', 'auditor'].includes(role()) && canAudit()) await loadAudit();
    } catch (error) {
      const list = byId('pgywf-list');
      if (list) list.innerHTML = `<div class="pgywf-error">${esc(error.message || 'PGY 指派載入失敗')}</div>`;
    }
  }

  async function init() {
    if (area() !== 'pgy') return;
    ensureMount();
    await loadAll(false);
  }

  window.PgyWorkflowUI = {
    reload: () => loadAll(true),
    showAudit
  };

  window.addEventListener('DOMContentLoaded', () => setTimeout(init, 30));
})();
