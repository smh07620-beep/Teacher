/* 1032 · Learner study ⇄ exam loop.
 *
 * 1. Material "完成標記" is never a gate: learners may start an exam directly
 *    from the course list or from inside the reader / media viewer.
 * 2. While answering (or after submitting) learners can jump back to the
 *    materials / atlas area at any time. In-page switching keeps the current
 *    attempt and result; a floating "回到考核" pill brings them back.
 * 3. Failed exams are not locked. The course list shows "未通過" with a hint to
 *    review the materials again; a retake draws a freshly shuffled attempt.
 * 4. Wrong atlas (image) questions always get a "回圖譜區重新判讀" hint, even
 *    when the teacher did not configure an exact review source.
 *
 * Frontend-only convenience. Scoring, attempts and authorization stay on the
 * Flask server; this file never sees answer keys.
 */
(function () {
  'use strict';

  const RETURN_KEY = 'loop1032:returnExam';
  const RESULT_PREFIX = 'loop1032:lastResult:';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch]);
  const ss = {
    get(key) { try { return JSON.parse(sessionStorage.getItem(key) || 'null'); } catch (_) { return null; } },
    set(key, value) { try { sessionStorage.setItem(key, JSON.stringify(value)); } catch (_) {} },
    del(key) { try { sessionStorage.removeItem(key); } catch (_) {} }
  };
  // Learner runtime state lives in top-level let/const bindings of classic
  // scripts (not window properties), so read them through explicit guards.
  const g = name => {
    try {
      switch (name) {
        case 'currentTrainingArea': return typeof currentTrainingArea !== 'undefined' ? currentTrainingArea : undefined;
        case 'currentGroupKey': return typeof currentGroupKey !== 'undefined' ? currentGroupKey : undefined;
        case 'currentCatKey': return typeof currentCatKey !== 'undefined' ? currentCatKey : undefined;
        case 'allQuizData': return typeof allQuizData !== 'undefined' ? allQuizData : undefined;
        case 'isSubmittedMap': return typeof isSubmittedMap !== 'undefined' ? isSubmittedMap : undefined;
        case 'dynamicCategoriesCache': return typeof dynamicCategoriesCache !== 'undefined' ? dynamicCategoriesCache : undefined;
        case 'cachedQuizCategories': return typeof cachedQuizCategories !== 'undefined' ? cachedQuizCategories : undefined;
        case 'cachedSlidesList': return typeof cachedSlidesList !== 'undefined' ? cachedSlidesList : undefined;
        case 'teachingMediaId': return typeof teachingMediaId !== 'undefined' ? teachingMediaId : undefined;
        default: return window[name];
      }
    } catch (_) { return undefined; }
  };

  /* ---------------- data helpers ---------------- */
  function area() { return g('currentTrainingArea') || 'internal'; }
  function group() { return g('currentGroupKey') || 'grpBio'; }
  function categories() {
    const cache = g('dynamicCategoriesCache') || {};
    const list = cache[`${area()}:${group()}`] || g('cachedQuizCategories') || [];
    return Array.isArray(list) ? list : [];
  }
  function materials() { const list = g('cachedSlidesList'); return Array.isArray(list) ? list : []; }
  function examsForCourse(courseId) {
    if (!courseId) return [];
    return categories().filter(c => String(c.courseId || '') === String(courseId) && Number(c.questionCount || 0) > 0);
  }
  function currentReaderMaterial() {
    const id = window.slideViewerState?.materialId || g('teachingMediaId') || '';
    return materials().find(m => String(m.id) === String(id)) || null;
  }

  /* ---------------- exam pass / fail status per quiz ---------------- */
  const examStatus = new Map();
  let statusLoadedFor = '';
  function recordPassed(r) {
    if (!r || r.reviewStatus === 'pending') return false;
    return r.status === '合格' || Number(r.score) >= Number(r.passingScore || 80);
  }
  async function loadExamStatus(force) {
    const key = `${area()}:${group()}`;
    if (!force && statusLoadedFor === key) return;
    statusLoadedFor = key;
    try {
      const res = await fetch(`/api/my-progress?area=${encodeURIComponent(area())}&group=${encodeURIComponent(group())}`, {credentials: 'same-origin', cache: 'no-store'});
      if (!res.ok) return;
      const data = await res.json().catch(() => ({}));
      examStatus.clear();
      for (const r of (data.records || [])) {
        const id = String(r.quizCategoryId || '');
        if (!id) continue;
        const cur = examStatus.get(id) || {attempts: 0, passed: false, best: null, latest: null, pending: false};
        cur.attempts++;
        if (!cur.latest) cur.latest = r; // records arrive newest first
        if (r.reviewStatus === 'pending') cur.pending = true;
        if (recordPassed(r)) {
          cur.passed = true;
          if (!cur.best || Number(r.score) > Number(cur.best.score)) cur.best = r;
        }
        examStatus.set(id, cur);
      }
      if (typeof window.renderCourseOverview === 'function') window.renderCourseOverview();
    } catch (_) {}
  }
  function statusBadge(examId) {
    const s = examStatus.get(String(examId || ''));
    if (!s) return '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">尚未考核</span>';
    if (s.passed) return `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">✅ 已通過 ${esc(s.best?.score ?? '')} 分</span>`;
    if (s.pending) return '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">⏳ 待人工批改</span>';
    return `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-700">❌ 未通過（最近 ${esc(s.latest?.score ?? 0)} 分）</span>`;
  }
  // Read-only view of the learner's per-exam result for course status badges (teaching.js).
  window.LearnerExamStatus = Object.freeze({get: examId => examStatus.get(String(examId || '')) || null});
  function failHint(examId) {
    const s = examStatus.get(String(examId || ''));
    if (!s || s.passed || s.pending) return '';
    return '<p class="mt-1 text-[11px] font-bold text-rose-700">⚠️ 尚未通過：請先回上方教材重新閱覽，再重新考核（不會鎖定，重考時題目順序會重新打亂）。</p>';
  }

  function wrapExamRow() {
    if (typeof window.buildCourseExamRow !== 'function' || window.buildCourseExamRow.__loop1032) return;
    const original = window.buildCourseExamRow;
    const wrapped = function (exam) {
      const html = original.apply(this, arguments);
      if (!exam || !exam.id || /data-exam-not-ready/.test(html)) return html;
      const holder = document.createElement('div');
      holder.innerHTML = html;
      const row = holder.firstElementChild;
      if (!row) return html;
      row.dataset.loop1032Exam = String(exam.id);
      const titleLine = row.querySelector('.flex.items-center.gap-2.flex-wrap');
      if (titleLine) titleLine.insertAdjacentHTML('beforeend', statusBadge(exam.id));
      const body = row.querySelector('.min-w-0.flex-1');
      if (body) body.insertAdjacentHTML('beforeend', failHint(exam.id));
      const s = examStatus.get(String(exam.id));
      const btn = row.querySelector('[data-csp-click^="openCourseExam("]');
      if (btn && s && !s.passed && !s.pending && !/繼續作答/.test(btn.textContent)) btn.textContent = '重新考核 →';
      if (btn && s && s.passed) btn.textContent = '再練習一次 →';
      return holder.innerHTML;
    };
    wrapped.__loop1032 = true;
    window.buildCourseExamRow = wrapped;
  }

  /* ---------------- reader → exam ---------------- */
  function ensureReaderExamButton(anchorId, closeFn) {
    const anchor = document.getElementById(anchorId);
    if (!anchor) return;
    let button = document.getElementById(`${anchorId}-loop1032-exam`);
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.id = `${anchorId}-loop1032-exam`;
      button.className = 'px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold';
      button.addEventListener('click', async () => {
        const material = currentReaderMaterial();
        const exams = examsForCourse(material?.courseId);
        const target = exams.find(e => !examStatus.get(String(e.id))?.passed) || exams[0];
        if (!target) return;
        try { typeof closeFn === 'function' && closeFn(); } catch (_) {}
        await goToExam(target.id);
      });
      anchor.insertAdjacentElement('afterend', button);
    }
    const material = currentReaderMaterial();
    const exams = examsForCourse(material?.courseId);
    button.hidden = !exams.length;
    const ret = ss.get(RETURN_KEY);
    button.textContent = ret && exams.some(e => String(e.id) === String(ret.catId)) ? '↩ 回到考核（保留作答）' : '📝 看完了，直接考核 →';
  }
  function syncReaderButtons() {
    ensureReaderExamButton('reader-next', () => g('closeSlideViewer')?.());
    const mediaNext = document.querySelector('#media-viewer-modal [data-csp-click^="teachingNextMaterial"], #media-viewer-modal [data-csp-click^="markMaterialComplete"]');
    if (mediaNext && !mediaNext.id) mediaNext.id = 'media-viewer-loop1032-anchor';
    if (mediaNext) ensureReaderExamButton(mediaNext.id, () => g('closeMediaViewer')?.());
  }

  /* ---------------- exam ⇄ materials ---------------- */
  async function goToExam(catId) {
    if (typeof window.openCourseExam === 'function') await window.openCourseExam(catId);
    else { g('switchLearningModule')?.('exam'); await g('switchDynamicCategory')?.(catId); }
    paintPill();
    restoreLastResultCard();
  }
  function rememberExam(catId) {
    const data = (g('allQuizData') || {})[catId] || {};
    const meta = categories().find(c => String(c.id) === String(catId)) || {};
    ss.set(RETURN_KEY, {catId, title: data.title || meta.title || '考卷', courseId: data.courseId || meta.courseId || '', submitted: Boolean((g('isSubmittedMap') || {})[catId])});
  }
  function backToStudy(module) {
    const catId = g('currentCatKey');
    if (catId) rememberExam(catId);
    g('switchLearningModule')?.(module || 'materials');
    const ret = ss.get(RETURN_KEY);
    if (ret?.courseId) {
      setTimeout(() => {
        const card = document.querySelector(`.course-learning-card[data-course="${CSS.escape(ret.courseId)}"]`);
        if (card) { card.open = true; card.scrollIntoView({behavior: 'smooth', block: 'start'}); }
      }, 250);
    }
    paintPill();
  }
  window.loop1032BackToStudy = backToStudy;

  function ensureExamToolbar() {
    const panel = document.getElementById('panel-exam');
    if (!panel || document.getElementById('loop1032-exam-toolbar')) return;
    const bar = document.createElement('div');
    bar.id = 'loop1032-exam-toolbar';
    bar.className = 'flex flex-wrap items-center gap-2 rounded-2xl border border-teal-200 bg-teal-50/70 px-4 py-3 text-xs';
    bar.innerHTML = '<span class="font-bold text-teal-900">考核中也能隨時回去看教材，作答與結果都會保留。</span><span class="flex-1"></span><button type="button" data-loop1032-back="materials" class="rounded-lg bg-teal-700 hover:bg-teal-600 px-3 py-2 font-bold text-white">📖 回教材閱覽</button><button type="button" data-loop1032-back="atlas" class="rounded-lg border border-teal-300 bg-white px-3 py-2 font-bold text-teal-800">🔬 回圖譜區</button>';
    bar.addEventListener('click', event => {
      const btn = event.target.closest('[data-loop1032-back]');
      if (btn) backToStudy(btn.dataset.loop1032Back);
    });
    panel.insertBefore(bar, panel.firstChild);
  }

  function paintPill() {
    let pill = document.getElementById('loop1032-return-pill');
    const ret = ss.get(RETURN_KEY);
    const slides = document.getElementById('panel-slides');
    const inStudy = slides && !slides.classList.contains('hidden');
    if (!ret || !inStudy) { if (pill) pill.hidden = true; return; }
    if (!pill) {
      pill = document.createElement('div');
      pill.id = 'loop1032-return-pill';
      pill.className = 'fixed bottom-4 right-4 z-[96] flex items-center gap-2 rounded-2xl border border-indigo-200 bg-white/95 px-3 py-2 shadow-2xl';
      pill.addEventListener('click', async event => {
        if (event.target.closest('[data-loop1032-dismiss]')) { ss.del(RETURN_KEY); paintPill(); return; }
        const go = event.target.closest('[data-loop1032-go]');
        if (!go) return;
        const r = ss.get(RETURN_KEY);
        if (!r) return;
        g('closeSlideViewer')?.(); g('closeMediaViewer')?.();
        document.getElementById('atlas-modal')?.classList.add('hidden');
        await goToExam(r.catId);
      });
      document.body.appendChild(pill);
    }
    pill.hidden = false;
    pill.innerHTML = `<button type="button" data-loop1032-go class="rounded-xl bg-indigo-600 hover:bg-indigo-500 px-4 py-2 text-xs font-bold text-white">↩ 回到考核：${esc(ret.title)}${ret.submitted ? '（看結果／重考）' : '（保留作答）'}</button><button type="button" data-loop1032-dismiss class="text-slate-400 text-sm px-1" aria-label="關閉">✕</button>`;
  }

  /* ---------------- after submit: keep result, atlas hints ---------------- */
  function isWrong(index) {
    const d = Array.isArray(window.currentExamAnswerDetails) ? window.currentExamAnswerDetails[index] : null;
    return Boolean(d && d.isCorrect === false);
  }
  function isAtlasQuestion(q) {
    return q && (q.questionType === 'image' || Boolean(q.imageUrl || q.answerConfig?.imageUrl));
  }
  function injectAtlasHints() {
    const catId = g('currentCatKey');
    if (!catId || !(g('isSubmittedMap') || {})[catId]) return;
    const qs = ((g('allQuizData') || {})[catId] || {}).questions || [];
    qs.forEach((q, i) => {
      const card = document.getElementById(`question-card-${i}`);
      if (!card || !isWrong(i) || !isAtlasQuestion(q) || card.querySelector('[data-review-link66],[data-loop1032-atlas]')) return;
      const box = document.createElement('div');
      box.dataset.loop1032Atlas = '1';
      box.className = 'rounded-xl border border-teal-200 bg-teal-50/70 p-4 space-y-2';
      const hint = q.category || q.tag ? `建議回到「${esc(q.category || q.tag)}」相關圖譜重新判讀。` : '建議回到圖譜區重新判讀相同類型的影像。';
      box.innerHTML = `<div class="font-bold text-teal-900">🔬 本題判讀錯誤</div><div class="text-xs text-slate-700">${hint}</div><button type="button" class="inline-flex items-center gap-2 rounded-lg bg-teal-700 hover:bg-teal-600 text-white text-xs font-bold px-4 py-2">🔬 回圖譜區重新閱覽</button>`;
      box.querySelector('button').addEventListener('click', () => backToStudy('atlas'));
      card.appendChild(box);
    });
  }

  function saveLastResult(catId) {
    const data = (g('allQuizData') || {})[catId];
    if (!data) return;
    const score = Number(document.getElementById('final-score-text')?.textContent || 0);
    const passing = Number(data.passingScore || 80);
    const wrong = [];
    (data.questions || []).forEach((q, i) => {
      if (!isWrong(i)) return;
      wrong.push({number: i + 1, text: String(q.question || '').slice(0, 160), atlas: isAtlasQuestion(q), category: q.category || q.tag || '', reviewSource: q.reviewSource || q.answerConfig?.reviewSource || null});
    });
    ss.set(RESULT_PREFIX + catId, {catId, title: data.title, score, passing, passed: score >= passing, wrong, at: Date.now()});
  }

  function restoreLastResultCard() {
    const catId = g('currentCatKey');
    const panel = document.getElementById('panel-exam');
    document.getElementById('loop1032-last-result')?.remove();
    if (!catId || !panel || (g('isSubmittedMap') || {})[catId]) return;
    const last = ss.get(RESULT_PREFIX + catId);
    if (!last) return;
    const card = document.createElement('section');
    card.id = 'loop1032-last-result';
    card.className = `rounded-2xl border p-4 text-xs space-y-2 ${last.passed ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50'}`;
    const items = last.wrong.map((w, idx) => `<li class="flex flex-wrap items-center gap-2"><span>${esc(w.text || '第' + w.number + '題')}</span>${w.reviewSource?.materialId ? `<button type="button" data-loop1032-review="${idx}" class="rounded border border-teal-300 bg-white px-2 py-1 font-bold text-teal-800">${w.atlas ? '🔬 回圖譜' : '📖 回教材'}</button>` : (w.atlas ? '<button type="button" data-loop1032-back="atlas" class="rounded border border-teal-300 bg-white px-2 py-1 font-bold text-teal-800">🔬 回圖譜區</button>' : '')}</li>`).join('');
    card.innerHTML = `<div class="flex flex-wrap items-center gap-2"><b class="text-sm ${last.passed ? 'text-emerald-900' : 'text-rose-900'}">上次考核結果：${esc(last.score)} 分 · ${last.passed ? '✅ 已通過' : '❌ 未通過'}</b><span class="text-slate-500">及格 ${esc(last.passing)} 分；本次為新一輪作答，題目順序已重新打亂。</span></div>${last.wrong.length ? `<div class="font-bold text-slate-700">上次答錯的題目（可先回去複習）：</div><ul class="list-disc pl-5 space-y-1">${items}</ul>` : ''}`;
    card.addEventListener('click', event => {
      const back = event.target.closest('[data-loop1032-back]');
      if (back) return backToStudy(back.dataset.loop1032Back);
      const rev = event.target.closest('[data-loop1032-review]');
      if (rev) {
        rememberExam(catId);
        const w = last.wrong[Number(rev.dataset.loop1032Review)];
        if (w?.reviewSource && typeof window.teacher66OpenReviewSource === 'function') window.teacher66OpenReviewSource(w.reviewSource);
      }
    });
    const toolbar = document.getElementById('loop1032-exam-toolbar');
    (toolbar ? toolbar.after(card) : panel.insertBefore(card, panel.firstChild));
  }

  function wrapSubmit() {
    const original = g('submitQuiz');
    if (typeof original !== 'function' || original.__loop1032) return;
    const wrapped = async function () {
      const catId = g('currentCatKey');
      const result = await original.apply(this, arguments);
      if (catId && (g('isSubmittedMap') || {})[catId]) {
        saveLastResult(catId);
        rememberExam(catId);
        injectAtlasHints();
        const last = ss.get(RESULT_PREFIX + catId);
        const summary = document.getElementById('result-remediation-summary');
        if (summary && last && !last.passed) summary.textContent += ' 重考不會被鎖定，系統會重新抽題並打亂題目順序。';
        loadExamStatus(true);
      }
      return result;
    };
    wrapped.__loop1032 = true;
    window.submitQuiz = wrapped;
  }

  function wrapRender() {
    const original = g('renderQuestions');
    if (typeof original !== 'function' || original.__loop1032) return;
    const wrapped = function () { const r = original.apply(this, arguments); injectAtlasHints(); return r; };
    wrapped.__loop1032 = true;
    window.renderQuestions = wrapped;
  }

  function wrapModuleSwitch() {
    const original = g('switchLearningModule');
    if (typeof original !== 'function' || original.__loop1032) return;
    const wrapped = function (module) {
      const r = original.apply(this, arguments);
      if (module === 'exam') { ensureExamToolbar(); setTimeout(restoreLastResultCard, 0); }
      setTimeout(paintPill, 0);
      return r;
    };
    wrapped.__loop1032 = true;
    window.switchLearningModule = wrapped;
  }

  function wrapCategorySwitch() {
    const original = g('switchDynamicCategory');
    if (typeof original !== 'function' || original.__loop1032) return;
    const wrapped = async function () { const r = await original.apply(this, arguments); ensureExamToolbar(); restoreLastResultCard(); return r; };
    wrapped.__loop1032 = true;
    window.switchDynamicCategory = wrapped;
  }

  function wrapRemediationButton() {
    // Stay on the page so the just-finished result is kept in memory.
    window.openExamRemediationMaterials = function () { backToStudy('materials'); };
  }

  function boot() {
    wrapExamRow(); wrapSubmit(); wrapRender(); wrapModuleSwitch(); wrapCategorySwitch(); wrapRemediationButton();
    ensureExamToolbar();
    loadExamStatus(false);
    paintPill();
    const observer = new MutationObserver(() => syncReaderButtons());
    ['slide-viewer-modal', 'media-viewer-modal'].forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el, {attributes: true, attributeFilter: ['class']});
    });
    window.addEventListener('focus', () => paintPill());
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 0), {once: true});
  else setTimeout(boot, 0);
})();
