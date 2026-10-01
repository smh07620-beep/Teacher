/* Phase 3L: teacher/results workspace mode state.
 * Loaded after admin-workspace.js and before RBAC/workspace decorators so the
 * extracted router remains canonical while later guards continue to wrap it.
 */
(() => {
  'use strict';

  const legacyFetchAdminRecords = window.fetchAdminRecords;
  const legacyRenderAdminTable = window.renderAdminTable;
  const legacyRenderResultsAnalytics = window.renderResultsAnalytics;

  const state = {
    teacherMode: 'scoring',
    resultMode: 'results'
  };

  function isScoringRecord(record) {
    return record?.reviewStatus === 'pending' ||
      (record?.answersDetail || []).some(answer => answer?.questionType === 'essay');
  }

  function ensureTeacherDocumentsNavigation() {
    const pgy = document.getElementById('teacher-mode-pgy');
    const host = pgy?.parentElement || document.querySelector('#admin-teacher-subnav .flex');
    if (!host || document.getElementById('teacher-mode-documents')) return;
    const button = document.createElement('button');
    button.id = 'teacher-mode-documents';
    button.type = 'button';
    button.textContent = '📄 紙本文件與匯出';
    button.className = 'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
    button.addEventListener('click', () => window.switchTeacherMode?.('documents'));
    host.appendChild(button);
  }

  function syncTeacherSubnavVisibility() {
    const subnav = document.getElementById('admin-teacher-subnav');
    if (!subnav) return;
    // The left teacher workspace navigation already exposes "紙本文件與匯出".
    // Hide the older horizontal teacher-mode strip while paper export is open so
    // the same destination is not presented twice. Other teacher modes keep the
    // legacy strip because PGY/scoring still use it as a local mode switcher.
    subnav.classList.toggle('hidden', state.teacherMode === 'documents');
  }

  function ensurePaperDocumentWorkspace() {
    const resultsPanel = document.getElementById('admin-section-results');
    if (!resultsPanel) return null;
    let section = document.getElementById('teacher-paper-documents');
    if (section) return section;
    section = document.createElement('section');
    section.id = 'teacher-paper-documents';
    section.className = 'hidden bg-white border border-sky-200 rounded-2xl p-5 shadow-sm space-y-5';
    section.innerHTML = `
      <div class="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        <div>
          <p class="admin-page-eyebrow text-sky-700">PAPER RECORDS</p>
          <h4 class="font-black text-slate-950 text-xl">📄 紙本文件與匯出</h4>
          <p class="text-xs text-slate-500 mt-1 max-w-3xl">將正式考核紀錄輸出為 Word，列印後依院內流程完成簽核與紙本歸檔。電子紀錄仍保留在系統，紙本作為正式留存文件。</p>
        </div>
        <span class="admin-workspace-chip">Word · 列印 · 簽核 · 歸檔</span>
      </div>
      <div class="grid sm:grid-cols-2 xl:grid-cols-4 gap-3 text-xs">
        <div class="rounded-xl border border-sky-100 bg-sky-50 p-3"><b class="text-sky-950">1. 確認紀錄</b><p class="text-slate-600 mt-1">確認姓名、工號、組別、考核主題、成績與評核者資料完整。</p></div>
        <div class="rounded-xl border border-indigo-100 bg-indigo-50 p-3"><b class="text-indigo-950">2. 匯出 Word</b><p class="text-slate-600 mt-1">從下方正式考核紀錄按「匯出 Word」，系統自動套用組別範本。</p></div>
        <div class="rounded-xl border border-amber-100 bg-amber-50 p-3"><b class="text-amber-950">3. 列印簽核</b><p class="text-slate-600 mt-1">列印後依表單規範完成受評者、評核者或必要複核人員簽名。</p></div>
        <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-3"><b class="text-emerald-950">4. 紙本歸檔</b><p class="text-slate-600 mt-1">填寫紙本歸檔編號並依科內文件管理方式分類、排序與保存。</p></div>
      </div>
      <div class="grid lg:grid-cols-[1.35fr_1fr] gap-4">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <h5 class="text-sm font-black text-slate-900">列印前留存檢核</h5>
          <div class="mt-3 grid sm:grid-cols-2 gap-2 text-xs text-slate-700">
            <div>□ 文件／表單名稱與版本正確</div><div>□ 姓名、工號與組別正確</div>
            <div>□ 考核主題、日期與成績完整</div><div>□ 及格標準與結果正確</div>
            <div>□ 評核者姓名／職稱完整</div><div>□ 簽名欄位與日期欄位完整</div>
            <div>□ 紙本歸檔編號已填寫</div><div>□ 列印頁面完整、無缺頁</div>
          </div>
        </div>
        <div class="rounded-2xl border border-slate-200 bg-white p-4">
          <h5 class="text-sm font-black text-slate-900">文件可追溯欄位</h5>
          <p class="mt-2 text-xs text-slate-600 leading-5">新版 Word 輸出資料會提供文件識別碼、原始考核時間、輸出時間、輸出人、紙本狀態、簽名欄與歸檔編號等欄位。範本有放入對應佔位字時即可直接顯示。</p>
          <p class="mt-2 text-[11px] text-slate-500">原本的 Word 範本仍可繼續使用，不會因新增欄位而失效。</p>
        </div>
      </div>
      <div class="rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3 text-xs text-sky-900">下方列表就是正式考核紀錄來源。需要紙本時直接選擇對應紀錄並按「📄 匯出 Word」；不要重新手打姓名、工號、分數或評核者資料，以避免紙本與系統紀錄不一致。</div>`;
    const anchor = document.getElementById('admin-results-analytics') || resultsPanel.firstElementChild;
    resultsPanel.insertBefore(section, anchor || null);
    return section;
  }

  function renderTeacherReviewOverview(records) {
    const rows = Array.isArray(records) ? records : [];
    const pending = rows.filter(isScoringRecord);
    const people = new Set(rows.map(row => `${row?.empId || ''}|${row?.name || ''}`).filter(value => value !== '|'));
    const essayCount = pending.reduce((total, row) => total + (row?.answersDetail || []).filter(answer => answer?.questionType === 'essay').length, 0);
    const pendingNode = document.getElementById('teacher-review-pending-count');
    const peopleNode = document.getElementById('teacher-review-people-count');
    const essayNode = document.getElementById('teacher-review-essay-count');
    if (pendingNode) pendingNode.textContent = String(pending.length);
    if (peopleNode) peopleNode.textContent = String(people.size);
    if (essayNode) essayNode.textContent = String(essayCount);
  }

  async function filteredFetchAdminRecords() {
    if (typeof legacyFetchAdminRecords !== 'function') return null;
    const records = await legacyFetchAdminRecords();
    if (!Array.isArray(records) || state.resultMode !== 'scoring') return records;
    renderTeacherReviewOverview(records);
    window.renderAdminActivitySummary?.(records);
    const filtered = records.filter(isScoringRecord);
    adminRecords = filtered;
    return filtered;
  }

  function modeButtonClass(active) {
    return active
      ? 'px-3 py-1.5 rounded-lg bg-indigo-700 text-white text-xs font-bold'
      : 'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
  }

  function paintTeacherMode() {
    ensureTeacherDocumentsNavigation();
    const scoring = document.getElementById('teacher-mode-scoring');
    const pgy = document.getElementById('teacher-mode-pgy');
    const documents = document.getElementById('teacher-mode-documents');
    if (scoring) scoring.className = modeButtonClass(state.teacherMode === 'scoring');
    if (pgy) pgy.className = modeButtonClass(state.teacherMode === 'pgy');
    if (documents) documents.className = modeButtonClass(state.teacherMode === 'documents');
    syncTeacherSubnavVisibility();
  }

  function updateResultsWorkspacePresentation() {
    ensureTeacherDocumentsNavigation();
    const paperDocuments = ensurePaperDocumentWorkspace();
    const title = document.getElementById('admin-results-title');
    const description = document.getElementById('admin-results-desc');
    const analytics = document.getElementById('admin-results-analytics');
    const activity = document.getElementById('teacher-activity-overview');
    const overview = document.getElementById('teacher-review-overview');
    const resultsOverview = document.getElementById('results-workspace-overview');
    const scoring = state.resultMode === 'scoring';
    const documents = state.resultMode === 'documents';
    analytics?.classList.toggle('hidden', scoring || documents);
    activity?.classList.toggle('hidden', !scoring);
    overview?.classList.toggle('hidden', !scoring);
    resultsOverview?.classList.toggle('hidden', scoring || documents);
    paperDocuments?.classList.toggle('hidden', !documents);
    if (title) {
      title.textContent = scoring
        ? '🎯 教師評核｜待人工評分'
        : (documents ? '📄 紙本留存｜正式考核紀錄' : '📊 歷次考核成績');
    }
    if (description) {
      description.textContent = scoring
        ? '近期受評活動與待批改考卷集中在同一工作台；可搜尋、篩選並直接進入問答評分。'
        : (documents
          ? '選擇要留存的正式考核紀錄，直接使用「匯出 Word」產生紙本表單；列印後完成簽核與歸檔。'
          : '顯示全部歷次成績，可匯出 Word / CSV。');
    }
    syncTeacherSubnavVisibility();
  }

  async function renderAdminTableWithMode(...args) {
    if (typeof legacyRenderAdminTable !== 'function') return undefined;
    const result = await legacyRenderAdminTable(...args);
    if (state.resultMode === 'scoring') {
      document.getElementById('admin-results-analytics')?.classList.add('hidden');
      const body = document.getElementById('admin-table-body');
      if (body && body.textContent?.includes('目前尚無任何考核紀錄')) {
        body.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-400">目前沒有待人工評分的考核。</td></tr>';
      }
    }
    return result;
  }

  function renderResultsAnalyticsWithMode(records) {
    if (state.resultMode === 'scoring' || state.resultMode === 'documents') {
      document.getElementById('admin-results-analytics')?.classList.add('hidden');
      return;
    }
    if (typeof legacyRenderResultsAnalytics === 'function') {
      return legacyRenderResultsAnalytics(records);
    }
  }

  async function switchTeacherMode(mode) {
    state.teacherMode = mode === 'pgy' ? 'pgy' : (mode === 'documents' ? 'documents' : 'scoring');
    paintTeacherMode();
    if (state.teacherMode === 'pgy') {
      const result = await window.switchAdminSection?.('pgy', true);
      syncTeacherSubnavVisibility();
      return result;
    }
    state.resultMode = state.teacherMode === 'documents' ? 'documents' : 'scoring';
    updateResultsWorkspacePresentation();
    const result = await window.switchAdminSection?.('results', true);
    // switchAdminSection updates generic workspace chrome and may reveal the old
    // horizontal teacher subnav again; enforce the paper-mode presentation last.
    syncTeacherSubnavVisibility();
    return result;
  }

  async function switchWorkspace({requested, workspace, force, switchSection}) {
    if (workspace === 'teacher') {
      state.teacherMode = requested === 'pgy' ? 'pgy' : 'scoring';
      paintTeacherMode();
      if (state.teacherMode === 'pgy') {
        const result = await switchSection('pgy', true);
        syncTeacherSubnavVisibility();
        return result;
      }
      state.resultMode = 'scoring';
      updateResultsWorkspacePresentation();
      const result = await switchSection('results', true);
      syncTeacherSubnavVisibility();
      return result;
    }
    if (workspace === 'results') {
      state.resultMode = 'results';
      updateResultsWorkspacePresentation();
      const result = await switchSection('results', force || true);
      syncTeacherSubnavVisibility();
      return result;
    }
  }

  const adminShell = window.AdminWorkspaceShell;
  adminShell?.registerWorkspace('teacher', switchWorkspace);
  adminShell?.registerWorkspace('results', switchWorkspace);

  ensureTeacherDocumentsNavigation();
  ensurePaperDocumentWorkspace();
  window.fetchAdminRecords = filteredFetchAdminRecords;
  window.renderAdminTable = renderAdminTableWithMode;
  window.renderResultsAnalytics = renderResultsAnalyticsWithMode;
  window.paintTeacherMode = paintTeacherMode;
  window.updateResultsWorkspacePresentation = updateResultsWorkspacePresentation;
  window.renderTeacherReviewOverview = renderTeacherReviewOverview;
  window.switchTeacherMode = switchTeacherMode;
})();
