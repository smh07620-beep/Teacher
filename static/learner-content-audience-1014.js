/* Learner presentation for cross-group shared content. */
(function () {
  'use strict';

  const catalog = typeof GROUPS !== 'undefined' ? GROUPS : (window.GROUPS || {});
  const label = key => catalog[key]?.label || catalog[key]?.name || key || '其他組別';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function badge(item) {
    if (!item?.sharedFromGroup) return '';
    const audience = item.audienceScope === 'all_staff' ? '全科共用' : '跨組共用';
    return `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100">🌐 ${audience}｜來源：${esc(label(item.ownerGroup || item.sharedFromGroup))}</span>`;
  }

  if (typeof buildSlideCardHTML === 'function') {
    const original = buildSlideCardHTML;
    buildSlideCardHTML = function (item) {
      const html = original(item);
      const mark = badge(item);
      if (!mark) return html;
      return html.replace(/(<div class="slide-card[^"]*">)/, `$1<div class="mb-2 flex flex-wrap gap-1">${mark}</div>`);
    };
  }

  if (typeof buildCourseMaterialRow === 'function') {
    const original = buildCourseMaterialRow;
    buildCourseMaterialRow = function (item) {
      const html = original(item);
      const mark = badge(item);
      if (!mark) return html;
      return html.replace(
        /(<div class="flex items-center gap-2 flex-wrap">)/,
        `$1${mark}`
      );
    };
  }
})();
