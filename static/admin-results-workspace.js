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

  async function filteredFetchAdminRecords() {
    if (typeof legacyFetchAdminRecords !== 'function') return null;
    const records = await legacyFetchAdminRecords();
    if (!Array.isArray(records) || state.resultMode !== 'scoring') return records;
    return records.filter(isScoringRecord);
  }

  function paintTeacherMode() {
    const scoring = document.getElementById('teacher-mode-scoring');
    const pgy = document.getElementById('teacher-mode-pgy');
    if (scoring) {
      scoring.className = state.teacherMode === 'scoring'
        ? 'px-3 py-1.5 rounded-lg bg-indigo-700 text-white text-xs font-bold'
        : 'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
    }
    if (pgy) {
      pgy.className = state.teacherMode === 'pgy'
        ? 'px-3 py-1.5 rounded-lg bg-indigo-700 text-white text-xs font-bold'
        : 'px-3 py-1.5 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-xs font-bold';
    }
  }

  function updateResultsWorkspacePresentation() {
    const title = document.getElementById('admin-results-title');
    const description = document.getElementById('admin-results-desc');
    const analytics = document.getElementById('admin-results-analytics');
    const scoring = state.resultMode === 'scoring';
    analytics?.classList.toggle('hidden', scoring);
    if (title) title.textContent = scoring ? '🎯 待人工評分' : '📊 歷次考核成績';
    if (description) {
      description.textContent = scoring
        ? '只顯示含問答題或尚待批改的考核，點「批改問答題」直接進入評分。'
        : '顯示全部歷次成績，可匯出 Word / CSV。';
    }
  }

  async function renderAdminTableWithMode(...args) {
    if (typeof legacyRenderAdminTable !== 'function') return undefined;
    const result = await legacyRenderAdminTable(...args);
    if (state.resultMode === 'scoring') {
      document.getElementById('admin-results-analytics')?.classList.add('hidden');
      const body = document.getElementById('admin-records-body');
      if (body && body.textContent?.includes('目前尚無任何考核紀錄')) {
        body.innerHTML = '<tr><td colspan="8" class="p-6 text-center text-slate-400">目前沒有待人工評分的考核。</td></tr>';
      }
    }
    return result;
  }

  function renderResultsAnalyticsWithMode(records) {
    if (state.resultMode === 'scoring') {
      document.getElementById('admin-results-analytics')?.classList.add('hidden');
      return;
    }
    if (typeof legacyRenderResultsAnalytics === 'function') {
      return legacyRenderResultsAnalytics(records);
    }
  }

  async function switchTeacherMode(mode) {
    state.teacherMode = mode === 'pgy' ? 'pgy' : 'scoring';
    paintTeacherMode();
    if (state.teacherMode === 'pgy') {
      return window.switchAdminSection?.('pgy', true);
    }
    state.resultMode = 'scoring';
    updateResultsWorkspacePresentation();
    return window.switchAdminSection?.('results', true);
  }

  async function switchWorkspace({requested, workspace, force, switchSection}) {
    if (workspace === 'teacher') {
      state.teacherMode = requested === 'pgy' ? 'pgy' : 'scoring';
      paintTeacherMode();
      if (state.teacherMode === 'pgy') return switchSection('pgy', true);
      state.resultMode = 'scoring';
      updateResultsWorkspacePresentation();
      return switchSection('results', true);
    }
    if (workspace === 'results') {
      state.resultMode = 'results';
      updateResultsWorkspacePresentation();
      return switchSection('results', force || true);
    }
  }

  window.fetchAdminRecords = filteredFetchAdminRecords;
  window.renderAdminTable = renderAdminTableWithMode;
  window.renderResultsAnalytics = renderResultsAnalyticsWithMode;
  window.paintTeacherMode = paintTeacherMode;
  window.updateResultsWorkspacePresentation = updateResultsWorkspacePresentation;
  window.switchTeacherMode = switchTeacherMode;
  window.__teacherAdminResultsWorkspace = {
    switchWorkspace,
    getState: () => ({...state})
  };
})();
