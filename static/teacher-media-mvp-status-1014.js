/* Teacher 10/14 MVP readiness: keep media studio labels aligned with shipped capabilities. */
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
      ready: 'mt-3 inline-flex rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-800',
      partial: 'mt-3 inline-flex rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-bold text-amber-800',
    };
    node.className = classes[tone] || classes.ready;
  }

  function syncCards() {
    const media = document.getElementById('teacher-media-production-1014');
    if (!media) return false;
    const cards = [...media.querySelectorAll('article')];
    cards.forEach(card => {
      const title = card.querySelector('h5')?.textContent || '';
      if (title.includes('教材轉講稿')) badge(card, '可使用｜AI 草稿＋教師核准', 'ready');
      else if (title.includes('老師錄音／AI 語音')) badge(card, '可使用｜真人錄音＋AI 語音', 'ready');
      else if (title.includes('老師錄影／教學影片')) badge(card, '可使用｜攝影機＋螢幕錄影', 'ready');
    });

    let summary = document.getElementById('teacher-media-mvp-summary-1014');
    if (!summary) {
      summary = document.createElement('section');
      summary.id = 'teacher-media-mvp-summary-1014';
      summary.className = 'rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4';
      summary.innerHTML = `
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
          <div><p class="text-[11px] font-black tracking-wide text-emerald-700">10/14 MVP READY</p><h5 class="mt-1 text-sm font-black text-emerald-950">媒體製作第一階段已可操作</h5><p class="mt-1 text-xs leading-5 text-emerald-900">教材轉講稿、教師核准、AI 語音、老師錄音、攝影機錄影與螢幕＋麥克風錄製已接入現有教材流程。產生或上傳完成後會回到原課程教材。</p></div>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] font-bold text-emerald-900">
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ 講稿</span>
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ AI 語音</span>
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ 真人錄音</span>
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ 攝影機錄影</span>
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ 螢幕錄製</span>
            <span class="rounded-lg bg-white/80 px-2.5 py-1.5">✓ 回流教材</span>
          </div>
        </div>`;
      media.prepend(summary);
    }
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
