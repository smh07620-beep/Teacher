/* Teacher 7.1 P0 runtime guard.
 * Keeps legacy renderers alive even when a browser/CDN serves an older shared-core.js.
 */
(function (global) {
  'use strict';

  if (typeof global.escapeHtml === 'function') {
    global.__teacherEscapeGuard7111 = 'existing';
    return;
  }

  const canonical = global.AppCore && typeof global.AppCore.escapeHtml === 'function'
    ? global.AppCore.escapeHtml
    : null;

  global.escapeHtml = canonical || function (value) {
    return String(value ?? '').replace(/[&<>"']/g, function (char) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[char];
    });
  };

  global.__teacherEscapeGuard7111 = canonical ? 'app-core' : 'fallback';
})(window);
