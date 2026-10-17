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

  /* Loading placeholders (CSS .skeleton) so lists never flash empty or say only "loading...". */
  function skeletonBlocks(count, heightPx) {
    const height = Number(heightPx) || 72;
    return Array.from({length: Math.max(1, Number(count) || 3)}, () =>
      `<div class="skeleton" style="height:${height}px;margin-bottom:12px" aria-hidden="true"></div>`).join('')
      + '<span class="sr-only" role="status">載入中…</span>';
  }
  function skeletonRows(columns, rows) {
    const cells = Array.from({length: Math.max(1, Number(columns) || 6)}, () => '<td class="p-3"><div class="skeleton" style="height:14px"></div></td>').join('');
    return Array.from({length: Math.max(1, Number(rows) || 6)}, () => `<tr aria-hidden="true">${cells}</tr>`).join('');
  }

  /* Plain-language error text with a next step. Accepts an Error, a status number or a message. */
  function humanError(error, what) {
    const subject = what ? String(what) : '資料';
    const status = Number(error && error.status !== undefined ? error.status : (typeof error === 'number' ? error : 0));
    const text = String((error && error.message) || (typeof error === 'string' ? error : '')).toLowerCase();
    if (status === 401 || (error && error.loginRequired)) return '登入已逾時，請重新登入後再繼續。';
    if (status === 403) return `你沒有權限查看${subject}。如果需要，請洽組長或教學管理者。`;
    if (status === 404) return `找不到${subject}，可能已被移除。請重新整理頁面，或回到上一層再試。`;
    if (status === 409) return `${subject}剛剛被別人更新了。請重新整理後再操作。`;
    if (status === 429) return '操作太頻繁了，請等一分鐘再試。';
    if (status >= 500) return `伺服器暫時忙碌，${subject}稍後才能顯示。請等一兩分鐘再試；若一直如此，請告知管理者。`;
    if (error && error.name === 'AbortError') return '等待太久沒有回應。請檢查網路後再試一次。';
    if (!status && (error instanceof TypeError || /failed to fetch|network|load failed|offline/.test(text))) {
      return '網路中斷了。已讀的進度會暫存，恢復連線後會自動補送；請稍後再試。';
    }
    return `${subject}暫時無法顯示，請重新整理後再試。`;
  }

  global.fetch = fetchWithMiddleware;
  global.AppApiClient = Object.freeze({
    skeletonBlocks,
    skeletonRows,
    humanError,
    aiBusy,
    isAiBusy: () => aiBusyKeys.size > 0,
    pollBackoff,
    fetch: fetchWithMiddleware,
    nativeFetch,
    use,
    middlewareNames: () => middlewares.map(item => item.name)
  });
})(window);
