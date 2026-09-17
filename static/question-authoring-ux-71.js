/* Retired by Teacher runtime convergence.
 *
 * The former 7.1 overlay wrapped the duplicate assessment-681 question drawer.
 * The canonical question UI is now static/admin-question-editor-ui.js with
 * mutations in static/admin-question-actions.js and orchestration in
 * static/admin-question-panel.js. This compatibility marker intentionally owns
 * no UI, API calls, persistence, authorization, or mutation behavior.
 */
(function () {
  'use strict';
  window.QuestionAuthoringUx71 = Object.freeze({
    retired: true,
    canonicalOwner: 'admin-question-editor-ui.js',
    mutationOwner: 'admin-question-actions.js'
  });
})();
