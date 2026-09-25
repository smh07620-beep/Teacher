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
    const statusHost = document.getElementById('learning-status-detail-71');
    const course = document.getElementById('course-overview');
    const host = course || document.querySelector('main.flex-grow') || document.querySelector('main');
    if (!host) return null;
    const section = document.createElement('details');
    section.id = ID;
    section.className = 'rounded-xl border border-amber-100 bg-amber-50/20 px-3 py-3';
    section.innerHTML = `
      <summary class="cursor-pointer list-none flex items-center justify-between gap-3">
        <span><b class="text-sm text-slate-900">🔔 通知中心</b><span id="notification-status-71" class="ml-2 text-[11px] text-slate-500">讀取中…</span></span>
        <span class="text-[11px] font-bold text-amber-700">展開 ▾</span>
      </summary>
      <div class="mt-3 flex justify-end"><button id="notification-refresh-71" type="button" class="text-[10px] font-bold text-amber-700">↻ 更新</button></div>
      <div id="notification-list-71" class="space-y-2 mt-3"></div>
      <p class="text-[10px] text-slate-400 mt-3">一般人員彙整考核與公告；只有後台明確標記的 PGY 學員才會額外出現 PGY 學員待辦。通知中心本身不執行任何 mutation。</p>`;
    const grid = document.getElementById('course-overview-grid');
    if (statusHost) statusHost.appendChild(section);
    else if (grid) grid.after(section);
    else if (course) course.appendChild(section);
    else host.appendChild(section);
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

  function courseHref(item) {
    const query = new URLSearchParams({
      area: item?.area || 'internal',
      group: item?.group || 'grpBio',
      module: 'materials',
      from: 'notification-center'
    });
    return `/system?${query.toString()}`;
  }

  function normalizeNotifications(command, dashboard, announcements) {
    const rows = [];
    const tasks = Array.isArray(command?.items) ? command.items : [];
    tasks.forEach(task => rows.push({
      kind: 'pgy', priority: task?.overdue ? 0 : 1,
      title: task?.title || 'PGY 訓練待辦',
      detail: task?.overdue ? '已逾期，請回 PGY 工作區處理。' : (task?.statusLabel || '等待處理'),
      badge: task?.overdue ? '逾期' : 'PGY', overdue: Boolean(task?.overdue), href: '', target: 'pgy'
    }));

    const pendingCourses = Array.isArray(dashboard?.pendingCourses) ? dashboard.pendingCourses : [];
    const pendingCourseIds = new Set(pendingCourses.map(item => String(item?.id || '')));
    pendingCourses.forEach(course => {
      const due = String(course?.dueAt || '').trim();
      const progress = `教材 ${Number(course?.materialsCompleted || 0)}/${Number(course?.materialsTotal || 0)}`;
      rows.push({
        kind: 'course', priority: course?.overdue ? 0 : 1,
        title: course?.title || '待完成課程',
        detail: `${course?.overdue ? '已逾期' : due ? `期限 ${due.slice(0, 10)}` : '正式指派'} · ${progress}${course?.examRequired ? course?.examPassed ? ' · 考核已通過' : ' · 尚待考核' : ''}`,
        badge: course?.overdue ? '逾期' : '必修課程', overdue: Boolean(course?.overdue), href: courseHref(course), target: ''
      });
    });

    const pendingExams = Array.isArray(dashboard?.pendingExams) ? dashboard.pendingExams : [];
    pendingExams.filter(exam => !pendingCourseIds.has(String(exam?.courseId || ''))).forEach(exam => rows.push({
      kind: 'exam', priority: 2, title: exam?.title || '待完成考核',
      detail: `${exam?.area === 'pgy' ? 'PGY' : '院內'}考核 · 及格 ${Number(exam?.passingScore || 80)} 分`,
      badge: '考核', overdue: false, href: examHref(exam), target: ''
    }));

    const notices = Array.isArray(announcements) ? announcements : [];
    notices.slice(0, 5).forEach(item => rows.push({
      kind: 'announcement', priority: 3, title: item?.title || '平台公告',
      detail: item?.body || '平台有新的公告。', badge: '公告', overdue: false, href: '', target: ''
    }));
    return rows.sort((a, b) => a.priority - b.priority);
  }

  function openPGY() {
    if (typeof window.switchLearningModule === 'function') window.switchLearningModule('assessment');
    window.setTimeout(() => (document.getElementById('pgy-workflow-center') || document.getElementById('panel-assessment'))?.scrollIntoView?.({behavior:'smooth',block:'start'}), 120);
  }

  function render(rows) {
    const status = document.getElementById('notification-status-71');
    const list = document.getElementById('notification-list-71');
    if (!status || !list) return;
    const urgent = rows.filter(item => item.overdue).length;
    const actionable = rows.filter(item => item.kind === 'pgy' || item.kind === 'course' || item.kind === 'exam').length;
    const info = rows.filter(item => item.kind === 'announcement').length;
    status.textContent = rows.length ? `${actionable} 待處理 · ${urgent} 逾期 · ${info} 公告` : '沒有新通知';
    if (!rows.length) {
      list.innerHTML = '<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-700">✓ 目前沒有需要注意的新事項。</div>';
      return;
    }
    list.innerHTML = rows.slice(0, 10).map((item, index) => `
      <article class="rounded-xl border ${item.overdue ? 'border-rose-200 bg-rose-50/50' : 'border-slate-200 bg-white'} px-3 py-2 flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0 flex-1"><div class="flex items-center gap-2 flex-wrap"><span class="text-xs font-black text-slate-900">${escapeHtml(item.title)}</span><span class="text-[10px] rounded-full ${item.overdue ? 'bg-rose-100 text-rose-700' : 'bg-amber-50 text-amber-700'} px-2 py-0.5 font-bold">${escapeHtml(item.badge)}</span></div><p class="text-[11px] text-slate-500 mt-1 line-clamp-2">${escapeHtml(item.detail)}</p></div>
        ${item.target === 'pgy' ? `<button type="button" data-notification-pgy="${index}" class="text-xs font-bold px-3 py-2 rounded-xl bg-indigo-700 text-white shrink-0">開啟 PGY</button>` : item.href ? `<a href="${escapeHtml(item.href)}" class="text-xs font-bold px-3 py-2 rounded-xl bg-amber-600 text-white shrink-0">${item.kind === 'course' ? '前往課程' : '前往考核'}</a>` : ''}
      </article>`).join('');
    list.querySelectorAll('[data-notification-pgy]').forEach(button => button.addEventListener('click', openPGY));
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('notification-status-71');
    if (status) status.textContent = force ? '更新中…' : '讀取中…';
    try {
      const auth = await getJSON('/api/auth/me');
      if (!auth?.authenticated || !auth?.user) { section.classList.add('hidden'); return; }
      const user = auth.user;
      const requests = [
        getJSON('/api/training-command-center').catch(error => error?.status === 403 ? {items: []} : Promise.reject(error)),
        getJSON('/api/announcements?limit=5').catch(() => [])
      ];
      if (user.empId) {
        const query = new URLSearchParams({empId:user.empId}); if (user.name) query.set('name',user.name);
        requests.push(getJSON(`/api/dashboard/me?${query.toString()}`).catch(()=>({pendingCourses:[],pendingExams:[]})));
      } else requests.push(Promise.resolve({pendingCourses:[],pendingExams:[]}));
      const [command, announcements, dashboard] = await Promise.all(requests);
      section.classList.remove('hidden');
      render(normalizeNotifications(command, dashboard, announcements));
    } catch (error) {
      if (status) status.textContent = `❌ ${error.message || '無法讀取通知'}`;
    }
  }

  window.teacher71NotificationCenterRefresh = () => load(true);
  function init(){ if(mount()) load(false); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
