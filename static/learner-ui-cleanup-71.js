/* Teacher 7.1/7.3: keep learner pages focused on the next useful action.
 * Presentation-only compatibility cleanup; first-paint hiding is owned by
 * learner-layout-stability-73.css, so this script runs once and never observes DOM.
 */
(function () {
  'use strict';

  function hide(el) {
    if (!el) return;
    el.classList.add('hidden');
    el.setAttribute('aria-hidden', 'true');
  }

  function show(el) {
    if (!el) return;
    el.classList.remove('hidden');
    el.removeAttribute('aria-hidden');
  }

  function apply() {
    const slidesPanel = document.getElementById('panel-slides');
    if (slidesPanel) {
      const intro = slidesPanel.querySelector(':scope > section.edu-card');
      hide(intro);
    }

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

    const resultCount = document.getElementById('learning-result-count');
    if (resultCount) {
      if (String(resultCount.textContent || '').trim()) show(resultCount);
      else hide(resultCount);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply, {once: true});
  } else {
    apply();
  }
})();
