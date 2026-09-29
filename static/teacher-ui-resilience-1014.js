/* Teacher 10/14 resilience + progressive disclosure.
 * Keeps operational/empty/error state visible while collapsing explanatory copy
 * until the user explicitly asks for it. Also self-heals assessment scope on
 * teacher workspace entry and enriches the Worker surface with failure detail.
 */
(async function () {
  'use strict';

  if (!['/system', '/system.html'].includes(window.location.pathname)) return;

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  // ------------------------------------------------------------------
  // Progressive disclosure for explanatory copy.
  // ------------------------------------------------------------------
  const HELP_VISIBLE_KEY = 'teacher-help-visible-1014';
  const IMPORTANT_RE = /(失敗|錯誤|警告|無法|離線|中斷|逾期|尚未完成|需要處理|請重新上傳|權限不足)/;

  function helpVisible() {
    try { return sessionStorage.getItem(HELP_VISIBLE_KEY) === '1'; }
    catch (_) { return false; }
  }

  function setHelpVisible(visible) {
    document.body.classList.toggle('teacher-help-visible-1014', Boolean(visible));
    try { sessionStorage.setItem(HELP_VISIBLE_KEY, visible ? '1' : '0'); } catch (_) {}
    const button = document.getElementById('teacher-help-toggle-1014');
    if (button) {
      button.textContent = visible ? '隱藏說明' : '？ 顯示說明';
      button.setAttribute('aria-pressed', visible ? 'true' : 'false');
    }
  }

  function isHelpCandidate(node) {
    if (!(node instanceof HTMLElement) || node.tagName !== 'P') return false;
    if (node.dataset.teacherHelpKeep === '1' || node.dataset.teacherHelp === '1') return false;
    if (node.closest('details, summary, button, label, [role="alert"], [aria-live], table, nav')) return false;
    if (node.closest('[class*="border-rose"], [class*="bg-rose"], [class*="border-amber"]')) return false;
    const id = String(node.id || '');
    if (/(status|error|warning|empty|progress)/i.test(id)) return false;
    const text = (node.textContent || '').trim();
    if (text.length < 18 || text.length > 700 || IMPORTANT_RE.test(text)) return false;
    const classes = String(node.className || '');
    const muted = /(text-(slate|gray|teal|indigo|cyan)-(400|500|600|700|800)|text-xs|text-sm|text-\[11px\]|text-\[10px\])/i.test(classes);
    return muted;
  }

  function scanHelp(root = document) {
    const candidates = root instanceof HTMLElement && root.tagName === 'P'
      ? [root]
      : [...(root.querySelectorAll?.('p') || [])];
    candidates.forEach(node => {
      if (!isHelpCandidate(node)) return;
      node.dataset.teacherHelp = '1';
      node.classList.add('teacher-context-help-copy-1014');
    });
  }

  function installHelpToggle() {
    if (document.getElementById('teacher-help-toggle-1014')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.id = 'teacher-help-toggle-1014';
    button.className = 'teacher-help-toggle-1014';
    button.setAttribute('aria-label', '顯示或隱藏頁面說明文字');
    button.addEventListener('click', () => setHelpVisible(!document.body.classList.contains('teacher-help-visible-1014')));
    const host = document.querySelector('.v56-system-actions') || document.querySelector('header .flex') || document.body;
    host.appendChild(button);
    setHelpVisible(helpVisible());
  }

  // ------------------------------------------------------------------
  // Assessment list: normalize URL/current scope before every canonical load.
  // This prevents the teacher workspace from briefly requesting an empty stale
  // scope while group selectors are still being populated.
  // ------------------------------------------------------------------
  function assessmentScope() {
    const params = new URLSearchParams(window.location.search);
    return {
      area: params.get('area') || window.currentTrainingArea || 'internal',
      group: params.get('group') || window.currentGroupKey || 'grpBio'
    };
  }

  function syncAssessmentScope() {
    window.populateAdminGroupSelects?.();
    const wanted = assessmentScope();
    const area = document.getElementById('admin-quiz-area');
    const group = document.getElementById('admin-quiz-group');
    if (area && [...area.options].some(option => option.value === wanted.area)) area.value = wanted.area;
    if (group && [...group.options].some(option => option.value === wanted.group)) group.value = wanted.group;
    return {
      area: area?.value || wanted.area,
      group: group?.value || wanted.group
    };
  }

  const canonicalQuizRender = window.renderAdminQuizCategories;
  if (typeof canonicalQuizRender === 'function' && !canonicalQuizRender.__teacher1014ScopeGuard) {
    const guarded = async function(force = false) {
      syncAssessmentScope();
      return canonicalQuizRender(Boolean(force));
    };
    guarded.__teacher1014ScopeGuard = true;
    window.renderAdminQuizCategories = guarded;
  }

  function ensureAssessmentRecovery(count = null) {
    const list = document.getElementById('admin-quiz-categories-list');
    if (!list) return;
    document.getElementById('assessment-empty-recovery-1014')?.remove();
    if (count !== 0) return;
    const scope = syncAssessmentScope();
    const box = document.createElement('div');
    box.id = 'assessment-empty-recovery-1014';
    box.className = 'mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950';
    const text = document.createElement('div');
    text.className = 'font-bold';
    text.textContent = `目前範圍（${scope.area} / ${scope.group}）沒有讀到可管理考卷。教材轉檔失敗不會刪除考卷資料。`;
    const actions = document.createElement('div');
    actions.className = 'mt-3 flex flex-wrap gap-2';
    const refresh = document.createElement('button');
    refresh.type = 'button';
    refresh.className = 'rounded-lg bg-amber-700 px-3 py-2 font-bold text-white';
    refresh.textContent = '↻ 重新同步此範圍';
    refresh.addEventListener('click', () => window.renderAdminQuizCategories?.(true));
    actions.appendChild(refresh);
    box.append(text, actions);
    list.parentElement?.appendChild(box);
  }

  const canonicalPaint = window.paintAdminQuizCategories;
  if (typeof canonicalPaint === 'function' && !canonicalPaint.__teacher1014EmptyRecovery) {
    const painted = function(items) {
      const result = canonicalPaint(items);
      ensureAssessmentRecovery(Array.isArray(items) ? items.length : null);
      return result;
    };
    painted.__teacher1014EmptyRecovery = true;
    window.paintAdminQuizCategories = painted;
  }

  const shell = window.AdminWorkspaceShell;
  shell?.addBeforeWorkspace(({requested, workspace}) => {
    if (requested === 'assessment' || workspace === 'assessment') syncAssessmentScope();
  });
  shell?.addAfterWorkspace(({requested, workspace}) => {
    if (requested !== 'assessment' && workspace !== 'assessment') return;
    syncAssessmentScope();
    setTimeout(() => window.renderAdminQuizCategories?.(true), 0);
  });

  // ------------------------------------------------------------------
  // Worker observability: explicit capability fallback + recent failures.
  // The fallback runner itself is a GitHub Actions workflow; this surface never
  // receives its secrets and remains read-only.
  // ------------------------------------------------------------------
  let workerEnhanceTimer = null;
  let workerFetchInFlight = false;

  function capabilityWarning(article) {
    if (!(article instanceof HTMLElement) || article.querySelector('[data-worker-capability-warning-1014]')) return;
    const badgeText = [...article.querySelectorAll('span')].map(node => node.textContent || '').join(' | ');
    const officeMissing = /LibreOffice\s*✕/.test(badgeText);
    const ffmpegMissing = /FFmpeg\s*✕/.test(badgeText);
    if (!officeMissing && !ffmpegMissing) return;
    const warning = document.createElement('div');
    warning.dataset.workerCapabilityWarning1014 = '1';
    warning.className = 'rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900';
    const affected = [officeMissing ? 'DOC/DOCX/PPT/PPTX/XLS/XLSX' : '', ffmpegMissing ? 'MP4/MOV/WebM/音訊' : ''].filter(Boolean).join('、');
    warning.textContent = `⚠ 本機轉換能力不足：${affected}。這些排隊工作可由 GitHub Actions 免費備援 Worker 接手。`;
    article.appendChild(warning);
  }

  function fallbackCard() {
    const section = document.createElement('section');
    section.id = 'worker-fallback-1014';
    section.className = 'rounded-2xl border border-sky-200 bg-sky-50/60 p-4 shadow-sm';
    section.innerHTML = `<div class="flex items-start justify-between gap-3 flex-wrap"><div><h5 class="font-black text-sky-950">☁ 免費備援 Worker</h5><div class="mt-1 text-sm text-sky-900">GitHub Actions 每 15 分鐘短暫啟動；先等待 5 分鐘讓本機 Worker 優先取得工作，仍在排隊才接手，單次最多處理 3 筆後自動關閉。</div></div><span class="rounded-full border border-sky-200 bg-white px-2.5 py-1 text-sm font-bold text-sky-700">待命 / 自動救援</span></div><div class="mt-3 grid gap-2 sm:grid-cols-2 text-sm"><div class="rounded-xl bg-white/80 px-3 py-2">Office 備援：<b>LibreOffice</b></div><div class="rounded-xl bg-white/80 px-3 py-2">影音備援：<b>FFmpeg + FFprobe</b></div></div><div class="mt-2 text-sm text-sky-800">輸出固定使用 Google Drive；GitHub Secrets 未完成時 workflow 會安全跳過，不會接觸任何教材。</div>`;
    return section;
  }

  function buildFailureSection(jobs) {
    const failures = (Array.isArray(jobs) ? jobs : []).filter(job => ['failed', 'retry_wait'].includes(String(job.status || ''))).slice(0, 8);
    const section = document.createElement('section');
    section.id = 'worker-recent-failures-1014';
    section.className = 'rounded-2xl border border-rose-200 bg-white p-4 shadow-sm space-y-3';
    const title = document.createElement('div');
    title.className = 'flex items-center justify-between gap-3';
    title.innerHTML = `<h5 class="font-black text-slate-900">❌ 最近失敗 / 等待重試</h5><span class="text-sm text-slate-500">${failures.length} 筆</span>`;
    section.appendChild(title);
    if (!failures.length) {
      const empty = document.createElement('div');
      empty.className = 'rounded-xl bg-emerald-50 px-3 py-3 text-sm font-bold text-emerald-800';
      empty.textContent = '目前最近工作沒有失敗紀錄。';
      section.appendChild(empty);
      return section;
    }
    const list = document.createElement('div');
    list.className = 'space-y-2';
    failures.forEach(job => {
      const row = document.createElement('article');
      row.className = 'rounded-xl border border-rose-100 bg-rose-50/50 p-3';
      const detail = String(job.error || job.detail || '未提供錯誤細節').slice(0, 800);
      row.innerHTML = `<div class="flex items-start justify-between gap-2 flex-wrap"><div class="font-bold text-slate-900">${escapeHtml(job.title || job.originalName || '未命名教材')}</div><span class="text-sm font-bold text-rose-700">${escapeHtml(job.status || '')}</span></div><div class="mt-1 text-sm text-slate-700"><b>階段：</b>${escapeHtml(job.stage || '—')}</div><div class="mt-1 text-sm text-rose-800 break-words"><b>原因：</b>${escapeHtml(detail)}</div><div class="mt-1 text-sm text-slate-500"><b>Worker：</b>${escapeHtml(job.workerId || '—')} · ${escapeHtml(job.updatedAt || job.createdAt || '')}</div>`;
      list.appendChild(row);
    });
    section.appendChild(list);
    return section;
  }

  async function enhanceWorkerPanel() {
    const panel = document.getElementById('admin-section-worker');
    if (!panel || panel.classList.contains('hidden')) return;
    panel.querySelectorAll('article').forEach(capabilityWarning);
    if (!document.getElementById('worker-fallback-1014')) {
      const sections = [...panel.children];
      const localSection = sections.find(node => node.textContent?.includes('本機 Worker'));
      if (localSection) localSection.insertAdjacentElement('afterend', fallbackCard());
      else panel.appendChild(fallbackCard());
    }
    if (document.getElementById('worker-recent-failures-1014') || workerFetchInFlight) return;
    workerFetchInFlight = true;
    try {
      const response = await fetch('/api/material-jobs?limit=30', {credentials:'same-origin', cache:'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) return;
      const recent = [...panel.children].find(node => node.textContent?.includes('最近背景工作'));
      const failures = buildFailureSection(data.jobs || []);
      if (recent) panel.insertBefore(failures, recent);
      else panel.appendChild(failures);
    } finally {
      workerFetchInFlight = false;
    }
  }

  function scheduleWorkerEnhance() {
    if (workerEnhanceTimer) clearTimeout(workerEnhanceTimer);
    workerEnhanceTimer = setTimeout(() => { workerEnhanceTimer = null; void enhanceWorkerPanel(); }, 80);
  }

  installHelpToggle();
  scanHelp(document);
  const observer = new MutationObserver(records => {
    records.forEach(record => record.addedNodes.forEach(node => {
      if (node instanceof HTMLElement) scanHelp(node);
    }));
    scheduleWorkerEnhance();
  });
  observer.observe(document.body, {childList:true, subtree:true});
  scheduleWorkerEnhance();
})();
