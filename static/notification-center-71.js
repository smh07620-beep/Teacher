/* Teacher 7.1 M4 · Notification Center
 * Read-only aggregation over existing canonical APIs. No workflow mutation lives here.
 */
(function () {
  'use strict';

  const ID = 'notification-center-71';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function mount() {
    if (document.getElementById(ID)) return document.getElementById(ID);
    const host = document.querySelector('main.flex-grow') || document.querySelector('main');
    if (!host) return null;
    const section = document.createElement('section');
    section.id = ID;
    section.className = 'edu-card p-5 sm:p-6 border border-amber-100 bg-gradient-to-br from-white to-amber-50/40';
    section.innerHTML = `
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] font-black tracking-[0.18em] text-amber-600">TEACHER 7.1 · NOTIFICATION CENTER</p>
          <h2 class="text-xl font-black text-slate-950 mt-1">🔔 通知中心</h2>
          <p class="text-xs text-slate-500 mt-1">整合待處理 PGY、待完成考核與平台公告；實際操作仍回到原本正式流程。</p>
        </div>
        <button id="notification-refresh-71" type="button" class="text-xs font-bold px-3 py-2 rounded-xl border border-amber-200 bg-white text-amber-700 hover:bg-amber-50">↻ 更新</button>
      </div>
      <div id="notification-status-71" class="text-xs text-slate-500 mt-4">讀取通知中…</div>
      <div id="notification-stats-71" class="hidden grid grid-cols-3 gap-2 sm:gap-3 mt-4"></div>
      <div id="notification-list-71" class="space-y-2 mt-4"></div>
      <p class="text-[10px] text-slate-400 mt-4">M4 為唯讀聚合層，不會在通知中心內執行簽核、考試提交、教材進度修改或公告管理。</p>`;
    const anchor = document.getElementById('learning-analytics-71') || document.getElementById('pgy-competency-matrix-71') || document.getElementById('training-command-center-71');
    if (anchor?.nextSibling) anchor.parentNode.insertBefore(section, anchor.nextSibling);
    else if (anchor) anchor.after(section);
    else host.prepend(section);
    section.querySelector('#notification-refresh-71').addEventListener('click', () => load(true));
    return section;
  }

  async function getJSON(url) {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store'});
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(data?.error || `讀取失敗（${response.status}）`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function examHref(item) {
    const query = new URLSearchParams({
      area: item?.area || 'internal',
      group: item?.group || 'grpBio',
      module: 'exam',
      from: 'notification-center'
    });
    const examId = String(item?.id || item?.examId || item?.quizId || '').trim();
    if (examId) query.set('examId', examId);
    return `/system?${query.toString()}`;
  }

  function normalizeNotifications(command, dashboard, announcements) {
    const rows = [];
    const tasks = Array.isArray(command?.items) ? command.items : [];
    tasks.forEach(task => rows.push({
      kind: 'pgy',
      priority: task?.overdue ? 0 : 1,
      title: task?.title || 'PGY 訓練待辦',
      detail: task?.overdue ? '已逾期，請回 PGY 工作區處理。' : (task?.statusLabel || '等待處理'),
      badge: task?.overdue ? '逾期' : 'PGY',
      overdue: Boolean(task?.overdue),
      href: '',
      target: 'pgy'
    }));

    const pendingExams = Array.isArray(dashboard?.pendingExams) ? dashboard.pendingExams : [];
    pendingExams.forEach(exam => rows.push({
      kind: 'exam',
      priority: 2,
      title: exam?.title || '待完成考核',
      detail: `${exam?.area === 'pgy' ? 'PGY' : '院內'}考核 · 及格 ${Number(exam?.passingScore || 80)} 分`,
      badge: '考核',
      overdue: false,
      href: examHref(exam),
      target: ''
    }));

    const notices = Array.isArray(announcements) ? announcements : [];
    notices.slice(0, 5).forEach(item => rows.push({
      kind: 'announcement',
      priority: 3,
      title: item?.title || '平台公告',
      detail: item?.body || '平台有新的公告。',
      badge: '公告',
      overdue: false,
      href: '',
      target: ''
    }));

    return rows.sort((a, b) => a.priority - b.priority);
  }

  function stat(label, value, emphasis = '') {
    return `<div class="rounded-xl border border-slate-200 bg-white px-3 py-3">
      <div class="text-[10px] text-slate-500">${escapeHtml(label)}</div>
      <div class="text-lg font-black ${emphasis || 'text-slate-900'} mt-0.5">${Number(value || 0)}</div>
    </div>`;
  }

  function openPGY() {
    if (typeof window.switchLearningModule === 'function') window.switchLearningModule('assessment');
    window.setTimeout(() => {
      const target = document.getElementById('pgy-workflow-center') || document.getElementById('panel-assessment');
      target?.scrollIntoView?.({behavior: 'smooth', block: 'start'});
    }, 120);
  }

  function render(rows) {
    const status = document.getElementById('notification-status-71');
    const stats = document.getElementById('notification-stats-71');
    const list = document.getElementById('notification-list-71');
    if (!status || !stats || !list) return;
    const urgent = rows.filter(item => item.overdue).length;
    const actionable = rows.filter(item => item.kind === 'pgy' || item.kind === 'exam').length;
    const info = rows.filter(item => item.kind === 'announcement').length;
    status.textContent = rows.length ? `目前彙整 ${rows.length} 則通知。` : '目前沒有新的通知。';
    stats.classList.remove('hidden');
    stats.innerHTML = [
      stat('需處理', actionable),
      stat('逾期', urgent, urgent ? 'text-rose-600' : 'text-slate-900'),
      stat('公告', info)
    ].join('');
    if (!rows.length) {
      list.innerHTML = '<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-xs text-emerald-700">✓ 目前沒有需要注意的新事項。</div>';
      return;
    }
    list.innerHTML = rows.slice(0, 10).map((item, index) => `
      <article class="rounded-xl border ${item.overdue ? 'border-rose-200 bg-rose-50/50' : 'border-slate-200 bg-white'} px-4 py-3 flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-xs font-black text-slate-900">${escapeHtml(item.title)}</span>
            <span class="text-[10px] rounded-full ${item.overdue ? 'bg-rose-100 text-rose-700' : 'bg-amber-50 text-amber-700'} px-2 py-0.5 font-bold">${escapeHtml(item.badge)}</span>
          </div>
          <p class="text-[11px] text-slate-500 mt-1 line-clamp-2">${escapeHtml(item.detail)}</p>
        </div>
        ${item.target === 'pgy'
          ? `<button type="button" data-notification-pgy="${index}" class="text-xs font-bold px-3 py-2 rounded-xl bg-indigo-700 text-white hover:bg-indigo-600 shrink-0">開啟 PGY</button>`
          : item.href
            ? `<a href="${escapeHtml(item.href)}" class="text-xs font-bold px-3 py-2 rounded-xl bg-amber-600 text-white hover:bg-amber-500 shrink-0">前往考核</a>`
            : ''}
      </article>`).join('');
    list.querySelectorAll('[data-notification-pgy]').forEach(button => button.addEventListener('click', openPGY));
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('notification-status-71');
    if (status) status.textContent = force ? '更新通知中…' : '讀取通知中…';
    try {
      const auth = await getJSON('/api/auth/me');
      if (!auth?.authenticated || !auth?.user) {
        section.classList.add('hidden');
        return;
      }
      const user = auth.user;
      const requests = [
        getJSON('/api/training-command-center').catch(error => error?.status === 403 ? {items: []} : Promise.reject(error)),
        getJSON('/api/announcements?limit=5').catch(() => [])
      ];
      if (user.empId) {
        const query = new URLSearchParams({empId: user.empId});
        if (user.name) query.set('name', user.name);
        requests.push(getJSON(`/api/dashboard/me?${query.toString()}`).catch(() => ({pendingExams: []})));
      } else {
        requests.push(Promise.resolve({pendingExams: []}));
      }
      const [command, announcements, dashboard] = await Promise.all(requests);
      section.classList.remove('hidden');
      render(normalizeNotifications(command, dashboard, announcements));
    } catch (error) {
      if (status) status.textContent = `❌ ${error.message || '無法讀取通知'}`;
    }
  }

  function init() {
    if (!mount()) return;
    load(false);
  }

  window.teacher71NotificationCenterRefresh = () => load(true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
