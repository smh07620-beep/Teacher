/* Teacher 10/14 MVP readiness: keep legacy media cards aligned without duplicating the primary studio UI. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  const roles = R.roles instanceof Set ? R.roles : new Set();
  const has = permission => typeof R.hasPermission === 'function' && R.hasPermission(permission);
  const teacherRole = ['clinical_teacher','group_leader','education_admin'].some(role => roles.has(role));
  if (!teacherRole || !has('material.manage')) return;

  function badge(card, text, tone) {
    if (!card) return;
    let node = card.querySelector('[data-teacher1014-readiness]') || card.querySelector('span');
    if (!node) {
      node = document.createElement('span');
      card.appendChild(node);
    }
    node.dataset.teacher1014Readiness = '1';
    node.textContent = text;
    const classes = {
      ready: 'mt-3 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800',
      partial: 'mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800',
    };
    node.className = classes[tone] || classes.ready;
  }

  function syncCards() {
    const media = document.getElementById('teacher-media-production-1014');
    if (!media) return false;

    // AI 媒體製作室現在是正式主介面；舊的大型 MVP 摘要與主介面重複，
    // 若舊 render 留下節點就移除，且不再重新建立。
    document.getElementById('teacher-media-mvp-summary-1014')?.remove();

    const cards = [...media.querySelectorAll('article')];
    cards.forEach(card => {
      const title = card.querySelector('h5')?.textContent || '';
      if (title.includes('教材轉講稿')) badge(card, '可使用｜AI 草稿＋教師核准', 'ready');
      else if (title.includes('老師錄音／AI 語音')) badge(card, '可使用｜真人錄音＋AI 語音', 'ready');
      else if (title.includes('老師錄影／教學影片')) badge(card, '可使用｜攝影機＋螢幕錄影', 'ready');
    });
    return true;
  }

  if (!syncCards()) {
    const observer = new MutationObserver(() => {
      if (syncCards()) observer.disconnect();
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.TeacherMediaMvpStatus1014 = Object.freeze({ sync: syncCards });
})();

/* ---- merged from teacher-media-status-fix-1014.js (2026-10-17 slimming; same load position) ---- */
;/* Teacher 10/14: media readiness reflects free local Kokoro narration. */
(async function () {
  'use strict';

  const R = await (window.TeacherRBAC681Ready || Promise.resolve(window.TeacherRBAC681 || {}));
  if (typeof R.hasPermission !== 'function' || !R.hasPermission('material.manage')) return;

  function audioCard() {
    return [...document.querySelectorAll('#teacher-media-production-1014 article')]
      .find(card => (card.querySelector('h5')?.textContent || '').includes('老師錄音／AI 語音')) || null;
  }

  function paintBadge(text, enabled) {
    const card = audioCard();
    if (!card) return false;
    const badge = card.querySelector('[data-teacher1014-readiness]') || card.querySelector('span');
    if (!badge) return false;
    badge.textContent = text;
    badge.className = enabled
      ? 'mt-3 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800'
      : 'mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800';
    return true;
  }

  function updateSummary(enabled) {
    const summary = document.getElementById('teacher-media-mvp-summary-1014');
    if (!summary) return;
    const paragraph = summary.querySelector('p.mt-1.text-xs');
    if (paragraph) paragraph.textContent = enabled
      ? '教材轉講稿、教師核准、AI 語音、老師錄音、攝影機錄影與螢幕＋麥克風錄製已接入現有教材流程。'
      : '教材轉講稿、教師核准、老師錄音、攝影機錄影與螢幕＋麥克風錄製可正常使用；AI 語音目前暫時不可用。';
  }

  function readinessLabel(data) {
    if (data?.readyForPreview) return '可使用｜真人錄音＋AI 語音';
    if (data?.enabled === false) return '真人錄音可用｜AI 語音尚未啟用';
    return '真人錄音可用｜AI 語音暫時不可用';
  }

  async function refresh() {
    if (!audioCard()) return false;
    const data = window.TeacherMediaAudioStatus1014 || null;
    if (!data) {
      paintBadge('真人錄音可用｜AI 語音狀態確認中…', false);
      updateSummary(false);
      return true;
    }
    const ready = !!data.readyForPreview;
    paintBadge(readinessLabel(data), ready);
    updateSummary(ready);
    return true;
  }

  if (!(await refresh())) {
    const observer = new MutationObserver(() => {
      if (audioCard()) {
        observer.disconnect();
        void refresh();
      }
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  window.addEventListener('teacher-media-audio-status-1014', event => {
    const data = event.detail?.status || null;
    if (!data || !audioCard()) return;
    const ready = !!data.readyForPreview;
    paintBadge(readinessLabel(data), ready);
    updateSummary(ready);
  });

  window.TeacherMediaStatusFix1014 = Object.freeze({ refresh });
})();
