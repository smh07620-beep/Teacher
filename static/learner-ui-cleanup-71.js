/* Teacher 7.1: keep learner pages focused on the next useful action.
 * Presentation-only cleanup; no learning/progress data is changed.
 */
(function () {
  'use strict';

  function hide(el) {
    if (!el) return;
    el.classList.add('hidden');
    el.setAttribute('aria-hidden', 'true');
  }

  function apply() {
    const slidesPanel = document.getElementById('panel-slides');
    if (slidesPanel) {
      // The large introductory card repeats the course center directly below it.
      // Hide it so learners see search + courses without unnecessary scrolling.
      const intro = slidesPanel.querySelector(':scope > section.edu-card');
      hide(intro);
    }

    // Home identity is already visible in the global header. Do not repeat an
    // instructional identity card inside the course list.
    const learningStart = document.getElementById('learning-start');
    if (learningStart) {
      learningStart.replaceChildren();
      learningStart.dataset.ready = '1';
      hide(learningStart);
    }

    const overview = document.getElementById('course-overview');
    if (overview) {
      const header = overview.querySelector(':scope > .edu-card');
      header?.querySelector('.edu-kicker')?.remove();
      const heading = header?.querySelector('h3');
      const desc = heading?.nextElementSibling;
      if (desc?.tagName === 'P') hide(desc);
      if (header) {
        header.classList.remove('p-5', 'sm:p-6');
        header.classList.add('p-4');
      }
    }

    // Keep the filter because it changes what learners see, but remove empty
    // helper/status prose when it contains no useful result information.
    const resultCount = document.getElementById('learning-result-count');
    if (resultCount && !String(resultCount.textContent || '').trim()) hide(resultCount);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply, {once: true});
  } else {
    apply();
  }

  // Course rendering can happen after async data arrives. Reapply the compact
  // presentation without touching any data or interactive course cards.
  const observer = new MutationObserver(() => apply());
  document.addEventListener('DOMContentLoaded', () => {
    const host = document.getElementById('panel-slides');
    if (host) observer.observe(host, {childList: true, subtree: true});
  }, {once: true});
})();
