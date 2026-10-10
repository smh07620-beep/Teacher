/* Learner exam: case/scenario (情境題) question.
 *
 * Owner of: rendering one scenario question's follow-up steps and reporting a
 * chosen option.  The question text (the case) is rendered by system-exam.js;
 * this module renders only the steps from answerConfig.steps.  The right option
 * never reaches the browser (the server strips the answer key); grading is
 * server-side.  A scenario answer is an array with one chosen index (or null)
 * per step; system-exam.js owns the answer store (setScenarioAnswer).
 *
 * Clicks arrive through the CSP delegate (data-csp-change -> scenarioPick).
 */
(function (root) {
  'use strict';

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function steps(q) {
    var s = q && q.answerConfig && q.answerConfig.steps;
    return Array.isArray(s) ? s : [];
  }

  function answeredCount(ans, total) {
    if (!Array.isArray(ans)) return 0;
    var n = 0;
    for (var k = 0; k < total; k++) if (ans[k] !== null && ans[k] !== undefined && ans[k] !== '') n++;
    return n;
  }

  function render(q, i, submitted, ans) {
    var list = steps(q);
    if (!list.length) return '<p class="text-sm text-rose-600">這題的小問題不見了，請通知老師。</p>';
    var html = '<div class="aa-scenario space-y-4" data-scenario-index="' + i + '">' +
      '<p class="text-xs font-bold text-slate-500">這是一題情境題，共 ' + list.length + ' 個小問題，全部答對才算答對。</p>';
    list.forEach(function (step, s) {
      var chosen = Array.isArray(ans) ? ans[s] : null;
      html += '<fieldset class="rounded-xl border border-slate-200 bg-slate-50/60 p-3 space-y-2">' +
        '<legend class="px-1 text-sm font-black text-slate-800">' + (s + 1) + '. ' + esc(step.prompt) + '</legend>';
      (step.options || []).forEach(function (opt, j) {
        var on = chosen === j;
        html += '<label class="flex items-start gap-3 rounded-lg border p-3 ' +
          (submitted ? (on ? 'border-teal-400 bg-teal-50 font-bold' : 'opacity-60 bg-slate-50') : 'cursor-pointer bg-white hover:bg-slate-50') + '">' +
          '<input type="radio" class="mt-1" name="scenario-' + i + '-' + s + '"' + (on ? ' checked' : '') + (submitted ? ' disabled' : '') +
          ' data-csp-change="scenarioPick(' + i + ',' + s + ',' + j + ')">' +
          '<span class="text-sm"><b class="mr-1">' + String.fromCharCode(65 + j) + '.</b>' + esc(opt) + '</span></label>';
      });
      html += '</fieldset>';
    });
    return html + '<p class="text-xs text-slate-500" id="aa-scenario-progress-' + i + '">已作答 ' + answeredCount(ans, list.length) + ' / ' + list.length + '</p></div>';
  }

  // Called by the CSP delegate when a radio changes.
  function pick(i, s, j) {
    if (typeof root.setScenarioAnswer === 'function') root.setScenarioAnswer(i, s, j);
  }

  function updateProgress(i, ans, total) {
    var el = document.getElementById('aa-scenario-progress-' + i);
    if (el) el.textContent = '已作答 ' + answeredCount(ans, total) + ' / ' + total;
  }

  var api = { render: render, pick: pick, updateProgress: updateProgress, _answeredCount: answeredCount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else {
    root.ScenarioQuestion = api;
    root.scenarioPick = pick;
  }
})(typeof window !== 'undefined' ? window : globalThis);
