/* Teacher 7.4 · Shared admin runtime state.
 *
 * This file owns only cross-module cache/state helpers that are consumed by
 * multiple canonical admin modules. It must not grow product UI or business
 * mutations. Authorization remains server-side session RBAC; getAdminKey is a
 * compatibility header seam for existing endpoints that still accept it.
 */

async function getAdminKey() {
  return 'rbac-session';
}

const ADMIN_CACHE_MS = 30000;
const ADMIN_QUIZ_CACHE_MS = 60000;
const ADMIN_COURSE_CACHE_MS = 60000;
let adminMaterialsCache = {data:null, at:0};
const adminQuizCategoriesCache = new Map();
const adminCoursesCache = new Map();
const adminQuizQuestionCache = {};
let adminUserAccountsCache = [];
let adminRecords = [];
let adminKey = '';

function adminScopeKey(area, group) {
  return `${area || 'internal'}::${group || 'grpBio'}`;
}

function setAdminQuizSyncStatus(text, tone='slate') {
  const el = document.getElementById('admin-quiz-sync-status');
  if (!el) return;
  const tones = {
    slate:'bg-slate-100 text-slate-500',
    indigo:'bg-indigo-50 text-indigo-700',
    emerald:'bg-emerald-50 text-emerald-700',
    rose:'bg-rose-50 text-rose-700',
    amber:'bg-amber-50 text-amber-700'
  };
  el.className = `text-[11px] px-2.5 py-1 rounded-full font-bold ${tones[tone] || tones.slate}`;
  el.textContent = text;
}

function adminHasExpandedQuestionEditor(box) {
  return !!box?.querySelector('[id^="qedit-"]:not(.hidden), textarea[id^="qedit-"]:focus, input[id^="qedit-"]:focus');
}

function difficultyLabel(value) {
  return ({basic:'基礎', standard:'一般', advanced:'進階'})[value || 'standard'] || '一般';
}
