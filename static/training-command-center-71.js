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

  function taskHref(item) {
    if (item?.target === 'pgy-workflow') return '';
    const moduleName = item?.target === 'exam' ? 'exam' : 'materials';
    const query = new URLSearchParams({
      area: item?.area || 'internal',
      group: item?.group || 'grpBio',
      module: moduleName,
      from: 'training-command-center'
    });
    if (moduleName === 'exam' && item?.resourceId) query.set('examId', String(item.resourceId));
    if (item?.courseId) query.set('courseId', String(item.courseId));
    if (item?.materialId) query.set('materialId', String(item.materialId));
    else if (item?.kind === 'material' || item?.kind === 'retraining') query.set('materialId', String(item.resourceId || item.id || ''));
    return `/system?${query.toString()}`;
  }

  function dueLabel(item) {
    const due = String(item?.dueAt || '').trim();
    if (!due) return '';
    return `${item?.overdue ? '已逾期' : '期限'} ${due.slice(0, 10)}`;
  }

  function mount() {
    let section = document.getElementById(ID);
    if (section) return section;
    const course = document.getElementById('course-overview');
    if (!course) return null;
    section = document.createElement('details');
    section.id = ID;
    section.className = 'rounded-2xl border border-indigo-100 bg-white px-4 py-3 shadow-sm';
    section.innerHTML = `
      <summary class="cursor-pointer list-none flex items-center justify-between gap-3">
        <span class="flex items-center gap-2 min-w-0"><b class="text-sm text-slate-900">📊 學習狀態</b><span id="training-command-summary-71" class="text-[11px] text-slate-500 truncate">讀取中…</span></span>
        <span class="text-[11px] font-bold text-indigo-700">展開 ▾</span>
      </summary>
      <div id="learning-status-detail-71" class="mt-3 space-y-4 border-t border-slate-100 pt-3">
        <section id="training-command-tasks-71">
          <div class="flex items-center justify-between gap-2"><b class="text-xs text-slate-800">📌 我的待辦</b><span id="training-command-status-71" class="text-[10px] text-slate-400">讀取中…</span></div>
          <div id="training-command-next-71" class="mt-2"></div>
          <div id="training-command-list-71" class="space-y-2 mt-2"></div>
        </section>
      </div>`;
    const header = course.querySelector(':scope > .edu-card');
    if (header) header.after(section); else course.prepend(section);
    return section;
  }

  function openPGY() {
    if (typeof window.switchLearningModule === 'function') window.switchLearningModule('assessment');
    window.setTimeout(() => (document.getElementById('pgy-workflow-center') || document.getElementById('panel-assessment'))?.scrollIntoView?.({behavior:'smooth', block:'start'}), 120);
  }

  function render(profile, command) {
    const status = document.getElementById('training-command-status-71');
    const summaryLine = document.getElementById('training-command-summary-71');
    const list = document.getElementById('training-command-list-71');
    const nextBox = document.getElementById('training-command-next-71');
    if (!status || !summaryLine || !list || !nextBox) return;

    const learnerItems = (Array.isArray(command?.items) ? command.items : []).filter(item => item?.persona === 'learner');
    const nextAction = command?.nextAction?.persona === 'learner' ? command.nextAction : learnerItems[0] || null;
    summaryLine.textContent = learnerItems.length ? `${learnerItems.length} 項需要處理` : '目前沒有待辦';
    const overdue = learnerItems.filter(item => item?.overdue).length;
    const retraining = learnerItems.filter(item => item?.kind === 'retraining').length;
    status.textContent = `${profile?.pgyLearner ? 'PGY／線上學習' : '線上學習'}${overdue ? ` · ${overdue} 項逾期` : ''}${retraining ? ` · ${retraining} 項需重訓` : ''}`;

    if (nextAction) {
      const nextMeta = [dueLabel(nextAction), nextAction?.detail || ''].filter(Boolean).join(' · ');
      if (nextAction?.target === 'pgy-workflow') {
        nextBox.innerHTML = `<article class="rounded-xl border-2 border-indigo-200 bg-indigo-50 px-3 py-3"><div class="text-[10px] font-black tracking-wide text-indigo-700">下一步</div><div class="mt-1 flex items-center justify-between gap-3"><div class="min-w-0"><b class="block text-sm text-slate-900 truncate">${escapeHtml(nextAction.title || 'PGY 訓練指派')}</b>${nextMeta ? `<span class="block text-[10px] text-slate-500 mt-1">${escapeHtml(nextMeta)}</span>` : ''}</div><button type="button" data-next-pgy class="shrink-0 rounded-lg bg-indigo-700 px-3 py-2 text-[11px] font-bold text-white">${escapeHtml(nextAction.actionLabel || '開啟')}</button></div></article>`;
      } else {
        nextBox.innerHTML = `<a data-learner-next-action href="${taskHref(nextAction)}" class="block rounded-xl border-2 border-teal-200 bg-teal-50 px-3 py-3"><div class="text-[10px] font-black tracking-wide text-teal-700">下一步</div><div class="mt-1 flex items-center justify-between gap-3"><div class="min-w-0"><b class="block text-sm text-slate-900 truncate">${escapeHtml(nextAction.title || '繼續學習')}</b>${nextMeta ? `<span class="block text-[10px] text-slate-500 mt-1">${escapeHtml(nextMeta)}</span>` : ''}</div><span class="shrink-0 rounded-lg bg-teal-700 px-3 py-2 text-[11px] font-bold text-white">${escapeHtml(nextAction.actionLabel || '繼續')} →</span></div></a>`;
      }
    } else {
      nextBox.innerHTML = '<div class="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">✓ 目前沒有下一個必做項目。</div>';
    }

    const rows = learnerItems.slice(0, 12).map(item => {
      const href = taskHref(item);
      const badge = item?.statusLabel || '待處理';
      const meta = [dueLabel(item), item?.detail || ''].filter(Boolean).join(' · ');
      const cls = item?.overdue ? 'border-rose-200 bg-rose-50/60' : item?.kind === 'retraining' ? 'border-amber-200 bg-amber-50/60' : 'border-slate-200 bg-white';
      if (item?.target === 'pgy-workflow') {
        return `<article class="rounded-xl border ${cls} px-3 py-2 flex items-center justify-between gap-3"><div class="min-w-0"><div class="flex items-center gap-2"><span class="text-[10px] font-black text-indigo-700">${escapeHtml(badge)}</span><b class="block text-xs text-slate-800 truncate">${escapeHtml(item.title || 'PGY 訓練指派')}</b></div>${meta ? `<span class="block text-[10px] text-slate-500 mt-1">${escapeHtml(meta)}</span>` : ''}</div><button type="button" data-pgy-command class="shrink-0 text-[10px] font-bold rounded-lg bg-indigo-700 text-white px-2.5 py-1.5">${escapeHtml(item.actionLabel || '開啟')}</button></article>`;
      }
      return `<a href="${href}" class="block rounded-xl border ${cls} px-3 py-2 hover:border-teal-300"><div class="flex items-center justify-between gap-2"><span class="min-w-0"><span class="text-[10px] font-black ${item?.overdue ? 'text-rose-700' : item?.kind === 'retraining' ? 'text-amber-700' : 'text-teal-700'}">${escapeHtml(badge)}</span><b class="block text-xs text-slate-800 truncate mt-0.5">${escapeHtml(item.title || '待辦')}</b></span><span class="text-[10px] font-bold text-teal-700 shrink-0">${escapeHtml(item.actionLabel || '前往處理')} →</span></div>${meta ? `<div class="text-[10px] text-slate-500 mt-1">${escapeHtml(meta)}</div>` : ''}</a>`;
    });

    list.innerHTML = rows.length
      ? rows.join('')
      : '<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-700">✓ 目前沒有待處理的線上學習工作。</div>';
    list.querySelectorAll('[data-pgy-command]').forEach(button => button.addEventListener('click', openPGY));
    nextBox.querySelector('[data-next-pgy]')?.addEventListener('click', openPGY);
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    try {
      const [profile, command] = await Promise.all([
        loadProfile(force),
        getJSON('/api/training-command-center?persona=learner')
      ]);
      section.classList.remove('hidden');
      render(profile, command);
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
