/* Teacher 6.5 M6 · 全站共用核心：路由、組別、API、錯誤處理與使用者身分 */
(function (global) {
  const groups = Object.freeze({
    grpBio: Object.freeze({ label: '1 生化組', name: '生化組', icon: '🧫' }),
    grpMicro: Object.freeze({ label: '2 鏡檢組', name: '鏡檢組', icon: '🔬' }),
    grpSero: Object.freeze({ label: '3 血清組', name: '血清組', icon: '🧪' }),
    grpBB: Object.freeze({ label: '4 血庫組', name: '血庫組', icon: '🩸' }),
    grpBact: Object.freeze({ label: '5 細菌組', name: '細菌組', icon: '🦠' }),
    grpHema: Object.freeze({ label: '6 血液組', name: '血液組', icon: '🧬' }),
    grpNew: Object.freeze({ label: '新進醫檢師專區', name: '新進醫檢師專區', icon: '🧑‍🔬', pgyOnly: true }),
    grpPgyDocs: Object.freeze({ label: 'PGY專用資料區', name: 'PGY專用資料放置區', icon: '📘', pgyOnly: true })
  });

  const memoryKeys = Object.freeze({ learnerName: 'smh_learner_name', learnerEmpId: 'smh_learner_empid' });
  const readMemory = key => { try { return localStorage.getItem(key) || ''; } catch (_) { return ''; } };
  const writeMemory = (key, value) => { try { value ? localStorage.setItem(key, value) : localStorage.removeItem(key); } catch (_) {} };
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  class AppApiError extends Error {
    constructor(message, {
      status = 0,
      code = '',
      data = null,
      requestId = '',
      retryAfter = 0,
      loginRequired = false
    } = {}) {
      super(message);
      this.name = 'AppApiError';
      this.status = Number(status || 0);
      this.code = String(code || '');
      this.data = data;
      this.requestId = String(requestId || '');
      this.retryAfter = Number(retryAfter || 0);
      this.loginRequired = Boolean(loginRequired);
    }
  }

  function requestIdFrom(response, data) {
    const fromBody = data && typeof data === 'object'
      ? (data.requestId || data.request_id || '')
      : '';

    const fromHeader = response?.headers?.get?.('x-request-id')
      || response?.headers?.get?.('x-correlation-id')
      || '';

    return String(fromBody || fromHeader || '');
  }

  function fallbackMessage(status, retryAfter = 0) {
    switch (Number(status || 0)) {
      case 400:
        return '送出的資料格式不正確，請檢查後再試。';
      case 401:
        return '登入狀態已失效，請重新登入。';
      case 403:
        return '權限不足，無法執行此操作。';
      case 404:
        return '找不到指定的資料。';
      case 409:
        return '資料狀態已變更，請重新整理後再試。';
      case 413:
        return '上傳內容超過系統允許大小。';
      case 429:
        return retryAfter > 0
          ? `操作過於頻繁，請 ${retryAfter} 秒後再試。`
          : '操作過於頻繁，請稍後再試。';
      default:
        if (Number(status || 0) >= 500) {
          return '伺服器暫時無法完成操作，請稍後再試。';
        }
        return status
          ? `請求失敗（${status}）。`
          : '無法連線到伺服器，請檢查網路後再試。';
    }
  }

  function normalizeApiError(response, data) {
    const status = Number(response?.status || 0);

    const detail = data
      && typeof data === 'object'
      && data.errorDetail
      && typeof data.errorDetail === 'object'
      ? data.errorDetail
      : {};

    const headerRetryAfter = Number(
      response?.headers?.get?.('retry-after') || 0
    );

    const bodyRetryAfter = data && typeof data === 'object'
      ? Number(data.retryAfter || 0)
      : 0;

    const retryAfter = bodyRetryAfter || headerRetryAfter || 0;

    let serverMessage = '';

    if (detail.message) {
      serverMessage = String(detail.message);
    } else if (
      data
      && typeof data === 'object'
      && data.error
    ) {
      serverMessage = String(data.error);
    } else if (typeof data === 'string') {
      serverMessage = data.trim();
    }

    return new AppApiError(
      serverMessage || fallbackMessage(status, retryAfter),
      {
        status,
        code: String(
          detail.code
          || (
            data
            && typeof data === 'object'
            && data.code
          )
          || ''
        ),
        data,
        requestId: requestIdFrom(response, data),
        retryAfter,
        loginRequired: Boolean(
          status === 401
          || (
            data
            && typeof data === 'object'
            && data.loginRequired
          )
        )
      }
    );
  }

  function errorMessage(error, fallback = '操作失敗，請稍後再試。') {
    if (error && typeof error.message === 'string' && error.message.trim()) {
      return error.message.trim();
    }
    return fallback;
  }

  async function api(path, options = {}) {
    let response;

    try {
      response = await fetch(path, {
        credentials: 'same-origin',
        ...options
      });
    } catch (cause) {
      const error = new AppApiError(
        fallbackMessage(0),
        {
          status: 0,
          code: 'NETWORK_ERROR'
        }
      );
      error.cause = cause;
      throw error;
    }

    const contentType = response.headers.get('content-type') || '';

    let data;

    if (contentType.includes('application/json')) {
      data = await response.json().catch(() => ({}));
    } else {
      data = await response.text().catch(() => '');
    }

    if (!response.ok) {
      throw normalizeApiError(response, data);
    }

    return data;
  }

  async function getCurrentUser() {
    const state = await api('/api/auth/me', { cache: 'no-store' });
    const user = state.authenticated ? state.user : null;
    if (user) {
      writeMemory(memoryKeys.learnerName, user.name || '');
      writeMemory(memoryKeys.learnerEmpId, user.empId || '');
    }
    return user;
  }

  function learningUrl({ area = 'internal', group = 'grpBio', module = 'materials', ...extra } = {}) {
    const params = new URLSearchParams({ area, group, module });
    Object.entries(extra).forEach(([key, value]) => value !== undefined && value !== null && params.set(key, String(value)));
    return `/system?${params.toString()}`;
  }

  global.AppCore = Object.freeze({
    api,
    AppApiError,
    errorMessage,
    normalizeApiError,
    escapeHtml,
    getCurrentUser,
    groups,
    learningUrl,
    memoryKeys,
    readMemory,
    writeMemory
  });
})(window);
