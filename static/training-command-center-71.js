/* Teacher 7.1 M1 · compact Training Command Center / 我的待辦.
 * PGY learner content is explicitly opt-in; all actions remain canonical links.
 */
(function () {
  'use strict';

  const ID = 'training-command-center-71';
  const ROLE_LABELS = {
    student: '學員', clinical_teacher: '臨床教師', group_leader: '組長',
    education_admin: '教學管理者', system_admin: '系統管理者', auditor: '稽核／唯讀'
  };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  let profilePromise = null;

  async function getJSON(url) {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data?.error || `讀取失敗（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function updateIdentityBadge(profile) {
    if (!profile) return;
    const name = document.getElementById('v573-system-user-name');
    const meta = document.getElementById('v573-system-user-id');
    if (name && profile.name) name.textContent = profile.name;
    if (meta) {
      const title = String(profile.professionalTitle || ROLE_LABELS[profile.role] || '醫檢師').trim();
      const emp = String(profile.empId || '').trim();
      meta.textContent = [title, emp ? `工號 ${emp}` : ''].filter(Boolean).join(' · ');
      meta.dataset.profileHydrated = '1';
    }
  }

  async function loadProfile(force = false) {
    if (!profilePromise || force) {
      profilePromise = getJSON('/api/training-command-center/profile').then(profile => {
        updateIdentityBadge(profile);
        document.documentElement.dataset.trainingAudience = profile?.pgyLearner ? 'pgy' : 'online';
        return profile;
      });
    }
    return profilePromise;
  }

  window.Teacher71Profile = Object.freeze({load: loadProfile, roleLabels: ROLE_LABELS});

  function dashboardUrl(profile) {
    const query = new URLSearchParams({empId: profile?.empId || ''});
    if (profile?.name) query.set('name', profile.name);
    return `/api/dashboard/me?${query.toString()}`;
  }

  function examHref(item) {
    const query = new URLSearchParams({
      area: item?.area || 'internal',
      group: item?.group || 'grpBio',
      module: 'exam',
      from: 'training-command-center'
    });
    const examId = String(item?.id || item?.examId || item?.quizId || '').trim();
    if (examId) query.set('examId', examId);
    return `/system?${query.toString()}`;
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const course = document.getElementById('course-overview');
    if (!course) return null;
    section = document.createElement('details');
    section.id = ID;
    section.className = 'rounded-2xl border border-indigo-100 bg-indigo-50/30 px-4 py-3';
    section.innerHTML = `
      <summary class="cursor-pointer list-none flex items-center justify-between gap-3">
        <span class="flex items-center gap-2 min-w-0"><b class="text-sm text-slate-900">📌 我的待辦</b><span id="training-command-summary-71" class="text-[11px] text-slate-500 truncate">讀取中…</span></span>
        <span class="text-[11px] font-bold text-indigo-700">展開 ▾</span>
      </summary>
      <div id="training-command-status-71" class="text-xs text-slate-500 mt-3">讀取待辦中…</div>
      <div id="training-command-stats-71" class="hidden grid grid-cols-3 gap-2 mt-3"></div>
      <div id="training-command-list-71" class="space-y-2 mt-3"></div>`;
    const header = course.querySelector(':scope > .edu-card');
    if (header) header.after(section); else course.prepend(section);
    return section;
  }

  function chip(label, value) {
    return `<div class="rounded-xl border border-slate-200 bg-white px-3 py-2"><div class="text-[9px] text-slate-400">${escapeHtml(label)}</div><div class="text-sm font-black text-slate-800 mt-0.5">${escapeHtml(value)}</div></div>`;
  }

  function openPGY() {
    if (typeof window.switchLearningModule === 'function') window.switchLearningModule('assessment');
    window.setTimeout(() => (document.getElementById('pgy-workflow-center') || document.getElementById('panel-assessment'))?.scrollIntoView?.({behavior:'smooth', block:'start'}), 120);
  }

  function render(profile, command, dashboard) {
    const status = document.getElementById('training-command-status-71');
    const summaryLine = document.getElementById('training-command-summary-71');
    const stats = document.getElementById('training-command-stats-71');
    const list = document.getElementById('training-command-list-71');
    if (!status || !summaryLine || !stats || !list) return;

    const pending = Array.isArray(dashboard?.pendingExams) ? dashboard.pendingExams : [];
    const pgyItems = profile?.pgyLearner && Array.isArray(command?.items) ? command.items : [];
    const total = pending.length + pgyItems.length;
    summaryLine.textContent = total ? `${total} 項需要處理` : '目前沒有待辦';
    status.textContent = profile?.pgyLearner
      ? 'PGY 學員會同時看到線上課程／考核與自己的 PGY 學員待辦。'
      : '一般／線上人員只顯示課程、教材與考核相關待辦。';

    stats.classList.remove('hidden');
    const statRows = [
      chip('待完成考核', String(pending.length)),
      chip('進行中課程', String(Number(dashboard?.activeCourses || 0))),
      profile?.pgyLearner
        ? chip('PGY 待辦', String(pgyItems.length))
        : chip('教材完成', `${Number(dashboard?.materialsCompleted || 0)}/${Number(dashboard?.materialsTotal || 0)}`)
    ];
    stats.innerHTML = statRows.join('');

    const rows = [];
    pending.slice(0, 4).forEach(exam => rows.push(`
      <a href="${examHref(exam)}" class="block rounded-xl border border-slate-200 bg-white px-3 py-2 hover:border-teal-300">
        <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-800">${escapeHtml(exam.title || '待完成考核')}</b><span class="text-[10px] font-bold text-teal-700">前往考核 →</span></div>
        <div class="text-[10px] text-slate-400 mt-1">${escapeHtml(exam.area === 'pgy' ? 'PGY考核' : '院內考核')} · 及格 ${Number(exam.passingScore || 80)} 分</div>
      </a>`));

    if (profile?.pgyLearner) {
      pgyItems.slice(0, 4).forEach(item => rows.push(`
        <article class="rounded-xl border ${item.overdue ? 'border-rose-200 bg-rose-50/60' : 'border-indigo-100 bg-white'} px-3 py-2 flex items-center justify-between gap-3">
          <div class="min-w-0"><b class="block text-xs text-slate-800 truncate">${escapeHtml(item.title || 'PGY 訓練指派')}</b><span class="text-[10px] text-slate-400">${escapeHtml(item.statusLabel || item.status || '')}${item.overdue ? ' · 已逾期' : ''}</span></div>
          <button type="button" data-pgy-command class="shrink-0 text-[10px] font-bold rounded-lg bg-indigo-700 text-white px-2.5 py-1.5">${escapeHtml(item.actionLabel || '開啟')}</button>
        </article>`));
    }

    list.innerHTML = rows.length
      ? rows.join('')
      : '<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-700">✓ 目前沒有待處理的線上學習工作。</div>';
    list.querySelectorAll('[data-pgy-command]').forEach(button => button.addEventListener('click', openPGY));
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    try {
      const profile = await loadProfile(force);
      const requests = [
        getJSON('/api/training-command-center').catch(() => ({items:[], counts:{}})),
        profile?.empId ? getJSON(dashboardUrl(profile)).catch(() => ({pendingExams:[]})) : Promise.resolve({pendingExams:[]})
      ];
      const [command, dashboard] = await Promise.all(requests);
      section.classList.remove('hidden');
      render(profile, command, dashboard);
    } catch (error) {
      if (error?.status === 401) { section.classList.add('hidden'); return; }
      const status = document.getElementById('training-command-status-71');
      if (status) status.textContent = `❌ ${error.message || '無法讀取待辦'}`;
    }
  }

  function init() { if (mount()) load(false); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
