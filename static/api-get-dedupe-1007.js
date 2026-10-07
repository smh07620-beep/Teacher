/* Same-page request de-duplication for read-only API calls.
 *
 * Many independent page scripts each ask for the same summary data while the
 * page boots (course list, learning progress, command-center progress, ...).
 * Without this, the browser sends every copy to the server.
 *
 * Rules, deliberately conservative:
 * - only same-origin GET requests to the short allow-list below are shared;
 * - concurrent identical requests share one network call, and a successful
 *   answer is reused for a few seconds so near-simultaneous callers also share;
 * - ANY write (POST/PUT/PATCH/DELETE) to /api/ clears everything, before and
 *   after it runs, so a screen can never show data older than its own change;
 * - callers that pass an AbortSignal are never shared, so cancelling one can
 *   not break another;
 * - callers that ask for fresh data (cache: no-store / reload / no-cache, the
 *   habit of most scripts here) never receive an answer that has already
 *   finished, so a refresh button always asks the server again; they only join
 *   an identical request that is still in flight at that very moment;
 * - failed (non-2xx) answers are shared only with callers already waiting and
 *   are never kept for later.
 * Registered as middleware (see api-client.js); it never reassigns window.fetch.
 */
(function (global) {
  'use strict';

  const client = global.AppApiClient;
  if (!client || typeof client.use !== 'function' || global.AppApiGetDedupe) return;

  const REUSE_MS = 3000;
  const SHARED_PATHS = new Set([
    '/api/auth/me',
    '/api/auth/profile',
    '/api/courses',
    '/api/slides',
    '/api/slides/admin',
    '/api/learning-progress',
    '/api/training-command-center/progress',
    '/api/training-command-center/learning-analytics',
  ]);
  const NO_BODY_STATUS = new Set([101, 204, 205, 304]);
  const FRESH_CACHE_MODES = new Set(['no-store', 'reload', 'no-cache']);

  const entries = new Map();
  const stats = {network: 0, shared: 0, cleared: 0};

  function keyFor(url) {
    const params = [...url.searchParams.entries()].sort(([a, av], [b, bv]) =>
      a === b ? String(av).localeCompare(String(bv)) : a.localeCompare(b));
    return `${url.pathname}?${params.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')}`;
  }

  function requestSignal(context) {
    const input = context.input;
    return (context.init && context.init.signal)
      || (typeof Request !== 'undefined' && input instanceof Request ? input.signal : null);
  }

  function wantsFresh(context) {
    const input = context.input;
    const mode = (context.init && context.init.cache)
      || (typeof Request !== 'undefined' && input instanceof Request ? input.cache : '');
    return FRESH_CACHE_MODES.has(String(mode || ''));
  }

  function isShareable(context) {
    if (!context.url || !context.sameOrigin || context.method !== 'GET') return false;
    if (!SHARED_PATHS.has(context.url.pathname)) return false;
    return !requestSignal(context);
  }

  function isApiWrite(context) {
    return !!context.url && context.sameOrigin
      && context.method !== 'GET' && context.method !== 'HEAD' && context.method !== 'OPTIONS'
      && context.url.pathname.startsWith('/api/');
  }

  function clear() {
    if (entries.size) stats.cleared += entries.size;
    entries.clear();
  }

  async function snapshot(response) {
    return {
      status: response.status,
      statusText: response.statusText,
      headers: [...response.headers.entries()],
      body: await response.text(),
    };
  }

  function toResponse(snap) {
    return new Response(NO_BODY_STATUS.has(snap.status) ? null : snap.body, {
      status: snap.status,
      statusText: snap.statusText,
      headers: snap.headers,
    });
  }

  function dedupeMiddleware(context, next) {
    if (isApiWrite(context)) {
      clear();
      const done = () => clear();
      return next().then(
        response => { done(); return response; },
        error => { done(); throw error; },
      );
    }
    if (!isShareable(context)) return next();

    const key = keyFor(context.url);
    const existing = entries.get(key);
    const reusable = existing
      && (existing.pending || (!wantsFresh(context) && Date.now() - existing.at < REUSE_MS));
    if (reusable) {
      stats.shared += 1;
      return existing.promise.then(toResponse);
    }

    const entry = {pending: true, at: 0, promise: null};
    stats.network += 1;
    entry.promise = next().then(snapshot).then(
      snap => {
        entry.pending = false;
        entry.at = Date.now();
        if (!(snap.status >= 200 && snap.status < 300) && entries.get(key) === entry) entries.delete(key);
        return snap;
      },
      error => {
        entry.pending = false;
        if (entries.get(key) === entry) entries.delete(key);
        throw error;
      },
    );
    entries.set(key, entry);
    return entry.promise.then(toResponse);
  }

  client.use('api-get-dedupe-1007', dedupeMiddleware, 50);
  global.AppApiGetDedupe = Object.freeze({
    stats: () => ({...stats, size: entries.size}),
    clear,
  });
})(window);
