/* Legacy admin entrypoint compatibility shim.
 *
 * Current Teacher builds use admin-system.js + production-readiness-f6.js.
 * This file is intentionally NOT added to the asset manifest. It only keeps
 * stale/open browser tabs from receiving a 404 if they still request the
 * retired /admin-entrypoint-69.js path after a deployment.
 */
(function () {
  'use strict';

  function resumeCanonicalAdminStatus() {
    try {
      window.renderAdminSystemStatus?.(false);
    } catch (_error) {
      // Canonical module owns rendering; this bridge must stay fail-soft.
    }
    try {
      const workspace = new URLSearchParams(window.location.search).get('workspace') || '';
      if (workspace === 'worker') window.ProductionReadinessF6?.refresh?.(false);
    } catch (_error) {
      // Do not let a stale compatibility request disturb the current UI.
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', resumeCanonicalAdminStatus, { once: true });
  } else {
    queueMicrotask(resumeCanonicalAdminStatus);
  }

  window.AdminEntrypoint69Compat = Object.freeze({
    refresh: resumeCanonicalAdminStatus,
  });
})();
