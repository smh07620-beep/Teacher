/* 0092 · People × training competency matrix. */
(() => {
  'use strict';

  let matrixRows = [];
  let matrixMode = false;
  let selectedEvidenceKey = '';

  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const groups = () => window.AppCore?.groups || window.GROUPS || {};
  const dateText = value => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : date.toLocaleDateString('zh-TW');
  };

  const qualificationMeta = {
    untrained: ['⚪ 未訓練', 'border-slate-200 bg-white text-slate-500'],
    training: ['🔵 訓練中', 'border-sky-200 bg-sky-50 text-sky-700'],
    awaiting_assessment: ['🟦 待考核', 'border-blue-200 bg-blue-50 text-blue-700'],
    pending_review: ['🟡 待評核', 'border-amber-200 bg-amber-50 text-amber-700'],
    passed: ['✅ 已通過', 'border-emerald-200 bg-emerald-50 text-emerald-700'],
    overdue: ['🔴 已逾期', 'border-rose-200 bg-rose-50 text-rose-700'],
    retraining: ['🟣 需重訓', 'border-violet-200 bg-violet-50 text-violet-700'],
    remediation: ['🟠 需補強', 'border-orange-200 bg-orange-50 text-orange-700'],
  };

  function queryParams() {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries({
      area: el('admin-compliance-area')?.value,
      group: el('admin-compliance-group')?.value,
      courseId: el('admin-compliance-course')?.value,
    })) {
      if (value) params.set(key, value);
    }
    return params;
  }

  function qualificationStatus(item) {
    if (qualificationMeta[item?.qualificationStatus]) return item.qualificationStatus;
    if (!item) return '';
    if (item.status === 'complete') return 'passed';
    if (item.status === 'pending_review') return 'pending_review';
    if (item.status === 'awaiting_exam') return 'awaiting_assessment';
    if (item.status === 'overdue') return 'overdue';
    if (item.status === 'retraining') return 'retraining';
    if (item.status === 'remediation') return 'remediation';
    if (Number(item.materialsCompleted || 0) <= 0 && ['not_started','not_required',''].includes(String(item.examStatus || ''))) return 'untrained';
    return 'training';
  }

  function pivot(rows) {
    const abilities = new Map();
    const people = new Map();
    for (const item of rows) {
      const courseId = String(item.courseId || '');
      const username = String(item.username || '').toLowerCase();
      if (!courseId || !username) continue;
      if (!abilities.has(courseId)) {
        abilities.set(courseId, {id:courseId, title:item.courseTitle || courseId, group:item.group || ''});
      }
      if (!people.has(username)) {
        people.set(username, {
          username,
          name:item.name || username,
          empId:item.empId || '',
          group:item.group || '',
          role:item.role || '',
          cells:{},
        });
      }
      people.get(username).cells[courseId] = item;
    }
    return {
      abilities:[...abilities.values()].sort((a,b) => String(a.title).localeCompare(String(b.title), 'zh-TW')),
      people:[...people.values()].sort((a,b) => `${a.group}|${a.name}|${a.empId}`.localeCompare(`${b.group}|${b.name}|${b.empId}`, 'zh-TW')),
    };
  }

  function ensureMatrixTools() {
    const view = el('admin-competency-matrix-view');
    const summary = el('admin-competency-matrix-summary');
    if (!view || !summary) return;

    if (!el('admin-competency-matrix-tools')) {
      const tools = document.createElement('div');
      tools.id = 'admin-competency-matrix-tools';
      tools.className = 'grid sm:grid-cols-2 xl:grid-cols-4 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3';
      tools.innerHTML = `
        <label class="text-xs font-bold text-slate-600">能力狀態
          <select id="admin-competency-status-filter" class="learning-input mt-1">
            <option value="">全部能力狀態</option>
            <option value="untrained">未訓練</option>
            <option value="training">訓練中</option>
            <option value="awaiting_assessment">待考核</option>
            <option value="pending_review">待評核</option>
            <option value="passed">已通過</option>
            <option value="overdue">已逾期</option>
            <option value="retraining">需重訓</option>
            <option value="remediation">需補強</option>
          </select>
        </label>
        <label class="text-xs font-bold text-slate-600">顯示範圍
          <select id="admin-competency-display-filter" class="learning-input mt-1">
            <option value="all">全部已指派項目</option>
            <option value="gaps">只顯示待完成／異常</option>
            <option value="passed">只顯示已通過</option>
          </select>
        </label>
        <div class="sm:col-span-2 flex items-end gap-2">
          <p class="text-[11px] leading-5 text-slate-500">上方既有「訓練區／組別／課程／搜尋」仍可一起使用；矩陣篩選只影響人員 × 能力檢視，不改寫任何資格或學習紀錄。</p>
          <button id="admin-competency-clear-filters" type="button" class="admin-toolbar-button shrink-0">清除矩陣篩選</button>
        </div>`;
      view.insertBefore(tools, summary);
    }

    if (!el('admin-competency-evidence-panel')) {
      const panel = document.createElement('section');
      panel.id = 'admin-competency-evidence-panel';
      panel.className = 'hidden rounded-xl border border-teal-200 bg-white p-4 shadow-sm';
      panel.setAttribute('aria-live', 'polite');
      view.appendChild(panel);
    }
  }

  function itemMatchesFilters(item) {
    if (!item) return false;
    const status = qualificationStatus(item);
    const wantedStatus = el('admin-competency-status-filter')?.value || '';
    const display = el('admin-competency-display-filter')?.value || 'all';
    if (wantedStatus && status !== wantedStatus) return false;
    if (display === 'gaps' && status === 'passed') return false;
    if (display === 'passed' && status !== 'passed') return false;
    return true;
  }

  function evidenceKey(item) {
    return `${String(item?.username || '').toLowerCase()}::${String(item?.courseId || '')}`;
  }

  function cellHtml(item) {
    if (!item) return '<span class="text-slate-300">—</span>';
    if (!itemMatchesFilters(item)) return '<span class="text-slate-200">·</span>';
    const status = qualificationStatus(item);
    const meta = qualificationMeta[status] || qualificationMeta.training;
    const evidence = [
      `教材 ${Number(item.materialsCompleted || 0)}/${Number(item.materialsTotal || 0)}`,
      item.examRequired ? (item.examPassed ? '考核已通過' : '考核尚未通過') : '無指定考核',
      item.retrainingRequired ? '需重新訓練' : '',
      item.certificateStatus === 'current' ? '有目前有效完訓證明' : '',
      '點選查看評核證據',
    ].filter(Boolean).join('；');
    const selected = selectedEvidenceKey === evidenceKey(item);
    return `<button type="button" data-competency-cell="1" data-username="${esc(item.username)}" data-course-id="${esc(item.courseId)}" title="${esc(evidence)}" aria-label="${esc((item.name || item.username) + '，' + item.courseTitle + '，' + meta[0] + '，查看評核證據')}" class="inline-flex min-w-[88px] justify-center rounded-full border px-2 py-1 text-[10px] font-bold transition ${meta[1]} ${selected ? 'ring-2 ring-teal-500 ring-offset-1' : 'hover:ring-2 hover:ring-slate-200'}">${meta[0]}</button>`;
  }

  function visibleData() {
    const data = pivot(matrixRows);
    const query = (el('admin-compliance-search')?.value || '').trim().toLowerCase();
    let people = data.people;
    let abilities = data.abilities;

    if (query) {
      const personMatches = data.people.filter(person => [
        person.name,
        person.empId,
        person.username,
        (groups()[person.group] || {}).name,
        person.group,
      ].some(value => String(value || '').toLowerCase().includes(query)));
      const abilityMatches = data.abilities.filter(ability => [
        ability.title,
        (groups()[ability.group] || {}).name,
        ability.group,
      ].some(value => String(value || '').toLowerCase().includes(query)));
      if (personMatches.length) {
        people = personMatches;
      } else if (abilityMatches.length) {
        abilities = abilityMatches;
      } else {
        people = [];
      }
    }

    abilities = abilities.filter(ability => people.some(person => itemMatchesFilters(person.cells[ability.id])));
    people = people.filter(person => abilities.some(ability => itemMatchesFilters(person.cells[ability.id])));
    return {people, abilities};
  }

  function renderMatrix() {
    ensureMatrixTools();
    const host = el('admin-competency-matrix-table');
    const summary = el('admin-competency-matrix-summary');
    if (!host) return;

    const data = visibleData();
    const visibleItems = [];
    for (const person of data.people) {
      for (const ability of data.abilities) {
        const item = person.cells[ability.id];
        if (itemMatchesFilters(item)) visibleItems.push(item);
      }
    }
    const passed = visibleItems.filter(item => qualificationStatus(item) === 'passed').length;
    const gaps = visibleItems.length - passed;
    if (summary) {
      summary.textContent = `顯示 ${data.people.length} 位人員 × ${data.abilities.length} 個能力項目；目前篩選範圍共 ${visibleItems.length} 個已指派項目，已通過 ${passed}、待完成／異常 ${gaps}。`;
    }

    if (!data.people.length || !data.abilities.length) {
      host.innerHTML = '<div class="p-6 text-center text-xs text-slate-400">目前沒有符合搜尋或能力狀態篩選的正式課程指派。</div>';
      if (selectedEvidenceKey && !matrixRows.some(item => evidenceKey(item) === selectedEvidenceKey)) clearEvidence();
      return;
    }

    host.innerHTML = `<table class="min-w-max w-full text-left text-xs">
      <thead class="bg-slate-50 text-slate-700"><tr>
        <th class="sticky left-0 z-10 min-w-[190px] border-b border-r border-slate-200 bg-slate-50 p-3">人員</th>
        ${data.abilities.map(ability => `<th class="min-w-[138px] border-b border-slate-200 p-3 text-center"><div class="font-bold text-slate-800">${esc(ability.title)}</div><div class="mt-0.5 text-[9px] font-normal text-slate-400">${esc((groups()[ability.group] || {}).name || ability.group || '')}</div></th>`).join('')}
      </tr></thead>
      <tbody>${data.people.map(person => `<tr>
        <td class="sticky left-0 z-[1] border-b border-r border-slate-100 bg-white p-3"><div class="font-bold text-slate-900">${esc(person.name || person.username)}</div><div class="mt-0.5 text-[9px] text-slate-400">${esc(person.empId || person.username)} · ${esc((groups()[person.group] || {}).name || person.group || '')}</div></td>
        ${data.abilities.map(ability => `<td class="border-b border-slate-100 bg-white p-2 text-center">${cellHtml(person.cells[ability.id])}</td>`).join('')}
      </tr>`).join('')}</tbody>
    </table>`;
  }

  function examResultText(item, exam) {
    if (!item.examRequired) return '不要求考核';
    if (!exam) return item.examPassed ? '已通過（目前無可顯示的考核紀錄）' : '尚無考核紀錄';
    const score = exam.score === null || exam.score === undefined || exam.score === '' ? '—' : exam.score;
    const passing = exam.passingScore === null || exam.passingScore === undefined || exam.passingScore === '' ? '—' : exam.passingScore;
    return `${score} / 及格 ${passing}`;
  }

  function renderEvidence(item) {
    const panel = el('admin-competency-evidence-panel');
    if (!panel || !item) return;
    selectedEvidenceKey = evidenceKey(item);
    const status = qualificationStatus(item);
    const meta = qualificationMeta[status] || qualificationMeta.training;
    const evidence = item.evidence || {};
    const exam = evidence.exam || null;
    const certificate = evidence.certificate || {};
    const reviewer = exam?.reviewerName || exam?.evaluatorName || '—';
    const reviewerTitle = exam?.evaluatorTitle ? `（${esc(exam.evaluatorTitle)}）` : '';
    const reviewTime = exam?.reviewedAt || exam?.recordedAt || '';
    const reviewComment = exam?.reviewComment || '';

    panel.innerHTML = `
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-[10px] font-black tracking-wide text-teal-700">ASSESSMENT EVIDENCE</p>
          <h5 class="mt-1 text-base font-black text-slate-950">${esc(item.name || item.username)} · ${esc(item.courseTitle || item.courseId)}</h5>
          <p class="mt-1 text-[11px] text-slate-500">工號 ${esc(item.empId || item.username)} · ${esc((groups()[item.group] || {}).name || item.group || '')}</p>
        </div>
        <div class="flex items-center gap-2"><span class="inline-flex rounded-full border px-2.5 py-1 text-[10px] font-bold ${meta[1]}">${meta[0]}</span><button id="admin-competency-close-evidence" type="button" class="admin-toolbar-button">關閉</button></div>
      </div>
      <div class="mt-4 grid md:grid-cols-2 xl:grid-cols-4 gap-3">
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><p class="text-[10px] font-bold text-slate-500">教材完成</p><p class="mt-1 font-black text-slate-900">${Number(item.materialsCompleted || 0)} / ${Number(item.materialsTotal || 0)}</p><p class="mt-1 text-[10px] text-slate-500">${item.retrainingRequired ? '目前標記：需重新訓練' : '目前無重訓標記'}</p></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><p class="text-[10px] font-bold text-slate-500">考核結果</p><p class="mt-1 font-black text-slate-900">${esc(examResultText(item, exam))}</p><p class="mt-1 text-[10px] text-slate-500">${item.examPassed ? '考核已通過' : item.examRequired ? '考核尚未通過' : '本能力未指定考核'}</p></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><p class="text-[10px] font-bold text-slate-500">指派／截止</p><p class="mt-1 font-black text-slate-900">${esc(dateText(item.assignedAt))}</p><p class="mt-1 text-[10px] text-slate-500">截止 ${esc(dateText(item.dueAt))} · ${item.required ? '必修' : '選修／建議'}</p></div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-3"><p class="text-[10px] font-bold text-slate-500">完訓證明</p><p class="mt-1 font-black text-slate-900">${certificate.status === 'current' || item.certificateStatus === 'current' ? '目前有效' : certificate.status === 'historical' || item.certificateStatus === 'historical' ? '僅歷史證明' : '尚無'}</p><p class="mt-1 text-[10px] text-slate-500">核發 ${esc(dateText(certificate.issuedAt || item.certificateIssuedAt))}</p></div>
      </div>
      <div class="mt-3 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
        <div class="grid md:grid-cols-3 gap-3 text-xs">
          <div><span class="block text-[10px] font-bold text-teal-700">評核／批改者</span><strong class="mt-1 block text-slate-900">${esc(reviewer)}${reviewerTitle}</strong></div>
          <div><span class="block text-[10px] font-bold text-teal-700">評核時間</span><strong class="mt-1 block text-slate-900">${esc(dateText(reviewTime))}</strong></div>
          <div><span class="block text-[10px] font-bold text-teal-700">評核狀態</span><strong class="mt-1 block text-slate-900">${esc(exam?.reviewStatus || (item.examRequired ? item.examStatus || '尚無紀錄' : '不要求'))}</strong></div>
        </div>
        <div class="mt-3 border-t border-teal-100 pt-3"><span class="block text-[10px] font-bold text-teal-700">評語／備註</span><p class="mt-1 whitespace-pre-wrap text-xs text-slate-700">${esc(reviewComment || '目前沒有評核評語。')}</p></div>
      </div>
      <p class="mt-3 text-[10px] leading-5 text-slate-400">此區只顯示既有學習、考核與證明紀錄的可追溯摘要；不提供在矩陣直接改寫評核結果或資格狀態。</p>`;
    panel.classList.remove('hidden');
    renderMatrix();
  }

  function clearEvidence() {
    selectedEvidenceKey = '';
    const panel = el('admin-competency-evidence-panel');
    if (panel) {
      panel.classList.add('hidden');
      panel.innerHTML = '';
    }
  }

  function findMatrixItem(username, courseId) {
    const wantedUser = String(username || '').toLowerCase();
    const wantedCourse = String(courseId || '');
    return matrixRows.find(item => String(item.username || '').toLowerCase() === wantedUser && String(item.courseId || '') === wantedCourse) || null;
  }

  async function loadMatrix(force=false) {
    ensureMatrixTools();
    const summary = el('admin-competency-matrix-summary');
    if (summary) summary.textContent = '正在讀取人員 × 能力矩陣…';
    try {
      const res = await fetch('/api/training-compliance?' + queryParams().toString(), {credentials:'same-origin', cache:force ? 'reload' : 'no-store'});
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || '無法讀取能力矩陣');
      matrixRows = Array.isArray(data.rows) ? data.rows : [];
      if (selectedEvidenceKey && !matrixRows.some(item => evidenceKey(item) === selectedEvidenceKey)) clearEvidence();
      renderMatrix();
    } catch (error) {
      matrixRows = [];
      clearEvidence();
      if (summary) summary.textContent = `❌ ${error.message || '無法讀取能力矩陣'}`;
      const host = el('admin-competency-matrix-table');
      if (host) host.innerHTML = '';
    }
  }

  function paintMode() {
    el('admin-compliance-list-view')?.classList.toggle('hidden', matrixMode);
    el('admin-competency-matrix-view')?.classList.toggle('hidden', !matrixMode);
    for (const [id, active] of [['admin-compliance-view-list', !matrixMode], ['admin-compliance-view-matrix', matrixMode]]) {
      const button = el(id);
      if (!button) continue;
      button.classList.toggle('bg-teal-700', active);
      button.classList.toggle('text-white', active);
    }
  }

  function setMode(mode) {
    matrixMode = mode === 'matrix';
    paintMode();
    if (matrixMode) void loadMatrix(true);
  }

  function bind() {
    ensureMatrixTools();
    const list = el('admin-compliance-view-list');
    const matrix = el('admin-compliance-view-matrix');
    if (list && list.dataset.bound92 !== '1') {
      list.dataset.bound92 = '1';
      list.addEventListener('click', () => setMode('list'));
    }
    if (matrix && matrix.dataset.bound92 !== '1') {
      matrix.dataset.bound92 = '1';
      matrix.addEventListener('click', () => setMode('matrix'));
    }
    for (const id of ['admin-compliance-area','admin-compliance-group','admin-compliance-course']) {
      const node = el(id);
      if (node && node.dataset.bound92 !== '1') {
        node.dataset.bound92 = '1';
        node.addEventListener('change', () => {
          clearEvidence();
          if (matrixMode) void loadMatrix(true);
        });
      }
    }
    const search = el('admin-compliance-search');
    if (search && search.dataset.bound92 !== '1') {
      search.dataset.bound92 = '1';
      search.addEventListener('input', () => { if (matrixMode) renderMatrix(); });
    }
    for (const id of ['admin-competency-status-filter','admin-competency-display-filter']) {
      const node = el(id);
      if (node && node.dataset.bound92 !== '1') {
        node.dataset.bound92 = '1';
        node.addEventListener('change', () => {
          clearEvidence();
          if (matrixMode) renderMatrix();
        });
      }
    }
    const clear = el('admin-competency-clear-filters');
    if (clear && clear.dataset.bound92 !== '1') {
      clear.dataset.bound92 = '1';
      clear.addEventListener('click', () => {
        const status = el('admin-competency-status-filter');
        const display = el('admin-competency-display-filter');
        if (status) status.value = '';
        if (display) display.value = 'all';
        clearEvidence();
        if (matrixMode) renderMatrix();
      });
    }
    const host = el('admin-competency-matrix-table');
    if (host && host.dataset.bound92 !== '1') {
      host.dataset.bound92 = '1';
      host.addEventListener('click', event => {
        const button = event.target.closest('[data-competency-cell]');
        if (!button || !host.contains(button)) return;
        const item = findMatrixItem(button.dataset.username, button.dataset.courseId);
        if (item) renderEvidence(item);
      });
    }
    const view = el('admin-competency-matrix-view');
    if (view && view.dataset.evidenceBound92 !== '1') {
      view.dataset.evidenceBound92 = '1';
      view.addEventListener('click', event => {
        if (event.target.closest('#admin-competency-close-evidence')) {
          clearEvidence();
          if (matrixMode) renderMatrix();
        }
      });
    }
    const refresh = el('admin-compliance-refresh');
    if (refresh && refresh.dataset.bound92 !== '1') {
      refresh.dataset.bound92 = '1';
      refresh.addEventListener('click', () => { if (matrixMode) void loadMatrix(true); });
    }
    paintMode();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, {once:true});
  } else {
    bind();
  }
})();
