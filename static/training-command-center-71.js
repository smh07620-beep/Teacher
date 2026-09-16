/* Teacher 7.1 M1 · Training Command Center / 我的待辦
 * Read-only aggregation. Mutations remain in their canonical workflow UIs.
 */
(function () {
  'use strict';

  const ID = 'training-command-center-71';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  function formatDue(value) {
    if (!value) return '未設定期限';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('zh-TW', {hour12: false});
  }

  function groupLabel(key) {
    const group = (window.GROUPS || {})[key];
    return group?.name || group?.label || key || '—';
  }

  function mount() {
    if (document.getElementById(ID)) return document.getElementById(ID);
    const host = document.querySelector('main.flex-grow') || document.querySelector('main');
    if (!host) return null;
    const section = document.createElement('section');
    section.id = ID;
    section.className = 'edu-card p-5 sm:p-6 border border-indigo-100 bg-gradient-to-br from-white to-indigo-50/40';
    section.innerHTML = `
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] font-black tracking-[0.18em] text-indigo-500">TEACHER 7.1 · TRAINING COMMAND CENTER</p>
          <h2 class="text-xl font-black text-slate-950 mt-1">📌 我的待辦</h2>
          <p class="text-xs text-slate-500 mt-1">集中顯示目前真正需要你處理的訓練工作；操作仍回到原本正式流程完成。</p>
        </div>
        <button id="training-command-refresh-71" type="button" class="text-xs font-bold px-3 py-2 rounded-xl border border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-50">↻ 更新</button>
      </div>
      <div id="training-command-status-71" class="text-xs text-slate-500 mt-4">讀取待辦中…</div>
      <div id="training-command-stats-71" class="hidden grid grid-cols-3 gap-2 sm:gap-3 mt-4"></div>
      <div id="training-command-list-71" class="space-y-2 mt-4"></div>
      <p class="text-[10px] text-slate-400 mt-4">M1 保持 PGY 待辦的正式操作入口；M2 能力矩陣、M3 Learning Analytics 與 M4 通知中心皆為唯讀聚合／分析層。</p>`;
    const firstSection = host.querySelector(':scope > section');
    if (firstSection?.nextSibling) host.insertBefore(section, firstSection.nextSibling);
    else if (firstSection) firstSection.after(section);
    else host.prepend(section);
    section.querySelector('#training-command-refresh-71').addEventListener('click', () => load(true));
    return section;
  }

  function statCard(label, value, emphasis = '') {
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
      target?.classList?.add('ring-2', 'ring-indigo-200');
      window.setTimeout(() => target?.classList?.remove('ring-2', 'ring-indigo-200'), 1600);
    }, 120);
  }

  function render(data) {
    const status = document.getElementById('training-command-status-71');
    const stats = document.getElementById('training-command-stats-71');
    const list = document.getElementById('training-command-list-71');
    if (!status || !stats || !list) return;
    const counts = data?.counts || {};
    const items = Array.isArray(data?.items) ? data.items : [];
    status.textContent = items.length
      ? `目前有 ${items.length} 項待辦${counts.overdue ? `，其中 ${counts.overdue} 項逾期` : ''}。`
      : '目前沒有需要你執行的 PGY 待辦。';
    stats.classList.remove('hidden');
    stats.innerHTML = [
      statCard('全部待辦', counts.total),
      statCard('逾期', counts.overdue, counts.overdue ? 'text-rose-600' : 'text-slate-900'),
      statCard('PGY', counts.pgy)
    ].join('');
    if (!items.length) {
      list.innerHTML = '<div class="rounded-xl border border-emerald-100 bg-emerald-50/70 px-4 py-3 text-xs text-emerald-700">✓ 目前沒有等待你處理的 PGY 工作。</div>';
      return;
    }
    const visible = items.slice(0, 6);
    list.innerHTML = visible.map(item => `
      <article class="rounded-xl border ${item.overdue ? 'border-rose-200 bg-rose-50/50' : 'border-slate-200 bg-white'} px-4 py-3 flex items-start justify-between gap-3 flex-wrap">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-xs font-black text-slate-900">${escapeHtml(item.title || 'PGY 訓練指派')}</span>
            <span class="text-[10px] rounded-full bg-indigo-50 text-indigo-700 px-2 py-0.5 font-bold">${escapeHtml(item.statusLabel || item.status)}</span>
            ${item.overdue ? '<span class="text-[10px] rounded-full bg-rose-100 text-rose-700 px-2 py-0.5 font-bold">已逾期</span>' : ''}
          </div>
          <div class="text-[11px] text-slate-500 mt-1">${escapeHtml(groupLabel(item.group))} · ${escapeHtml(formatDue(item.dueAt))}</div>
        </div>
        <button type="button" data-command-target="pgy-workflow" class="text-xs font-bold px-3 py-2 rounded-xl bg-indigo-700 text-white hover:bg-indigo-600 shrink-0">${escapeHtml(item.actionLabel || '開啟待辦')}</button>
      </article>`).join('') + (items.length > visible.length
        ? `<div class="text-[11px] text-slate-400 text-center">另有 ${items.length - visible.length} 項，進入 PGY 工作區查看全部。</div>`
        : '');
    list.querySelectorAll('[data-command-target="pgy-workflow"]').forEach(button => button.addEventListener('click', openPGY));
  }

  async function load(force = false) {
    const section = mount();
    if (!section) return;
    const status = document.getElementById('training-command-status-71');
    if (status) status.textContent = force ? '更新待辦中…' : '讀取待辦中…';
    try {
      const response = await fetch('/api/training-command-center', {
        credentials: 'same-origin',
        cache: 'no-store'
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        section.classList.add('hidden');
        return;
      }
      if (!response.ok) throw new Error(data?.error || `讀取失敗（${response.status}）`);
      section.classList.remove('hidden');
      render(data);
    } catch (error) {
      if (status) status.textContent = `❌ ${error.message || '無法讀取待辦'}`;
    }
  }

  function init() {
    if (!mount()) return;
    load(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
