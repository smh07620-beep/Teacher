/* Canonical browser request pipeline.
 * Feature modules register middleware here instead of wrapping window.fetch.
 */
(function (global) {
  'use strict';

  if (global.AppApiClient) return;

  const nativeFetch = global.fetch.bind(global);
  const middlewares = [];
  let sequence = 0;

  function requestMeta(input, init = {}) {
    try {
      const raw = typeof input === 'string' ? input : input?.url || '';
      const url = new URL(raw, global.location?.href || 'http://localhost/');
      const method = String(init?.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase();
      return {url, method, sameOrigin: !global.location || url.origin === global.location.origin};
    } catch (_error) {
      return {url: null, method: 'GET', sameOrigin: false};
    }
  }

  function makeContext(input, init = {}) {
    return {input, init: init || {}, ...requestMeta(input, init), nativeFetch};
  }

  function withOverrides(context, overrides = {}) {
    const input = Object.prototype.hasOwnProperty.call(overrides, 'input') ? overrides.input : context.input;
    const init = Object.prototype.hasOwnProperty.call(overrides, 'init') ? overrides.init : context.init;
    return makeContext(input, init);
  }

  async function dispatch(context, index) {
    const entry = middlewares[index];
    if (!entry) return nativeFetch(context.input, context.init);
    return entry.handler(context, overrides => dispatch(withOverrides(context, overrides), index + 1));
  }

  function use(name, handler, priority = 100) {
    if (!name || typeof handler !== 'function') throw new TypeError('AppApiClient middleware requires name and handler');
    const existing = middlewares.findIndex(item => item.name === name);
    const entry = {name: String(name), handler, priority: Number(priority || 0), sequence: sequence++};
    if (existing >= 0) middlewares.splice(existing, 1, entry);
    else middlewares.push(entry);
    middlewares.sort((a, b) => (a.priority - b.priority) || (a.sequence - b.sequence));
    return () => {
      const index = middlewares.findIndex(item => item.name === entry.name);
      if (index >= 0) middlewares.splice(index, 1);
    };
  }

  function fetchWithMiddleware(input, init = {}) {
    return dispatch(makeContext(input, init), 0);
  }

  /* Job polling: 2s -> 5s -> 10s, paused while the tab is hidden (resumes with an immediate check). */
  function pollBackoff() {
    let attempt = 0;
    return function wait() {
      const delay = attempt < 3 ? 2000 : attempt < 10 ? 5000 : 10000;
      attempt += 1;
      return new Promise(resolve => {
        let timer = 0;
        const done = () => {
          clearTimeout(timer);
          global.document.removeEventListener('visibilitychange', onVisible);
          resolve();
        };
        const onVisible = () => { if (!global.document.hidden) done(); };
        if (global.document.hidden) {
          global.document.addEventListener('visibilitychange', onVisible);
        } else {
          timer = setTimeout(done, delay);
          global.document.addEventListener('visibilitychange', onVisible);
        }
      });
    };
  }

  /* AI production busy registry: modules report work in flight; the course wizard locks its navigation. */
  const aiBusyKeys = new Set();
  function aiBusy(key, on) {
    if (on) aiBusyKeys.add(String(key)); else aiBusyKeys.delete(String(key));
    global.dispatchEvent(new CustomEvent('teacher:ai-busy', {detail: {busy: aiBusyKeys.size > 0, keys: [...aiBusyKeys]}}));
  }

  global.fetch = fetchWithMiddleware;
  global.AppApiClient = Object.freeze({
    aiBusy,
    isAiBusy: () => aiBusyKeys.size > 0,
    pollBackoff,
    fetch: fetchWithMiddleware,
    nativeFetch,
    use,
    middlewareNames: () => middlewares.map(item => item.name)
  });
})(window);
